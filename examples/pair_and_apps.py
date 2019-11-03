"""Example script to pair the device and start an app."""
from sonyapilib.device import SonyDevice

CONFIG_FILE = "bluray.json"


def save_device():
    """Save the device to disk."""
    data = device.save_to_json()
    text_file = open(CONFIG_FILE, "w")
    text_file.write(data)
    text_file.close()


def load_device():
    """Restore the device from disk."""
    import os
    sony_device = None
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as content_file:
            json_data = content_file.read()
            sony_device = SonyDevice.load_from_json(json_data)
    return sony_device


if __name__ == "__main__":
    device = load_device()
    if not device:
        # device must be on for registration
        host = "192.168.178.23"
        device = SonyDevice(host, "Test123")
        device.register()
        pin = input("Enter the PIN displayed at your device: ")
        if device.send_authentication(pin):
            save_device()
        else:
            print("Registration failed")
            exit(1)

    # wake device
    is_on = device.get_power_status()
    if not is_on:
        device.power(True)

    status = device.get_playing_status()

    apps = device.get_apps()
    device.pause()
    for app in device.apps:
        if "youtube" in app.lower():
            device.start_app(app)
    device.get_playing_status()
    # Play media
    device.play()
