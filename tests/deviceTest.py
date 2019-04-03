import unittest
from unittest import mock
import os.path

from inspect import getsourcefile
import os.path as path
import sys
import requests

current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
from sonyapilib.device import SonyDevice
sys.path.pop(0)

def read_file(file_name):
    """ Reads a file from disk """
    __location__ = os.path.realpath(os.path.join(
        os.getcwd(), os.path.dirname(__file__)))
    with open(os.path.join(__location__, file_name)) as f:
        return f.read()


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

    if args[0] == 'http://test:52323/dmr.xml':
        return MockResponse(None, 200, read_file("xml/dmr_v3.xml"))
    elif args[0] == 'http://someotherurl.com/anothertest.json':
        return MockResponse({"key2": "value2"}, 200)

    return MockResponse(None, 404)


class SonyDeviceTest(unittest.TestCase):

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
        self.assertEqual(device.actions["register"].url,
                         'http://192.168.178.23/sony/accessControl')
        self.assertEqual(device.actions["register"].mode, 4)
        self.assertEqual(device.actions["getRemoteCommandList"].url,
                         'http://192.168.178.23/sony/system')

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_ircc(self, mock_get):
        content = read_file("xml/ircc.xml")
        device = self.create_device()
        device._parse_ircc(content)
        self.assertEqual(device.actionlist_url,
                         'http://192.168.240.4:50002/actionList')
        self.assertEqual(device.control_url,
                         'http://test:50001/upnp/control/IRCC')

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_parse_action_list(self, mock_get):
        content = read_file("xml/actionlist.xml")
        device = self.create_device()
        device._parse_action_list(content)
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
        content = read_file("xml/getSysteminformation.xml")
        device = self.create_device()
        device._parse_system_information(content)
        self.assertEqual(device.mac, "30-52-cb-cc-16-ee")
    
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_update_commands_v3(self, mock_get):
        content = read_file("xml/getRemoteCommandList.xml")
        device = self.create_device()
        device._parse_command_list(content)
        self.assertEqual(len(device.commands), 48)

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
