# Swarm-FM

Compare your Last.fm scrobble history against your Foursquare/Swarm checkins — generates a self-contained HTML dashboard with no database, no server, just Python and a browser.

**What you get:** an interactive dashboard showing where and how you listen to music — attributed scrobbles by venue, venue type, city, and country; a world map of listening hotspots; trip detection with per-trip listening stats; day-of-week and monthly patterns for both plays and checkins; and a travel artist affinity chart showing which artists you reach for on the road.

**[Try it in your browser](https://jpgamboa.github.io/Swarm-FM/)** — no install required, runs entirely client-side.

## Web App

A browser-based version is available at the project's GitHub Pages site — no Python install needed. Everything runs client-side via [Pyodide](https://pyodide.org/) (Python compiled to WebAssembly).

1. Visit the [hosted page](https://jpgamboa.github.io/Swarm-FM/) (or serve `docs/` locally: `cd docs && python3 -m http.server 8765`)
2. Drop your Last.fm CSV + Foursquare JSON exports
3. Files are parsed and correlated in your browser
4. Download the generated dashboard HTML

**To deploy your own instance:** push this repo to GitHub, then go to Settings > Pages > Source: deploy from branch `main`, folder `/docs`.

After editing the source Python files, run `./build_web.sh` to sync them into `docs/`.

## How correlation works

A scrobble is attributed to a venue if it occurred within a **per-category time window** after a checkin. Different venue types get different windows:

| Venue type | Window |
|---|---|
| Transit, hotel, work | 4 hours |
| Coffee shop, bar/brewery | 3 hours |
| Restaurant, music venue | 1.5 hours |
| Gym, outdoor | 2 hours |
| Shopping | 1 hour |
| Cinema | 30 min |
| Other | 3 hours |

**Weekday lunch suppression:** restaurant checkins on weekdays between 10am–4pm are not attributed, to avoid false positives from work-adjacent dining.

The most recent matching checkin wins if windows overlap.

**Home city** is inferred automatically from your checkin patterns. If you moved during the period covered by your data, Swarm-FM detects the transition using a rolling 90-day window and tracks multiple home periods (e.g. Shanghai 2011–2013 → Austin 2013–2023). Lunch suppression, trip detection, and travel artist analysis all respect the home city that was active at each point in time.

**Trips** are detected by finding consecutive days where all checkins are outside your home city. Gaps of up to 7 days are tolerated. Trips must be at least 2 days and have at least 5 scrobbles to appear in the dashboard. Trip type (flight, train, or road) is inferred from venue names during the trip.

**Map:** the dashboard map shows two layers — green dots for cities with attributed music plays, and gray dots for all other visited cities.

## Run App Locally

## Requirements

- Python 3.8+
- No external packages needed — stdlib only
- No API keys needed — everything runs from local export files

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/swarmfm.git
cd swarmfm
```

**2. Export your Last.fm history**

Go to https://lastfmstats.com/, enter your username, and export your scrobble history as CSV. Save it somewhere on your machine.

Also accepts CSVs from [benjaminbenben.com/lastfm-to-csv](https://benjaminbenben.com/lastfm-to-csv/) and the official Last.fm GDPR export.

**3. Export your Foursquare/Swarm history**

Request a data export through Foursquare (exports both City Guide and Swarm data together):

**On the web:** Log in at foursquare.com → click your name (top right) → Settings → Privacy Settings → Initiate Data Download Request

**In the Swarm app:** Profile (top left) → gear icon → Settings → Privacy Settings → Initiate Data Download Request

You'll get a confirmation email from `noreply@legal.foursquare.com`, then a second email with a download link when your data is ready (up to 7 days). Extract the zip — you'll get a folder containing `checkins1.json`, `checkins2.json`, etc.

**4. Configure**
```bash
cp config.py.example config.py
```
Edit `config.py` and set:
- `LASTFM_EXPORT_FILE` — path to your Last.fm CSV file
- `FOURSQUARE_EXPORT_DIR` — path to your Foursquare export folder

## Usage

**Run the full pipeline:**
```bash
python3 run.py
```

**Or run individual steps:**
```bash
python3 run.py lastfm       # Step 1: import Last.fm CSV
python3 run.py foursquare   # Step 2: import Foursquare checkins + geocode
python3 run.py correlate    # Step 3: correlate scrobbles with checkins
python3 run.py dashboard    # Step 4: generate dashboard
```

Then open `data/dashboard.html` in any browser.

## Pipeline overview

| Step | Script | Input | Output |
|------|--------|-------|--------|
| 1. Last.fm | `import_lastfm.py` | Last.fm CSV export | `data/scrobbles.json` |
| 2. Foursquare | `import_foursquare.py` + `geocode.py` | Export folder | `data/checkins.json` |
| 3. Correlate | `correlate.py` | Scrobbles + checkins | `data/correlated.json` |
| 4. Dashboard | `generate_dashboard.py` | Correlated + scrobbles | `data/dashboard.html` |

## About geocoding

Step 2 reverse-geocodes every checkin's lat/lng coordinates to city + country using the [Nominatim API](https://nominatim.org/) (OpenStreetMap, free, no key required). Results are cached in `data/geo_cache.json`. The first run over a large checkin history (~1,400 unique locations) takes about 25 minutes at Nominatim's 1 req/sec rate limit; all subsequent runs are instant.

## Data privacy

All data stays on your machine. No tracking, cookies, or analytics.

- **Client-side processing** — both the CLI and web versions process your data locally. The web app runs entirely in your browser via Pyodide (Python in WebAssembly). Your Last.fm and Foursquare files are never uploaded to any server.
- **Nominatim geocoding** — the only network requests containing location data are to [OpenStreetMap's Nominatim](https://nominatim.openstreetmap.org) service, used to resolve coordinates to city/country names. Coordinates are rounded to ~1 km (CLI) or ~10 km (web) before lookup. See the [OSM Foundation privacy policy](https://osmfoundation.org/wiki/Privacy_Policy).
- **Pre-built location cache** — the web version ships a `geo_seed.json` file to reduce Nominatim requests. It contains only coordinate-to-city mappings (e.g. `"40.1,-74.2" → "New York, US"`) at ~10 km grid resolution. No venue names, timestamps, or personally identifying information.
- **Browser localStorage** — geocoding results are cached in your browser's `localStorage` for faster subsequent runs. You can clear this anytime via your browser's developer tools.
- **Config and data files** — `config.py` and the `data/` directory are gitignored by default.
