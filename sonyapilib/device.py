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

from sonyapilib import ssdp
_LOGGER = logging.getLogger(__name__)

TIMEOUT = 5


class AuthenicationResult(Enum):
    SUCCESS = 0
    ERROR = 1
    PIN_NEEDED = 2


class HttpMethod(Enum):
    GET = 0,
    POST = 1


class XmlApiObject():
    """ Holds data for a device action or a command """

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
                    if (arg == "mode"):
                        setattr(self, arg, int(xml_data[arg]))
                    else:
                        setattr(self, arg, xml_data[arg])  

class SonyDevice():
    """
    Contains all data for the device
    """

    def __init__(self, host, nickname, port=50001, dmr_port=52323, app_port=50202, ircc_location=None):
        """ Init the device with the entry point"""
        self.host = host
        self.nickname = nickname
        self.ircc_url = ircc_location
        self.actionlist_url = None
        self.control_url = None
        self.av_transport_url = None
        self.app_url = None

        self.app_port = app_port

        self.actions = {}
        self.headers = {}
        self.commands = {}
        self.apps = {}

        self.pin = None
        self.name = None
        self.cookies = None
        self.mac = None
        self.authenticated = False

        if self.ircc_url == None:
            self.ircc_url = "http://{0}:{1}/Ircc.xml".format(host, port)

        self.dmr_port = dmr_port

        self.dmr_url = "http://{0}:{1}/dmr.xml".format(
            self.host, self.dmr_port)
        self.app_url = "http://{0}:{1}".format(self.host, self.app_port)

        if len(self.actions) == 0 and self.pin is not None:
            self.update_service_urls()
            
    @staticmethod
    def discover():
        """
        Discover all available devices.
        """
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover("urn:schemas-sony-com:service:headersIRCC:1"):
            host = device.location.split(":")[1].split("//")[1]
            devices.append(SonyDevice(host, device.location))

        return devices

    @staticmethod
    def load_from_json(data):
        """ Loads a device configuration from a stored json """
        return jsonpickle.decode(data)

    def save_to_json(self):
        
        return jsonpickle.dumps(self)

    def create_json_v4(self, method, params=None):
        """ Create json data which will be send via post for the V4 api"""
        if params is not None:
            ret = json.dumps({"method": method, "params": [
                             params], "id": 1, "version": "1.0"})
        else:
            ret = json.dumps({"method": method, "params": [],
                              "id": 1, "version": "1.0"})
        return ret

    def wakeonlan(self):
        if self.mac is not None:
            addr_byte = self.mac.split('-')
            hw_addr = struct.pack('BBBBBB', int(addr_byte[0], 16),
                                  int(addr_byte[1], 16),
                                  int(addr_byte[2], 16),
                                  int(addr_byte[3], 16),
                                  int(addr_byte[4], 16),
                                  int(addr_byte[5], 16))
            msg = b'\xff' * 6 + hw_addr * 16
            socket_instance = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            socket_instance.setsockopt(
                socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            socket_instance.sendto(msg, ('<broadcast>', 9))
            socket_instance.close()

    def update_service_urls(self):
        """ Initalizes the device by reading the necessary resources from it """

        lirc_url = urllib.parse.urlparse(self.ircc_url)
        response = self.send_http(self.ircc_url, method=HttpMethod.GET)
        if response is None:
            return
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
        if response is not None:
            raw_data = response.text
            xml_data = xml.etree.ElementTree.fromstring(raw_data)
            for element in xml_data.findall("action"):
                action = XmlApiObject(element.attrib)
                self.actions[action.name] = action
                
                # some data has to overwritten for the registration to work properly
                if action.name == "register":
                    if action.mode < 4:
                        # the authenication later on is based on the device id and the mac
                        action.url = "{0}?name={1}&registrationType=initial&deviceId={1}".format(
                        action.url, urllib.parse.quote(self.nickname))
                        if action.mode == 3:
                            action.url = action.url + "&wolSupport=true"
                    elif action.mode == 4:
                        pass
                        # overwrite urls for api version 4 to be consistent later.
                        # todo check if this is necessary
                        # if self.actions["register"].mode == 4:
                        #    self.actions["getRemoteCommandList"].url = "http://{0}/sony/system".format(
                        #        lirc_url.netloc.split(":")[0])
        
        # make sure we are authenticated before
        self.recreate_authentication()
        
        if services is not None:
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

        # get systeminformation
        response = self.send_http(
            self.get_action("getSystemInformation").url, method=HttpMethod.GET)

        if response is not None:
            raw_data = response.text
            xml_data = xml.etree.ElementTree.fromstring(raw_data)
            for element in xml_data.findall("supportFunction"):
                for function in element.findall("function"):
                    if function.attrib["name"] == "WOL":
                        self.mac = function.find("functionItem").attrib["value"]

        # get control data for sending commands
        response = self.send_http(self.dmr_url, method=HttpMethod.GET)
        if response is not None:
            raw_data = response.text
            xml_data = xml.etree.ElementTree.fromstring(raw_data)
            for device in xml_data.findall("{0}device".format(urn_upnp_device)):
                serviceList = device.find("{0}serviceList".format(urn_upnp_device))
                for service in serviceList:
                    service_id = service.find(
                        "{0}serviceId".format(urn_upnp_device))
                    if "urn:upnp-org:serviceId:AVTransport" not in service_id.text:
                        continue
                    transport_location = service.find(
                        "{0}controlURL".format(urn_upnp_device)).text
                    self.av_transport_url = "{0}://{1}:{2}{3}".format(
                        lirc_url.scheme, lirc_url.netloc.split(":")[0], self.dmr_port, transport_location)

        if len(self.commands) > 0:
            self.update_commands()
            self.update_applist()

    def update_commands(self):
        
        # needs to be registred to do that 
        if self.pin is None:
            return

        url = self.get_action("getRemoteCommandList").url
        if self.get_action("register").mode < 4:
            response = self.send_http(url, method=HttpMethod.GET)
            if response is not None:
                xml_data = xml.etree.ElementTree.fromstring(response.text)

                for command in xml_data.findall("command"):
                    name = command.get("name")
                    self.commands[name] = XmlApiObject(command.attrib)
        else:
            response = self.send_http(
                url, method=HttpMethod.POST, data=self.create_json_v4("getRemoteControllerInfo"))
            if response is not None:
                json = response.json()
                if not json.get('error'):
                    # todo this does not fit 100% with the structure of this lib.
                    # see github issue#2
                    self.commands = json.get('result')[1]
                else:
                    _LOGGER.error("JSON request error: " +
                                json.dumps(json, indent=4))

    def update_applist(self, log_errors=True):
        url = self.app_url + "/appslist"
        response = self.send_http(url, method=HttpMethod.GET)
        if response is not None:
            xml_data = xml.etree.ElementTree.fromstring(response.text)
            apps = xml_data.findall(".//app")
            for app in apps:
                name = app.find("name").text
                id = app.find("id").text
                data = XmlApiObject(None)
                data.name = name
                data.id = id
                self.apps[name] = data

    def recreate_authentication(self):
        """
        The default cookie is for URL/sony. For some commands we need it for the root path.
        Only for api v4
        """

        if self.pin == None:
            return

        # todo fix cookies
        cookies = None
        #cookies = requests.cookies.RequestsCookieJar()
        #cookies.set("auth", self.cookies.get("auth"))
        
        username = ''
        base64string = base64.encodebytes(('%s:%s' % (username, self.pin)).encode()) \
            .decode().replace('\n', '')
        
        registration_action = self.get_action("register")

        self.headers['Authorization'] = "Basic %s" % base64string
        if registration_action.mode == 3:
            self.headers['X-CERS-DEVICE-ID'] = self.nickname
        elif registration_action.mode == 4:
            self.headers['Connection'] = "keep-alive"

        return cookies

    def register(self):
        """
        Register at the api.50001
        :param str name: The name which will be displayed in the UI of the device. Make sure this name does not exist yet
        For this the device must be put in registration mode.
        The tested sd5500 has no separte mode but allows registration in the overview "
        """
        registrataion_result = AuthenicationResult.ERROR
        registration_action = registration_action = self.get_action("register")

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
                    "params": [{"clientid": self.nickname,
                                "nickname": self.nickname,
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
                    self.cookies = response.cookies
                    registrataion_result = AuthenicationResult.SUCCESS

        else:
            raise ValueError(
                "Regisration mode {0} is not supported".format(registration_action.mode))

        return registrataion_result

    def send_authentication(self, pin):
        
        registration_action = self.get_action("register")

        # they do not need a pin
        if registration_action.mode < 3:
            return True

        self.pin = pin
        self.recreate_authentication()

        if registration_action.mode == 3:
            try:
                self.send_http(
                    self.get_action("register").url, method=HttpMethod.GET, raise_errors=True)
            except:
                return False
            else:
                self.pin = pin
                return True
            return False

        elif registration_action.mode == 4:
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
                response = self.send_http(self.get_action("register").url, method=HttpMethod.post,
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

    def send_http(self, url, method, data=None, headers=None, log_errors=True, raise_errors=False):
        """ Send request command via HTTP json to Sony Bravia."""

        if headers is None:
            headers = self.headers

        if url is None:
            return

        _LOGGER.debug("Calling http url {0} method {1}".format(url, str(method)))

        try:
            params = ""
            if data is not None:
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

    def post_soap_request(self, url, params, action):
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
        response = self.send_http(url, method=HttpMethod.POST,headers=headers, data=data)
        if response is not None:
            return response.content.decode("utf-8")

    def send_req_ircc(self, params, log_errors=True):
        """Send an IRCC command via HTTP to Sony Bravia."""

        data = "<u:X_SendIRCC xmlns:u=\"urn:schemas-sony-com:service:IRCC:1\">" +\
            "<IRCCCode>" + params + "</IRCCCode>" +\
            "</u:X_SendIRCC>"
        action = "urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"

        content = self.post_soap_request(
            url=self.control_url, params=data, action=action)
        return content

    def get_playing_status(self):
        data = '<m:GetTransportInfo xmlns:m="urn:schemas-upnp-org:service:AVTransport:1">' + \
                '<InstanceID>0</InstanceID>' + \
                '</m:GetTransportInfo>'

        action = "urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"

        content = self.post_soap_request(
            url=self.av_transport_url, params=data, action=action)
        if None is content:
            return "OFF"
        response = xml.etree.ElementTree.fromstring(content)
        state = response.find(".//CurrentTransportState").text
        return state

    def get_power_status(self):
        url = self.actionlist_url
        try:
            response = self.send_http(url, HttpMethod.GET,
                           log_errors=False, raise_errors=True)
        except Exception as ex:
            _LOGGER.debug(ex)
            return False
        return True

    # def get_source(self, source):
    #     pass

    def start_app(self, app_name, log_errors=True):
        """Start an app by name"""
        # sometimes device does not start app if already running one
        self.home()
        url = "{0}/apps/{1}".format(self.app_url, self.apps[app_name].id)
        data = "LOCATION: {0}/run".format(url)
        self.send_http(url, HttpMethod.POST, data=data)
        pass

    def send_command(self, name):
        if len(self.commands) == 0:
            self.update_commands()

        self.send_req_ircc(self.commands[name].value)

    def get_action(self, name):
        if not name in self.actions and len(self.actions) == 0: 
            self.update_service_urls()
            if not name in self.actions and len(self.actions) == 0:
                raise ValueError('Failed to read action list from device.')

        return self.actions[name]

    def power(self, on):
        if (on):
            self.wakeonlan()
            if not self.get_power_status():
                self.send_command('Power')
        else:
            self.send_command('Power')

        # Try using the power on command incase the WOL doesn't work
        

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
