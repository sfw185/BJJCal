#!/usr/bin/env python3
"""
Static Site Generator for Smoothcomp Calendar

Scrapes events and generates static files for GitHub Pages hosting.

Usage:
    python generate_static.py              # Full scrape
    python generate_static.py --limit 20   # Quick test with 20 events
    python generate_static.py --help
"""

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from scraper import SmoothcompScraper, Event
from calendar_gen import generate_ical


# Output directory
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "static"))


def log(msg: str):
    """Print with flush for streaming output in CI."""
    print(msg, flush=True)


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


async def main(limit: int | None = None):
    log(f"Output directory: {OUTPUT_DIR}")
    if limit:
        log(f"Test mode: limiting to {limit} events")
    OUTPUT_DIR.mkdir(exist_ok=True)
    calendars_dir = OUTPUT_DIR / "calendars"
    calendars_dir.mkdir(exist_ok=True)
    events_dir = OUTPUT_DIR / "events"
    events_dir.mkdir(exist_ok=True)

    # Clear stale calendars/event lists so a country that no longer has
    # events cannot leave an orphaned file behind
    for stale in calendars_dir.glob("*.ics"):
        stale.unlink()
    for stale in events_dir.glob("*.json"):
        stale.unlink()

    # Scrape all events
    log("\nScraping events...")

    async with SmoothcompScraper() as scraper:
        events: list[Event] = await scraper.get_events(max_events=limit)

    log(f"\nCollected {len(events)} upcoming events")

    # Fail loudly rather than deploying an empty calendar over good data
    if not events:
        raise SystemExit("No events collected - refusing to generate empty calendars")

    # Group events by ISO country code, not the human-readable name: source
    # data splinters some countries by region (UK events carry "United
    # Kingdom", "England", "Scotland", "Wales", or "Northern Ireland" for the
    # same GB code), which would otherwise produce duplicate calendars.
    events_by_code: dict[str, list[Event]] = {}
    for event in events:
        code = event.country_code or "UNKNOWN"
        events_by_code.setdefault(code, []).append(event)

    codes_sorted = [
        c for c in sorted(
            events_by_code.keys(),
            key=lambda c: len(events_by_code[c]),
            reverse=True
        )
        if c != "UNKNOWN"
    ]

    def display_name(country_events: list[Event]) -> str:
        """Most common human-readable name among a code's events."""
        names = Counter(e.country for e in country_events if e.country)
        return names.most_common(1)[0][0] if names else "Unknown"

    # Generate metadata.json
    log("\nGenerating metadata.json...")
    metadata = {
        "generated_at": datetime.now().isoformat(),
        "total_events": len(events),
        "countries": [
            {
                "name": display_name(events_by_code[code]),
                "slug": slugify(display_name(events_by_code[code])),
                "count": len(events_by_code[code]),
                "code": code
            }
            for code in codes_sorted
        ]
    }

    with open(OUTPUT_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Generate per-country calendars and event lists (the latter power the
    # "upcoming events" preview on the page; kept separate from the .ics
    # files so the front end doesn't need an iCal parser)
    log(f"Generating {len(codes_sorted)} country calendars...")
    for code in codes_sorted:
        country_events = events_by_code[code]
        name = display_name(country_events)
        slug = slugify(name)
        cal_data = generate_ical(
            country_events,
            calendar_name=f"BJJ Calendar - {name}"
        )
        with open(OUTPUT_DIR / "calendars" / f"{slug}.ics", "wb") as f:
            f.write(cal_data)

        event_list = [
            {
                "id": e.id,
                "name": e.name,
                "url": e.url,
                "start_date": e.start_date.isoformat() if e.start_date else None,
                # Source data occasionally has end_date before start_date
                # (an organizer typo upstream); clamp so the preview never
                # shows a backwards date range. calendar_gen.py applies the
                # same clamp for the .ics output.
                "end_date": (
                    e.end_date.isoformat()
                    if e.end_date and e.start_date and e.end_date >= e.start_date
                    else e.start_date.isoformat() if e.start_date else None
                ),
                "city": e.city or ""
            }
            for e in country_events
        ]
        with open(events_dir / f"{slug}.json", "w") as f:
            json.dump(event_list, f, indent=2)

        log(f"  {name}: {len(country_events)} events")

    log(f"\nDone! Files written to {OUTPUT_DIR}/")
    log(f"  - metadata.json ({len(codes_sorted)} countries)")
    log(f"  - calendars/*.ics")
    log(f"  - events/*.json")
    log(f"\nTo test locally:")
    log(f"  python -m http.server 8000 -d {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate static Smoothcomp calendar files")
    parser.add_argument("--limit", type=int, help="Limit number of events (for testing)")
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit))
