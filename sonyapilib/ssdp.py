"""SSDP Implementation"""
import email
import logging
import socket
from io import StringIO

_LOGGER = logging.getLogger(__name__)


class SSDPResponse:
    # pylint: disable=too-few-public-methods
    """Hold the response of a ssdp request."""

    def __init__(self, response):
        """Init the ssdp response with given data"""
        if not response:
            return

        # construct a message from the request string
        message = email.message_from_file(StringIO(response))

        # construct a dictionary containing the headers
        headers = dict(message.items())
        if "Location" in headers:
            self.location = headers["Location"]
        else:
            self.location = headers["LOCATION"]

        if "Cache-Control" in headers:
            self.cache = headers["Cache-Control"].split("=")[1]
        else:
            self.cache = headers["CACHE-CONTROL"].split("=")[1]

        self.usn = headers["USN"]
        # pylint: disable=invalid-name
        self.st = headers["ST"]

    def __repr__(self):
        """Define how string representation looks"""
        return "<SSDPResponse({location}, {st}, {usn})>"\
            .format(**self.__dict__)


class SSDPDiscovery():
    # pylint: disable=too-few-public-methods
    """Discover devices via the ssdp protocol."""

    @staticmethod
    def _parse_response(data):
        responses = {}
        lines = ""
        http_ok = "HTTP/1.1 200 OK"
        for line in data.split('\r\n'):
            if http_ok in line and lines:
                response = SSDPResponse(lines)
                responses[response.location] = response
                lines = ""
            elif http_ok not in line:
                line_content = line.split(":")
                if len(line_content) >= 2 and line_content[1]:
                    lines += line + '\r\n'
        return list(responses.values())

    @staticmethod
    def discover(service="ssdp:all", timeout=1, retries=5, mx=3):
        # pylint: disable=invalid-name
        """Discovers the ssdp services."""
        socket.setdefaulttimeout(timeout)

        # fppp
        host = ("239.255.255.250", 1900)
        message = "\r\n".join([
            'M-SEARCH * HTTP/1.1',
            'HOST: {0}:{1}',
            'MAN: "ssdp:discover"',
            'ST: {st}', 'MX: {mx}', '', ''])
        # using a dict to prevent duplicated entries.
        for _ in range(0, retries):
            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

            # msg = DISCOVERY_MSG % dict(service='id1', library=LIB_ID)
            for _ in range(0, retries):
                # sending it more than once will
                # decrease the probability of a timeout
                sock.sendto(str.encode(message.format(
                    *host, st=service, mx=mx)), host)

            data = ""
            while True:
                try:
                    data = data + bytes.decode(sock.recv(1024))
                except socket.timeout:
                    break

            return SSDPDiscovery._parse_response(data)
