"""
Sony Media player lib
"""
import base64
import json
import logging
import xml.etree.ElementTree
from enum import Enum
from urllib.parse import (
    urljoin,
    urlparse,
    quote,
)

import jsonpickle
import requests
import wakeonlan

from sonyapilib import ssdp
from sonyapilib.xml_helper import find_in_xml

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 5
URN_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"
URN_SONY_AV = "{urn:schemas-sony-com:av}"
URN_SONY_IRCC = "urn:schemas-sony-com:serviceId:IRCC"
URN_SCALAR_WEB_API_DEVICE_INFO = "{urn:schemas-sony-com:av}"
WEBAPI_SERVICETYPE = "av:X_ScalarWebAPI_ServiceType"


class AuthenticationResult(Enum):
    """Stores the result of the authentication process."""
    SUCCESS = 0
    ERROR = 1
    PIN_NEEDED = 2


class HttpMethod(Enum):
    """Defines which http method is used."""
    GET = "get"
    POST = "post"


class XmlApiObject:
    # pylint: disable=too-few-public-methods
    """Holds data for a device action or a command."""

    def __init__(self, xml_data):
        self.name = None
        self.mode = None
        self.url = None
        self.type = None
        self.value = None
        self.mac = None
        # must be named that way to match xml
        # pylint: disable=invalid-name
        self.id = None
        if not xml_data:
            return

        for attr in self.__dict__:
            if attr == "mode" and xml_data.get(attr):
                xml_data[attr] = int(xml_data[attr])
            setattr(self, attr, xml_data.get(attr))


class SonyDevice:
    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=fixme
    """Contains all data for the device."""

    def __init__(self, host, nickname, psk=None):
        """Init the device with the entry point."""
        self.host = host
        self.nickname = nickname
        self.client_id = nickname
        self.actionlist_url = None
        self.control_url = None
        self.av_transport_url = None
        self.app_url = None
        self.psk = psk

        self.app_port = 50202
        self.dmr_port = 52323
        self.ircc_port = 50001

        # actions are thing like getting status
        self.actions = {}
        self.headers = {}
        # commands are alike to buttons on the remote
        self.commands = {}
        self.apps = {}

        self.pin = None
        self.cookies = None
        self.mac = None
        self.api_version = 0

        ircc_base = "http://{0.host}:{0.ircc_port}".format(self)
        self.ircc_url = urljoin(ircc_base, "/Ircc.xml")
        self.irccscpd_url = urljoin(ircc_base, "/IRCCSCPD.xml")

        self.dmr_url = "http://{0.host}:{0.dmr_port}/dmr.xml".format(self)
        self.app_url = "http://{0.host}:{0.app_port}".format(self)
        self.base_url = "http://{0.host}/sony/".format(self)

    def init_device(self):
        """Update this object with data from the device"""
        self._update_service_urls()
        self._update_commands()

        if self.pin:
            self._recreate_authentication()
            self._update_applist()

    @staticmethod
    def discover():
        """Discover all available devices."""
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover(
                "urn:schemas-sony-com:service:IRCC:1"
        ):
            host = device.location.split(":")[1].split("//")[1]
            devices.append(SonyDevice(host, device.location))

        return devices

    @staticmethod
    def load_from_json(data):
        """Load a device configuration from a stored json."""
        device = jsonpickle.decode(data)
        device.init_device()
        return device

    def save_to_json(self):
        """Save this device configuration into a json."""
        # make sure object is up to date
        self.init_device()
        return jsonpickle.dumps(self)

    def _update_service_urls(self):
        """Initialize the device by reading the necessary resources from it."""
        response = self._send_http(self.dmr_url, method=HttpMethod.GET)
        if not response:
            _LOGGER.error("Failed to get DMR")
            return

        try:
            self._parse_dmr(response.text)
            if self.api_version <= 3:
                self._parse_ircc()
                self._parse_action_list()
                self._parse_system_information()
            else:
                self._parse_system_information_v4()

        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error("failed to get device information: %s", str(ex))

    def _parse_action_list(self):
        response = self._send_http(self.actionlist_url, method=HttpMethod.GET)
        if not response:
            return

        for element in find_in_xml(response.text, [("action", True)]):
            action = XmlApiObject(element.attrib)
            self.actions[action.name] = action

            if action.name == "register":
                # the authentication later on is based on the device id and the mac
                action.url = "{0}?name={1}&registrationType=initial&deviceId={2}".format(
                    action.url,
                    quote(self.nickname),
                    quote(self.client_id))
                self.api_version = action.mode
                if action.mode == 3:
                    action.url = action.url + "&wolSupport=true"

    def _parse_ircc(self):
        response = self._send_http(self.ircc_url, method=HttpMethod.GET, raise_errors=True)
        if not response:
            return

        upnp_device = "{}device".format(URN_UPNP_DEVICE)
        # the action list contains everything the device supports
        self.actionlist_url = find_in_xml(
            response.text,
            [upnp_device,
             "{}X_UNR_DeviceInfo".format(URN_SONY_AV),
             "{}X_CERS_ActionList_URL".format(URN_SONY_AV)]
        ).text
        services = find_in_xml(
            response.text,
            [upnp_device,
             "{}serviceList".format(URN_UPNP_DEVICE),
             ("{}service".format(URN_UPNP_DEVICE), True)],
        )

        lirc_url = urlparse(self.ircc_url)
        for service in services:
            service_id = service.find(
                "{0}serviceId".format(URN_UPNP_DEVICE))

            if any([
                    service_id is None,
                    URN_SONY_IRCC not in service_id.text,
            ]):
                continue

            service_location = service.find(
                "{0}controlURL".format(URN_UPNP_DEVICE)).text
            service_url = lirc_url.scheme + "://" + lirc_url.netloc
            self.control_url = service_url + service_location

    def _parse_system_information_v4(self):
        url = urljoin(self.base_url, "system")
        json_data = self._create_api_json("getSystemSupportedFunction")
        response = self._send_http(url, HttpMethod.POST, json=json_data)
        if not response:
            _LOGGER.debug("no response received, device might be off")
            return

        json_resp = response.json()
        if json_resp and not json_resp.get('error'):
            for option in json_resp.get('result')[0]:
                if option['option'] == 'WOL':
                    self.mac = option['value']

    def _parse_system_information(self):
        response = self._send_http(
            self._get_action("getSystemInformation").url, method=HttpMethod.GET)
        if not response:
            return

        for element in find_in_xml(
                response.text, [("supportFunction", "all"), ("function", True)]
        ):
            for function in element:
                if function.attrib["name"] == "WOL":
                    self.mac = function.find(
                        "functionItem").attrib["value"]

    def _parse_dmr(self, data):
        lirc_url = urlparse(self.ircc_url)
        xml_data = xml.etree.ElementTree.fromstring(data)

        for device in find_in_xml(xml_data, [
                ("{0}device".format(URN_UPNP_DEVICE), True),
                "{0}serviceList".format(URN_UPNP_DEVICE)
        ]):
            for service in device:
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

        # this is only true for v4 devices.
        if WEBAPI_SERVICETYPE not in data:
            return

        self.api_version = 4
        device_info_name = "{0}X_ScalarWebAPI_DeviceInfo".format(
            URN_SCALAR_WEB_API_DEVICE_INFO
        )

        search_params = [
            ("{0}device".format(URN_UPNP_DEVICE), True),
            (device_info_name, True),
            "{0}X_ScalarWebAPI_BaseURL".format(URN_SCALAR_WEB_API_DEVICE_INFO),
        ]
        for device in find_in_xml(xml_data, search_params):
            for xml_url in device:
                self.base_url = xml_url.text
                if not self.base_url.endswith("/"):
                    self.base_url = "{}/".format(self.base_url)

                action = XmlApiObject({})
                action.url = urljoin(self.base_url, "accessControl")
                action.mode = 4
                self.actions["register"] = action

                action = XmlApiObject({})
                action.url = urljoin(self.base_url, "system")
                action.value = "getRemoteControllerInfo"
                self.actions["getRemoteCommandList"] = action
                self.control_url = urljoin(self.base_url, "IRCC")

    def _update_commands(self):
        """Update the list of commands."""

        if self.api_version <= 3:
            self._parse_command_list()
        elif self.api_version > 3 and self.pin:
            _LOGGER.debug("Registration necessary to read command list.")
            self._parse_command_list_v4()

    def _parse_command_list_v4(self):
        action_name = "getRemoteCommandList"
        action = self.actions[action_name]
        json_data = self._create_api_json(action.value)

        response = self._send_http(
            action.url, HttpMethod.POST, json=json_data, headers={}
        )

        if not response:
            _LOGGER.debug("no response received, device might be off")
            return

        json_resp = response.json()
        if json_resp and not json_resp.get('error'):
            for command in json_resp.get('result')[1]:
                api_object = XmlApiObject(command)
                if api_object.name == "PowerOff":
                    api_object.name = "Power"
                self.commands[api_object.name] = api_object
        else:
            _LOGGER.error("JSON request error: %s",
                          json.dumps(json_resp, indent=4))

    def _parse_command_list(self):
        """Parse the list of available command in devices with the legacy api."""
        action_name = "getRemoteCommandList"
        if action_name not in self.actions:
            _LOGGER.debug("Action list not set in device, try calling init_device")
            return

        action = self.actions[action_name]
        url = action.url
        response = self._send_http(url, method=HttpMethod.GET)
        if not response:
            _LOGGER.debug("Failed to get response for command list, device might be off")
            return

        for command in find_in_xml(response.text, [("command", True)]):
            name = command.get("name")
            self.commands[name] = XmlApiObject(command.attrib)

    def _update_applist(self):
        """Update the list of apps which are supported by the device."""
        if self.api_version < 4:
            url = self.app_url + "/appslist"
            response = self._send_http(url, method=HttpMethod.GET)
        else:
            url = 'http://{}/DIAL/sony/applist'.format(self.host)
            response = self._send_http(
                url, method=HttpMethod.GET, cookies=self._recreate_auth_cookie())

        if response:
            for app in find_in_xml(response.text, [(".//app", True)]):
                data = XmlApiObject({
                    "name": app.find("name").text,
                    "id": app.find("id").text,
                })
                self.apps[data.name] = data

    def _recreate_authentication(self):
        """The default cookie is for URL/sony. For some commands we need it for the root path."""
        registration_action = self._get_action("register")
        if any([not registration_action, registration_action.mode < 3]):
            return

        username = ''
        base64string = base64.encodebytes(
            ('%s:%s' % (username, self.pin)).encode()).decode().replace('\n', '')

        self.headers['Authorization'] = "Basic %s" % base64string
        if registration_action.mode == 3:
            self.headers['X-CERS-DEVICE-ID'] = self.client_id
        elif registration_action.mode == 4:
            self.headers['Connection'] = "keep-alive"

        if self.psk:
            self.headers['X-Auth-PSK'] = self.psk

    def _create_api_json(self, method, params=None):
        # pylint: disable=invalid-name
        """Create json data which will be send via post for the V4 api"""
        if not params:
            params = [{
                "clientid": self.client_id,
                "nickname": self.nickname
            }, [{
                "clientid": self.client_id,
                "nickname": self.nickname,
                "value": "yes",
                "function": "WOL"
            }]]

        return {
            "method": method,
            "params": params,
            "id": 1,
            "version": "1.0"
        }

    def _send_http(self, url, method, **kwargs):
        # pylint: disable=too-many-arguments
        """Send request command via HTTP json to Sony Bravia."""

        log_errors = kwargs.pop("log_errors", True)
        raise_errors = kwargs.pop("raise_errors", False)
        method = kwargs.pop("method", method.value)

        params = {
            "cookies": self.cookies,
            "timeout": TIMEOUT,
            "headers": self.headers,
        }
        params.update(kwargs)

        _LOGGER.debug(
            "Calling http url %s method %s", url, method)

        try:
            response = getattr(requests, method)(url, **params)
            response.raise_for_status()
        except requests.exceptions.RequestException as ex:
            if log_errors:
                _LOGGER.error("HTTPError: %s", str(ex))
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

    def _send_command(self, name):
        if not self.commands:
            self.init_device()

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
            self.init_device()
            if name not in self.actions and not self.actions:
                raise ValueError('Failed to read action list from device.')

        return self.actions[name]

    def _register_without_auth(self, registration_action):
        try:
            self._send_http(
                registration_action.url,
                method=HttpMethod.GET,
                raise_errors=True)
            # set the pin to something to make sure init_device is called
            self.pin = 9999
        except requests.exceptions.RequestException:
            return AuthenticationResult.ERROR
        else:
            return AuthenticationResult.SUCCESS

    @staticmethod
    def _handle_register_error(ex):
        if isinstance(ex, requests.exceptions.HTTPError) \
                and ex.response.status_code == 401:
            return AuthenticationResult.PIN_NEEDED
        return AuthenticationResult.ERROR

    def _register_v3(self, registration_action):
        try:
            self._send_http(registration_action.url,
                            method=HttpMethod.GET, raise_errors=True)
        except requests.exceptions.RequestException as ex:
            return self._handle_register_error(ex)
        else:
            return AuthenticationResult.SUCCESS

    def _register_v4(self, registration_action):
        authorization = self._create_api_json("actRegister")

        try:
            headers = {
                "Content-Type": "application/json"
            }
            response = self._send_http(registration_action.url,
                                       method=HttpMethod.POST, headers=headers,
                                       auth=('', self.pin),
                                       data=json.dumps(authorization), raise_errors=True)

        except requests.exceptions.RequestException as ex:
            return self._handle_register_error(ex)
        else:
            resp = response.json()
            if not resp or resp.get('error'):
                return AuthenticationResult.ERROR

            self.cookies = response.cookies
            return AuthenticationResult.SUCCESS

    def _recreate_auth_cookie(self):
        """
        The default cookie is for URL/sony.
        For some commands we need it for the root path
        """
        # pylint: disable=abstract-class-instantiated
        cookies = requests.cookies.RequestsCookieJar()
        cookies.set("auth", self.cookies.get("auth"))
        return cookies

    def register(self):
        """
        Register at the api. The name which will be displayed in the UI of the device.
        Make sure this name does not exist yet.
        For this the device must be put in registration mode.
        """

        registration_result = AuthenticationResult.ERROR
        registration_action = registration_action = self._get_action(
            "register")

        if registration_action.mode < 3:
            registration_result = self._register_without_auth(
                registration_action)
        elif registration_action.mode == 3:
            registration_result = self._register_v3(registration_action)
        elif registration_action.mode == 4:
            registration_result = self._register_v4(registration_action)
        else:
            raise ValueError(
                "Registration mode {0} is not supported".format(registration_action.mode))

        if registration_result is AuthenticationResult.SUCCESS:
            self.init_device()

        return registration_result

    def send_authentication(self, pin):
        """Authenticate against the device."""
        registration_action = self._get_action("register")

        # they do not need a pin
        if registration_action.mode < 3:
            return True

        if not pin:
            return False

        self.pin = pin
        self._recreate_authentication()
        result = self.register()

        return AuthenticationResult.SUCCESS == result

    def wakeonlan(self, broadcast='255.255.255.255'):
        """Starts the device either via wakeonlan."""
        if self.mac:
            wakeonlan.send_magic_packet(self.mac, ip_address=broadcast)

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
        return find_in_xml(content, [".//CurrentTransportState"]).text

    def get_power_status(self):
        """Checks if the device is online."""
        if self.api_version < 4:
            url = self.actionlist_url
            try:
                self._send_http(url, HttpMethod.GET, log_errors=False, raise_errors=True)
            except requests.exceptions.RequestException as ex:
                _LOGGER.debug(ex)
                return False
            return True
        try:
            resp = self._send_http(urljoin(self.base_url, "system"), HttpMethod.POST,
                                   json=self._create_api_json("getPowerStatus"))
            if not resp:
                return False
            json_data = resp.json()
            if not json_data.get('error'):
                power_data = json_data.get('result')[0]
                return power_data.get('status') != "off"
        except requests.RequestException:
            pass
        return False

    def start_app(self, app_name):
        """Start an app by name"""
        # sometimes device does not start app if already running one
        self.home()

        if self.api_version < 4:
            url = "{0}/apps/{1}".format(self.app_url, self.apps[app_name].id)
            data = "LOCATION: {0}/run".format(url)
            self._send_http(url, HttpMethod.POST, data=data)
        else:
            url = 'http://{}/DIAL/apps/{}'.format(self.host, self.apps[app_name].id)
            self._send_http(url, HttpMethod.POST, cookies=self._recreate_auth_cookie())

    def power(self, power_on, broadcast='255.255.255.255'):
        """Powers the device on or shuts it off."""
        if power_on:
            self.wakeonlan(broadcast)
            # Try using the power on command incase the WOL doesn't work
            if not self.get_power_status():
                # Try using the power on command incase the WOL doesn't work
                self._send_command('Power')
        else:
            self._send_command('Power')

    def get_apps(self):
        """Get the apps from the stored dict."""
        return list(self.apps.keys())

    def volume_up(self):
        # pylint: disable=invalid-name
        """Sends the command 'VolumeUp' to the connected device."""
        self._send_command('VolumeUp')
    
    def volume_down(self):
        # pylint: disable=invalid-name
        """Sends the command 'VolumeDown' to the connected device."""
        self._send_command('VolumeDown')
    
    def mute_volume(self):
        # pylint: disable=invalid-name
        """Sends the command 'Mute' to the connected device."""
        self._send_command('Mute')
    
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
