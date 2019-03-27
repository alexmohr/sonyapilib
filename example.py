from sonyapilib.device import SonyDevice

def save_device():
    data = device.save_to_json()
    text_file = open("bluray.json", "w")
    text_file.write(data)
    text_file.close()
