import os.path
import sys
import unittest
from inspect import getsourcefile
from unittest import mock
from urllib.parse import (
    urljoin
)

import jsonpickle
from requests import HTTPError, URLRequired, RequestException

from tests.testutil import read_file

current_dir = os.path.dirname(os.path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(os.path.sep)])
# cannot be imported at a different position because path modification
# is necessary to load the local library.
# otherwise it must be installed after every change
import sonyapilib.device  # import  to change timeout
from sonyapilib.ssdp import SSDPResponse
from sonyapilib.device import SonyDevice, XmlApiObject, AuthenticationResult
sys.path.pop(0)


ACTION_LIST_URL = 'http://192.168.240.4:50002/actionList'
DMR_URL = 'http://test:52323/dmr.xml'
IRCC_URL = 'http://test:50001/Ircc.xml'
SYSTEM_INFORMATION_URL = 'http://192.168.240.4:50002/getSystemInformation'
SYSTEM_INFORMATION_URL_V4 = 'http://test/sony/system'
GET_REMOTE_COMMAND_LIST_URL = 'http://192.168.240.4:50002/getRemoteCommandList'
REGISTRATION_URL_LEGACY = 'http://192.168.240.4:50002/register'
REGISTRATION_URL_V4 = 'http://192.168.170.23/sony/accessControl'
REGISTRATION_URL_V4_FAIL = 'http://192.168.170.22/sony/accessControl'
REGISTRATION_URL_V4_FAIL_401 = 'http://192.168.170.25/sony/accessControl'
REGISTRATION_URL_V3_FAIL_401 = 'http://192.168.240.7:50002/register'
COMMAND_LIST_V4 = 'http://192.168.240.4:50002/getRemoteCommandList'
APP_LIST_URL = 'http://test:50202/appslist'
APP_LIST_URL_V4 = 'http://test/DIAL/sony/applist'
APP_START_URL_LEGACY = 'http://test:50202/apps/'
APP_START_URL = 'http://test/DIAL/apps/'
SOAP_URL = 'http://test/soap'
GET_REMOTE_CONTROLLER_INFO_URL = "http://test/getRemoteControllerInfo"
BASE_URL = 'http://test/sony'
AV_TRANSPORT_URL = 'http://test:52323/upnp/control/AVTransport'
AV_TRANSPORT_URL_NO_MEDIA = 'http://test2:52323/upnp/control/AVTransport'


def mock_request_error(*args, **kwargs):
    raise HTTPError()


def mock_error(*args, **kwargs):
    raise Exception()


def mock_nothing(*args, **kwargs):
    pass


def mock_register_success(*args, **kwargs):
    return AuthenticationResult.SUCCESS


def mock_discovery(*args, **kwargs):
    if args[0] == "urn:schemas-sony-com:service:IRCC:1":
        resp = SSDPResponse(None)
        resp.location = IRCC_URL
        return [resp]
    return None


class MockResponseJson:
    def __init__(self, data):
        self.data = data

    def get(self, key):
        if key in self.data:
            return self.data[key]
        return None


class MockResponse:
    def __init__(self, json_data, status_code, text=None, cookies=None):
        self.json_obj = MockResponseJson(json_data)
        self.status_code = status_code
        self.text = text
        self.cookies = cookies
        if text:
            self.content = text.encode()

    def json(self):
        return self.json_obj

    def raise_for_status(self):
        if self.status_code == 200:
            return
        error = HTTPError()
        error.response = self
        raise error


def mocked_requests_post(*args, **kwargs):
    url = args[0]
    print("POST for URL: {}".format(url))
    if not url:
        raise URLRequired()
    elif url == REGISTRATION_URL_V4:
            return MockResponse({}, 200)
    elif url == REGISTRATION_URL_V4_FAIL:
        return MockResponse({"error": 402}, 200)
    elif url == REGISTRATION_URL_V4_FAIL_401:
        MockResponse(None, 401).raise_for_status()
    elif url == SOAP_URL:
        return MockResponse({}, 200, "data")
    elif url == urljoin(BASE_URL, 'system'):
        result = MockResponseJson({"status": "on"})
        return MockResponse({"result": [result]}, 200)
    elif APP_START_URL_LEGACY in url:
        return MockResponse(None, 200)
    elif APP_START_URL in url:
        return MockResponse(None, 200)
    elif url == AV_TRANSPORT_URL:
        return MockResponse(None, 200, read_file('data/playing_status_legacy_playing.xml'))
    elif url == AV_TRANSPORT_URL_NO_MEDIA:
        return MockResponse(None, 200, read_file('data/playing_status_legacy_no_media.xml'))
    elif url == COMMAND_LIST_V4:
        json_data = jsonpickle.decode(read_file('data/commandList.json'))
        return MockResponse(json_data, 200, "")
    elif url == SYSTEM_INFORMATION_URL_V4:
        json_data = jsonpickle.decode(read_file('data/systemInformation.json'))
        return MockResponse(json_data, 200, "")
    else:
        raise ValueError("Unknown url requested: {}".format(url))


def mocked_requests_get(*args, **kwargs):
    url = args[0]
    print("GET for URL: {}".format(url))
    if url == DMR_URL:
        return MockResponse(None, 200, read_file("data/dmr_v3.xml"))
    elif url == IRCC_URL:
        return MockResponse(None, 200, read_file("data/ircc.xml"))
    elif url == ACTION_LIST_URL:
        return MockResponse(None, 200, read_file("data/actionlist.xml"))
    elif url == SYSTEM_INFORMATION_URL:
        return MockResponse(None, 200, read_file("data/getSysteminformation.xml"))
    elif url == GET_REMOTE_COMMAND_LIST_URL:
        return MockResponse(None, 200, read_file("data/getRemoteCommandList.xml"))
    elif url == APP_LIST_URL or url == APP_LIST_URL_V4:
        return MockResponse(None, 200, read_file("data/appsList.xml"))
    elif url == REGISTRATION_URL_LEGACY: 
        return MockResponse({}, 200)
    elif url == REGISTRATION_URL_V3_FAIL_401:
        MockResponse(None, 401).raise_for_status()
    elif url == GET_REMOTE_CONTROLLER_INFO_URL:
        return MockResponse(None, 200)
    else:
        raise ValueError("Unknown url requested: {}".format(url))

    return MockResponse(None, 404)


class SonyDeviceTest(unittest.TestCase):

    @mock.patch('sonyapilib.device.SonyDevice._update_service_urls', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._recreate_authentication', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_commands', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_applist', side_effect=mock_nothing)
    def test_init_device_no_pin(self, mock_update_applist, mock_update_command,
                                mock_recreate_auth, mock_update_service_url):
        device = self.create_device()
        device.init_device()
        self.assertEqual(mock_update_service_url.call_count, 1)
        self.assertEqual(mock_recreate_auth.call_count, 0)
        self.assertEqual(mock_update_command.call_count, 1)
        self.assertEqual(mock_update_applist.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice._update_service_urls', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._recreate_authentication', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_commands', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_applist', side_effect=mock_nothing)
    def test_init_device_with_pin(self, mock_update_applist, mock_update_command,
                                  mock_recreate_auth, mock_update_service_url):
        device = self.create_device()
        device.pin = 1234
        device.init_device()
        self.assertEqual(mock_update_service_url.call_count, 1)
        self.assertEqual(mock_recreate_auth.call_count, 1)
        self.assertEqual(mock_update_command.call_count, 1)
        self.assertEqual(mock_update_applist.call_count, 1)

    @mock.patch('sonyapilib.ssdp.SSDPDiscovery.discover', side_effect=mock_discovery)
    def test_discovery(self, mock_discover):
        devices = SonyDevice.discover()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].host, "test")

    def test_save_load_from_json(self):
        device = self.create_device()
        jdata = device.save_to_json()
        restored_device = SonyDevice.load_from_json(jdata)
        jdata_restored = restored_device.save_to_json()
        self.assertEqual(jdata, jdata_restored)
        self.assertEqual(restored_device.uuid, device.uuid)

    def test_update_service_urls_error_response(self):
        device = self.create_device()
        device._update_service_urls()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('sonyapilib.device.SonyDevice._parse_ircc', side_effect=mock_error)
    def test_update_service_urls_error_processing(self, mock_error, mocked_requests_get):
        device = self.create_device()
        device._update_service_urls()
        self.assertEqual(mock_error.call_count, 1)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('sonyapilib.device.SonyDevice._parse_ircc', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._parse_action_list', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._parse_system_information', side_effect=mock_nothing)
    def test_update_service_urls_v3(self, mock_ircc, mock_action_list,
                                    mock_system_information, mocked_requests_get):
        device = self.create_device()
        device.pin = 1234
        device._update_service_urls()
        self.assertEqual(mock_ircc.call_count, 1)
        self.assertEqual(mock_action_list.call_count, 1)
        self.assertEqual(mock_system_information.call_count, 1)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_update_service_urls_v4(self, mocked_requests_post, mocked_requests_get):
        device = self.create_device()
        device.pin = 1234
        device.api_version = 4
        device._update_service_urls()
        self.assertEqual(device.mac, "10:08:B1:31:81:B5")

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_dmr_v3(self, mock_get):
        content = read_file("data/dmr_v3.xml")
        device = self.create_device()
        device._parse_dmr(content)
        self.verify_device_dmr(device)
        self.assertLess(device.api_version, 4)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_dmr_v4(self, mock_get):
        content = read_file("data/dmr_v4.xml")
        device = self.create_device()
        device._parse_dmr(content)
        self.verify_device_dmr(device)
        self.assertGreater(device.api_version, 3)
        self.assertEqual(
            device.actions["register"].url, REGISTRATION_URL_V4)
        self.assertEqual(device.actions["register"].mode, 4)
        self.assertEqual(
            device.actions["getRemoteCommandList"].url, 'http://192.168.170.23/sony/system')

    def test_parse_ircc_error(self):
        device = self.create_device()
        with self.assertRaises(RequestException):
            device._parse_ircc()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_ircc(self, mock_get):
        device = self.create_device()
        device._parse_ircc()
        self.assertEqual(
            device.actionlist_url, ACTION_LIST_URL)
        self.assertEqual(
            device.control_url, 'http://test:50001/upnp/control/IRCC')

    def test_parse_action_list_error(self):
        # just make sure nothing crashes
        device = self.create_device()
        device.actionlist_url = ACTION_LIST_URL
        device._parse_action_list()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_action_list(self, mock_get):
        device = self.create_device()
        # must be set before prior methods are not called.
        device.actionlist_url = ACTION_LIST_URL
        device._parse_action_list()
        self.assertEqual(device.actions["register"].mode, 3)
        actions = ["getText",
                   "sendText",
                   "getContentInformation",
                   "getSystemInformation",
                   "getRemoteCommandList",
                   "getStatus",
                   "getHistoryList",
                   "getContentUrl",
                   "sendContentUrl"]
        base_url = "http://192.168.240.4:50002/"
        for action in actions:
            self.assertEqual(device.actions[action].url, base_url + action)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_system_information(self, mock_get):
        device = self.create_device()
        data = XmlApiObject({})
        data.url = SYSTEM_INFORMATION_URL
        device.actions["getSystemInformation"] = data
        device._parse_system_information()
        self.assertEqual(device.mac, "30-52-cb-cc-16-ee")

    def prepare_test_action_list(self):
        device = self.create_device()
        data = XmlApiObject({})
        data.url = GET_REMOTE_COMMAND_LIST_URL
        device.actions["getRemoteCommandList"] = data
        return device

    def test_parse_command_list_error(self):
        versions = [1, 2, 3, 4]
        for version in versions:
            device = self.prepare_test_action_list()
            device.api_version = version
            if version < 4:
                device._parse_command_list()
            else:
                device._parse_command_list_v4()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_parse_command_list(self, mock_get, mock_post):
        versions = [1, 2, 3, 4]
        for version in versions:
            device = self.prepare_test_action_list()
            device.version = version
            if version < 4:
                cmd_length = 48
                device._parse_command_list()
            else:
                cmd_length = 98
                device._parse_command_list_v4()
            self.assertTrue("Power" in device.commands)
            self.assertTrue("Left" in device.commands)
            self.assertTrue("Pause" in device.commands)
            self.assertTrue("Num3" in device.commands)
            self.assertEqual(len(device.commands), cmd_length)

    @mock.patch('sonyapilib.device.SonyDevice._parse_command_list', side_effect=mock_nothing)
    def test_update_commands_no_pin(self, mock_parse_cmd_list):
        device = self.create_device()
        device._update_commands()
        self.assertEqual(mock_parse_cmd_list.call_count, 1)

    @mock.patch('sonyapilib.device.SonyDevice._parse_command_list', side_effect=mock_nothing)
    def test_update_commands_v3(self, mock_parse_cmd_list):
        device = self.create_device()
        device.pin = 1234
        device._update_commands()
        self.assertEqual(mock_parse_cmd_list.call_count, 1)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_update_commands_v4(self, mock_get):
        device = self.create_device()
        device.pin = 1234
        device.api_version = 4
        action = XmlApiObject({})
        action.url = GET_REMOTE_CONTROLLER_INFO_URL
        device.actions["getRemoteCommandList"] = action
        device._update_commands()

    def start_app(self, device, app_name, mock_post, mock_send_command):
        versions = [1, 2, 3, 4]
        apps = {
            "Video Explorer": "com.sony.videoexplorer",
            "Music Explorer": "com.sony.musicexplorer",
            "Video Player": "com.sony.videoplayer",
            "Music Player": "com.sony.musicplayer",
            "PlayStation Video": "com.sony.videounlimited",
            "Amazon Prime Video": "com.sony.iptv.4976",
            "Netflix": "com.sony.iptv.type.NRDP",
            "Rakuten TV": "com.sony.iptv.3479",
            "Tagesschau": "com.sony.iptv.type.EU-TAGESSCHAU_6x3",
            "Functions with Gracenote ended": "com.sony.iptv.6317",
            "watchmi Themenkanäle": "com.sony.iptv.4766",
            "Netzkino": "com.sony.iptv.4742",
            "MUBI": "com.sony.iptv.5498",
            "WWE Network": "com.sony.iptv.4340",
            "DW for Smart TV": "com.sony.iptv.4968",
            "YouTube": "com.sony.iptv.type.ytleanback",
            "uStudio": "com.sony.iptv.4386",
            "Meteonews TV": "com.sony.iptv.3487",
            "Digital Concert Hall": "com.sony.iptv.type.WW-BERLINPHIL_NBIV",
            "Activate Enhanced Features": "com.sony.iptv.4834"
        }

        for version in versions:
            device.api_version = version
            device.start_app(app_name)

            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_send_command.call_count, 1)

            if version < 4:
                url = APP_START_URL_LEGACY + apps[app_name]
            else:
                url = APP_START_URL + apps[app_name]
            self.assertEqual(url, mock_post.call_args[0][0])
            mock_send_command.call_count = 0
            mock_post.call_count = 0
            mock_post.mock_calls.clear()

    @mock.patch('sonyapilib.device.SonyDevice._send_command', side_effect=mock_nothing)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_update_applist(self, mock_get, mock_post, mock_send_command):
        device = self.create_device()
        app_list = [
            "Video Explorer", "Music Explorer", "Video Player", "Music Player",
            "PlayStation Video", "Amazon Prime Video", "Netflix", "Rakuten TV",
            "Tagesschau", "Functions with Gracenote ended", "watchmi Themenkanäle",
            "Netzkino", "MUBI", "WWE Network", "DW for Smart TV", "YouTube",
             "uStudio", "Meteonews TV", "Digital Concert Hall", "Activate Enhanced Features"
        ]

        versions = [1, 2, 3, 4]
        for version in versions:
            device.api_version = version
            device._update_applist()
            for app in device.get_apps():
                self.assertTrue(app in app_list)
                self.start_app(device, app, mock_post, mock_send_command)
            self.assertEqual(len(device.apps), len(app_list))

    def test_recreate_authentication_no_auth(self):
        versions = [1, 2]
        for version in versions:
            device = self.create_device()
            self.add_register_to_device(device, version)
            device._recreate_authentication()
            self.assertEqual(len(device.headers), 0)

    def test_recreate_authentication_v3(self):
        device = self.create_device()
        device.pin = 1234
        self.add_register_to_device(device, 3)
        device._recreate_authentication()

        self.assertEqual(device.headers["Authorization"], "Basic OjEyMzQ=")
        self.assertEqual(device.headers["X-CERS-DEVICE-ID"], device.get_device_id())

    def test_recreate_authentication_v4(self):
        device = self.create_device()
        device.pin = 1234
        self.add_register_to_device(device, 4)
        device._recreate_authentication()

        self.assertEqual(device.headers["Authorization"], "Basic OjEyMzQ=")
        self.assertEqual(device.headers["Connection"], "keep-alive")
        self.verify_cookies(device)

    def test_recreate_authentication_v4_psk(self):
        device = SonyDevice("test", "test", "foobarPSK")
        device.pin = 1234
        self.add_register_to_device(device, 4)
        device._recreate_authentication()
        self.assertTrue(device.psk)
        self.assertEqual(device.headers["X-Auth-PSK"], device.psk)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_no_auth(self, mocked_get):
        versions = [1, 2]
        for version in versions:
            result = self.register_with_version(version)
            self.assertEqual(result[0], AuthenticationResult.SUCCESS)

    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_not_supported(self, mocked_get, mocked_init_device):
        with self.assertRaises(ValueError):
            self.register_with_version(5)
        self.assertEqual(mocked_init_device.call_count, 0)

    def verify_register_fail(self, version, auth_result, mocked_init_device, url=None):
        result = self.register_with_version(version, url)
        self.assertEqual(result[0], auth_result)
        self.assertEqual(mocked_init_device.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    def test_register_fail_http_timeout(self, mocked_init_device):
        versions = [1, 2, 3, 4]
        for version in versions:
            self.verify_register_fail(version, AuthenticationResult.ERROR, mocked_init_device)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    def test_register_fail_pin_needed(self, mocked_init_device, mock_request_get_401, mock_request_post_401):
        self.verify_register_fail(3, AuthenticationResult.PIN_NEEDED, mocked_init_device, REGISTRATION_URL_V3_FAIL_401)
        self.verify_register_fail(4, AuthenticationResult.PIN_NEEDED, mocked_init_device, REGISTRATION_URL_V4_FAIL_401)

    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_success_v3(self, mocked_requests_get, mocked_init_device):
        result = self.register_with_version(3)
        self.assertEqual(result[0], AuthenticationResult.SUCCESS)
        self.assertEqual(mocked_init_device.call_count, 1)

    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_register_no_json_v4(self, mocked_requests_post, mocked_init_device):
        result = self.register_with_version(4, REGISTRATION_URL_V4_FAIL)
        self.assertEqual(result[0], AuthenticationResult.ERROR)
        self.assertEqual(mocked_init_device.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_register_success_v4(self, mocked_requests_post, mocked_init_device):
        result = self.register_with_version(4, REGISTRATION_URL_V4)
        self.assertEqual(result[0], AuthenticationResult.SUCCESS)
        self.assertEqual(mocked_init_device.call_count, 1)

    @mock.patch('sonyapilib.device.SonyDevice.register', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._recreate_authentication', side_effect=mock_nothing)
    def test_send_authentication_no_auth(self, mock_register, mock_recreate_auth):
        versions = [[1, True], [2, True], [3, False], [4, False]]
        for version in versions:
            device = self.create_device()
            self.add_register_to_device(device, version[0])
            self.assertEqual(device.send_authentication(0), version[1])
            self.assertEqual(mock_register.call_count, 0)
            self.assertEqual(mock_recreate_auth.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice.register', side_effect=mock_register_success)
    @mock.patch('sonyapilib.device.SonyDevice._recreate_authentication', side_effect=mock_nothing)
    def test_send_authentication_with_auth(self, mock_register, mock_recreate_auth):
        versions = [3, 4]
        for version in versions:
            device = self.create_device()
            self.add_register_to_device(device, version)
            self.assertTrue(device.send_authentication(1234))
            self.assertEqual(mock_register.call_count, 1)
            self.assertEqual(mock_recreate_auth.call_count, 1)
            mock_register.call_count = 0
            mock_recreate_auth.call_count = 0

    @mock.patch('sonyapilib.device.SonyDevice._send_command', side_effect=mock_nothing)
    def test_commands(self, mock_send_command):
        device = self.create_device()
        methods = ["up", "confirm", "down", "right", "left", "home", "options", "returns", "num1", "num2", "num3",
                   "num4",
                   "num5", "num6", "num7", "num8", "num9", "num0", "display", "audio", "sub_title", "favorites",
                   "yellow",
                   "blue", "red", "green", "play", "stop", "pause", "rewind", "forward", "prev", "next", "replay",
                   "advance",
                   "angle", "top_menu", "pop_up_menu", "eject", "karaoke", "netflix", "mode_3d", "zoom_in", "zoom_out",
                   "browser_back", "browser_forward", "browser_bookmark_list", "list"]
        for method in methods:
            cmd_name = ''.join(x.capitalize() or '_' for x in method.split('_'))
            # method cannot be named return
            if method == "returns":
                cmd_name = "Return"
            elif method == "mode_3d":
                cmd_name = "Mode3D"

            getattr(device, method)()
            self.assertEqual(mock_send_command.call_count, 1)
            self.assertEqual(mock_send_command.mock_calls[0][1][0], cmd_name)
            mock_send_command.call_count = 0
            mock_send_command.mock_calls.clear()

    @staticmethod
    def add_register_to_device(device, mode):
        register_action = XmlApiObject({})
        register_action.mode = mode
        if mode < 4:
            register_action.url = REGISTRATION_URL_LEGACY
        else:
            register_action.url = REGISTRATION_URL_V4
        device.actions["register"] = register_action

    def register_with_version(self, version, reg_url=""):
        device = self.create_device()
        self.add_register_to_device(device, version)
        if reg_url:
            device.actions["register"].url = reg_url
        
        result = device.register()
        return [result, device]

    def test_post_soap_request_invalid(self):
        device = self.create_device()
        params = "foobar"
        self.assertFalse(device._post_soap_request(SOAP_URL, params, params))

    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_post_soap_request(self, mocked_requests_post):
        params = "foobar"
        data = """<?xml version='1.0' encoding='utf-8'?>
                    <SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                        SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                        <SOAP-ENV:Body>
                            {0}
                        </SOAP-ENV:Body>
                    </SOAP-ENV:Envelope>""".format("foobar")

        device = self.create_device()
        self.assertTrue(device._post_soap_request(SOAP_URL, params, params))
        mock_call = mocked_requests_post.mock_calls[0][2]
        headers = mock_call["headers"]
        self.assertEqual(headers['SOAPACTION'], '"{}"'.format(params))
        self.assertEqual(headers['Content-Type'], "text/xml")
        self.assertEqual(mock_call["data"], data)
        self.assertEqual(mocked_requests_post.call_count, 1)

    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    def test_get_action(self, mock_init_device):
        device = self.create_device()
        action = XmlApiObject({})
        action.name = "test"
        with self.assertRaises(ValueError):
            device._get_action(action.name)
        self.assertEqual(mock_init_device.call_count, 1)
        device.actions[action.name] = action
        self.assertEqual(device._get_action(action.name), action)

    @mock.patch('sonyapilib.device.SonyDevice._send_req_ircc', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice.init_device', side_effect=mock_nothing)
    def test_send_command_error(self, mock_init_device, mock_send_req_ircc):
        device = self.create_device()
        with self.assertRaises(ValueError):
            device._send_command("test")
        self.create_command_list(device)
        with self.assertRaises(ValueError):
            device._send_command("foo")
        device._send_command("test")
        self.assertEqual(mock_send_req_ircc.call_count, 1)

    @mock.patch('sonyapilib.device.SonyDevice._post_soap_request', side_effect=mock_nothing)
    def test_send_req_ircc(self, mock_post_soap_request):
        device = self.create_device()
        params = "foobar"
        data = """<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">
                    <IRCCCode>{0}</IRCCCode>
                  </u:X_SendIRCC>""".format(params)
        device._send_req_ircc(params)
        self.assertEqual(mock_post_soap_request.call_count, 1)
        self.assertEqual(mock_post_soap_request.call_args_list[0][1]['params'], data)

    def test_get_power_status_false(self):
        versions = [1, 2, 3, 4]
        device = self.create_device()
        for version in versions:
            device.api_version = version
            self.assertFalse(device.get_power_status())

    @mock.patch('requests.post', side_effect=mock_request_error)
    def test_get_power_status_error(self, mocked_request_error):
        device = self.create_device()
        device.api_version = 4
        self.assertFalse(device.get_power_status())

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_get_power_status_true(self, mocked_post, mocked_get):
        versions = [1, 2, 3, 4]
        device = self.create_device()
        device.actionlist_url = ACTION_LIST_URL
        device.base_url = BASE_URL
        for version in versions:
            device.api_version = version
            self.assertTrue(device.get_power_status())

    @mock.patch('sonyapilib.device.SonyDevice._send_command', side_effect=mock_nothing)
    def test_power_off(self, mock_send_command):
        device = self.create_device()
        device.power(False)
        self.assertEqual(mock_send_command.call_count, 1)
        self.assertEqual(mock_send_command.mock_calls[0][1][0], "Power")

    @mock.patch('sonyapilib.device.SonyDevice.get_power_status', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._send_command', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice.wakeonlan', side_effect=mock_nothing)
    def test_power_on(self, mock_wake_on_lan, mock_send_command, mock_get_power_status):
        device = self.create_device()
        device.power(True)
        self.assertEqual(mock_send_command.call_count, 1)
        self.assertEqual(mock_wake_on_lan.call_count, 1)
        self.assertEqual(mock_send_command.mock_calls[0][1][0], "Power")

    @mock.patch('wakeonlan.send_magic_packet', side_effect=mock_nothing())
    def test_wake_on_lan(self, mocked_wol):
        device = self.create_device()
        device.wakeonlan()
        self.assertEqual(mocked_wol.call_count, 0)
        device.mac = "foobar"
        device.wakeonlan()
        self.assertEqual(mocked_wol.call_count, 1)

    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_playing_status_no_media_legacy(self, mocked_requests_post):
        device = self.create_device()
        self.assertEqual("OFF", device.get_playing_status())

        device.av_transport_url = AV_TRANSPORT_URL_NO_MEDIA
        device.get_playing_status()

        device.av_transport_url = AV_TRANSPORT_URL
        self.assertEqual("PLAYING", device.get_playing_status())
        
    @staticmethod
    def create_command_list(device):
        command = XmlApiObject({})
        command.name = "test"
        device.commands[command.name] = command

    @staticmethod
    def create_device():
        sonyapilib.device.TIMEOUT = 0.1
        device = SonyDevice("test", "test")
        device.cookies = jsonpickle.decode(read_file("data/cookies.json"))
        return device

    def verify_device_dmr(self, device):
        self.assertEqual(device.av_transport_url, AV_TRANSPORT_URL)

    def verify_cookies(self, device):
        self.assertTrue(device.cookies is not None)


if __name__ == '__main__':
    unittest.main()
