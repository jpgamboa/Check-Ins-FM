#!/usr/bin/env python3
"""
Build a suburb → metro correction table from GeoNames cities15000 data.

For each city with population < 100K, finds the nearest city with
population > 250K within 35 km. Outputs a JSON mapping suitable for
correcting offline-geocode-city results in the browser.

Output format: { "Lakeway|US": "Austin", "Kunp'o|KR": "Incheon", ... }
Key is "cityName|countryCode" to avoid cross-country collisions.
"""

import json
import math
import os
import urllib.request
import zipfile
import tempfile

GEONAMES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "suburb_corrections.json")

# Thresholds
SMALL_POP = 500_000    # cities below this are "suburbs" candidates
BIG_POP = 500_000      # cities above this are "metros"
MAX_DIST_KM = 30       # max distance to associate suburb with metro
POP_RATIO = 3          # metro must be at least this many times bigger


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def main():
    # Download and extract
    print("Downloading GeoNames cities15000...")
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "cities15000.zip")
        urllib.request.urlretrieve(GEONAMES_URL, zip_path)

        with zipfile.ZipFile(zip_path) as zf:
            zf.extract("cities15000.txt", tmpdir)
        txt_path = os.path.join(tmpdir, "cities15000.txt")

        # Parse: geonameid, name, asciiname, alternatenames, lat, lng,
        #        feature_class, feature_code, country_code, cc2,
        #        admin1, admin2, admin3, admin4, population, ...
        print("Parsing cities...")
        cities = []
        with open(txt_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 15:
                    continue
                name = parts[1]
                alt_names = parts[3].split(",") if parts[3] else []
                lat = float(parts[4])
                lng = float(parts[5])
                cc = parts[8]
                try:
                    pop = int(parts[14])
                except ValueError:
                    pop = 0
                cities.append({
                    "name": name, "alt_names": alt_names,
                    "lat": lat, "lng": lng,
                    "cc": cc, "pop": pop,
                })

        print(f"  {len(cities)} cities loaded")

        # Separate into big and small
        big = [c for c in cities if c["pop"] >= BIG_POP]
        small = [c for c in cities if 0 < c["pop"] < SMALL_POP]
        print(f"  {len(big)} metros (pop >= {BIG_POP:,})")
        print(f"  {len(small)} small cities (pop < {SMALL_POP:,})")

        # For each small city, find nearest big city within MAX_DIST_KM
        # that is at least POP_RATIO times larger
        corrections = {}
        for s in small:
            best_dist = MAX_DIST_KM
            best_metro = None
            for b in big:
                # Quick lat/lng filter before haversine (~0.3° ≈ 30km)
                if abs(s["lat"] - b["lat"]) > 0.3 or abs(s["lng"] - b["lng"]) > 0.4:
                    continue
                if b["pop"] < s["pop"] * POP_RATIO:
                    continue
                dist = haversine_km(s["lat"], s["lng"], b["lat"], b["lng"])
                if dist < best_dist:
                    best_dist = dist
                    best_metro = b

            if best_metro and best_metro["name"] != s["name"]:
                key = f"{s['name']}|{s['cc']}"
                corrections[key] = best_metro["name"]
                # Also add corrections for key alternate names
                # Only include names that start with uppercase (proper names)
                for alt in s["alt_names"]:
                    alt = alt.strip()
                    if (alt and alt != s["name"] and alt != best_metro["name"]
                            and len(alt) > 2 and alt[0].isupper()
                            and all(ord(c) < 0x250 for c in alt)):  # Latin Extended
                        alt_key = f"{alt}|{s['cc']}"
                        if alt_key not in corrections:
                            corrections[alt_key] = best_metro["name"]

        # Manual overrides for names the offline geocoder returns
        # that aren't in GeoNames cities15000
        manual = {
            "Deerfield|US": "Denver",
            "Lakeway|US": "Austin",
            "Bee Cave|US": "Austin",
            "West Lake Hills|US": "Austin",
            "Rollingwood|US": "Austin",
        }
        for k, v in manual.items():
            corrections[k] = v

        # Fix metro-cluster corrections (e.g., Gunpo→Suwon should be Gunpo→Seoul)
        # For cities near multiple large metros, prefer the largest one
        metro_overrides = {
            "Seoul": ["Suwon", "Incheon"],  # Seoul metro area
            "Tokyo": ["Kawasaki", "Yokohama", "Saitama"],
            "London": ["Croydon"],
            "Paris": ["Boulogne-Billancourt", "Saint-Denis", "Argenteuil"],
            "Shanghai": ["Suzhou"],
            "Beijing": ["Langfang"],
        }
        # Build reverse: Suwon → Seoul, Incheon → Seoul for override targets
        override_map = {}
        for mega, subordinates in metro_overrides.items():
            for sub in subordinates:
                override_map[sub] = mega
        # Apply: if a correction points to a subordinate metro, redirect to the megacity
        for k, v in list(corrections.items()):
            if v in override_map:
                corrections[k] = override_map[v]

        print(f"\n{len(corrections)} suburb → metro corrections generated")

        # Show some examples
        examples = list(corrections.items())[:20]
        for k, v in examples:
            print(f"  {k} → {v}")

        # Save
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(corrections, f, ensure_ascii=False, separators=(",", ":"))

        size_kb = os.path.getsize(OUTPUT_PATH) / 1024
        print(f"\nSaved to {OUTPUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
