import argparse
import json

from route_planner.osm_import import import_pbf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--elevation")
    args = parser.parse_args()
    report = import_pbf(args.input, "data/graph.pkl.gz", args.elevation)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
