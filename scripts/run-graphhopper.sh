#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GH_DIR="$PROJECT_ROOT/graphhopper/src"

if [ ! -d "$GH_DIR" ]; then
    echo "ERROR: expected graphhopper at $GH_DIR" >&2
    exit 1
fi

cd "$GH_DIR"

PBF_FILE="Melbourne.osm.pbf"
PBF_URL="https://download.bbbike.org/osm/bbbike/Melbourne/Melbourne.osm.pbf"
JAR_FILE="graphhopper-web-11.0.jar"
JAR_URL="https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/11.0/graphhopper-web-11.0.jar"
CONFIG="config-example.yml"

OS="$(uname -s)"

has_java_21() {
    command -v java >/dev/null 2>&1 && java -version 2>&1 | grep -Eq 'version "21(\.|")'
}

install_java_21_linux() {
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "ERROR: apt-get not found. Install OpenJDK 21 manually." >&2
        exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y openjdk-21-jdk
}

install_java_21_macos() {
    if ! command -v brew >/dev/null 2>&1; then
        echo "ERROR: Homebrew not found. Install it from https://brew.sh and re-run." >&2
        exit 1
    fi
    brew install openjdk@21

    # brew installs openjdk@21 keg-only; expose it on PATH for this run.
    local brew_prefix
    brew_prefix="$(brew --prefix openjdk@21)"
    export PATH="$brew_prefix/bin:$PATH"
    export JAVA_HOME="$brew_prefix/libexec/openjdk.jdk/Contents/Home"
}

install_java_21() {
    if has_java_21; then
        echo "Java 21 already installed: $(java -version 2>&1 | head -1)"
        return
    fi

    echo "Installing OpenJDK 21..."
    case "$OS" in
        Linux)  install_java_21_linux  ;;
        Darwin) install_java_21_macos  ;;
        *)
            echo "ERROR: unsupported OS '$OS'. Install OpenJDK 21 manually." >&2
            exit 1
            ;;
    esac

    if ! has_java_21; then
        echo "ERROR: Java 21 install completed but 'java -version' still does not report 21." >&2
        echo "Open a new shell or update your PATH/JAVA_HOME and re-run." >&2
        exit 1
    fi
}

download_if_missing() {
    local file="$1" url="$2"
    if [ -s "$file" ]; then
        echo "Found existing $file — skipping download."
        return
    fi
    echo "Downloading $file ..."
    curl -fL --retry 3 --progress-bar -o "$file" "$url"
}

install_java_21
download_if_missing "$PBF_FILE" "$PBF_URL"
download_if_missing "$JAR_FILE" "$JAR_URL"

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found in $(pwd)" >&2
    exit 1
fi

echo "Launching GraphHopper server (UI on http://localhost:8989) ..."
exec java -Ddw.graphhopper.datareader.file="$PBF_FILE" -jar "$JAR_FILE" server "$CONFIG"
