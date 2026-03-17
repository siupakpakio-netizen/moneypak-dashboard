#!/usr/bin/env python3
"""Auto-update dashboard data from Google Sheet"""
import json, urllib.request, re

SHEET_ID = "1xqfcjSPHaHg-4n7k8t0eMmJ6X6eL9sMB6tc04_PUD-8"
GIDS = {"trades": 0, "history": 1139931391}

def fetch_sheet(gid):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:json&gid={gid}"
    with urllib.request.urlopen(url) as r:
        text = r.read().decode()
    return json.loads(text[47:-2])

def main():
    # Fetch latest data and update dashboard_data.json
    # This is run by GitHub Actions
    data = {"lastUpdate": "", "positions": [], "trades": [], "history": []}
    # ... (update logic)
    with open("dashboard_data.json", "w") as f:
        json.dump(data, f, indent=2)
    print("✅ Data updated")

if __name__ == "__main__":
    main()
