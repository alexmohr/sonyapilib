import json
from sonyapilib.device import SonyDevice


config_file = 'bluray.json'

with open(config_file, 'r') as myfile:
    data = myfile.read()

device = SonyDevice.load_from_json(data)

hass_cfg = {}
hass_cfg[device.host] = {}
hass_cfg[device.host]["device"] = data
print(json.dumps(hass_cfg), file=open("sony.conf", "w"))
