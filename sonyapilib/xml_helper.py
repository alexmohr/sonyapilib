"""XML helper functions for the library."""
import xml.etree.ElementTree


def xml_search_helper(data, param):
    """Perform find or findall on given xml with string from param."""
    if isinstance(param, (tuple, list)) and param[1]:
        result = data.findall(param[0])
    else:
        result = data.find(param)
    return result


def iterate_search_data(data, param):
    """Search in nested lists."""
    result = []
    for element in data:
        if isinstance(element, list):
            result.append(iterate_search_data(element, param))
        else:
            result.append(xml_search_helper(element, param))
    return result


def find_in_xml(data, search_params):
    """Try to find an element in an xml

    Take an xml from string or as xml.etree.ElementTree
    and an iterable of strings (and/or tuples in case of findall) to search.
    The tuple should contain the string to search for and a true value.
    """
    if isinstance(data, str):
        data = xml.etree.ElementTree.fromstring(data)
    param = search_params[0]
    if isinstance(data, list):
        result = iterate_search_data(data, param)
    else:
        result = xml_search_helper(data, param)

    if len(search_params) == 1:
        return result
    return find_in_xml(result, search_params[1:])
