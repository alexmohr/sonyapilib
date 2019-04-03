"""
Sony Mediaplayer lib
"""
from enum import Enum
from urllib.parse import urljoin
import base64
import json
import logging
import socket
import struct
import urllib.parse
import uuid
import xml.etree.ElementTree

import jsonpickle
import requests
import wakeonlan

from sonyapilib import ssdp


_LOGGER = logging.getLogger(__name__)

TIMEOUT = 5
URN_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"
URN_SONY_AV = "{urn:schemas-sony-com:av}"
URN_SCALAR_WEB_API_DEVICE_INFO = "{urn:schemas-sony-com:av}"


class AuthenticationResult(Enum):
    """Stores the result of the authentication process."""
    SUCCESS = 0
    ERROR = 1
    PIN_NEEDED = 2


class HttpMethod(Enum):
    """Defines which http method is used."""
    GET = 0
    POST = 1


class XmlApiObject():
    # pylint: disable=too-few-public-methods
    """Holds data for a device action or a command."""

    def __init__(self, xml_data={}):
        attributes = ["name", "mode", "url", "type", "value", "mac", "id"]

        if xml_data:
            for attr in attributes:
                if attr == "mode" and xml_data.get(attr):
                    xml_data[attr] = int(xml_data[attr])
                setattr(self, attr, xml_data.get(attr))


class SonyDevice():
    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=fixme
    # todo remove this again.
    # todo check if commands, especially soap does work with v4.
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
        self.uuid = uuid.uuid4()

        ircc_base = "http://{0.host}:{0.ircc_port}".format(self)
        self.ircc_url = urljoin(ircc_base, "/Ircc.xml")
        self.irccscpd_url = urljoin(ircc_base, "/IRCCSCPD.xml")

        self.dmr_url = "http://{0.host}:{0.dmr_port}/dmr.xml".format(self)
        self.app_url = "http://{0.host}:{0.app_port}".format(self)

    def _init_device(self):
        self._update_service_urls()

        if self.pin:
            self._recreate_authentication()
            self._update_commands()
            self._update_applist()

    @staticmethod
    def discover():
        """Discover all available devices."""

        # Todo check if this works with v4
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover(
            "urn:schemas-sony-com:service:headersIRCC:1"
        ):
            host = device.location.split(":")[1].split("//")[1]
            devices.append(SonyDevice(host, device.location))

        return devices

    @staticmethod
    def load_from_json(data):
        """Load a device configuration from a stored json."""
        return jsonpickle.decode(data)

    def save_to_json(self):
        """Save this device configuration into a json."""
        return jsonpickle.dumps(self)

    def _update_service_urls(self):
        """Initialize the device by reading the necessary resources from it """
        response = self._send_http(self.dmr_url, method=HttpMethod.GET)
        if not response:
            _LOGGER.error("Failed to get DMR")
            return None

        self._parse_dmr(response.text)

        try:
            if self.is_v4:
                pass
            else:
                response = self._send_http(
                    self.ircc_url, method=HttpMethod.GET)
                if response:
                    self._parse_ircc(response.text)

                response = self._send_http(
                    self.actionlist_url, method=HttpMethod.GET)
                if response:
                    self._parse_action_list(response.text)

                response = self._send_http(
                    self._get_action("getSystemInformation").url, method=HttpMethod.GET)
                if response:
                    self._parse_system_information(response.text)

        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error("failed to get device information: %s", str(ex))

    def _parse_action_list(self, data):
        xml_data = xml.etree.ElementTree.fromstring(data)
        for element in xml_data.findall("action"):
            action = XmlApiObject(element.attrib)
            self.actions[action.name] = action

            if action.name == "register":
                # the authentication later on is based on the device id and the mac
                # todo maybe refactor this to requests
                # http://docs.python-requests.org/en/master/_modules/requests/api/?highlight=param
                action.url = "{0}?name={1}&registrationType=initial&deviceId={2}".format(
                    action.url,
                    urllib.parse.quote(self.nickname),
                    urllib.parse.quote(self.get_device_id()))

                if action.mode == 3:
                    action.url = action.url + "&wolSupport=true"

    def _parse_ircc(self, data):
        xml_data = xml.etree.ElementTree.fromstring(data)

        # the action list contains everything the device supports
        self.actionlist_url = xml_data.find(
            "{0}device".format(URN_UPNP_DEVICE))\
            .find("{0}X_UNR_DeviceInfo".format(URN_SONY_AV))\
            .find("{0}X_CERS_ActionList_URL".format(URN_SONY_AV))\
            .text

        services = xml_data.find("{0}device".format(URN_UPNP_DEVICE))\
            .find("{0}serviceList".format(URN_UPNP_DEVICE))\
            .findall("{0}service".format(URN_UPNP_DEVICE))

        lirc_url = urllib.parse.urlparse(self.ircc_url)
        if services:
            # read service list
            for service in services:
                service_id = service.find(
                    "{0}serviceId".format(URN_UPNP_DEVICE))

                if any([
                    service_id is None,
                    "urn:schemas-sony-com:serviceId:IRCC"
                    not in service_id.text
                ]):
                    continue

                service_location = service.find(
                    "{0}controlURL".format(URN_UPNP_DEVICE)).text
                service_url = lirc_url.scheme + "://" + lirc_url.netloc
                self.control_url = service_url + service_location

    def _parse_system_information(self, data):
        xml_data = xml.etree.ElementTree.fromstring(data)
        for element in xml_data.findall("supportFunction"):
            for function in element.findall("function"):
                if function.attrib["name"] == "WOL":
                    self.mac = function.find(
                        "functionItem").attrib["value"]

    def _parse_dmr(self, data):
        lirc_url = urllib.parse.urlparse(self.ircc_url)
        xml_data = xml.etree.ElementTree.fromstring(data)
        for device in xml_data.findall("{0}device".format(URN_UPNP_DEVICE)):
            service_list = device.find(
                "{0}serviceList".format(URN_UPNP_DEVICE))
            for service in service_list:
                service_id = service.find(
                    "{0}serviceId".format(URN_UPNP_DEVICE))
                if "urn:upnp-org:serviceId:AVTransport" not in service_id.text:
                    continue
                transport_location = service.find(
                    "{0}controlURL".format(URN_UPNP_DEVICE)).text
                self.av_transport_url = "{0}://{1}:{2}{3}".format(
                    lirc_url.scheme, lirc_url.netloc.split(":")[0],
                    self.dmr_port, transport_location
                )

        # this is only for v4 devices.
        if "av:X_ScalarWebAPI_ServiceType" not in data:
            return None

        self.is_v4 = True
        deviceInfo = "{0}X_ScalarWebAPI_DeviceInfo".format(
            URN_SCALAR_WEB_API_DEVICE_INFO
        )

        for device in xml_data.findall("{0}device".format(URN_UPNP_DEVICE)):
            for deviceInfo in device.findall(deviceInfo):
                base_url = deviceInfo.find(
                    "{0}X_ScalarWebAPI_BaseURL".format(
                        URN_SCALAR_WEB_API_DEVICE_INFO
                    )
                ).text
                if not base_url.endswith("/"):
                    base_url = "{}/".format(base_url)

                action = XmlApiObject()
                action.url = urljoin(base_url, "accessControl")
                action.mode = 4
                self.actions["register"] = action

                action = XmlApiObject()
                action.url = urljoin(base_url, "system")
                self.actions["getRemoteCommandList"] = action

    def _update_commands(self):
        """Update the list of commands."""

        # need to be registered to do that
        if not self.pin:
            _LOGGER.info("Registration necessary to read command list.")
            return

        url = self._get_action("getRemoteCommandList").url
        if self._get_action("register").mode < 4:
            response = self._send_http(url, method=HttpMethod.GET)
            if response:
                self._parse_command_list(response.text)
            else:
                _LOGGER.error("Failed to get response")
        else:
            action_name = "getRemoteCommandList"
            action = self.actions[action_name]
            json_data = self._create_api_json(action.value)

            resp = self._request_json(action.url, json_data, None)
            if resp and not resp.get('error'):
                # todo parse this into the old structure.
                self.commands = resp.get('result')[1]
            else:
                _LOGGER.error("JSON request error: %s",
                              json.dumps(resp, indent=4))

    def _parse_command_list(self, data):
        xml_data = xml.etree.ElementTree.fromstring(data)
        for command in xml_data.findall("command"):
            name = command.get("name")
            self.commands[name] = XmlApiObject(command.attrib)

    def _update_applist(self):
        """Update the list of apps which are supported by the device."""
        url = self.app_url + "/appslist"
        response = self._send_http(url, method=HttpMethod.GET)
        # todo add support for v4
        if response:
            xml_data = xml.etree.ElementTree.fromstring(response.text)
            apps = xml_data.findall(".//app")
            for app in apps:
                name = app.find("name").text
                app_id = app.find("id").text
                data = XmlApiObject(None)
                data.name = name
                data.id = app_id
                self.apps[name] = data

    def _recreate_authentication(self):
        """The default cookie is for URL/sony. For some commands we need it for the root path."""

        # todo fix cookies
        # cookies = None
        # cookies = requests.cookies.RequestsCookieJar()
        # cookies.set("auth", self.cookies.get("auth"))

        username = ''
        base64string = base64.encodebytes(('%s:%s' % (username, self.pin))
                                          .encode()).decode().replace('\n', '')

        registration_action = self._get_action("register")

        self.headers['Authorization'] = "Basic %s" % base64string
        if registration_action.mode == 3:
            self.headers['X-CERS-DEVICE-ID'] = self.get_device_id()
        elif registration_action.mode == 4:
            self.headers['Connection'] = "keep-alive"

    def _request_json(self, url, params, log_errors=True):
        """Send request command via HTTP json to Sony Bravia."""

        headers = {}

        built_url = 'http://{}/{}'.format(self.host, url)

        try:
            # todo refactor to use http send.
            response = requests.post(built_url,
                                     data=params.encode("UTF-8"),
                                     cookies=self.cookies,
                                     timeout=TIMEOUT,
                                     headers=headers)

        except requests.exceptions.HTTPError as exception_instance:
            if log_errors:
                _LOGGER.error("HTTPError: %s", str(exception_instance))

        except Exception as exception_instance:  # pylint: disable=broad-except
            if log_errors:
                _LOGGER.error("Exception: %s", str(exception_instance))

        else:
            html = json.loads(response.content.decode('utf-8'))
            return html

    def _create_api_json(self, method, params=None):
        # pylint: disable=invalid-name
        """Create json data which will be send via post for the V4 api"""
        if not params:
            params = [{
                "clientid": self.get_device_id(),
                "nickname": self.nickname
            }, [{
                "clientid": self.get_device_id(),
                "nickname": self.nickname,
                "value": "yes",
                "function": "WOL"
            }]]

        ret = json.dumps(
            {
                "method": method,
                "params": params,
                "id": 1,
                "version": "1.0"
            })

        return ret

    def _send_http(self, url, method, data=None, headers=None, log_errors=True, raise_errors=False):
        # pylint: disable=too-many-arguments
        """Send request command via HTTP json to Sony Bravia."""

        if not headers:
            headers = self.headers

        if not url:
            return None

        _LOGGER.debug(
            "Calling http url %s method %s", url, method)

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
                _LOGGER.error("HTTPError: %s", str(ex))
            if raise_errors:
                raise
        except Exception as ex:  # pylint: disable=broad-except
            if log_errors:
                _LOGGER.error("Exception: %s", str(ex))
            if raise_errors:
                raise
        else:
            return response

    def _post_soap_request(self, url, params, action):
        headers = {
            'SOAPACTION': '"{0}"'.format(action),
            "Content-Type": "text/xml"
        }

        data = """<?xml version='1.0' encoding='utf-8'?>
                    <SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                        SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                        <SOAP-ENV:Body>
                            {0}
                        </SOAP-ENV:Body>
                    </SOAP-ENV:Envelope>""".format(params)
        response = self._send_http(
            url, method=HttpMethod.POST, headers=headers, data=data)
        if response:
            return response.content.decode("utf-8")
        return False

    def _send_req_ircc(self, params):
        """Send an IRCC command via HTTP to Sony Bravia."""

        data = """<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">
                    <IRCCCode>{0}</IRCCCode>
                  </u:X_SendIRCC>""".format(params)
        action = "urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"

        content = self._post_soap_request(
            url=self.control_url, params=data, action=action)
        return content

    def get_device_id(self):
        """Returns the id which is used for the registration."""
        return "TVSideView:{0}".format(self.uuid)

    def register(self):
        # pylint: disable=too-many-branches
        """
        Register at the api. The name which will be displayed in the UI of the device.
        Make sure this name does not exist yet
        For this the device must be put in registration mode.
        The tested sd5500 has no separate mode but allows registration in the overview "
        """
        registration_result = AuthenticationResult.ERROR

        registration_action = registration_action = self._get_action(
            "register")

        # protocol version 1 and 2
        if registration_action.mode < 3:
            try:
                self._send_http(
                    registration_action.url,
                    method=HttpMethod.GET,
                    raise_errors=True)
                registration_result = AuthenticationResult.SUCCESS
            except requests.exceptions.HTTPError:
                registration_result = AuthenticationResult.ERROR

        # protocol version 3
        elif registration_action.mode == 3:
            try:
                self._send_http(registration_action.url,
                                method=HttpMethod.GET, raise_errors=True)
            except requests.exceptions.HTTPError as ex:
                if ex.response.status_code == 401:
                    registration_result = AuthenticationResult.PIN_NEEDED
                else:
                    registration_result = AuthenticationResult.ERROR

        # newest protocol version 4 this is the same method as braviarc uses
        elif registration_action.mode == 4:
            authorization = self._create_api_json("actRegister", 13)

            try:
                headers = {
                    "Content-Type": "application/json"
                }
                response = self._send_http(registration_action.url,
                                           method=HttpMethod.POST, headers=headers,
                                           data=authorization, raise_errors=True)

            except requests.exceptions.HTTPError as ex:
                _LOGGER.error("[W] HTTPError: %s", str(ex))
                # todo set the correct result.
                registration_result = AuthenticationResult.PIN_NEEDED

            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.error("[W] Exception: %s", str(ex))
            else:
                resp = response.json()
                if not resp or not resp.get('error'):
                    self.cookies = response.cookies
                    registration_result = AuthenticationResult.SUCCESS

        else:
            raise ValueError(
                "Regisration mode {0} is not supported".format(registration_action.mode))

        if AuthenticationResult.SUCCESS:
            self._init_device()

        return registration_result

    def send_authentication(self, pin):
        """Authenticate against the device."""
        registration_action = self._get_action("register")

        # they do not need a pin
        if registration_action.mode < 3:
            return True

        self.pin = pin
        self._recreate_authentication()
        result = self.register()

        if AuthenticationResult.SUCCESS == result:
            self._init_device()
            return True

        return False

    def wakeonlan(self):
        """Starts the device either via wakeonlan."""
        if self.mac:
            wakeonlan.send_magic_packet(self.mac, ip_address=self.host)

    def get_playing_status(self):
        """Get the status of playback from the device"""
        data = """<m:GetTransportInfo xmlns:m="urn:schemas-upnp-org:service:AVTransport:1">
            <InstanceID>0</InstanceID>
            </m:GetTransportInfo>"""

        action = "urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"

        content = self._post_soap_request(
            url=self.av_transport_url, params=data, action=action)
        if not content:
            return "OFF"
        response = xml.etree.ElementTree.fromstring(content)
        state = response.find(".//CurrentTransportState").text
        return state

    def get_power_status(self):
        """Checks if the device is online."""
        url = self.actionlist_url
        try:
            # todo parse response
            self._send_http(url, HttpMethod.GET,
                            log_errors=False, raise_errors=True)
        except requests.exceptions.HTTPError as ex:
            _LOGGER.debug(ex)
            return False
        return True

    def _send_command(self, name):
        if not self.commands:
            self._init_device()

        if self.commands:
            if name in self.commands:
                self._send_req_ircc(self.commands[name].value)
            else:
                raise ValueError('Unknown command: %s' % name)
        else:
            raise ValueError('Failed to read command list from device.')

    def _get_action(self, name):
        """Get the action object for the action with the given name"""
        if name not in self.actions and not self.actions:
            if name not in self.actions and not self.actions:
                raise ValueError('Failed to read action list from device.')

        return self.actions[name]

    def start_app(self, app_name):
        """Start an app by name"""
        # sometimes device does not start app if already running one
        # todo add support for v4
        self.home()
        url = "{0}/apps/{1}".format(self.app_url, self.apps[app_name].id)
        data = "LOCATION: {0}/run".format(url)
        self._send_http(url, HttpMethod.POST, data=data)

    def power(self, power_on):
        """Powers the device on or shuts it off."""
        if power_on:
            self.wakeonlan()
            # Try using the power on command incase the WOL doesn't work
            if not self.get_power_status():
                # Try using the power on command incase the WOL doesn't work
                self._send_command('Power')
        else:
            self._send_command('Power')

    def get_apps(self):
        """Get the apps from the stored dict."""
        return list(self.apps.keys())

    def up(self):
        # pylint: disable=invalid-name
        """Sends the command 'up' to the connected device."""
        self._send_command('Up')

    def confirm(self):
        """Sends the command 'confirm' to the connected device."""
        self._send_command('Confirm')

    def down(self):
        """Sends the command 'down' to the connected device."""
        self._send_command('Down')

    def right(self):
        """Sends the command 'right' to the connected device."""
        self._send_command('Right')

    def left(self):
        """Sends the command 'left' to the connected device."""
        self._send_command('Left')

    def home(self):
        """Sends the command 'home' to the connected device."""
        self._send_command('Home')

    def options(self):
        """Sends the command 'options' to the connected device."""
        self._send_command('Options')

    def returns(self):
        """Sends the command 'returns' to the connected device."""
        self._send_command('Return')

    def num1(self):
        """Sends the command 'num1' to the connected device."""
        self._send_command('Num1')

    def num2(self):
        """Sends the command 'num2' to the connected device."""
        self._send_command('Num2')

    def num3(self):
        """Sends the command 'num3' to the connected device."""
        self._send_command('Num3')

    def num4(self):
        """Sends the command 'num4' to the connected device."""
        self._send_command('Num4')

    def num5(self):
        """Sends the command 'num5' to the connected device."""
        self._send_command('Num5')

    def num6(self):
        """Sends the command 'num6' to the connected device."""
        self._send_command('Num6')

    def num7(self):
        """Sends the command 'num7' to the connected device."""
        self._send_command('Num7')

    def num8(self):
        """Sends the command 'num8' to the connected device."""
        self._send_command('Num8')

    def num9(self):
        """Sends the command 'num9' to the connected device."""
        self._send_command('Num9')

    def num0(self):
        """Sends the command 'num0' to the connected device."""
        self._send_command('Num0')

    def display(self):
        """Sends the command 'display' to the connected device."""
        self._send_command('Display')

    def audio(self):
        """Sends the command 'audio' to the connected device."""
        self._send_command('Audio')

    def sub_title(self):
        """Sends the command 'subTitle' to the connected device."""
        self._send_command('SubTitle')

    def favorites(self):
        """Sends the command 'favorites' to the connected device."""
        self._send_command('Favorites')

    def yellow(self):
        """Sends the command 'yellow' to the connected device."""
        self._send_command('Yellow')

    def blue(self):
        """Sends the command 'blue' to the connected device."""
        self._send_command('Blue')

    def red(self):
        """Sends the command 'red' to the connected device."""
        self._send_command('Red')

    def green(self):
        """Sends the command 'green' to the connected device."""
        self._send_command('Green')

    def play(self):
        """Sends the command 'play' to the connected device."""
        self._send_command('Play')

    def stop(self):
        """Sends the command 'stop' to the connected device."""
        self._send_command('Stop')

    def pause(self):
        """Sends the command 'pause' to the connected device."""
        self._send_command('Pause')

    def rewind(self):
        """Sends the command 'rewind' to the connected device."""
        self._send_command('Rewind')

    def forward(self):
        """Sends the command 'forward' to the connected device."""
        self._send_command('Forward')

    def prev(self):
        """Sends the command 'prev' to the connected device."""
        self._send_command('Prev')

    def next(self):
        """Sends the command 'next' to the connected device."""
        self._send_command('Next')

    def replay(self):
        """Sends the command 'replay' to the connected device."""
        self._send_command('Replay')

    def advance(self):
        """Sends the command 'advance' to the connected device."""
        self._send_command('Advance')

    def angle(self):
        """Sends the command 'angle' to the connected device."""
        self._send_command('Angle')

    def top_menu(self):
        """Sends the command 'top_menu' to the connected device."""
        self._send_command('TopMenu')

    def pop_up_menu(self):
        """Sends the command 'pop_up_menu' to the connected device."""
        self._send_command('PopUpMenu')

    def eject(self):
        """Sends the command 'eject' to the connected device."""
        self._send_command('Eject')

    def karaoke(self):
        """Sends the command 'karaoke' to the connected device."""
        self._send_command('Karaoke')

    def netflix(self):
        """Sends the command 'netflix' to the connected device."""
        self._send_command('Netflix')

    def mode_3d(self):
        """Sends the command 'mode_3d' to the connected device."""
        self._send_command('Mode3D')

    def zoom_in(self):
        """Sends the command 'zoom_in' to the connected device."""
        self._send_command('ZoomIn')

    def zoom_out(self):
        """Sends the command 'zoom_out' to the connected device."""
        self._send_command('ZoomOut')

    def browser_back(self):
        """Sends the command 'browser_back' to the connected device."""
        self._send_command('BrowserBack')

    def browser_forward(self):
        """Sends the command 'browser_forward' to the connected device."""
        self._send_command('BrowserForward')

    def browser_bookmark_list(self):
        """Sends the command 'browser_bookmarkList' to the connected device."""
        self._send_command('BrowserBookmarkList')

    def list(self):
        """Sends the command 'list' to the connected device."""
        self._send_command('List')
