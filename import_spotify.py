#!/usr/bin/env python3
"""
Import Spotify extended streaming history
==========================================
Parses Spotify's extended streaming history JSON files
(Streaming_History_Audio_*.json) and saves as data/scrobbles.json.

Spotify's extended history includes rich metadata:
  - ms_played: actual playback duration in milliseconds
  - skipped: whether the track was skipped
  - platform: device/app used for playback
  - shuffle: whether shuffle mode was active
  - reason_start / reason_end: playback triggers
  - offline: whether playback was offline

Podcasts (entries with episode_name set) are separated into
data/podcasts.json automatically.

Tracks played for less than 30 seconds are treated as skips.

Usage:
    from import_spotify import parse
    parse("/path/to/spotify_export", "./data")

Or standalone:
    python import_spotify.py
"""

import glob
import json
import os
from datetime import datetime, timezone, timedelta

MIN_PLAY_MS = 30_000  # 30 seconds — below this is a skip


def _parse_ts(ts_str):
    """Parse Spotify timestamp to UTC ISO 8601. Spotify ts is when stream ended."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def parse(export_dir, data_dir="./data"):
    os.makedirs(data_dir, exist_ok=True)

    # Find all streaming history audio files
    patterns = [
        os.path.join(export_dir, "Streaming_History_Audio_*.json"),
        os.path.join(export_dir, "endsong_*.json"),
    ]
    files = []
    for pat in patterns:
        files.extend(sorted(glob.glob(pat)))
    if not files:
        print(f"  ✗  No Spotify streaming history files found in: {export_dir}")
        print(f"     Expected: Streaming_History_Audio_*.json or endsong_*.json")
        return []

    scrobbles = []
    podcasts = []
    skipped_short = 0
    skipped_no_track = 0

    for path in files:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        print(f"  {os.path.basename(path)}: {len(entries):,} entries")

        for entry in entries:
            ts_raw = entry.get("ts", "")
            dt_end = _parse_ts(ts_raw)
            if not dt_end:
                continue

            ms_played = entry.get("ms_played", 0) or 0

            # Compute start time (Spotify records end time)
            dt_start = dt_end - timedelta(milliseconds=ms_played)
            timestamp = dt_start.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Podcast episode
            episode_name = entry.get("episode_name")
            episode_show = entry.get("episode_show_name")
            if episode_name and episode_show:
                if ms_played >= MIN_PLAY_MS:
                    podcasts.append({
                        "timestamp": timestamp,
                        "show": episode_show,
                        "episode": episode_name,
                        "ms_played": ms_played,
                        "platform": entry.get("platform", ""),
                    })
                continue

            # Music track
            artist = (entry.get("master_metadata_album_artist_name") or "").strip()
            track = (entry.get("master_metadata_track_name") or "").strip()
            album = (entry.get("master_metadata_album_album_name") or "").strip()

            if not artist or not track:
                skipped_no_track += 1
                continue

            is_skipped = entry.get("skipped") or ms_played < MIN_PLAY_MS
            if ms_played < MIN_PLAY_MS:
                skipped_short += 1

            scrobble = {
                "timestamp": timestamp,
                "artist": artist,
                "track": track,
                "album": album,
                # Spotify-specific fields
                "ms_played": ms_played,
                "skipped": bool(is_skipped),
                "platform": entry.get("platform", ""),
                "shuffle": bool(entry.get("shuffle")),
                "offline": bool(entry.get("offline")),
                "reason_start": entry.get("reason_start", ""),
                "reason_end": entry.get("reason_end", ""),
            }
            scrobbles.append(scrobble)

    scrobbles.sort(key=lambda s: s["timestamp"])

    # Write scrobbles (including short plays — let downstream decide)
    out_path = os.path.join(data_dir, "scrobbles.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scrobbles, f, ensure_ascii=False, indent=2)

    # Write podcasts separately
    if podcasts:
        podcasts.sort(key=lambda p: p["timestamp"])
        pod_path = os.path.join(data_dir, "podcasts.json")
        with open(pod_path, "w", encoding="utf-8") as f:
            json.dump(podcasts, f, ensure_ascii=False, indent=2)
        pod_hours = sum(p["ms_played"] for p in podcasts) / 3_600_000
        print(f"  {len(podcasts):,} podcast episodes → {pod_path} "
              f"({pod_hours:,.0f} hours)")

    # Summary
    total_ms = sum(s["ms_played"] for s in scrobbles)
    total_hours = total_ms / 3_600_000
    actual_plays = sum(1 for s in scrobbles if not s["skipped"])
    skip_count = sum(1 for s in scrobbles if s["skipped"])

    print(f"  {len(scrobbles):,} tracks ({actual_plays:,} played, "
          f"{skip_count:,} skipped/short)")
    if scrobbles:
        print(f"  {total_hours:,.0f} hours of music")
        print(f"  Date range: {scrobbles[0]['timestamp'][:10]} "
              f"→ {scrobbles[-1]['timestamp'][:10]}")
    print(f"✓  Saved → {out_path}")
    return scrobbles


if __name__ == "__main__":
    try:
        import config
    except ImportError:
        print("Error: config.py not found.")
        raise SystemExit(1)
    export_dir = getattr(config, "SPOTIFY_EXPORT_DIR", "")
    if not export_dir:
        print("SPOTIFY_EXPORT_DIR not set in config.py — skipping.")
    else:
        parse(export_dir, config.DATA_DIR)
