"""
SSDP Implementation

"""

import socket
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler
from io import StringIO
import email

class SSDPResponse():
    """
    Holds the response of a ssdp request
    """

    def __init__(self, response):
        # pop the first line so we only process headers
        # first line is http response
        _, headers = response.split('\r\n', 1)

        # construct a message from the request string
        message = email.message_from_file(StringIO(headers))

        # construct a dictionary containing the headers
        headers = dict(message.items())
        self.location = headers["LOCATION"]
        self.usn = headers["USN"]
        self.st = headers["ST"]
        self.cache = headers["CACHE-CONTROL"].split("=")[1]

    def __repr__(self):
        """
        Defines how string representation looks
        """
        return "<SSDPResponse({location}, {st}, {usn})>".format(**self.__dict__)

class SSDPDiscovery():
    def discover(self, service="ssdp:all", timeout=1, retries=5, mx=3):
        """
        Discovers the ssdp services.
        """
        socket.setdefaulttimeout(timeout)

        # fppp
        host = ("239.255.255.250", 1900)
        message = "\r\n".join([
            'M-SEARCH * HTTP/1.1',
            'HOST: {0}:{1}',
            'MAN: "ssdp:discover"',
            'ST: {st}', 'MX: {mx}', '', ''])
        # using a dict to prevent duplicated entries.
        responses = {}
        for _ in range(0, retries):
            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

            #msg = DISCOVERY_MSG % dict(service='id1', library=LIB_ID)
            for _ in range(0, retries):
                # sending it more than once will
                # decrease the probability of a timeout
                sock.sendto(str.encode(message.format(
                    *host, st=service, mx=mx)), host)

            while True:
                try:
                    response = SSDPResponse(bytes.decode(sock.recv(1024)))
                    responses[response.location] = response
                except socket.timeout:
                    break
            return list(responses.values())

if __name__ == '__main__':
    disco = SSDPDiscovery();
    for service in disco.discover():
        print(service)
