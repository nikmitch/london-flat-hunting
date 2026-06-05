# London Flat Hunter — Project Context

A Python/Flask web app that scrapes Rightmove, calculates TfL commute times for each listing, and shows results in a filterable card dashboard and interactive map. Built for two couples flat-hunting in London (May–July 2026).

## Quick start

```bash
conda activate london_flat_hunting
python main.py
# Dashboard → http://localhost:5000
# Map       → http://localhost:5000/map
```

## Key search parameters (config.py)

| Variable | Value | Notes |
|---|---|---|
| Price | £2,500–£3,300/mo | Weekly prices auto-converted (×4.3) |
| Bedrooms | 2+ | 2-bed allowed but penalised in ranking |
| Commute cutoff | 30 min | Non-bus transit to either work address |
| Avail ideal | +12 days from today | No score penalty |
| Avail cutoff | +49 days from today | Hard filter — rejected if later |

## Commute destinations

- **MATS (your work):** 71 Central Street, EC1V — departs 09:00
- **LISA:** 25 Holywell Row, EC2A 4XE — departs 07:00
- **King's Cross:** N1C — departs 19:00

## What's built

- **Scraper:** Rightmove `__NEXT_DATA__` JSON extraction, hourly via APScheduler
- **Travel times:** TfL Journey Planner API, 12 calls/listing (3 dests × 4 modes), 5 parallel workers, global 7 req/sec rate limiter. Env var: `TFL_API_KEY` in `.env`
- **Daily check:** fetches each listing page to mark removed listings + fill missing available-from dates
- **Dashboard (`/`):** card grid, 30/page, best-match sort, pagination, per-user shortlist/reject, vote summary row per card, collapsible comment threads, name picker modal
- **Map (`/map`):** Leaflet.js, theme 2 (light) default, theme 7 (disco) toggle, rich popups with photos + commute table + vote summary + last 2 comments, star icons for shortlisted
- **Multi-user voting:** `votes` + `comments` tables. `FLATMATES = ["Nik", "Jennifer", "Luis", "Demelza"]` in `config.py`. Endpoints: `POST /vote/<id>`, `POST /comment/<id>`, `GET /comments/<id>`
- **Database:** SQLite at `data/listings.db`, tables: `listings`, `travel_times`, `votes`, `comments`
- **Conda env:** `london_flat_hunting` (Python 3.12)
- **GitHub:** `https://github.com/nikmitch/london-flat-hunting` (private)

## Project structure

```
london_flat_hunting/
├── scraper/rightmove.py   # Scraping, removal check, date fetching
├── travel/tfl.py          # TfL API, parallel calls, rate limiter
├── travel/geocoder.py     # Postcode → lat/lon fallback
├── db/database.py         # SQLite schema, migrations, queries
├── web/app.py             # Flask routes, scoring, filtering
├── web/templates/
│   ├── index.html         # Card dashboard
│   └── map.html           # Leaflet map (themes 2 + 7)
├── config.py              # All tuneable parameters
├── main.py                # Entry point
├── data/listings.db       # SQLite database (gitignored)
├── .env                   # TFL_API_KEY (gitignored)
└── docs/                  # Project documentation
```

## What's next

See `docs/next-steps.html` for full detail. Short version:

1. ✅ **Multi-user comments + voting** — done
2. ✅ **Cloud deployment (Railway)** — done. Live with volume mounted (`/app/data`) and DB uploaded. `TFL_API_KEY` set, auto-deploys on push.
3. **Backlog:** Zoopla integration, Telegram/email alerts for new listings, price history tracking

## Forking for your own search

See `README.md` for a full guide to adapting this app for a different commute, price range, search area, and group of people. Key files: `config.py` (all tuneable parameters), `.env` (TfL API key). Includes both a localhost-only setup and Railway cloud deployment.

## Key architectural decisions

- Availability windows are **relative offsets from today** (not hard dates) so thresholds stay correct as time passes
- Travel time fallback: if TfL can't route without buses, `transit_all` is used for the 30-min check
- Rows where all transit times are null (TfL API glitch) are cleared each scrape and retried
- `date_listed` comes from `listingUpdate.listingUpdateDate` (agent's "Added on" date), not `firstVisibleDate` (which can be years old for re-listed properties)
- No auth planned — identity is a name picked from a cookie (flatmate collaboration only)
