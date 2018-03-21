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
import urllib.request
import xml.etree.ElementTree
import logging
import requests
from enum import Enum

import jsonpickle

import ssdp
_LOGGER = logging.getLogger(__name__)


class AuthenicationResult(Enum):
    SUCCESS = 0
    ERROR = 1
    PIN_NEEDED = 2


class ApiAction():
    """ Holds data for a device action"""

    def __init__(self, xml_data):
        self.name = xml_data["name"]
        self.url = xml_data["url"]
        if "mode" in xml_data:
            self.mode = xml_data["mode"]


class ApiDevice():
    """
    Contains all data for the device
    """

    def __init__(self, host, port=50001, ircc_location=None):
        """ Init the device with the entry point"""
        self.host = host
        self.ircc_url = ircc_location
        self.actionlist_url = None
        self.actions = {}
        self.cookies = None
        self.name = None

        if self.ircc_url == None:
            self.ircc_url = "http://{0}:{1}/Ircc.xml".format(host, port)

        self.registration_urls = {}

    @staticmethod
    def load_from_json(data):
        """ Loads a device configuration from a stored json """
        return jsonpickle.decode(data)

    def save_to_json(self):
        return jsonpickle.dumps(self)

    def setup_new_device(self):
        """ Initalizes the device by reading the necessary resources from it """
        response = urllib.request.urlopen(self.ircc_url)
        raw_data = bytes.decode(response.read())
        xml_data = xml.etree.ElementTree.fromstring(raw_data)

        # the action list contains everything the device supports
        self.actionlist_url = xml_data.find("{urn:schemas-upnp-org:device-1-0}device")\
            .find("{urn:schemas-sony-com:av}X_UNR_DeviceInfo")\
            .find("{urn:schemas-sony-com:av}X_CERS_ActionList_URL")\
            .text

        response = urllib.request.urlopen(self.actionlist_url)
        raw_data = bytes.decode(response.read())
        xml_data = xml.etree.ElementTree.fromstring(raw_data)
        for element in xml_data.findall("action"):
            action = ApiAction(element.attrib)
            self.actions[action.name] = action

    def _recreate_auth_cookie(self):
        """
        The default cookie is for URL/sony. For some commands we need it for the root path
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
        registration_mode = int(registration_action.mode)

        if registration_mode < 4:
            self.registration_url = "{0}?name={1}&registrationType=initial&deviceId={1}".format(
                            registration_action.url, urllib.parse.quote(name))
            if registration_mode == 3: 
                self.registration_url = self.registration_url + "&wolSupport=true"
        else: 
            self.registration_url = registration_action.url

        # protocoll version 1 and 2
        if registration_mode < 3:
            registration_response = urllib.request.urlopen(self.registration_url)
            if registration_response == "":
                registrataion_result = AuthenicationResult.SUCCESS
            else:
                registrataion_result = AuthenicationResult.ERROR

        # protocoll version 3
        elif registration_mode == 3:
            try:
                registration_response = urllib.request.urlopen(self.registration_url)
            except urllib.error.HTTPError as ex:
                _LOGGER.error("[W] HTTPError: " + str(ex))
                registrataion_result = AuthenicationResult.PIN_NEEDED

        # newest protocoll version 4 this is the same method as braviarc uses
        elif registration_mode == 4:
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

            headers = {}

            try:
                response = requests.post(self.registration_url, data=authorization, headers=headers, timeout=10)
                response.raise_for_status()

            except requests.exceptions.HTTPError as exception_instance:
                _LOGGER.error("[W] HTTPError: " + str(exception_instance))
                registrataion_result = AuthenicationResult.PIN_NEEDED

            except Exception as exception_instance:  # pylint: disable=broad-except
                _LOGGER.error("[W] Exception: " + str(exception_instance))
            else:
                resp = response.json()
                _LOGGER.debug(json.dumps(resp, indent=4))
                if resp is None or not resp.get('error'):
                    # todo make this available
                    self.cookies = response.cookies
                    registrataion_result = AuthenicationResult.SUCCESS

        else:
            raise ValueError(
                "Regisration mode {0} is not supported".format(registration_mode))

        return registrataion_result

    def send_auth_pin(self, pin):
        registration_action = self.actions["register"]
        registration_mode = int(registration_action.mode)

        headers = {}
        username = ''
        base64string = base64.encodebytes(('%s:%s' % (username, pin)).encode()) \
                .decode().replace('\n', '')
        headers['Authorization'] = "Basic %s" % base64string

        if registration_mode == 3:

            try:
                response = requests.get(self.registration_url, headers=headers, timeout=10)
                response.raise_for_status()
            except:
                return False
            else:
                if "[200]" in response:
                    return True
            return False
           

        elif registration_mode == 4:
            authorization=json.dumps(
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
            ).encode('utf-8')

            headers['Connection'] = "keep-alive"

            try:
                response = requests.post(self.registration_url, data=authorization, headers=headers, timeout=10)
                response.raise_for_status()
            except:
                return False
            else:
                resp = response.json()
                _LOGGER.debug(json.dumps(resp, indent=4))
                if resp is None or not resp.get('error'):
                    self.cookies = response.cookies
                    return True
            return False


class SonyApiLib:
    """
    Provides the access to the api funtions.
    """

    def create_device(self, host, ircc_location=None, port=50001):
        device = ApiDevice(host, port, ircc_location)
        device.setup_new_device()
        return device

    def discover(self):
        """
        Discover all available devices.
        """
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover("urn:schemas-sony-com:service:IRCC:1"):
            host = device.location.split(":")[1].split("//")[1]
            devices.append(self.create_device(host, device.location))

        return devices


if __name__ == '__main__':
    lib = SonyApiLib()

    stored_config = "bluray.json"
    device = None
    import os.path
    if os.path.exists(stored_config):
        with open(stored_config, 'r') as content_file:
            json_data = content_file.read()
            device = ApiDevice.load_from_json(json_data)
    else:
        device = lib.create_device("10.0.0.102")
        device.register("SonyApiLib Python Test")
        pin = input("Enter the PIN displayed at your device: ")
        device.send_auth_pin(pin)
        data = device.save_to_json()
        text_file = open("bluray.json", "w")
        text_file.write(data)
        text_file.close()

    

# for device in lib.discover():
# device.register("SonyApiLib Python Test")
