#!/usr/bin/env python3
"""Proxy Flask: récupère calendrier ForexFactory, sert JSON formaté fxverify-style.
Usage: .venv-proxy/bin/python proxy_calendar.py
Port: 5000
"""
import json
import re
import time
import urllib.request
from flask import Flask, jsonify, request, send_from_directory
import os

app = Flask(__name__)

DIR = os.path.dirname(os.path.abspath(__file__))


@app.route("/")
def index():
    return send_from_directory(DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(DIR, filename)


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET"
    return resp

CACHE = {"events": [], "fetched": 0}


def quote_keys(js_obj: str) -> str:
    """Quote bare JS object keys for JSON compatibility."""
    s = re.sub(r'([,{])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', js_obj)
    s = re.sub(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', s)
    return s


def parse_ff_html(html: str) -> list:
    """Extract and parse calendarComponentStates[1].days from FF HTML."""
    idx = html.find("window.calendarComponentStates[1]")
    if idx == -1:
        raise ValueError("calendarComponentStates[1] not found")
    chunk = html[idx:]
    m = re.search(r"days\s*:\s*(\[.*?\])\s*,", chunk, re.DOTALL)
    if not m:
        raise ValueError("days array not found")
    raw_days = m.group(1)
    try:
        fixed = quote_keys(raw_days)
        days = json.loads(fixed)
    except json.JSONDecodeError:
        # fallback: try with demjson3 / json5 if installed
        try:
            import json5
            days = json5.loads(raw_days)
        except (ImportError, Exception):
            import demjson3
            days = demjson3.decode(raw_days)

    events = []
    for day in days:
        date = day.get("date", "").replace("<span>", "").replace("</span>", "").strip()
        for ev in day.get("events", []):
            events.append(
                {
                    "date": date,
                    "time": ev.get("timeLabel", ""),
                    "timeMasked": ev.get("timeMasked", False),
                    "currency": ev.get("currency", ""),
                    "event": ev.get("trimmedPrefixedName", ev.get("name", "")),
                    "impact": ev.get("impactName", "low"),
                    "impactTitle": ev.get("impactTitle", ""),
                    "actual": ev.get("actual", ""),
                    "forecast": ev.get("forecast", ""),
                    "previous": ev.get("previous", ""),
                    "revision": ev.get("revision", ""),
                    "actualBetterWorse": ev.get("actualBetterWorse", 0),
                    "dateline": ev.get("dateline", 0),
                }
            )
    return events


def fetch_calendar() -> list:
    url = "https://www.forexfactory.com/calendar/summary"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_ff_html(html)


def refresh_cache():
    try:
        CACHE["events"] = fetch_calendar()
        CACHE["fetched"] = time.time()
        print(f"[calendar] {len(CACHE['events'])} events loaded")
    except Exception as e:
        print(f"[calendar] refresh error: {e}")


@app.route("/calendar")
def calendar():
    if time.time() - CACHE["fetched"] > 300:
        refresh_cache()
    events = list(CACHE["events"])

    # filtre today
    day_filter = request.args.get("day", "")
    if day_filter == "today":
        import datetime
        now = datetime.datetime.now()
        days_fr = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
        days_en = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        wd = now.weekday()
        months = ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"]
        months_en = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        today_fr = f"{days_fr[wd]} {now.day} {months[now.month-1]}"
        today_en = f"{days_en[wd]} {months_en[now.month-1]} {now.day}"
        events = [e for e in events if e["date"] in (today_fr, today_en)]

    # filtre impact
    impact_filter = request.args.get("impact", "")
    if impact_filter:
        impacts = set(impact_filter.split(","))
        events = [e for e in events if e["impact"] in impacts]

    # filtre devise
    currency_filter = request.args.get("currency", "")
    if currency_filter:
        currencies = set(currency_filter.split(","))
        events = [e for e in events if e["currency"] in currencies]

    return jsonify(events)


@app.route("/calendar/refresh")
def calendar_refresh():
    refresh_cache()
    return jsonify({"ok": True, "count": len(CACHE["events"])})


if __name__ == "__main__":
    print("[calendar] fetching initial data...")
    refresh_cache()
    print("[calendar] serving on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
