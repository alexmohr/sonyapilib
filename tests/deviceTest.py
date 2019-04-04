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
from sonyapilib.device import SonyDevice, XmlApiObject
from sonyapilib.ssdp import SSDPResponse
sys.path.pop(0)


ACTION_LIST_URL = 'http://192.168.240.4:50002/actionList'
DMR_URL = 'http://test:52323/dmr.xml'
IRCC_URL = 'http://test:50001/Ircc.xml'
SYSTEM_INFORMATION_URL = 'http://192.168.240.4:50002/getSystemInformation'
GET_REMOTE_COMMAND_LIST_URL = 'http://192.168.240.4:50002/getRemoteCommandList'

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
    print(url)
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
        self.assertEquals(mock_update_service_url.call_count, 1)
        self.assertEquals(mock_recreate_auth.call_count, 0)
        self.assertEquals(mock_update_command.call_count, 0)
        self.assertEquals(mock_update_applist.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice._update_service_urls', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._recreate_authentication', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_commands', side_effect=mock_nothing)
    @mock.patch('sonyapilib.device.SonyDevice._update_applist', side_effect=mock_nothing)
    def test_init_device_with_pin(self, mock_update_applist, mock_update_command,
                                  mock_recreate_auth, mock_update_service_url):
        device = self.create_device()
        device.pin = 1234
        device._init_device()
        self.assertEquals(mock_update_service_url.call_count, 1)
        self.assertEquals(mock_recreate_auth.call_count, 1)
        self.assertEquals(mock_update_command.call_count, 1)
        self.assertEquals(mock_update_applist.call_count, 1)

    @mock.patch('sonyapilib.ssdp.SSDPDiscovery.discover', side_effect=mock_discovery)
    def test_discovery(self, mock_discover):
        devices = SonyDevice.discover()
        self.assertEquals(len(devices), 1)
        self.assertEquals(devices[0].host, "test")

    def test_save_load_from_json(self):
        device = self.create_device()
        jdata = device.save_to_json()
        restored_device = SonyDevice.load_from_json(jdata)
        jdata_restored = restored_device.save_to_json()
        self.assertEquals(jdata, jdata_restored)

    def test_update_service_urls_error_response(self):
        device = self.create_device()
        device._update_service_urls()

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('sonyapilib.device.SonyDevice._parse_ircc', side_effect=mock_error)
    def test_update_service_urls_error_processing(self, mock_error, mocked_requests_get):
        device = self.create_device()
        device._update_service_urls()
        self.assertEquals(mock_error.call_count, 1)

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
        self.assertEquals(mock_ircc.call_count, 1)
        self.assertEquals(mock_action_list.call_count, 1)
        self.assertEquals(mock_system_information.call_count, 1)
        
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

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_command_list(self, mock_get):
        device = self.create_device()
        data = XmlApiObject({})
        data.url = GET_REMOTE_COMMAND_LIST_URL
        device.actions["getRemoteCommandList"] = data
        device._parse_command_list()
        self.assertEqual(len(device.commands), 48)

    @mock.patch('sonyapilib.device.SonyDevice._parse_command_list', side_effect=mock_nothing)
    def test_update_commands_no_pin(self, mock_parse_cmd_list):
        device = self.create_device()
        device._update_commands()
        self.assertEquals(mock_parse_cmd_list.call_count, 0)

    @mock.patch('sonyapilib.device.SonyDevice._parse_command_list', side_effect=mock_nothing)
    def test_update_commands_v3(self, mock_parse_cmd_list):
        device = self.create_device()
        device.pin = 1234
        device._update_commands()
        self.assertEquals(mock_parse_cmd_list.call_count, 1)

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_update_commands_v4(self, mock_get):
        pass

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_update_app_list(self, mock_get):
        pass

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_recreate_authentication(self, mock_get):
        pass

    def create_device(self):
        return SonyDevice("test", "test")

    def verify_device_dmr(self, device):
        self.assertEqual(device.av_transport_url,
                         'http://test:52323/upnp/control/AVTransport')


if __name__ == '__main__':
    unittest.main()
