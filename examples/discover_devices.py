import json
from sonyapilib.ssdp import SSDPDiscovery

ip = "10.0.0.102"
ssdp = SSDPDiscovery()
services = ssdp.discover()
for service in services:
    print(service)
