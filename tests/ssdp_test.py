"""Test for simple service discovery protocol"""
import os.path as path
import sys
import unittest
from inspect import getsourcefile
from socket import timeout
from unittest import mock

from tests.testutil import read_file_bin

current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
# cannot be imported at a different position because path modification
# is necessary to load the local library.
# otherwise it must be installed after every change
from sonyapilib.ssdp import SSDPDiscovery

sys.path.pop(0)


def mock_socket(*args, **kwargs):
    """Mock class for request socket"""
    class MockSocket:
        def __init__(self):
            self.offset = 0

        def setsockopt(self, *args):
            pass

        def sendto(self, *args):
            pass

        def recv(self, size):
            data = read_file_bin("data/ssdp.txt", size=size, offset=self.offset)
            if not data:
                raise timeout()

            self.offset = self.offset + len(data)
            return data

    return MockSocket()


class SSDPDiscoveryTest(unittest.TestCase):
    """SSDP discovery testing"""

    @mock.patch('socket.socket', side_effect=mock_socket)
    def test_discover(self, mock_socket):
        """Test discovery of ssdp services"""
        discovery = SSDPDiscovery()
        services = discovery.discover()
        self.assertEqual(len(services), 9)

        urls = ["http://10.0.0.1:49000/igd2desc.xml",
                "http://10.0.0.1:49000/fboxdesc.xml",
                "http://10.0.0.1:49000/igddesc.xml",
                "http://10.0.0.1:49000/avmnexusdesc.xml",
                "http://10.0.0.1:49000/l2tpv3.xml",
                "http://10.0.0.114:8008/ssdp/device-desc.xml",
                "http://10.0.0.102:50201/dial.xml",
                "http://10.0.0.151:8080/description.xml",
                "http://10.0.0.144:80/description.xml"]
        for service in services:
            self.assertTrue(service.location in urls)
            self.assertTrue(service.location in str(service))


if __name__ == '__main__':
    unittest.main()
