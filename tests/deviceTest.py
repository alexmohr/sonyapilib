import unittest
from unittest import mock
import os.path

from inspect import getsourcefile
import os.path as path
import sys
import requests


current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
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
APP_LIST_URL = 'http://test:50202/appslist'


def read_file(file_name):
    """ Reads a file from disk """
    __location__ = os.path.realpath(os.path.join(
        os.getcwd(), os.path.dirname(__file__)))
    with open(os.path.join(__location__, file_name)) as f:
        return f.read()


def mock_error(*args, **kwargs):
    raise Exception()


def mock_nothing(*args, **kwargs):
    pass


def mock_discovery(*args, **kwargs):
    if args[0] == "urn:schemas-sony-com:service:IRCC:1":
        resp = SSDPResponse(None)
        resp.location = IRCC_URL
        return [resp]
    return None


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code, text=None):
            self.json_data = json_data
            self.status_code = status_code
            self.text = text

        def json(self):
            return self.json_data

        def raise_for_status(self):
            pass
    url = args[0]
    print("Requesting URL: {}".format(url))
    if url == DMR_URL:
        return MockResponse(None, 200, read_file("xml/dmr_v3.xml"))
    elif url == IRCC_URL:
        return MockResponse(None, 200, read_file("xml/ircc.xml"))
    elif url == ACTION_LIST_URL:
        return MockResponse(None, 200, read_file("xml/actionlist.xml"))
    elif url == SYSTEM_INFORMATION_URL:
        return MockResponse(None, 200, read_file("xml/getSysteminformation.xml"))
    elif url == GET_REMOTE_COMMAND_LIST_URL:
        return MockResponse(None, 200, read_file("xml/getRemoteCommandList.xml"))
    elif url == APP_LIST_URL:
        return MockResponse(None, 200, read_file("xml/appsList.xml"))
    # elif url == 'http://someotherurl.com/anothertest.json':
    #    return MockResponse({"key2": "value2"}, 200)

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
        content = read_file("xml/dmr_v3.xml")
        device = self.create_device()
        device._parse_dmr(content)
        self.verify_device_dmr(device)
        self.assertFalse(device.is_v4)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_dmr_v4(self, mock_get):
        content = read_file("xml/dmr_v4.xml")
        device = self.create_device()
        device._parse_dmr(content)
        self.verify_device_dmr(device)
        self.assertTrue(device.is_v4)
        self.assertEqual(
            device.actions["register"].url, 'http://192.168.178.23/sony/accessControl')
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
            device.actionlist_url, 'http://192.168.240.4:50002/actionList')
        self.assertEqual(
            device.control_url, 'http://test:50001/upnp/control/IRCC')

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
        pass

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


    def test_recreate_authentication_v3(self):
        device = self.create_device()
        device.pin = 1234
        self.add_register_to_device(device, 3)
        device._recreate_authentication()

        self.assertEqual(device.headers["Authorization"], "Basic OjEyMzQ=")
        self.assertEqual(
            device.headers["X-CERS-DEVICE-ID"], device.get_device_id())

    def test_recreate_authentication_v4(self):
        device = self.create_device()
        device.pin = 1234
        self.add_register_to_device(device, 4)
        device._recreate_authentication()

        self.assertEqual(device.headers["Authorization"], "Basic OjEyMzQ=")
        self.assertEqual(device.headers["Connection"], "keep-alive")

    def test_recreate_authentication_v4_psk(self):
        # todo implement psk
        pass

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_register_v1(self, mocked_get):
        device = self.create_device()
        self.add_register_to_device(device, 1)
        result = device.register()
        self.assertEqual(result, AuthenticationResult.SUCCESS)

    def add_register_to_device(self, device, mode):
        register_action = XmlApiObject({})
        register_action.mode = mode
        if mode < 4:
            register_action.url = REGISTRATION_URL_LEGACY
        else:
            register_action.url = REGISTRATION_URL_V4
        device.actions["register"] = register_action

    def create_device(self):
        sonyapilib.device.TIMEOUT = 1
        return SonyDevice("test", "test")

    def verify_device_dmr(self, device):
        self.assertEqual(device.av_transport_url,
                         'http://test:52323/upnp/control/AVTransport')


if __name__ == '__main__':
    unittest.main()
