"""
Smoothcomp Event Scraper

Fetches upcoming events from smoothcomp.com and extracts event details.

All data comes from the events data embedded in the upcoming-events listing
page. Individual event pages sit behind a Cloudflare challenge and cannot be
fetched, but the listing already carries everything the calendar needs.
"""

import asyncio
import html as html_mod
import json
import re
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

import aiohttp


@dataclass
class Event:
    """Represents a Smoothcomp event."""
    id: str
    name: str
    url: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    sport: Optional[str] = None
    organizer: Optional[str] = None
    participants: Optional[int] = None
    registration_open: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary with ISO date strings."""
        d = asdict(self)
        if self.start_date:
            d['start_date'] = self.start_date.isoformat()
        if self.end_date:
            d['end_date'] = self.end_date.isoformat()
        return d


class ScrapeError(RuntimeError):
    """Raised when the listing page cannot be parsed."""


class SmoothcompScraper:
    """Scrapes events from Smoothcomp."""

    BASE_URL = "https://smoothcomp.com"
    EVENTS_URL = "https://smoothcomp.com/en/events/upcoming"

    def __init__(self, rate_limit: float = 0.5):
        """
        Initialize scraper.

        Args:
            rate_limit: Seconds to wait between requests (default 0.5s)
        """
        self.rate_limit = rate_limit
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": "SmoothcompCalendar/1.0"}
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def _fetch_listing(self) -> str:
        """Fetch the upcoming events page HTML."""
        async with self._session.get(
            self.EVENTS_URL, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                raise ScrapeError(f"{self.EVENTS_URL} returned HTTP {resp.status}")
            return await resp.text()

    def _bjj_category_ids(self, html: str) -> set[str]:
        """
        Extract Jiu-Jitsu category IDs from the page's category mapping.

        Format: :category-groups="{...html-encoded JSON...}"
        """
        cat_match = re.search(r':category-groups="(.*?)"', html)
        if not cat_match:
            raise ScrapeError("could not find :category-groups mapping on listing page")

        cat_data = json.loads(html_mod.unescape(cat_match.group(1)))
        ids = {
            str(cat['id'])
            for group_categories in cat_data.values()
            for cat in group_categories
            if 'Jiu-Jitsu' in cat.get('name', '')
        }
        if not ids:
            raise ScrapeError("no Jiu-Jitsu category IDs found in category mapping")
        return ids

    def _raw_events(self, html: str) -> list[dict]:
        """Extract the `var events = [...]` array from the listing page."""
        events_match = re.search(r'var events = (\[.*?\])\s*\n', html, re.DOTALL)
        if not events_match:
            raise ScrapeError("could not find `var events` array on listing page")
        return json.loads(events_match.group(1))

    def _event_from_listing(self, data: dict) -> Optional[Event]:
        """Build an Event from one entry of the listing's events array."""
        url = data.get('url')
        event_id = data.get('id')
        if not url or event_id is None:
            return None

        def parse_date(value: Optional[str]) -> Optional[date]:
            if not value:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None

        def clean(value: Optional[str]) -> str:
            """Trim and collapse the ragged whitespace found in source data."""
            text = re.sub(r'\s+', ' ', (value or '')).strip()
            return re.sub(r'\s+([,.])', r'\1', text)

        # Codes are ISO 3166-1 alpha-2, except UK sub-regions (e.g. GB-SCT)
        # which collapse to GB so they match Cloudflare's cf.country field.
        raw_code = clean(data.get('location_country')).upper()
        country_code = raw_code.split('-')[0] or None

        return Event(
            id=str(event_id),
            name=clean(data.get('title')) or 'Unknown Event',
            url=url,
            start_date=parse_date(data.get('startdate')),
            end_date=parse_date(data.get('enddate')),
            city=clean(data.get('location_city')),
            country=clean(data.get('location_country_human')),
            country_code=country_code,
            sport='Brazilian Jiu-Jitsu',
            registration_open=not data.get('eventEnded', False),
        )

    async def get_events(self, max_events: Optional[int] = None) -> list[Event]:
        """
        Fetch upcoming BJJ events from the listing page.

        Args:
            max_events: Maximum number of events to return (None for all)

        Returns:
            List of Event objects, sorted by start date

        Raises:
            ScrapeError: If the page layout changed and cannot be parsed
        """
        html = await self._fetch_listing()

        bjj_category_ids = self._bjj_category_ids(html)
        print(f"  BJJ category IDs: {sorted(bjj_category_ids)}", flush=True)

        all_events = self._raw_events(html)
        bjj_raw = [
            e for e in all_events
            if any(cg in bjj_category_ids for cg in e.get('categoryGroups', []))
        ]
        print(f"  Filtered {len(bjj_raw)} BJJ events from {len(all_events)} total", flush=True)

        events = [e for e in (self._event_from_listing(raw) for raw in bjj_raw) if e]

        skipped = len(bjj_raw) - len(events)
        if skipped:
            print(f"  Skipped {skipped} events with unusable data", flush=True)

        events.sort(key=lambda e: (e.start_date is None, e.start_date))

        if max_events:
            events = events[:max_events]

        return events


async def main():
    """Test the scraper."""
    print("Starting Smoothcomp scraper...")

    async with SmoothcompScraper() as scraper:
        events = await scraper.get_events()

    print(f"\nScraped {len(events)} events. First 5:")
    for event in events[:5]:
        print(f"\n  {event.name}")
        print(f"    Date: {event.start_date} - {event.end_date}")
        print(f"    Location: {event.city}, {event.country}")
        print(f"    URL: {event.url}")


if __name__ == "__main__":
    asyncio.run(main())
