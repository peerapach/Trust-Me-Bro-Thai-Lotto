#!/usr/bin/env python3
"""Fetch new Thai lottery draws from GLO API and prepend them to glo.csv."""

import os
import sys
import requests
from datetime import datetime, date

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glo.csv")
API_URL = "https://www.glo.or.th/api/lottery/getLotteryResultByYear"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.glo.or.th",
    "Referer": "https://www.glo.or.th/mission/awarding/orderby-time",
}

THAI_MONTHS = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม",
}
MONTH_TO_NUM = {v: k for k, v in THAI_MONTHS.items()}


def read_csv():
    with open(CSV_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    header = lines[0]
    body_lines = [l.rstrip("\n") for l in lines[1:] if l.strip()]

    existing_dates: set[date] = set()
    for line in body_lines:
        parts = line.split("|")
        if len(parts) >= 3:
            month_num = MONTH_TO_NUM.get(parts[1])
            if month_num:
                try:
                    d = date(int(parts[2]) - 543, month_num, int(parts[0]))
                    existing_dates.add(d)
                except ValueError:
                    pass

    return header, body_lines, existing_dates


def fetch_year(year_ce: int) -> list[dict]:
    resp = requests.post(API_URL, json={"year": str(year_ce)}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("status"):
        print(f"  API returned non-success for {year_ce}: {data.get('statusMessage')}", file=sys.stderr)
        return []
    return data.get("response", [])


def validate_entry(entry: dict) -> list[str]:
    """Return a list of problems found in an API entry, empty if all good."""
    problems = []
    if "date" not in entry:
        problems.append("missing 'date' field")
        return problems  # can't continue without date

    label = entry["date"]
    data = entry.get("data")
    if not isinstance(data, dict):
        problems.append(f"{label}: missing or invalid 'data' field")
        return problems

    for field in ("first", "last2", "last3f", "last3b"):
        if field not in data:
            problems.append(f"{label}: missing field data['{field}']")
        elif not isinstance(data[field], list) or len(data[field]) == 0:
            problems.append(f"{label}: data['{field}'] is empty or not a list")

    return problems


def format_row(entry: dict) -> str:
    d = datetime.strptime(entry["date"], "%Y-%m-%d").date()
    data = entry["data"]

    first = data["first"][0]
    last2_top = first[-2:]
    last3_top = first[-3:]
    last2_bottom = data["last2"][0]
    front3 = " ".join(data["last3f"])   # order preserved from API (matches website display)
    last3b = " ".join(data["last3b"])

    return "|".join([
        str(d.day),
        THAI_MONTHS[d.month],
        str(d.year + 543),
        first,
        last2_top,
        last3_top,
        last2_bottom,
        front3,
        last3b,
    ])


def main():
    header, body_lines, existing_dates = read_csv()

    # Find the most recent recorded year to determine where to start fetching
    most_recent = max(existing_dates) if existing_dates else date(date.today().year - 1, 1, 1)
    today = date.today()

    years_to_fetch = list(range(most_recent.year, today.year + 1))

    new_entries: list[tuple[date, dict]] = []
    skipped = 0
    for year in years_to_fetch:
        print(f"Checking {year}...")
        for entry in fetch_year(year):
            problems = validate_entry(entry)
            if problems:
                for p in problems:
                    print(f"  WARNING: {p} — skipping entry", file=sys.stderr)
                skipped += 1
                continue
            d = datetime.strptime(entry["date"], "%Y-%m-%d").date()
            if d > today:
                continue  # skip future draws
            if d not in existing_dates:
                new_entries.append((d, entry))

    if skipped:
        print(f"\nERROR: {skipped} entry/entries skipped due to unexpected API structure.", file=sys.stderr)
        print("The API response format may have changed — please review the output above.", file=sys.stderr)
        sys.exit(1)

    if not new_entries:
        print("Already up to date — no new draws found.")
        return

    new_entries.sort(key=lambda x: x[0], reverse=True)  # newest first

    print(f"\nAdding {len(new_entries)} new draw(s):")
    new_rows = []
    for d, entry in new_entries:
        row = format_row(entry)
        print(f"  {entry['date']}: {row}")
        new_rows.append(row)

    with open(CSV_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        for row in new_rows:
            f.write(row + "\n")
        for row in body_lines:
            f.write(row + "\n")

    print(f"\nDone. {CSV_PATH} updated.")


if __name__ == "__main__":
    main()
