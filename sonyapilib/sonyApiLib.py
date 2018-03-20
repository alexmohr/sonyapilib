"""
Sony Mediaplayer lib
"""
import logging
import base64
import collections
import json
import socket
import struct
import requests
import urllib.request
import xml.etree.ElementTree

import ssdp

class ApiAction():
    """ Holds data for a device action"""
    def __init__(self, xml_data):
        self.name = xml_data["name"]
        self.url = xml_data["url"]
        if "mode" in xml_data:
            self.mode = xml_data["mode"]



class ApiDevice():
    """
    Contains all data for the device
    """
    
    def __init__(self, ircc_location): 
        """ Init the device with the entry point"""
        self.ircc_url= ircc_location
        self.actionlist_url = None
        self.actions = {}

    def load_from_json(self):
        """ Loads a device configuration from a stored json """ 
        pass

    def setup_new_device(self):
        """ Initalizes the device by reading the necessary resources from it """
        response = urllib.request.urlopen(self.ircc_url)
        raw_data = bytes.decode(response.read())
        xml_data = xml.etree.ElementTree.fromstring(raw_data)
        
        # the action list contains everything the device supports
        self.actionlist_url = xml_data.find("{urn:schemas-upnp-org:device-1-0}device")\
            .find("{urn:schemas-sony-com:av}X_UNR_DeviceInfo")\
            .find("{urn:schemas-sony-com:av}X_CERS_ActionList_URL")\
            .text

        response = urllib.request.urlopen(self.actionlist_url)
        raw_data = bytes.decode(response.read())
        xml_data = xml.etree.ElementTree.fromstring(raw_data)
        for element in xml_data.findall("action"):
            action = ApiAction(element.attrib)
            self.actions[action.name] = action

    def register(self):
        pass
 
class SonyApiLib:
    """
    Provides the access to the api funtions.
    """

    def create_device(self, ircc_location):
        device = ApiDevice(ircc_location)
        device.setup_new_device()
        return device

    def create_device_by_host(self, host, port=50001):
        ircc_location = "http://{0}:{1}/Ircc.xml"
        return self.create_device(ircc_location.format(host, port))

    def discover(self):
        """
        Discover all available devices.
        """
        discovery = ssdp.SSDPDiscovery()
        devices = []
        for device in discovery.discover("urn:schemas-sony-com:service:IRCC:1"):
            devices.append(self.create_device(device.location))

        return devices

    def register(self, device):
        """
        Register a connection with a host
        """


if __name__ == '__main__':
   lib = SonyApiLib()
   for device in lib.discover():
       lib.register(device.location)

        