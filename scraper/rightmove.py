from __future__ import annotations
import re
import json
import time
import requests
from datetime import datetime, timezone

from config import SEARCH, HOME_OFFICE_PATTERNS, GEO_BOUNDS
from db.database import (
    upsert_listing,
    get_active_listing_urls,
    mark_removed,
    update_available_from,
)

HOME_OFFICE_RE = re.compile("|".join(HOME_OFFICE_PATTERNS), re.IGNORECASE)


def detect_home_office(*texts: str) -> bool:
    """True if any of the given text blobs mention a home-office / study feature."""
    for t in texts:
        if t and HOME_OFFICE_RE.search(t):
            return True
    return False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://www.rightmove.co.uk/property-to-rent/find.html"
LISTING_BASE = "https://www.rightmove.co.uk/properties/"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)


def _fetch_page(index: int) -> dict | None:
    params = {
        "locationIdentifier": SEARCH["location_id"],
        "minBedrooms": SEARCH["min_bedrooms"],
        "maxBedrooms": SEARCH["max_bedrooms"],
        "maxPrice": SEARCH["max_price"],
        "minPrice": SEARCH["min_price"],
        "propertyTypes": "flat",
        "furnishTypes": "furnished",
        "sortType": 6,  # newest first
        "index": index,
    }
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        match = NEXT_DATA_RE.search(resp.text)
        if not match:
            print("[scraper] __NEXT_DATA__ not found in page")
            return None
        data = json.loads(match.group(1))
        return data["props"]["pageProps"]["searchResults"]
    except Exception as e:
        print(f"[scraper] fetch error at index {index}: {e}")
        return None


def _parse_property(prop: dict) -> dict | None:
    try:
        rm_id = str(prop.get("id", ""))
        if not rm_id:
            return None

        # Skip let-agreed properties — they're gone from the market
        display_status = (prop.get("displayStatus") or "").strip()
        if display_status.lower() == "let agreed":
            return None

        price_info = prop.get("price", {})
        price = price_info.get("amount")
        if price and price_info.get("frequency") == "weekly":
            price = round(price * 4.3)
        address = prop.get("displayAddress", "")

        location = prop.get("location", {})
        lat = location.get("latitude")
        lon = location.get("longitude")

        # Drop properties outside the configured geographic bounding box
        if lat is not None and lon is not None:
            if not (GEO_BOUNDS["lat_min"] <= lat <= GEO_BOUNDS["lat_max"] and
                    GEO_BOUNDS["lon_min"] <= lon <= GEO_BOUNDS["lon_max"]):
                return None

        images = prop.get("propertyImages", {}).get("images", [])
        if not images:
            images = prop.get("images", {}).get("images", [])
        photo_url = images[0].get("srcUrl", "") if images else ""

        summary = prop.get("summary") or prop.get("propertyTypeFullDescription", "")

        # Key features are a curated bullet list in the search-results JSON — this
        # is where agents flag a "Study"/"Home office", so it's the best signal.
        key_features = [
            f.get("description", "") for f in (prop.get("keyFeatures") or [])
        ]
        features_text = " • ".join(kf for kf in key_features if kf)
        # Store features + summary together as the description we show/scan
        description = (features_text + ("\n" if features_text else "") + summary).strip()
        has_office = detect_home_office(features_text, summary)

        # displayAddress often ends with outcode e.g. "Hoxton, London N1"
        # We use it for postcode/area display; lat/lon comes from Rightmove directly
        postcode = address.split(",")[-1].strip() if address else ""

        # listingUpdateDate = when the agent most recently added/re-listed/reduced it
        # (what Rightmove shows as "Added on" / "Reduced on")
        listing_update = prop.get("listingUpdate", {})
        date_listed = listing_update.get("listingUpdateDate") or prop.get("firstVisibleDate", "")

        return {
            "url": f"{LISTING_BASE}{rm_id}",
            "rightmove_id": rm_id,
            "title": address,
            "price_pcm": int(price) if price else None,
            "bedrooms": prop.get("bedrooms"),
            "postcode": postcode,
            "lat": lat,
            "lon": lon,
            "description": (description or "")[:800],
            "photo_url": photo_url,
            "date_listed": date_listed,
            "date_scraped": datetime.now(timezone.utc).isoformat(),
            "available_from": prop.get("letAvailableDate", ""),
            "has_home_office": 1 if has_office else 0,
        }
    except Exception as e:
        print(f"[scraper] parse error on property {prop.get('id')}: {e}")
        return None


def run_scrape() -> int:
    print(f"[scraper] starting at {datetime.now().strftime('%H:%M:%S')}")
    new_count = 0
    index = 0

    while True:
        sr = _fetch_page(index)
        if not sr:
            print("[scraper] no data — stopping")
            break

        properties = sr.get("properties", [])
        if not properties:
            break

        for prop in properties:
            parsed = _parse_property(prop)
            if parsed:
                _, is_new = upsert_listing(parsed)
                if is_new:
                    new_count += 1

        raw_count = str(sr.get("resultCount", "0")).replace(",", "")
        total = int(raw_count) if raw_count.isdigit() else 0

        pagination = sr.get("pagination", {})
        next_index = pagination.get("next")
        index += len(properties)

        print(f"[scraper] {index}/{total} processed ({new_count} new)")

        if not next_index or index >= total or index >= 1000:
            break

        time.sleep(2)

    print(f"[scraper] done — {new_count} new listings added")
    return new_count


AVAIL_DATE_RE = re.compile(r'<dt>Let available date: ?</dt><dd>(\d{2}/\d{2}/\d{4})</dd>')
REMOVED_MARKER = "This property has been removed"
LET_AGREED_MARKER = "Let Agreed"


def fetch_missing_available_dates() -> int:
    """Fetch individual listing pages for listings where available_from is unknown,
    and extract the date from the Letting details section."""
    from db.database import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, url FROM listings WHERE is_removed=0 AND (available_from IS NULL OR available_from='')"
        ).fetchall()
    if not rows:
        return 0
    print(f"[avail] fetching dates for {len(rows)} listings...")
    found = 0
    for i, row in enumerate(rows, 1):
        try:
            resp = requests.get(row["url"], headers=HEADERS, timeout=10)
            if REMOVED_MARKER in resp.text or LET_AGREED_MARKER in resp.text:
                mark_removed(row["id"])
                continue
            m = AVAIL_DATE_RE.search(resp.text)
            if m:
                # Convert DD/MM/YYYY to ISO
                d, mo, y = m.group(1).split("/")
                iso = f"{y}-{mo}-{d}T00:00:00Z"
                update_available_from(row["id"], iso)
                found += 1
        except Exception as e:
            print(f"[avail] error on {row['url']}: {e}")
        time.sleep(0.4)
        if i % 100 == 0:
            print(f"[avail] {i}/{len(rows)} checked ({found} dates found)")
    print(f"[avail] done — {found} dates populated")
    return found


def daily_listing_check() -> tuple[int, int]:
    """Single daily pass over all active listings.
    Checks for removals AND fills in missing available_from dates.
    Returns (removed_count, dates_found)."""
    from db.database import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, url, available_from FROM listings WHERE is_removed=0"
        ).fetchall()
    if not rows:
        return 0, 0

    print(f"[daily] checking {len(rows)} listings for removal + missing dates...")
    removed = 0
    dates_found = 0

    for i, row in enumerate(rows, 1):
        needs_date = not row["available_from"]
        try:
            resp = requests.get(row["url"], headers=HEADERS, timeout=10)
            if REMOVED_MARKER in resp.text or LET_AGREED_MARKER in resp.text:
                mark_removed(row["id"])
                removed += 1
                print(f"[daily] removed/let-agreed: {row['url']}")
                continue
            if needs_date:
                m = AVAIL_DATE_RE.search(resp.text)
                if m:
                    d, mo, y = m.group(1).split("/")
                    iso = f"{y}-{mo}-{d}T00:00:00Z"
                    update_available_from(row["id"], iso)
                    dates_found += 1
        except Exception as e:
            print(f"[daily] error on {row['url']}: {e}")
        time.sleep(0.4)
        if i % 100 == 0:
            print(f"[daily] {i}/{len(rows)} — {removed} removed, {dates_found} dates found")

    print(f"[daily] done — {removed} removed, {dates_found} dates populated")
    return removed, dates_found
