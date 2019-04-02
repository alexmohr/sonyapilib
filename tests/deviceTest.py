import unittest
import os.path

from inspect import getsourcefile
import os.path as path, sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
from sonyapilib.device import SonyDevice
sys.path.pop(0)

class TestHelper:

    @staticmethod
    def read_file(file_name):
        """ Reads a file from disk """
        __location__ = os.path.realpath(os.path.join(
            os.getcwd(), os.path.dirname(__file__)))
        with open(os.path.join(__location__, file_name)) as f:
            return f.read()


class SonyDeviceTest(unittest.TestCase):

    def test_parse_dmr_v3(self):
        content = TestHelper.read_file("dmr_v3.xml")
        device = self.create_device()
        device._parse_dmr(content)
        self.verify_device_dmr(device)
        self.assertFalse(device.is_v4)

    def test_parse_dmr_v4(self):
        content = TestHelper.read_file("dmr_v4.xml")
        device = self.create_device()
        device._parse_dmr(content)
        self.verify_device_dmr(device)
        self.assertTrue(device.is_v4)
        self.assertEqual(device.actions["register"].url, 
            'http://192.168.178.23/sony/accessControl')
        self.assertEqual(device.actions["register"].mode, 4)
        self.assertEqual(device.actions["getRemoteCommandList"].url, 
            'http://192.168.178.23/sony/system')

    def test_parse_ircc(self):
        content = TestHelper.read_file("ircc.xml")
        device = self.create_device()
        device._parse_ircc(content)

    def create_device(self):
        return SonyDevice("test", "test")

    def verify_device_dmr(self, device):
        self.assertEqual(device.av_transport_url,
                         'http://test:52323/upnp/control/AVTransport')


if __name__ == '__main__':
    unittest.main()
