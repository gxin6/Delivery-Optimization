# Optimization For Industry Group Assignment

Members:
- Leran Zhang
- Fanrui Zhang
- Xin Guo
- Chi Ian Chan
- Yiming Yang
- Shih Chin Liang

## Table of Contents
- [Repository Layout](#repository-layout)
- [Quick Start](#quick-start)
- [Running the GraphHopper Server](#running-the-graphhopper-server)
  - [What the script does](#what-the-script-does)
  - [Usage](#usage)
  - [Requirements](#requirements)
- [Generating the Distance Matrix](#generating-the-distance-matrix)
  - [What it does](#what-it-does)
  - [Usage](#usage-1)
  - [Arguments](#arguments)
  - [Output](#output)

## Repository Layout
```
src/
├── run.sh                  # one-shot: venv + GraphHopper + usage hints
├── scripts/
│   ├── setup-venv.sh       # creates .venv and installs requirements.txt
│   ├── run-graphhopper.sh  # installs Java 21, downloads PBF/JAR, launches server
│   └── build_matrix.py     # builds the store to residence distance matrix
├── data/
│   ├── woolworths_stores_melbourne.csv # store locations
│   ├── buildings.parquet   # cached residential buildings (auto-generated)
│   └── matrix.json         # distance matrix output (auto-generated)
├── graphhopper/            # GraphHopper sources + Melbourne.osm.pbf + jar
├── requirements.txt
└── README.md
```

## Quick Start
From the `src/` directory:

```bash
./run.sh
```

This wraps the full setup: it creates the Python venv, launches GraphHopper in the background, waits for the server to be ready, then prints the commands to activate the venv and run `build_matrix.py`. The GraphHopper server stays running after `run.sh` exits so you can build matrices repeatedly; the script prints the `kill <pid>` command to stop it.

## Running the GraphHopper Server

A helper script `scripts/run-graphhopper.sh` is provided to set up and launch a local GraphHopper routing server with the Melbourne OSM map.

### What the script does
1. Installs OpenJDK 21 if Java 21 is not already available:
   - **Linux / WSL** — via `sudo apt-get install openjdk-21-jdk`
   - **macOS** — via `brew install openjdk@21`
2. Downloads `Melbourne.osm.pbf` from bbbike into `graphhopper/src/` if missing.
3. Downloads `graphhopper-web-11.0.jar` from Maven Central into `graphhopper/src/` if missing.
4. Launches the GraphHopper web server using `graphhopper/src/config-example.yml`.

### Usage
From the `src/` directory:

```bash
./scripts/run-graphhopper.sh
```

The first run will prompt for `sudo` (Linux) or use Homebrew (macOS) to install Java, and may take a few minutes to download the map and jar. Subsequent runs reuse existing files.

> **macOS note:** Homebrew installs `openjdk@21` as keg-only. The script puts it on `PATH` for the current run, but the install output prints how to make `java` available in future shells (either via `~/.zshrc` `PATH`/`JAVA_HOME` exports, or by symlinking the JDK into `/Library/Java/JavaVirtualMachines/`).

Once running, the web UI is available at:

```
http://localhost:8989
```

Stop the server with `Ctrl+C`.

### Requirements
- One of:
  - Linux / WSL with `apt-get` and `sudo` access, or
  - macOS with [Homebrew](https://brew.sh) installed.
- `bash` and `curl` available on `PATH`.

## Generating the Distance Matrix

`scripts/build_matrix.py` builds an `(n+1) × (n+1)` road-distance matrix (km) between a store and `n` randomly sampled residential buildings within a given radius, by querying the local GraphHopper `/route` endpoint.

### What it does
1. Parses `graphhopper/src/Melbourne.osm.pbf` to extract residential buildings (cached at `data/buildings.parquet` after the first run).
2. Filters buildings within `--radius` km of `(--lat, --lon)`.
3. Randomly samples `--n` of them (deterministic — `random_state=42`).
4. Issues async requests to GraphHopper for every ordered pair of points.
5. Writes coords, distances, and route geometries to `data/matrix.json` (and a human-readable `data/matrix.csv`).

### Usage
Make sure the GraphHopper server is running (`./run.sh` or `./scripts/run-graphhopper.sh`) and the venv is active:

```bash
source .venv/bin/activate
python scripts/build_matrix.py --lat <store_lat> --lon <store_lon> --n <count> --radius <km>
```

Sample (Woolworths Melbourne CBD, 40 nearby buildings within 2 km):

```bash
python scripts/build_matrix.py --lat -37.8136 --lon 144.9631 --n 40 --radius 2.0
```

### Arguments
| Flag       | Type  | Default        | Description                                  |
| ---------- | ----- | -------------- | -------------------------------------------- |
| `--lat`    | float | `-37.859286`   | Store latitude                               |
| `--lon`    | float | `144.978046`   | Store longitude                              |
| `--n`      | int   | `40`           | Number of residential buildings to sample    |
| `--radius` | float | `2`            | Search radius in km                          |
| `--out`    | str   | `data/matrix.json` | Output file path                         |

### Output
The script writes two files:

`data/matrix.json` — a flat JSON object with the following keys:

```json
{
  "coords":             [[lat, lon], ...],
  "types":              ["store", "apartments", "house", ...],
  "distances_km":       [[0.0, ...], ...],
  "routes":             [[null, [[lon, lat], ...], ...], ...],
  "routes_coord_order": "[lon, lat]"
}
```

- `coords[0]` is the store; `coords[1..n]` are the sampled residential buildings in sample order.
- `types[i]` is the OSM building tag for point `i` (`"store"` for the depot, otherwise one of `house`, `apartments`, `terrace`, `detached`, `semidetached_house`, `bungalow`, `residential`). Useful for residential-type lookups (e.g. service-time tables).
- `distances_km[i][j]` is the road distance (km) from point `i` to point `j`. Failed routes are recorded as `null`.
- `routes[i][j]` is the polyline returned by GraphHopper for plotting (list of `[lon, lat]` points). `null` when `i == j` or the route fetch failed.

`data/matrix.csv` — same coordinate order as `coords`, with extra `type` and `address` columns sourced from the OSM building tags. Human-readable; not consumed by the notebook.
