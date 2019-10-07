import os.path

__location__ = os.path.realpath(os.path.join(
    os.getcwd(), os.path.dirname(__file__)))


def read_file(file_name):
    """ Reads a file from disk """
    with open(os.path.join(__location__, file_name)) as f:
        return f.read()


def read_file_bin(file_name, size, offset):
    """ Reads a file from disk """
    with open(os.path.join(__location__, file_name), 'rb') as f:
        f.seek(offset)
        return f.read(size)
