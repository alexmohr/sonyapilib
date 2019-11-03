"""Example found in the readme."""
from sonyapilib.device import SonyDevice

if __name__ == "__main__":
    # device must be on for registration
    host = "10.0.0.102"
    device = SonyDevice(host, "SonyApiLib Python Test")
    device.register()
    pin = input("Enter the PIN displayed at your device: ")
    if not device.send_authentication(pin):
        print("Failed to register device")
        exit(1)

    apps = device.get_apps()
    device.start_app(apps[0])
    device.play()
