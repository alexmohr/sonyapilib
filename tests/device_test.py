import os.path
import sys
import unittest
from inspect import getsourcefile
from unittest import mock

from requests import HTTPError

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
GET_REMOTE_COMMAND_LIST_URL = 'http://192.168.240.4:50002/getRemoteCommandList'
REGISTRATION_URL_LEGACY = 'http://192.168.240.4:50002/register'
REGISTRATION_URL_V4 = 'http://192.168.178.23/sony/accessControl'
REGISTRATION_URL_V4_FAIL = 'http://192.168.178.22/sony/accessControl'
REGISTRATION_URL_V4_FAIL_401 = 'http://192.168.178.25/sony/accessControl'
REGISTRATION_URL_V3_FAIL_401 = 'http://192.168.240.7:50002/register'
APP_LIST_URL = 'http://test:50202/appslist'
SOAP_URL = 'http://test/soap'
GET_REMOTE_CONTROLLER_INFO_URL = "http://test/getRemoteControllerInfo"

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


class MockResponse:
    class MockResponseJson:
        def __init__(self, data):
            self.data = data
        
        def get(self, key):
            if key in self.data:
                return self.data[key]
            return None

    def __init__(self, json_data, status_code, text=None, cookies=None):
        self.json_obj = self.MockResponseJson(json_data)
        self.status_code = status_code
        self.text = text
        self.cookies = cookies
        if text:
            self.content = text.encode()

    def json(self):
        return self.json_obj

    def get(self):
        pass

    def raise_for_status(self):
        if self.status_code == 200:
            return
        error = HTTPError()
        error.response = self
        raise error


def mocked_requests_post(*args, **kwargs):
    url = args[0]
    print("POST for URL: {}".format(url))
    if url == REGISTRATION_URL_V4:
            return MockResponse({}, 200)
    elif url == REGISTRATION_URL_V4_FAIL:
        return MockResponse({"error": 402}, 200)
    elif url == REGISTRATION_URL_V4_FAIL_401:
        MockResponse(None, 401).raise_for_status()
    elif url == SOAP_URL:
        return MockResponse({}, 200, "data")


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
    elif url == APP_LIST_URL:
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
        device._init_device()
        self.assertEqual(mock_update_service_url.call_count, 1)
        self.assertEqual(mock_recreate_auth.call_count, 0)
        self.assertEqual(mock_update_command.call_count, 0)
        self.assertEqual(mock_update_applist.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice._update_service_urls', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._recreate_authentication', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_commands', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_applist', side_effect=mock_nothing)
    def test_init_device_with_pin(self, mock_update_applist, mock_update_command,
                                  mock_recreate_auth, mock_update_service_url):
        device = self.create_device()
        device.pin = 1234
        device._init_device()
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

    def test_update_service_urls_v4(self):
        # todo
        pass

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
            device.actions["getRemoteCommandList"].url, 'http://192.168.178.23/sony/system')

    def test_parse_ircc_error(self):
        device = self.create_device()
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

    def prepare_test_command_list(self):
        device = self.create_device()
        data = XmlApiObject({})
        data.url = GET_REMOTE_COMMAND_LIST_URL
        device.actions["getRemoteCommandList"] = data
        return device

    def test_parse_command_list_error(self):
        device = self.prepare_test_command_list()
        device._parse_command_list()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_command_list(self, mock_get):
        device = self.prepare_test_command_list()
        device._parse_command_list()
        self.assertEqual(len(device.commands), 48)

    @mock.patch('sonyapilib.device.SonyDevice._parse_command_list', side_effect=mock_nothing)
    def test_update_commands_no_pin(self, mock_parse_cmd_list):
        device = self.create_device()
        device._update_commands()
        self.assertEqual(mock_parse_cmd_list.call_count, 0)

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
        device.actions["getRemoteControllerInfo"] = action
        device._update_commands()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_update_applist(self, mock_get):
        device = self.create_device()
        app_list = [
            "Video Explorer", "Music Explorer", "Video Player", "Music Player",
            "PlayStation Video", "Amazon Prime Video", "Netflix", "Rakuten TV", 
            "Tagesschau", "Functions with Gracenote ended", "watchmi Themenkanäle", 
            "Netzkino", "MUBI", "WWE Network", "DW for Smart TV", "YouTube",
             "uStudio", "Meteonews TV", "Digital Concert Hall", "Activate Enhanced Features"
        ]

        device._update_applist()
        for app in device.apps:
            self.assertTrue(app in app_list)
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
        self.verify_cookies(device.cookies)

    def test_recreate_authentication_v4_psk(self):
        # todo implement psk
        pass

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_no_auth(self, mocked_get):
        versions = [1, 2]
        for version in versions:
            result = self.register_with_version(version)
            self.assertEqual(result[0], AuthenticationResult.SUCCESS)

    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_not_supported(self, mocked_get, mocked_init_device):
        with self.assertRaises(ValueError):
            self.register_with_version(5)
        self.assertEqual(mocked_init_device.call_count, 0)

    def verify_register_fail(self, version, auth_result, mocked_init_device, url=None):
        result = self.register_with_version(version, url)
        self.assertEqual(result[0], auth_result)
        self.assertEqual(mocked_init_device.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    def test_register_fail_http_timeout(self, mocked_init_device):
        versions = [1, 2, 3, 4]
        for version in versions:
            self.verify_register_fail(version, AuthenticationResult.ERROR, mocked_init_device)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    def test_register_fail_pin_needed(self, mocked_init_device, mock_request_get_401, mock_request_post_401):
        self.verify_register_fail(3, AuthenticationResult.PIN_NEEDED, mocked_init_device, REGISTRATION_URL_V3_FAIL_401)
        self.verify_register_fail(4, AuthenticationResult.PIN_NEEDED, mocked_init_device, REGISTRATION_URL_V4_FAIL_401)

    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_success_v3(self, mocked_requests_get, mocked_init_device):
        result = self.register_with_version(3)
        self.assertEqual(result[0], AuthenticationResult.SUCCESS)
        self.assertEqual(mocked_init_device.call_count, 1)

    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_register_no_json_v4(self, mocked_requests_post, mocked_init_device):
        result = self.register_with_version(4, REGISTRATION_URL_V4_FAIL)
        self.assertEqual(result[0], AuthenticationResult.ERROR)
        self.assertEqual(mocked_init_device.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_register_success_v4(self, mocked_requests_post, mocked_init_device):
        result = self.register_with_version(4, REGISTRATION_URL_V4)
        self.assertEqual(result[0], AuthenticationResult.SUCCESS)
        self.assertEqual(mocked_init_device.call_count, 1)
        self.verify_cookies(result[1].cookies)

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

    @mock.patch('sonyapilib.device.SonyDevice._init_device', side_effect=mock_nothing)
    def test_get_action(self, mock_init_device):
        device = self.create_device()
        action = XmlApiObject({})
        action.name = "test"
        with self.assertRaises(ValueError):
            device._get_action(action.name)
        self.assertEqual(mock_init_device.call_count, 1)
        device.actions[action.name] = action
        self.assertEqual(device._get_action(action.name), action)

    @staticmethod
    def create_device():
        sonyapilib.device.TIMEOUT = 0.1
        return SonyDevice("test", "test")

    def verify_device_dmr(self, device):
        self.assertEqual(device.av_transport_url,
                         'http://test:52323/upnp/control/AVTransport')

    @staticmethod
    def verify_cookies(device):
        pass  # todo implement cookie verification


if __name__ == '__main__':
    unittest.main()