from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring


def make_gpx(coordinates, name):
    if len(coordinates) < 2:
        raise ValueError("A GPX track needs at least two coordinates")

    root = Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "Motorcycle Route Planner IA",
            "xmlns": "http://www.topografix.com/GPX/1/1",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": (
                "http://www.topografix.com/GPX/1/1 "
                "http://www.topografix.com/GPX/1/1/gpx.xsd"
            ),
        },
    )
    metadata = SubElement(root, "metadata")
    SubElement(metadata, "name").text = name
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    SubElement(metadata, "time").text = now
    SubElement(metadata, "desc").text = "Planned with OpenStreetMap data"

    track = SubElement(root, "trk")
    SubElement(track, "name").text = name
    segment = SubElement(track, "trkseg")
    for lat, lon in coordinates:
        SubElement(segment, "trkpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")
