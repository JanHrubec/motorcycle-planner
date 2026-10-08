import gzip
import struct
from math import floor, isqrt
from pathlib import Path


class ElevationTiles:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.loaded = {}

    @staticmethod
    def _tile_name(lat, lon):
        bottom = floor(lat)
        left = floor(lon)
        ns = "N" if bottom >= 0 else "S"
        ew = "E" if left >= 0 else "W"
        return f"{ns}{abs(bottom):02d}{ew}{abs(left):03d}"

    def _load(self, name):
        if name in self.loaded:
            return self.loaded[name]

        plain = self.folder / f"{name}.hgt"
        zipped = self.folder / f"{name}.hgt.gz"
        if plain.exists():
            data = plain.read_bytes()
        elif zipped.exists():
            with gzip.open(zipped, "rb") as source:
                data = source.read()
        else:
            return None

        # square grid, two bytes per height
        side = isqrt(len(data) // 2)
        if side * side * 2 != len(data):
            raise ValueError(f"{name} is not a square HGT tile")
        self.loaded[name] = (data, side)
        return data, side

    def at(self, lat, lon):
        name = self._tile_name(lat, lon)
        tile = self._load(name)
        if tile is None:
            return None
        data, side = tile
        bottom = floor(lat)
        left = floor(lon)
        # rows start at the north edge
        row = round((bottom + 1 - lat) * (side - 1))
        column = round((lon - left) * (side - 1))
        row = min(side - 1, max(0, row))
        column = min(side - 1, max(0, column))
        # signed big-endian heights
        height = struct.unpack_from(">h", data, (row * side + column) * 2)[0]
        # -32768 means missing data
        return None if height == -32768 else float(height)
