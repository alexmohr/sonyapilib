from sonyapilib.device import SonyDevice

CONFIG_FILE = "bluray.json"

def save_device():
    data = device.save_to_json()
    text_file = open(CONFIG_FILE, "w")
    text_file.write(data)
    text_file.close()


def load_device():
    import os
    device = None
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as content_file:
            json_data = content_file.read()
            device = SonyDevice.load_from_json(json_data)
    return device


if __name__ == "__main__":
    device = load_device()
    if not device:
        # device must be on for registration
        host = "10.0.0.102"
        device = SonyDevice(host, "SonyApiLib Python Test")
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

    device.get_playing_status()
    apps = device.get_apps()
    device.start_app(apps[0])

    # Play media
    device.play()
