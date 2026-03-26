#!/usr/bin/env python3
"""
Step 4: Generate Foursquare dashboard
=======================================
Reads data/scrobbles.json, data/checkins.json, and data/correlated.json,
computes the data needed for the Foursquare tab, and generates
data/dashboard.html from foursquare_template.html.

Usage:
    python musicbrain.py dashboard
Or standalone:
    python generate_dashboard.py
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _parse_ts(ts):
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' to datetime."""
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def _normalize_trips(raw_trips):
    """
    Normalize correlate.py trip output into the shape the template expects.
    Filters out trips with zero scrobbles.
    """
    out = []
    for t in raw_trips:
        duration = t.get("duration_days", 0)
        plays = t.get("scrobble_count", 0)
        if plays == 0:
            continue
        top_artists = [{"artist": a["artist"], "count": a["plays"]}
                       for a in t.get("top_artists", [])]
        tracks = t.get("top_tracks", [])
        top_track = f"{tracks[0]['artist']} \u2014 {tracks[0]['track']}" if tracks else None
        ccs = [c["country_code"] for c in t.get("countries", [])]
        score = t.get("music_intensity", round(plays / max(duration, 1), 1))
        out.append({
            "start":        t["start"],
            "end":          t["end"],
            "days":         duration,
            "plays":        plays,
            "checkins":     t.get("checkins", 0),
            "destination":  t.get("destination", ""),
            "ccs":          ccs,
            "trip_type":    t.get("trip_type", "flight"),
            "music_score":  score,
            "top_artists":  top_artists,
            "top_track":    top_track,
        })
    return out


def run(data_dir="./data", template_path=None):
    if template_path is None:
        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "foursquare_template.html",
        )

    scrobbles_path  = os.path.join(data_dir, "scrobbles.json")
    checkins_path   = os.path.join(data_dir, "checkins.json")
    correlated_path = os.path.join(data_dir, "correlated.json")
    out_path        = os.path.join(data_dir, "dashboard.html")

    print("Loading data...")

    # ── Scrobbles ─────────────────────────────────────────────────────────────
    if not os.path.exists(scrobbles_path):
        print(f"  \u2717  scrobbles.json not found at {scrobbles_path}. Aborting.")
        return

    scrobbles = _load(scrobbles_path, [])
    checkins  = _load(checkins_path, [])
    print(f"  {len(scrobbles):,} scrobbles, {len(checkins):,} checkins")

    # ── plays_by_month ────────────────────────────────────────────────────────
    month_counter = Counter()
    dow_counter   = Counter()
    date_counter  = Counter()

    for s in scrobbles:
        ts = s.get("timestamp", "")
        try:
            dt = _parse_ts(ts)
            month_counter[dt.strftime("%Y-%m")] += 1
            dow_counter[dt.weekday()] += 1
            date_counter[dt.date().isoformat()] += 1
        except Exception:
            pass

    plays_by_month = [{"month": m, "count": c} for m, c in sorted(month_counter.items())]
    plays_by_dow   = [dow_counter.get(i, 0) for i in range(7)]
    plays_by_date  = dict(date_counter)
    total_plays    = len(scrobbles)

    # ── Listening history metrics ────────────────────────────────────────────
    # Parse all scrobbles into enriched rows
    rows = []
    for s in scrobbles:
        ts = s.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = _parse_ts(ts)
        except Exception:
            continue
        rows.append({
            **s,
            "_dt":    dt,
            "_year":  str(dt.year),
            "_month": dt.strftime("%Y-%m"),
            "_hour":  dt.hour,
            "_dow":   dt.weekday(),
        })

    years = sorted(set(r["_year"] for r in rows))
    unique_artists = len(set(r.get("artist", "") for r in rows))
    unique_albums  = len(set(
        f"{r.get('artist','')}|||{r.get('album','')}"
        for r in rows if r.get("album")
    ))

    # Top artists all time
    artist_total = Counter(r.get("artist", "") for r in rows)
    top_artists_all = [
        {"artist": a, "total": c}
        for a, c in artist_total.most_common(50) if a
    ]
    by_year_artist = defaultdict(Counter)
    for r in rows:
        a = r.get("artist", "")
        if a:
            by_year_artist[r["_year"]][a] += 1
    top_artists_by_year = {
        yr: [{"artist": a, "count": c} for a, c in ctr.most_common(15)]
        for yr, ctr in by_year_artist.items()
    }

    # Top albums all time
    album_total = Counter(
        (r.get("artist", ""), r.get("album", ""))
        for r in rows if r.get("album")
    )
    top_albums_all = [
        {"album": al, "artist": ar, "count": c}
        for (ar, al), c in album_total.most_common(30) if al
    ]
    by_year_album = defaultdict(Counter)
    for r in rows:
        if r.get("album"):
            by_year_album[r["_year"]][(r.get("artist", ""), r.get("album", ""))] += 1
    top_albums_by_year = {
        yr: [{"album": al, "artist": ar, "count": c}
             for (ar, al), c in ctr.most_common(15)]
        for yr, ctr in by_year_album.items()
    }

    # Top listening days
    day_counter_dt = Counter(r["_dt"].date() for r in rows)
    top_days = []
    for d, count in day_counter_dt.most_common(20):
        day_artists = Counter(
            r.get("artist", "") for r in rows if r["_dt"].date() == d
        ).most_common(1)
        top_a, top_c = day_artists[0] if day_artists else ("", 0)
        top_days.append({"date": str(d), "count": count,
                         "top_artist": top_a, "top_artist_count": top_c})

    # Sessions (30-min gap threshold)
    sorted_rows = sorted(rows, key=lambda r: r["_dt"])
    sessions = []
    if sorted_rows:
        session = [sorted_rows[0]]
        for r in sorted_rows[1:]:
            if (r["_dt"] - session[-1]["_dt"]).total_seconds() < 1800:
                session.append(r)
            else:
                sessions.append(session)
                session = [r]
        sessions.append(session)

    top_sessions = []
    for s in sorted(sessions, key=len, reverse=True)[:15]:
        dur_h = (s[-1]["_dt"] - s[0]["_dt"]).total_seconds() / 3600
        top_a = [a for a, _ in Counter(r.get("artist", "") for r in s).most_common(3)]
        top_sessions.append({
            "date": str(s[0]["_dt"].date()), "start": s[0]["_dt"].strftime("%H:%M"),
            "tracks": len(s), "hours": round(dur_h, 1), "top_artists": top_a,
        })

    avg_session_by_year = {}
    for yr in years:
        yr_sess = [s for s in sessions if str(s[0]["_dt"].year) == yr]
        if yr_sess:
            avg_session_by_year[yr] = round(sum(len(s) for s in yr_sess) / len(yr_sess), 1)

    # Hour / DOW patterns
    hour_counts = Counter(r["_hour"] for r in rows)
    plays_by_hour = [hour_counts.get(h, 0) for h in range(24)]
    by_year_hour = defaultdict(Counter)
    by_year_dow  = defaultdict(Counter)
    for r in rows:
        by_year_hour[r["_year"]][r["_hour"]] += 1
        by_year_dow[r["_year"]][r["_dow"]]   += 1
    plays_by_hour_by_year = {yr: [ctr.get(h, 0) for h in range(24)]
                             for yr, ctr in by_year_hour.items()}
    plays_by_dow_by_year  = {yr: [ctr.get(d, 0) for d in range(7)]
                             for yr, ctr in by_year_dow.items()}

    # New artist discoveries per year
    artist_first_year = {}
    for r in sorted_rows:
        a = r.get("artist", "")
        if a and a not in artist_first_year:
            artist_first_year[a] = r["_year"]
    first_year_counts = Counter(artist_first_year.values())
    new_artists_per_year = [{"year": yr, "count": first_year_counts.get(yr, 0)} for yr in years]

    # Artist loyalty (heard in N years)
    artist_years_set = defaultdict(set)
    for r in rows:
        artist_years_set[r.get("artist", "")].add(r["_year"])
    total_years = len(years)
    loyalty = sorted(
        [{"artist": a, "years_count": len(yrs), "years": sorted(yrs),
          "total_plays": artist_total.get(a, 0)}
         for a, yrs in artist_years_set.items()
         if a and len(yrs) >= max(3, total_years // 3)],
        key=lambda x: (-x["years_count"], -x["total_plays"]),
    )[:30]

    # Winners & losers (trending artists)
    year_totals = {yr: sum(by_year_artist[yr].values()) for yr in years}
    int_years = sorted(int(y) for y in years)
    recent_cutoff = int_years[-1] - 2 if int_years else 0
    faded = []
    rising = []
    for artist, total in artist_total.items():
        if not artist or total < 50:
            continue
        yr_shares = {}
        for yr in years:
            c = by_year_artist[yr].get(artist, 0)
            if year_totals.get(yr):
                yr_shares[int(yr)] = c / year_totals[yr] * 1000
        active_years = [y for y, s in yr_shares.items() if s > 0]
        if len(active_years) < 3:
            continue
        peak_yr  = max(yr_shares, key=yr_shares.get)
        peak_val = yr_shares[peak_yr]
        recent_vals = [yr_shares.get(y, 0) for y in int_years if y >= recent_cutoff]
        older_vals  = [yr_shares.get(y, 0) for y in int_years if y < recent_cutoff and yr_shares.get(y, 0) > 0]
        if not recent_vals or not older_vals:
            continue
        recent_avg = sum(recent_vals) / len(recent_vals)
        older_avg  = sum(older_vals)  / len(older_vals)
        if peak_yr < recent_cutoff and older_avg > 0 and peak_val >= 0.5:
            fade_ratio = older_avg / max(recent_avg, 0.01)
            if fade_ratio >= 3 and older_avg >= 0.3:
                faded.append({"artist": artist, "total_plays": total, "peak_year": peak_yr,
                              "fade_ratio": round(fade_ratio, 1),
                              "by_year": {str(y): round(yr_shares.get(y, 0), 3) for y in int_years}})
        if recent_avg > older_avg * 2 and recent_avg >= 0.3 and peak_yr >= recent_cutoff:
            rise_ratio = recent_avg / max(older_avg, 0.01)
            rising.append({"artist": artist, "total_plays": total, "peak_year": peak_yr,
                           "rise_ratio": round(rise_ratio, 1),
                           "by_year": {str(y): round(yr_shares.get(y, 0), 3) for y in int_years}})
    faded.sort(key=lambda x: -x["fade_ratio"])
    rising.sort(key=lambda x: -x["rise_ratio"])
    trends = {"faded": faded[:20], "rising": rising[:20], "recent_cutoff": recent_cutoff}

    # Personal records per year
    records_by_year = {}
    by_year_day = defaultdict(Counter)
    for r in rows:
        by_year_day[r["_year"]][r["_dt"].date()] += 1
    by_year_sessions = defaultdict(list)
    for s in sessions:
        by_year_sessions[str(s[0]["_dt"].year)].append(s)
    for yr in years:
        yr_rows = [r for r in rows if r["_year"] == yr]
        yr_dates = sorted(set(r["_dt"].date() for r in yr_rows))
        # Streak
        best_str = 0
        run = 1
        if yr_dates:
            for i in range(1, len(yr_dates)):
                if (yr_dates[i] - yr_dates[i - 1]).days == 1:
                    run += 1
                    best_str = max(best_str, run)
                else:
                    run = 1
            best_str = max(best_str, run)
        yr_top_day = by_year_day[yr].most_common(1)
        yr_sess = by_year_sessions.get(yr, [])
        yr_top_sess = max(yr_sess, key=len) if yr_sess else None
        records_by_year[yr] = {
            "total_plays": len(yr_rows),
            "unique_artists": len(set(r.get("artist", "") for r in yr_rows)),
            "unique_albums": len(set((r.get("artist", ""), r.get("album", "")) for r in yr_rows if r.get("album"))),
            "top_day_count": yr_top_day[0][1] if yr_top_day else 0,
            "top_day_date": str(yr_top_day[0][0]) if yr_top_day else "",
            "longest_session_tracks": len(yr_top_sess) if yr_top_sess else 0,
            "longest_streak": best_str,
        }

    # All-time streak
    all_dates = sorted(set(r["_dt"].date() for r in rows))
    all_best_str = 0
    run = 1
    if all_dates:
        for i in range(1, len(all_dates)):
            if (all_dates[i] - all_dates[i - 1]).days == 1:
                run += 1
                all_best_str = max(all_best_str, run)
            else:
                run = 1
        all_best_str = max(all_best_str, run)

    listening_history = {
        "meta": {
            "total_plays": total_plays,
            "unique_artists": unique_artists,
            "unique_albums": unique_albums,
            "years": years,
            "date_range": [plays_by_month[0]["month"], plays_by_month[-1]["month"]] if plays_by_month else [],
            "longest_streak": all_best_str,
            "most_plays_day": top_days[0] if top_days else None,
            "longest_session": top_sessions[0] if top_sessions else None,
        },
        "top_artists_all": top_artists_all,
        "top_artists_by_year": top_artists_by_year,
        "top_albums_all": top_albums_all,
        "top_albums_by_year": top_albums_by_year,
        "top_days": top_days,
        "top_sessions": top_sessions,
        "avg_session_by_year": avg_session_by_year,
        "plays_by_hour": plays_by_hour,
        "plays_by_hour_by_year": plays_by_hour_by_year,
        "plays_by_dow_by_year": plays_by_dow_by_year,
        "new_artists_per_year": new_artists_per_year,
        "loyalty": loyalty,
        "trends": trends,
        "records_by_year": records_by_year,
    }
    print(f"  Listening history: {len(years)} years, {unique_artists:,} artists, {unique_albums:,} albums")

    # ── Foursquare basics from checkins.json ─────────────────────────────────
    fs_by_month = Counter()
    fs_by_dow   = Counter()
    fs_by_date  = Counter()
    fs_venues   = Counter()

    for c in checkins:
        ts  = c.get("timestamp", "")
        try:
            dt = _parse_ts(ts)
            fs_by_month[dt.strftime("%Y-%m")] += 1
            fs_by_dow[dt.weekday()]            += 1
            fs_by_date[dt.date().isoformat()]  += 1
        except Exception:
            pass
        fs_venues[c.get("venue_name", "Unknown")] += 1

    date_range = []
    if fs_by_date:
        sorted_dates = sorted(fs_by_date)
        date_range = [sorted_dates[0][:7], sorted_dates[-1][:7]]

    # Find first checkin timestamp for attributed_pct denominator
    first_checkin_ts = None
    if checkins:
        try:
            first_checkin_ts = _parse_ts(
                min(c["timestamp"] for c in checkins if c.get("timestamp"))
            )
        except Exception:
            pass

    plays_since_checkins = total_plays
    if first_checkin_ts:
        plays_since_checkins = sum(
            1 for s in scrobbles
            if s.get("timestamp") and s["timestamp"] >= first_checkin_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    # ── correlated.json ───────────────────────────────────────────────────────
    if not os.path.exists(correlated_path):
        print(f"  correlated.json not found — running correlate.run({data_dir!r})...")
        try:
            import correlate
            correlate.run(data_dir)
        except Exception as e:
            print(f"  \u2717  Could not run correlate.run(): {e}")
    correlated = _load(correlated_path, {})

    home_obj   = correlated.get("home", {})
    home_city  = home_obj.get("city", "")
    home_cc    = home_obj.get("country_code", "")
    home_label = f"{home_city}, {home_cc}" if home_city and home_cc else home_city or home_cc or "unknown"
    print(f"  Home: {home_label}")

    attributed_plays = correlated.get("attributed", 0)
    attributed_pct   = round(
        attributed_plays / max(plays_since_checkins, 1) * 100, 1
    ) if plays_since_checkins else 0.0

    raw_trips      = correlated.get("trips", [])
    normalized_trips = _normalize_trips(raw_trips)

    # ── Assemble foursquare block ─────────────────────────────────────────────
    foursquare = {
        "total":            len(checkins),
        "unique_venues":    len(fs_venues),
        "date_range":       date_range,
        "home":             home_label,
        "by_month":         [{"month": m, "count": c} for m, c in sorted(fs_by_month.items())],
        "by_dow":           [fs_by_dow.get(i, 0) for i in range(7)],
        "by_date":          dict(fs_by_date),
        "top_venues":       [{"name": n, "count": c} for n, c in fs_venues.most_common(30)],
        "venue_plays":      correlated.get("venue_plays", []),
        "by_category":      correlated.get("by_category", []),
        "by_city":          correlated.get("by_city", []),
        "by_country":       correlated.get("by_country", []),
        "attributed_plays": attributed_plays,
        "attributed_pct":   attributed_pct,
        "all_checkin_cities": correlated.get("all_checkin_cities", []),
        "travel_artists":   correlated.get("travel_artists", []),
        "trips":            normalized_trips,
    }

    data = {
        "total_plays":       total_plays,
        "plays_by_month":    plays_by_month,
        "plays_by_dow":      plays_by_dow,
        "plays_by_date":     plays_by_date,
        "listening_history": listening_history,
        "foursquare":        foursquare,
    }

    # ── Inject into template ──────────────────────────────────────────────────
    if not os.path.exists(template_path):
        print(f"  \u2717  Template not found: {template_path}")
        return

    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    data_js  = f"const DASHBOARD_DATA = {json.dumps(data, ensure_ascii=False)};"
    html = re.sub(
        r"/\* DATA_INJECT_POINT \*/.*?/\* END_DATA_INJECT \*/",
        f"/* DATA_INJECT_POINT */\n{data_js}\n/* END_DATA_INJECT */",
        html,
        flags=re.DOTALL,
    )

    print(f"Writing dashboard \u2192 {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\u2713  Open {out_path} in a browser")


if __name__ == "__main__":
    try:
        import config
    except ImportError:
        print("Error: config.py not found.")
        raise SystemExit(1)
    run(config.DATA_DIR)
