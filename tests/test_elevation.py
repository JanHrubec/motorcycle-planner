import struct

from route_planner.elevation import ElevationTiles


def test_reads_height_from_hgt_tile(tmp_path):
    heights = [100, 110, 120, 200, 210, 220, 300, 310, 320]
    tile = tmp_path / "N49E015.hgt"
    tile.write_bytes(struct.pack(">9h", *heights))

    terrain = ElevationTiles(tmp_path)
    assert terrain.at(49.5, 15.5) == 210
    assert terrain.at(49.99, 15.01) == 100
    assert terrain.at(47.0, 15.0) is None
