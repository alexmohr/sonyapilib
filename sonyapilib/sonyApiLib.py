"""
Sony Mediaplayer lib
"""
import logging
import base64
import collections
import json
import socket
import struct
import requests
import urllib.parse
import xml.etree.ElementTree
import logging
import requests
from enum import Enum


import jsonpickle

import ssdp
_LOGGER = logging.getLogger(__name__)

TIMEOUT = 10


class AuthenicationResult(Enum):
    SUCCESS = 0
    ERROR = 1
    PIN_NEEDED = 2


class HttpMethod(Enum):
    GET = 0,
    POST = 1


class ApiAction():
    """ Holds data for a device action or a command """

    def __init__(self, xml_data):
        self.name = xml_data["name"]
        self.mode = None
        self.url = None
        self.type = None
        self.value = None

        for arg in self.__dict__:
            if "_" in arg:
                continue
            if arg in xml_data:
                if (arg == "mode"):
                    setattr(self, arg, int(xml_data[arg]))
                else:
                    setattr(self, arg, xml_data[arg])


class SonyDevice():
    """
    Contains all data for the device
    """

    def __init__(self, host, port=50001, ircc_location=None):
        """ Init the device with the entry point"""
        self.host = host
        self.ircc_url = ircc_location
        self.actionlist_url = None
        self.control_url = None

        self.actions = {}
        self.headers = {}
        self.commands = {}

        self.pin = None
        self.name = None
        self.cookies = None

        if self.ircc_url == None:
            self.ircc_url = "http://{0}:{1}/Ircc.xml".format(host, port)

    def create_json_v4(self, method, params=None):
        """ Create json data which will be send via post for the V4 api"""
        if params is not None:
            ret = json.dumps({"method": method, "params": [
                             params], "id": 1, "version": "1.0"})
        else:
            ret = json.dumps({"method": method, "params": [],
                              "id": 1, "version": "1.0"})
        return ret

    @staticmethod
    def load_from_json(data):
        """ Loads a device configuration from a stored json """
        return jsonpickle.decode(data)

    def save_to_json(self):
        return jsonpickle.dumps(self)

    def update_service_urls(self):
        """ Initalizes the device by reading the necessary resources from it """
        lirc_url = urllib.parse.urlparse(self.ircc_url)
        response = self.send_http(self.ircc_url, method=HttpMethod.GET)
        raw_data = response.text
        xml_data = xml.etree.ElementTree.fromstring(raw_data)

        urn_upnp_device = "{urn:schemas-upnp-org:device-1-0}"
        urn_sony_av = "{urn:schemas-sony-com:av}"

        # the action list contains everything the device supports
        self.actionlist_url = xml_data.find("{0}device".format(urn_upnp_device))\
            .find("{0}X_UNR_DeviceInfo".format(urn_sony_av))\
            .find("{0}X_CERS_ActionList_URL".format(urn_sony_av))\
            .text

        services = xml_data.find("{0}device".format(urn_upnp_device))\
            .find("{0}serviceList".format(urn_upnp_device))\
            .findall("{0}service".format(urn_upnp_device))

        # read action list
        response = self.send_http(self.actionlist_url, method=HttpMethod.GET)
        raw_data = response.text
        xml_data = xml.etree.ElementTree.fromstring(raw_data)
        for element in xml_data.findall("action"):
            action = ApiAction(element.attrib)
            self.actions[action.name] = action

        # overwrite urls for api version 4 to be consistent later.
        if self.actions["register"].mode == 4:
            self.actions["getRemoteCommandList"].url = "http://{0}/sony/system".format(
                lirc_url.netloc.split(":")[0])

        # read service list
        for service in services:
            service_id = service.find("{0}serviceId".format(urn_upnp_device))
            if service_id == None:
                continue
            if "urn:schemas-sony-com:serviceId:IRCC" not in service_id.text:
                continue

            service_location = service.find(
                "{0}controlURL".format(urn_upnp_device)).text
            service_url = lirc_url.scheme + "://" + lirc_url.netloc
            self.control_url = service_url + service_location

    def recreate_auth_cookie(self):
        """
        The default cookie is for URL/sony. For some commands we need it for the root path.
        Only for api v4
        """
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("auth", self.cookies.get("auth"))
        return cookies

    def register(self, name):
        """
        Register at the api.50001
        :param str name: The name which will be displayed in the UI of the device. Make sure this name does not exist yet
        For this the device must be put in registration mode.
        The tested sd5500 has no separte mode but allows registration in the overview "
        """

        self.name = name
        registrataion_result = AuthenicationResult.ERROR
        registration_action = self.actions["register"]

        if registration_action.mode < 4:
            # the authenication later on is based on the device id and the mac
            # address of the device
            registration_action.url = "{0}?name={1}&registrationType=initial&deviceId={1}".format(
                registration_action.url, urllib.parse.quote(name))
            if registration_action.mode == 3:
                registration_action.url = registration_action.url + "&wolSupport=true"
        else:
            registration_action.url = registration_action.url

        # protocoll version 1 and 2
        if registration_action.mode < 3:
            registration_response = self.send_http(
                registration_action.url, method=HttpMethod.GET, raise_errors=True)
            if registration_response.text == "":
                registrataion_result = AuthenicationResult.SUCCESS
            else:
                registrataion_result = AuthenicationResult.ERROR

        # protocoll version 3
        elif registration_action.mode == 3:
            try:
                self.send_http(registration_action.url,
                               method=HttpMethod.GET, raise_errors=True)
            except requests.exceptions.HTTPError as ex:
                _LOGGER.error("[W] HTTPError: " + str(ex))
                registrataion_result = AuthenicationResult.PIN_NEEDED

        # newest protocoll version 4 this is the same method as braviarc uses
        elif registration_action.mode == 4:
            authorization = json.dumps(
                {
                    "method": "actRegister",
                    "params": [{"clientid": name,
                                "nickname": name,
                                "level": "private"},
                               [{"value": "yes",
                                 "function": "WOL"}]],
                    "id": 1,
                    "version": "1.0"}
            ).encode('utf-8')

            try:
                response = self.send_http(registration_action.url, method=HttpMethod.POST,
                                          data=authorization, raise_errors=True)
            except requests.exceptions.HTTPError as ex:
                _LOGGER.error("[W] HTTPError: " + str(ex))
                registrataion_result = AuthenicationResult.PIN_NEEDED

            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.error("[W] Exception: " + str(ex))
            else:
                resp = response.json()
                _LOGGER.debug(json.dumps(resp, indent=4))
                if resp is None or not resp.get('error'):
                    # todo make this available
                    self.cookies = response.cookies
                    registrataion_result = AuthenicationResult.SUCCESS

        else:
            raise ValueError(
                "Regisration mode {0} is not supported".format(registration_action.mode))

        return registrataion_result

    def send_authentication(self, pin):
        registration_action = self.actions["register"]

        username = ''
        base64string = base64.encodebytes(('%s:%s' % (username, pin)).encode()) \
            .decode().replace('\n', '')
        self.headers['Authorization'] = "Basic %s" % base64string

        if registration_action.mode == 3:
            self.headers['X-CERS-DEVICE-ID'] = self.name

            try:
                self.send_http(
                    self.actions["register"].url, method=HttpMethod.GET, raise_errors=True)
            except:
                return False
            else:
                self.pin = pin
                return True
            return False

        elif registration_action.mode == 4:
            self.headers['Connection'] = "keep-alive"

            authorization = json.dumps(
                {
                    "id": 13,
                    "method": "actRegister",
                    "version": "1.0",
                    "params": [
                        {
                            "clientid": self.name,
                            "nickname": self.name,
                        },
                        [
                            {
                                "clientid": self.name,
                                "value": self.name,
                                "nickname": self.name,
                                "function": "WOL"
                            }
                        ]
                    ]
                }
            )

            try:
                response = self.send_http(self.actions["register"].url, method=HttpMethod.post,
                                          data=authorization, raise_errors=True)
            except:
                return False
            else:
                resp = response.json()
                _LOGGER.debug(json.dumps(resp, indent=4))
                if resp is None or not resp.get('error'):
                    self.cookies = response.cookies
                    self.pin = pin
                    return True
            return False

    def send_http(self, url, method, data=None, log_errors=True, raise_errors=False):
        """ Send request command via HTTP json to Sony Bravia."""
        try:
            params = ""
            if data is not None:
                data = data.encode("UTF-8")

            if method == HttpMethod.POST:
                response = requests.post(url,
                                         data=params,
                                         headers=self.headers,
                                         cookies=self.cookies,
                                         timeout=TIMEOUT)
            elif method == HttpMethod.GET:
                response = requests.get(url,
                                        data=params,
                                        headers=self.headers,
                                        cookies=self.cookies,
                                        timeout=TIMEOUT)

            response.raise_for_status()
        except requests.exceptions.HTTPError as ex:
            if log_errors:
                _LOGGER.error("HTTPError: " + str(ex))
            if raise_errors:
                raise
        except Exception as ex:  # pylint: disable=broad-except
            if log_errors:
                _LOGGER.error("Exception: " + str(ex))
            if raise_errors:
                raise
        else:
            return response

    def update_commands(self):

        url = self.actions["getRemoteCommandList"].url
        if self.actions["register"].mode < 4:
            response = self.send_http(url, method=HttpMethod.GET)
            xml_data = xml.etree.ElementTree.fromstring(response.text)

            for command in xml_data.findall("command"):
                name = command.get("name")
                self.commands[name] = ApiAction(command.attrib)
        else:
            response = self.send_http(
                url, method=HttpMethod.POST, data=self.create_json_v4("getRemoteControllerInfo"))
            json = response.json()
            if not json.get('error'):
                # todo this does not fit 100% with the structure of this lib.
                # see github issue#2
                self.commands = json.get('result')[1]
            else:
                _LOGGER.error("JSON request error: " +
                              json.dumps(json, indent=4))

    def send_command(self, command):
        """Sends a command to the Device."""
        if not self.commands:
            self.update_commands()
        # self.send_req_ircc(self.get_command_code(command))


class SonyApiLib:
    """
    Provides the access to the api funtions.
    """

    def create_device(self, host, ircc_location=None, port=50001):
        device = SonyDevice(host, port, ircc_location)
        device.update_service_urls()
        return device

    def discover(self):
        """
        Discover all available devices.
        """
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover("urn:schemas-sony-com:service:headersIRCC:1"):
            host = device.location.split(":")[1].split("//")[1]
            devices.append(self.create_device(host, device.location))

        return devices


if __name__ == '__main__':
    lib = SonyApiLib()

    stored_config = "bluray.json"
    device = None
    import os.path
    if os.path.exists(stored_config):
        pass
    #    with open(stored_config, 'r') as content_file:
    #        json_data = content_file.read()
    #        device = SonyDevice.load_from_json(json_data)
    # else:
        device = lib.create_device("10.0.0.102")
        device.headers = {"Authorization": "Basic OjE1MDY=",
                          "X-CERS-DEVICE-ID": "SonyApiLib Python Test"}
        # device.register("SonyApiLib Python Test")
        # pin = input("Enter the PIN displayed at your device: ")
        # device.send_authentication(pin)
        # data = device.save_to_json()
        # text_file = open("bluray.json", "w")
       # text_file.write(data)
        # text_file.close()

    device.update_service_urls()
    device.update_commands()

    requests.get(device.actions["getStatus"].url,
                 headers=device.headers, cookies=device.cookies, timeout=10)

    # for device in lib.discover():
    # device.register("SonyApiLib Python Test")
