from sonyapilib.device import SonyDevice

def save_device():
    data = device.save_to_json()
    text_file = open("bluray.json", "w")
    text_file.write(data)
    text_file.close()

if __name__ == "__main__":

    stored_config = "bluray.json"
    device = None
    import os.path
    if os.path.exists(stored_config):
        with open(stored_config, 'r') as content_file:
            json_data = content_file.read()
            device = SonyDevice.load_from_json(json_data)
    else:
        # device must be on for registration
        host = "10.0.0.102"
        device = SonyDevice(host, "SonyApiLib Python Test")
        device.register()
        pin = input("Enter the PIN displayed at your device: ")
        device.send_authentication(pin)
        save_device()

    # wake device
    is_on = device.get_power_status()
    if not is_on:
        device.power(True)

    apps = device.get_apps()

    device.start_app(apps[0])

    # Play media
    device.play()
