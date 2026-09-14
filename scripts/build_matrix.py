#!/usr/bin/env python3
import argparse
import asyncio
import json
import math
import sys
import osmium
import httpx
from pathlib import Path
import numpy as np
import pandas as pd

RESIDENTIAL_TAGS = [
    "residential",
    "house",
    "apartments",
    "terrace",
    "detached",
    "semidetached_house",
    "bungalow",
]

ADDR_KEYS = [
    "addr:housenumber",
    "addr:street",
    "addr:suburb",
]

def load_buildings(pbf_path: Path, cache_path: Path) -> pd.DataFrame:
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    print(f"parsing {pbf_path} (one-time, this takes a minute)...", file=sys.stderr)


    residential = set(RESIDENTIAL_TAGS)

    class BuildingHandler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.rows = []

        def way(self, w):
            btype = w.tags.get("building")
            if btype not in residential:
                return
            lat_sum = 0.0
            lon_sum = 0.0
            count = 0
            for n in w.nodes:
                if n.location.valid():
                    lat_sum += n.lat
                    lon_sum += n.lon
                    count += 1
            if count == 0:
                return
            parts = [w.tags.get(k) for k in ADDR_KEYS]
            address = ", ".join(p for p in parts if p)
            self.rows.append(
                (w.id, lat_sum / count, lon_sum / count, btype, address)
            )

    h = BuildingHandler()
    h.apply_file(str(pbf_path), locations=True)

    if not h.rows:
        raise RuntimeError("no residential buildings found in PBF")

    df = pd.DataFrame(
        h.rows, columns=["osm_id", "lat", "lon", "building_type", "address"]
    )
    df["osm_id"] = df["osm_id"].astype("int64")
    df.to_parquet(cache_path, index=False)
    print(f"cached {len(df)} residential buildings to {cache_path}", file=sys.stderr)
    return df


def filter_radius(df: pd.DataFrame, lat: float, lon: float, radius_km: float) -> pd.DataFrame:
    R = 6371.0  # km
    lat_rad = math.radians(lat)
    dlat = np.radians(df["lat"].to_numpy() - lat)
    dlon = np.radians(df["lon"].to_numpy() - lon) * math.cos(lat_rad)
    dist_km = R * np.sqrt(dlat * dlat + dlon * dlon)
    return df.loc[dist_km <= radius_km].copy()


async def fetch_route(client, sem, gh_url, p1, p2):
    async with sem:
        try:
            r = await client.get(
                f"{gh_url}/route",
                params=[
                    ("point", f"{p1[0]},{p1[1]}"),
                    ("point", f"{p2[0]},{p2[1]}"),
                    ("profile", "car"),
                    ("calc_points", "true"),
                    ("points_encoded", "false"),
                    ("instructions", "false"),
                ],
                timeout=30.0,
            )
            r.raise_for_status()
            path = r.json()["paths"][0]
            return {
                "distance_km": path["distance"] / 1000.0,
                "coords": path["points"]["coordinates"],
            }
        except Exception:
            return None


async def build_matrix(points, gh_url, request_size):
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    routes = [[None] * n for _ in range(n)]
    sem = asyncio.Semaphore(request_size)
    async with httpx.AsyncClient() as client:
        coords = [(i, j) for i in range(n) for j in range(n) if i != j]
        tasks = [
            fetch_route(client, sem, gh_url, points[i], points[j])
            for (i, j) in coords
        ]
        results = await asyncio.gather(*tasks)
    for (i, j), r in zip(coords, results):
        if r is None:
            matrix[i][j] = None
        else:
            matrix[i][j] = r["distance_km"]
            routes[i][j] = r["coords"]
    return matrix, routes


def main():
    ap = argparse.ArgumentParser(
        description="Build a (n+1)x(n+1) road-distance matrix (km) between a store and "
        "n random residential buildings within radius x km, via GraphHopper /route."
    )
    ap.add_argument("--lat", type=float, default=-37.859286, help="store latitude")
    ap.add_argument("--lon", type=float, default=144.978046, help="store longitude")
    ap.add_argument("--n", type=int, default=40, help="number of buildings")
    ap.add_argument("--radius", type=float, default=2, help="radius in km")
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    ap.add_argument("--out", default=str(data_dir / "matrix.json"), help="output matrix file")
    pbf_path = str(project_root / "graphhopper" / "src" / "Melbourne.osm.pbf")
    cache = str(data_dir / "buildings.parquet")
    graphhopper_server_url = "http://localhost:8989"
    request_size = 16
    args = ap.parse_args()

    df = load_buildings(Path(pbf_path), Path(cache))
    in_radius = filter_radius(df, args.lat, args.lon, args.radius)

    if len(in_radius) < args.n:
        print(
            f"error: only {len(in_radius)} residential buildings within "
            f"{args.radius} km of ({args.lat}, {args.lon}); requested n={args.n}",
            file=sys.stderr,
        )
        sys.exit(1)

    sample = in_radius.sample(n=args.n, random_state=42).reset_index(drop=True)
    points = [(args.lat, args.lon)] + list(zip(sample["lat"].tolist(), sample["lon"].tolist()))

    matrix, routes = asyncio.run(build_matrix(points, graphhopper_server_url, request_size))

    csv_path = Path(args.out).with_suffix(".csv")
    csv_rows = [{"lat": args.lat, "lon": args.lon, "type": "store", "address": ""}]
    for row in sample.itertuples(index=False):
        csv_rows.append({
            "lat": row.lat,
            "lon": row.lon,
            "type": row.building_type,
            "address": row.address or "",
        })
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"wrote {csv_path}", file=sys.stderr)

    types = ["store"] + sample["building_type"].tolist()
    out = {
        "coords": [[lat, lon] for lat, lon in points],
        "types": types,
        "distances_km": matrix,
        "routes": routes,
        "routes_coord_order": "[lon, lat]",
    }
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
