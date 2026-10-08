from math import asin, atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    # spherical distance and bearings use radians
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)

    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def bearing_degrees(lat1, lon1, lat2, lon2):
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    d_lambda = radians(lon2 - lon1)
    y = sin(d_lambda) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(d_lambda)
    return (degrees(atan2(y, x)) + 360) % 360


def bearing_change(first, second):
    # handles the 359 to 1 degree wrap
    return abs((second - first + 180) % 360 - 180)
