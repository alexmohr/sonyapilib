"""Sony Mediaplayer lib."""
import logging
import base64
import json
import urllib.parse
import xml.etree.ElementTree
from enum import Enum
import requests

import wakeonlan
import jsonpickle

from sonyapilib import ssdp
_LOGGER = logging.getLogger(__name__)

TIMEOUT = 5
URN_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"
URN_SONY_AV = "{urn:schemas-sony-com:av}"
URN_SCALAR_WEB_API_DEVICE_INFO = "{urn:schemas-sony-com:av}"


class AuthenticationResult(Enum):
    SUCCESS = 0
    ERROR = 1
    PIN_NEEDED = 2


class HttpMethod(Enum):
    GET = 0
    POST = 1


class XmlApiObject():
    """Holds data for a device action or a command."""

    def __init__(self, xml_data):
        self.name = None
        self.mode = None
        self.url = None
        self.type = None
        self.value = None
        self.mac = None
        self.id = None

        if xml_data is not None:
            for arg in self.__dict__:
                if "_" in arg:
                    continue
                if arg in xml_data:
                    if arg == "mode":
                        setattr(self, arg, int(xml_data[arg]))
                    else:
                        setattr(self, arg, xml_data[arg])


class SonyDevice():
    """Contains all data for the device."""

    def __init__(self, host, nickname):
        """Init the device with the entry point."""
        self.host = host
        self.nickname = nickname
        self.actionlist_url = None
        self.control_url = None
        self.av_transport_url = None
        self.app_url = None

        self.app_port = 50202
        self.dmr_port = 52323
        self.ircc_port = 50001

        self.actions = {}
        self.headers = {}
        self.commands = {}
        self.apps = {}

        self.pin = None
        self.name = None
        self.cookies = None
        self.mac = None
        self.is_v4 = False

        self.ircc_url = "http://{0}:{1}/Ircc.xml".format(host, self.ircc_port)
        self.irccscpd_url = "http://{0}:{1}/IRCCSCPD.xml".format(host, self.ircc_port)
        self.dmr_url = "http://{0}:{1}/dmr.xml".format(self.host, self.dmr_port)
        self.app_url = "http://{0}:{1}".format(self.host, self.app_port)

        if not self.actions and self.pin is not None:
            self.init_device()

    def init_device(self):
        self._update_service_urls()
        self._update_commands()
        self._update_applist()

    @staticmethod
    def discover():
        """Discover all available devices."""

        # Todo check if this works with v4
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover("urn:schemas-sony-com:service:headersIRCC:1"):
            host = device.location.split(":")[1].split("//")[1]
            devices.append(SonyDevice(host, device.location))

        return devices

    @staticmethod
    def load_from_json(data):
        """Load a device configuration from a stored json."""
        return jsonpickle.decode(data)

    def save_to_json(self):
        """ Save this device configuration into a json """
        return jsonpickle.dumps(self)

    def _update_service_urls(self):
        """ Initialize the device by reading the necessary resources from it """
        response = self._send_http(self.dmr_url, method=HttpMethod.GET)
        if not response:
            _LOGGER.error("Failed to get DMR")
            return

        self._parse_dmr(response.text)
        self._recreate_authentication()

        if not self.is_v4:
            response = self._send_http(self.ircc_url, method=HttpMethod.GET)
            self._parse_ircc(response.text)

        if len(self.commands) > 0:
            self._update_commands()
            self._update_applist()

    def _parse_ircc(self, data):
        response = self._send_http(self.ircc_url, method=HttpMethod.GET)
        if not response:
            return

        xml_data = xml.etree.ElementTree.fromstring(data)

        # the action list contains everything the device supports
        self.actionlist_url = xml_data.find("{0}device".format(URN_UPNP_DEVICE))\
            .find("{0}X_UNR_DeviceInfo".format(URN_SONY_AV))\
            .find("{0}X_CERS_ActionList_URL".format(URN_SONY_AV))\
            .text

        services = xml_data.find("{0}device".format(URN_UPNP_DEVICE))\
            .find("{0}serviceList".format(URN_UPNP_DEVICE))\
            .findall("{0}service".format(URN_UPNP_DEVICE))

        # read action list
        response = self._send_http(self.actionlist_url, method=HttpMethod.GET)
        if not response:
            raw_data = response.text
            xml_data = xml.etree.ElementTree.fromstring(raw_data)
            for element in xml_data.findall("action"):
                action = XmlApiObject(element.attrib)
                self.actions[action.name] = action

                # some data has to overwritten for the registration to work properly
                if action.name == "register":
                    if action.mode < 4:
                        # the authentication later on is based on the device id and the mac
                        # todo maybe refactor this to requests http://docs.python-requests.org/en/master/_modules/requests/api/?highlight=param
                        action.url = "{0}?name={1}&registrationType=initial&deviceId={1}".format(
                            action.url, urllib.parse.quote(self.nickname))
                        if action.mode == 3:
                            action.url = action.url + "&wolSupport=true"

        lirc_url = urllib.parse.urlparse(self.ircc_url)
        if services:
            # read service list
            for service in services:
                service_id = service.find(
                    "{0}serviceId".format(URN_UPNP_DEVICE))
                if not service_id:
                    continue
                if "urn:schemas-sony-com:serviceId:IRCC" not in service_id.text:
                    continue

                service_location = service.find(
                    "{0}controlURL".format(URN_UPNP_DEVICE)).text
                service_url = lirc_url.scheme + "://" + lirc_url.netloc
                self.control_url = service_url + service_location

        # get systeminformation
        response = self._send_http(
            self.get_action("getSystemInformation").url, method=HttpMethod.GET)

        if response is not None:
            raw_data = response.text
            xml_data = xml.etree.ElementTree.fromstring(raw_data)
            for element in xml_data.findall("supportFunction"):
                for function in element.findall("function"):
                    if function.attrib["name"] == "WOL":
                        self.mac = function.find(
                            "functionItem").attrib["value"]

    def _parse_dmr(self, data):
        lirc_url = urllib.parse.urlparse(self.ircc_url)
        xml_data = xml.etree.ElementTree.fromstring(data)
        for device in xml_data.findall("{0}device".format(URN_UPNP_DEVICE)):
            serviceList = device.find(
                "{0}serviceList".format(URN_UPNP_DEVICE))
            for service in serviceList:
                service_id = service.find(
                    "{0}serviceId".format(URN_UPNP_DEVICE))
                if "urn:upnp-org:serviceId:AVTransport" not in service_id.text:
                    continue
                transport_location = service.find(
                    "{0}controlURL".format(URN_UPNP_DEVICE)).text
                self.av_transport_url = "{0}://{1}:{2}{3}".format(
                    lirc_url.scheme, lirc_url.netloc.split(":")[0], self.dmr_port, transport_location)

        # this is only for v4 devices.
        if not "av:X_ScalarWebAPI_ServiceType" in data:
            return

        self.is_v4 = True
        deviceInfo = "{0}X_ScalarWebAPI_DeviceInfo"\
            .format(URN_SCALAR_WEB_API_DEVICE_INFO)

        for device in xml_data.findall("{0}device".format(URN_UPNP_DEVICE)):
            for deviceInfo in device.findall(deviceInfo):
                base_url = deviceInfo.find("{0}X_ScalarWebAPI_BaseURL"\
                    .format(URN_SCALAR_WEB_API_DEVICE_INFO))\
                    .text

                action = XmlApiObject(None)
                action.url = base_url + "/accessControl"
                action.mode = 4
                self.actions["register"] = action

                action = XmlApiObject(None)
                action.url = base_url + "/system"
                self.actions["getRemoteCommandList"] = action
                   

    def _update_commands(self):

        # needs to be registered to do that
        if not self.pin:
            return

        url = self.get_action("getRemoteCommandList").url
        if self.get_action("register").mode < 4:
            response = self._send_http(url, method=HttpMethod.GET)
            if response:
                xml_data = xml.etree.ElementTree.fromstring(response.text)

                for command in xml_data.findall("command"):
                    name = command.get("name")
                    self.commands[name] = XmlApiObject(command.attrib)
        else:
            response = self._send_http(
                url, method=HttpMethod.POST, data=self._create_api_json("getRemoteControllerInfo", 1))
            if response:
                json = response.json()
                # todo parse json
                if not json.get('error'):
                    # todo this does not fit 100% with the structure of this lib.
                    # see github issue#2
                    self.commands = json.get('result')[1]
                else:
                    _LOGGER.error("JSON request error: " +
                                  json.dumps(json, indent=4))

    def _update_applist(self):
        url = self.app_url + "/appslist"
        response = self._send_http(url, method=HttpMethod.GET)
        if response:
            xml_data = xml.etree.ElementTree.fromstring(response.text)
            apps = xml_data.findall(".//app")
            for app in apps:
                name = app.find("name").text
                id = app.find("id").text
                data = XmlApiObject(None)
                data.name = name
                data.id = id
                self.apps[name] = data

    def _recreate_authentication(self):
        """
        The default cookie is for URL/sony. For some commands we need it for the root path.
        """

        if not self.pin:
            return

        # todo fix cookies
        cookies = None
        # cookies = requests.cookies.RequestsCookieJar()
        # cookies.set("auth", self.cookies.get("auth"))

        username = ''
        base64string = base64.encodebytes(('%s:%s' % (username, self.pin))
                                          .encode()).decode().replace('\n', '')

        registration_action = self.get_action("register")

        self.headers['Authorization'] = "Basic %s" % base64string
        if registration_action.mode == 3:
            self.headers['X-CERS-DEVICE-ID'] = self.get_device_id()
        elif registration_action.mode == 4:
            self.headers['Connection'] = "keep-alive"

        return cookies

    def _request_json(self, url, params, log_errors=True):
        """Send request command via HTTP json to Sony Bravia."""
        built_url = 'http://{}/{}'.format(self.host, url)

        response = self._send_http(url, HttpMethod.POST, params)
        html = json.loads(response.content.decode('utf-8'))
        return html

    def _create_api_json(self, method, id, params=None):
        """Create json data which will be send via post for the V4 api"""
        if not params:
            params = [{
                "clientid": self.get_device_id(),
                "nickname": self.nickname
            },
                [{
                    "clientid": self.get_device_id(),
                    "nickname": self.nickname,
                    "value": "yes",
                    "function": "WOL"
                }]
            ]

        ret = json.dumps(
            {
                "method": method,
                "params": params,
                "id": id,
                "version": "1.0"
            })

        return ret

    def _send_http(self, url, method, data=None, headers=None, log_errors=True, raise_errors=False):
        """Send request command via HTTP json to Sony Bravia."""

        if not headers:
            headers = self.headers

        if not url:
            return

        _LOGGER.debug(
            "Calling http url {0} method {1}".format(url, str(method)))

        try:
            params = ""
            if data:
                params = data.encode("UTF-8")

            if method == HttpMethod.POST:
                response = requests.post(url,
                                         data=params,
                                         headers=headers,
                                         cookies=self.cookies,
                                         timeout=TIMEOUT)
            elif method == HttpMethod.GET:
                response = requests.get(url,
                                        data=params,
                                        headers=headers,
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

    def _post_soap_request(self, url, params, action):
        headers = {
            'SOAPACTION': '"{0}"'.format(action),
            "Content-Type": "text/xml"
        }

        data = "<?xml version='1.0' encoding='utf-8'?><SOAP-ENV:Envelope xmlns:SOAP-ENV=\"http://schemas.xmlsoap.org/soap/envelope/\" " + \
            "SOAP-ENV:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">" +\
            "<SOAP-ENV:Body>" +\
            params +\
            "</SOAP-ENV:Body>" +\
            "</SOAP-ENV:Envelope>"
        response = self._send_http(
            url, method=HttpMethod.POST, headers=headers, data=data)
        if response:
            return response.content.decode("utf-8")
        return False

    def _send_req_ircc(self, params):
        """Send an IRCC command via HTTP to Sony Bravia."""
        data = "<u:X_SendIRCC xmlns:u=\"urn:schemas-sony-com:service:IRCC:1\">" +\
            "<IRCCCode>" + params + "</IRCCCode>" +\
            "</u:X_SendIRCC>"
        action = "urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"

        content = self._post_soap_request(
            url=self.control_url, params=data, action=action)
        return content

    def get_device_id(self):
        return "TVSideView:{0}".format(self.mac)

    def register(self):
        """
        Register at the api. The name which will be displayed in the UI of the device. Make sure this name does not exist yet
        For this the device must be put in registration mode.
        The tested sd5500 has no separte mode but allows registration in the overview "
        """
        registration_result = AuthenticationResult.ERROR

        registration_action = registration_action = self.get_action("register")

        # protocol version 1 and 2
        if registration_action.mode < 3:
            registration_response = self._send_http(
                registration_action.url, method=HttpMethod.GET, raise_errors=True)
            registration_result = AuthenticationResult.SUCCESS

        # protocol version 3
        elif registration_action.mode == 3:
            try:
                self._send_http(registration_action.url,
                                method=HttpMethod.GET, raise_errors=True)
            except requests.exceptions.HTTPError as ex:
                _LOGGER.error("[W] HTTPError: " + str(ex))
                # todo set the correct result.
                registration_result = AuthenticationResult.PIN_NEEDED

        # newest protocol version 4 this is the same method as braviarc uses
        elif registration_action.mode == 4:
            authorization = self._create_api_json("actRegister", 13)

            try:
                headers = {
                    "Content-Type": "application/json"
                }
                response = self._send_http(registration_action.url, method=HttpMethod.POST, headers=headers,
                                           data=authorization, raise_errors=True)
            except requests.exceptions.HTTPError as ex:
                _LOGGER.error("[W] HTTPError: " + str(ex))
                # todo set the correct result.
                registration_result = AuthenticationResult.PIN_NEEDED

            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.error("[W] Exception: " + str(ex))
            else:
                resp = response.json()
                _LOGGER.debug(json.dumps(resp, indent=4))
                if not resp or not resp.get('error'):
                    self.cookies = response.cookies
                    registration_result = AuthenticationResult.SUCCESS

        else:
            raise ValueError(
                "Regisration mode {0} is not supported".format(registration_action.mode))
        
        if AuthenticationResult.SUCCESS:
            self.init_device()

        return registration_result

    def send_authentication(self, pin):
        registration_action = self.get_action("register")

        # they do not need a pin
        if registration_action.mode < 3:
            return True

        self.pin = pin
        self._recreate_authentication()
        self.register()

    def wakeonlan(self):
        if self.mac:
            wakeonlan.send_magic_packet(self.mac, ip_address=self.host)

    def get_playing_status(self):
        data = '<m:GetTransportInfo xmlns:m="urn:schemas-upnp-org:service:AVTransport:1">' + \
            '<InstanceID>0</InstanceID>' + \
            '</m:GetTransportInfo>'

        action = "urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"

        content = self._post_soap_request(
            url=self.av_transport_url, params=data, action=action)
        if not content:
            return "OFF"
        response = xml.etree.ElementTree.fromstring(content)
        state = response.find(".//CurrentTransportState").text
        return state

    def get_power_status(self):
        url = self.actionlist_url
        try:
            response = self._send_http(url, HttpMethod.GET,
                                       log_errors=False, raise_errors=True)
        except Exception as ex:
            _LOGGER.debug(ex)
            return False
        return True

    def send_command(self, name):
        if len(self.commands) == 0:
            self._update_commands()

        if not self.commands:
            if name in self.commands:
                self._send_req_ircc(self.commands[name].value)
            else:
                raise ValueError('Unknown command: %s' % name)
        else:
            raise ValueError('Failed to read command list from device.')

    def get_action(self, name):
        if not name in self.actions and len(self.actions) == 0:
            self._update_service_urls()
            if not name in self.actions and len(self.actions) == 0:
                raise ValueError('Failed to read action list from device.')

        return self.actions[name]

    def start_app(self, app_name, log_errors=True):
        """Start an app by name"""
        # sometimes device does not start app if already running one
        self.home()
        url = "{0}/apps/{1}".format(self.app_url, self.apps[app_name].id)
        data = "LOCATION: {0}/run".format(url)
        self._send_http(url, HttpMethod.POST, data=data)

    def power(self, on):
        if on:
            self.wakeonlan()
            # Try using the power on command incase the WOL doesn't work
            if not self.get_power_status():
                # Try using the power on command incase the WOL doesn't work
                self.send_command('Power')
        else:
            self.send_command('Power')

    def get_apps(self):
        return list(self.apps.keys())

    def up(self):
        self.send_command('Up')

    def confirm(self):
        self.send_command('Confirm')

    def down(self):
        self.send_command('Down')

    def right(self):
        self.send_command('Right')

    def left(self):
        self.send_command('Left')

    def home(self):
        self.send_command('Home')

    def options(self):
        self.send_command('Options')

    def returns(self):
        self.send_command('Return')

    def num1(self):
        self.send_command('Num1')

    def num2(self):
        self.send_command('Num2')

    def num3(self):
        self.send_command('Num3')

    def num4(self):
        self.send_command('Num4')

    def num5(self):
        self.send_command('Num5')

    def num6(self):
        self.send_command('Num6')

    def num7(self):
        self.send_command('Num7')

    def num8(self):
        self.send_command('Num8')

    def num9(self):
        self.send_command('Num9')

    def num0(self):
        self.send_command('Num0')

    def display(self):
        self.send_command('Display')

    def audio(self):
        self.send_command('Audio')

    def subTitle(self):
        self.send_command('SubTitle')

    def favorites(self):
        self.send_command('Favorites')

    def yellow(self):
        self.send_command('Yellow')

    def blue(self):
        self.send_command('Blue')

    def red(self):
        self.send_command('Red')

    def green(self):
        self.send_command('Green')

    def play(self):
        self.send_command('Play')

    def stop(self):
        self.send_command('Stop')

    def pause(self):
        self.send_command('Pause')

    def rewind(self):
        self.send_command('Rewind')

    def forward(self):
        self.send_command('Forward')

    def prev(self):
        self.send_command('Prev')

    def next(self):
        self.send_command('Next')

    def replay(self):
        self.send_command('Replay')

    def advance(self):
        self.send_command('Advance')

    def angle(self):
        self.send_command('Angle')

    def topMenu(self):
        self.send_command('TopMenu')

    def popUpMenu(self):
        self.send_command('PopUpMenu')

    def eject(self):
        self.send_command('Eject')

    def karaoke(self):
        self.send_command('Karaoke')

    def netflix(self):
        self.send_command('Netflix')

    def mode3D(self):
        self.send_command('Mode3D')

    def zoomIn(self):
        self.send_command('ZoomIn')

    def zoomOut(self):
        self.send_command('ZoomOut')

    def browserBack(self):
        self.send_command('BrowserBack')

    def browserForward(self):
        self.send_command('BrowserForward')

    def browserBookmarkList(self):
        self.send_command('BrowserBookmarkList')

    def list(self):
        self.send_command('List')


if __name__ == "__main__":

    stored_config = "bluray.json"
    device = None
    # device must be on for registration
    host = "192.168.178.23"
    device = SonyDevice(host, "SonyApiLib Python Test10")
    device.register()
    pin = input("Enter the PIN displayed at your device: ")
    device.send_authentication(pin)
    # save_device()

    apps = device.get_apps()

    device.start_app(apps[0])

    # Play media
    device.play()
