#!/bin/bash
# Sync source Python files + template into docs/ for GitHub Pages deployment.
# Run this after making changes to correlate.py, generate_dashboard.py,
# or foursquare_template.html.

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DOCS="$DIR/docs"

mkdir -p "$DOCS"
cp "$DIR/correlate.py"            "$DOCS/correlate.py"
cp "$DIR/generate_dashboard.py"   "$DOCS/generate_dashboard.py"
cp "$DIR/foursquare_template.html" "$DOCS/template.html"

# Publish geo cache as seed for web version (skips Nominatim for known locations)
if [ -f "$DIR/data/geo_cache.json" ]; then
  cp "$DIR/data/geo_cache.json" "$DOCS/geo_seed.json"
  echo "Published geo_seed.json ($(wc -c < "$DOCS/geo_seed.json" | tr -d ' ') bytes)"
fi

echo "Synced to docs/:"
ls -lh "$DOCS"
