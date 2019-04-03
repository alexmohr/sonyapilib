import unittest
import os.path

from inspect import getsourcefile
import os.path as path
import sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
from sonyapilib.device import SonyDevice, AuthenticationResult
sys.path.pop(0)


def register_device(device):
    result = device.register()
    if result != AuthenticationResult.PIN_NEEDED:
        print("Error in registration")
        return False
    
    pin = input("Enter the PIN displayed at your device: ")
    device.send_authentication(pin)
    return True

if __name__ == "__main__":
    
    stored_config = "bluray.json"
    device = None

    # device must be on for registration
    host = "10.0.0.102"
    device = SonyDevice(host, "SonyApiLib Python Test4")
    if register_device(device):
        # save_device()
        apps = device.get_apps()
        device.start_app(apps[0])

        # Play media
        device.play()

        

    