from functools import lru_cache
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

XML_PATH = "/home/rapidswords/SMH Coders/Kent/ConvertingDXFtoDEXPI/out/PA-A11090-001-3/PA-A11090-001-3.dexpi.xml"

# with open(XML_PATH, 'r') as xml_file:
# 	xml_data = xml_file.read()


tree = ET.parse(XML_PATH)
root = tree.getroot()

ROOT_PIPING_COMPONENTS = root.findall("PipingComponent")
PIPING_NETWORK_SYSTEM = root.find("PipingNetworkSystem")
PIPING_NETWORK_SEGMENTS = PIPING_NETWORK_SYSTEM.findall("PipingNetworkSegment")
SHAPE_CATALOGUE = root.find("ShapeCatalogue")

SHAPE_PIPING_COMPONENTS = SHAPE_CATALOGUE.findall("PipingComponent")


# for pc in SHAPE_PIPING_COMPONENTS:
# 	print(pc.attrib["ID"])

# for pc in ROOT_PIPING_COMPONENTS:
# 	print(pc.attrib["ID"])


# for pc in PIPING_NETWORK_SEGMENTS:
# 	print(pc.find("Connection").attrib["ToID"])


@lru_cache()
def get_from_of(comp_id: str) -> list[Element]:
    """
    This function returns list of components that are
    connected to the passed components from behind.
    i.e. from the returned components to the passed components

    e.g. if C-044 is returned by this function, means C-044 is
    connected to comp_id as C-044 is before comp_id
    """

    _all = []
    for pc in PIPING_NETWORK_SEGMENTS:
        cc = pc.find("Connection")
        if cc.attrib["ToID"] == comp_id:
            _all.append(cc)

    return tuple(_all)


@lru_cache()
def get_to_of(comp_id: str) -> list[Element]:
    """
    This function returns list of components that are
    connected to the passed components afterwards.
    i.e. to the returned components from the passed components

    e.g. if C-044 is returned by this function, means C-044 is
    connected to comp_id as C-044 is after comp_id
    """

    _all = []
    for pc in PIPING_NETWORK_SEGMENTS:
        cc = pc.find("Connection")
        if cc.attrib["FromID"] == comp_id:
            _all.append(cc)

    return tuple(_all)

@lru_cache()
def get_name(comp_id: str) -> str:
    for pc in ROOT_PIPING_COMPONENTS:
        if pc.attrib["ID"] == comp_id:
            return pc.attrib["ComponentName"]

if __name__ == "__main__":
    COMPONENT = "C-044"

    print(
        [
            f"{c.attrib['FromID']}: {get_name(c.attrib['FromID'])}"
            for c in get_from_of(COMPONENT)
        ]
    )
    print(
        [
            f"{c.attrib['ToID']}: {get_name(c.attrib['ToID'])}"
            for c in get_to_of(COMPONENT)
        ]
    )
