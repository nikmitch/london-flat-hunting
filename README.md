# 🏠 London Flat Hunter

A self-hosted flat-hunting dashboard for small groups. It **scrapes Rightmove**, calculates **TfL commute times** to each place you need to get to, and shows the results as a **filterable card dashboard** and an **interactive map** — with **per-person voting and comments** so a couple, a pair of couples, or a group of housemates can shortlist places together.

Built originally for two couples flat-hunting in London, but designed to be forked and pointed at *your* commute, budget, and people. **[Jump to the customisation guide →](#-make-it-your-own)**

---

## What it does

- **Scrapes Rightmove** for rentals matching your price range, bedrooms, and search area (hourly, in the background).
- **Calculates real commute times** from every listing to each of your destinations, across walking / cycling / transit / transit-with-bus, via the **TfL Journey Planner API**.
- **Scores and ranks** listings by commute, price, and how soon they're available.
- **Dashboard** (`/`) — card grid with filters, pagination, per-person shortlist/reject, vote summaries, and comment threads.
- **Map** (`/map`) — Leaflet map with rich popups (photos, commute table, votes, recent comments) and two themes.
- **Multi-user, no logins** — each person just picks their name; votes and comments are shared.
- **Daily housekeeping** — marks removed listings and fills in missing "available from" dates.

## Tech stack

Python 3.12 · Flask · SQLite · APScheduler · BeautifulSoup · Leaflet.js · TfL Journey Planner API

---

## ⚠️ Important: this is built for London

Two parts of the app assume **London**:

- **Commute times** use the **TfL Journey Planner API**, which only routes within London and its surrounding network.
- **Listings** come from **Rightmove**, which is UK-wide — so scraping works anywhere in the UK; only the commute calculation is London-bound.

| Your situation | What works |
|---|---|
| Flat-hunting **in/around London** | ✅ Everything works out of the box. |
| Elsewhere in the **UK** | ⚠️ Scraping works; commute times won't. Swap the TfL call in `travel/tfl.py` for a routing API that covers your city, or turn the commute feature off. |
| **Outside the UK** | ❌ You'd need to re-point the scraper at a local property site *and* swap the routing API. A bigger fork. |

The rest of this guide assumes you're **searching in or around London**.

---

## 🛠️ Make it your own

Almost everything you'll want to change lives in one file — **`config.py`**. The only external thing you need is a free **TfL API key**.

### 1. Prerequisites

- **Python 3.12** (3.10+ should be fine)
- **Git**
- **conda** (recommended) or any virtualenv tool
- A free **TfL API key** (step 3)
- *(Cloud deploy only)* a **Railway** account + a **GitHub** account

### 2. Get the code

> **Tip:** if you want to make this your own project, **fork** the repo on GitHub first and clone *that* — you'll need your own repo for the cloud-deploy step, and you don't want to push personal config to someone else's project.

```bash
# Clone (use your fork's URL if you forked it)
git clone https://github.com/nikmitch/london-flat-hunting.git
cd london-flat-hunting

# Create a dedicated conda environment
conda create -n flat_hunting python=3.12 -y
conda activate flat_hunting

# Install dependencies
pip install -r requirements.txt
```

### 3. Get a free TfL API key

1. Register at **[api-portal.tfl.gov.uk](https://api-portal.tfl.gov.uk/)** (free).
2. Go to **Products → Register** an application — you'll get an **app key** (a long hex string).
3. Create a `.env` file in the project root:

   ```
   TFL_API_KEY=your_app_key_here
   ```

`.env` is git-ignored, so your key never gets committed.

> **No key?** The app still runs and still scrapes — you just get blank commute times. Fine if you only care about the map and price/availability filtering.

### 4. Configure your search — `config.py`

This is the file you'll actually edit. Work through each section.

#### a) Your commute destinations

`DESTINATIONS` lists every place someone needs to commute **to**. Each listing is scored on how long it takes to reach each one. Replace these with your own:

```python
DESTINATIONS = {
    "alice_work": {
        "name": "Alice's office",   # full label shown in the UI
        "short": "ALICE",           # short tag for the commute table
        "address": "1 Some Street, EC1V",
        "lat": 51.5254,             # see "finding lat/lon" below
        "lon": -0.0907,
        "depart_time": "0900",      # 24h HHMM — when they leave home
    },
    # add as many as you like, or delete down to one
}
```

**Finding lat/lon:** open [Google Maps](https://www.google.com/maps), right-click the exact spot, and the first menu item is the coordinates (`51.5254, -0.0907`). First number is `lat`, second is `lon`. `depart_time` matters because TfL routes depend on the timetable at that hour.

#### b) Price, bedrooms & search area

```python
SEARCH = {
    "min_price": 2500,        # £/month (weekly prices auto-convert ×4.3)
    "max_price": 3300,
    "min_bedrooms": 2,
    "location_id": "REGION^87490",  # Greater London — see below
}
```

**Finding your `location_id`** (Rightmove's internal area code):

1. Run a "to rent" search for your area on [rightmove.co.uk](https://www.rightmove.co.uk).
2. Look at the results-page URL — it contains `locationIdentifier=REGION%5E87490` (or `OUTCODE%5E...`, or `STATION%5E...`).
3. `%5E` is a URL-encoded `^`, so `REGION%5E87490` becomes `REGION^87490` in `config.py`.

Use a broad region (all of Greater London) or a tight outcode (e.g. just `N1`). Narrower searches return fewer, more relevant listings.

> **Property type / furnishing:** the scraper hard-codes `propertyTypes=flat` and `furnishTypes=furnished` in `scraper/rightmove.py` (in `_fetch_page`). Edit those two lines for houses or unfurnished places.

#### c) The people voting

No logins — each person picks their name from a list:

```python
FLATMATES = ["Alice", "Bob", "Carol"]
```

The first name is treated as the "owner" on first run. Running solo? `FLATMATES = ["Me"]` is fine.

#### d) Commute cutoff, scrape frequency & move-in window

```python
MAX_COMMUTE_MINUTES = 30      # best non-bus transit beyond this is penalised/filtered
SCRAPE_INTERVAL_MINUTES = 60  # how often the scraper re-runs

# Move-in window — days from "today", so thresholds stay correct over time
AVAIL_IDEAL_DAYS  = 12   # available within 12 days = no score penalty
AVAIL_CUTOFF_DAYS = 49   # available later than this = rejected entirely
```

Not in a rush? Raise `AVAIL_CUTOFF_DAYS` (e.g. `120`) so further-out listings aren't filtered away.

> **Be polite to Rightmove.** Don't set `SCRAPE_INTERVAL_MINUTES` very low. Hourly is plenty and keeps you well under any rate that'd get you blocked.

---

## ▶️ Run it locally (just for you)

The simplest setup — nothing leaves your machine, no one else can see it. Perfect for solo hunting or a quick trial.

```bash
conda activate flat_hunting
python main.py
```

Then open:

- Dashboard → http://localhost:5000
- Map → http://localhost:5000/map

On first run a fresh SQLite DB is created at `data/listings.db`, the scraper runs immediately (then every `SCRAPE_INTERVAL_MINUTES`), and commute times are calculated as listings arrive. The first pass takes a few minutes — refresh and listings appear. Leave the terminal running; closing it stops the scraper.

> **Share on your home network, no cloud:** the app binds to `0.0.0.0`, so anyone on the **same Wi-Fi** can reach it at `http://YOUR-COMPUTER-IP:5000` (find your IP with `ipconfig getifaddr en0` on a Mac). Zero-cost way to let a partner vote — but only while your machine is on and on the same network.

---

## ☁️ Deploy to the cloud (share with others)

Want flatmates voting from their own phones, anytime? Deploy to [Railway](https://railway.app) — runs Python/Flask natively, persistent disk for the SQLite DB, public URL, ~**$5/month**.

1. **Push to your own GitHub repo** (fork or fresh). `.env` and `data/listings.db` are already git-ignored.
2. **Create a Railway project** → "Deploy from GitHub repo" → pick your repo. It auto-deploys on every push. The included `Procfile` (`web: python main.py`) starts it; the app reads its port from `$PORT`, which Railway sets.
3. **Add your TfL key as a variable:** Railway → your service → **Variables** → `TFL_API_KEY` = your key. (You set the variable here instead of uploading `.env`.)
4. **Add a Volume** so the DB survives restarts: project canvas → "+" → **Volume**, mount path `/app/data`, attach to the web service. Without this, votes/comments reset on every deploy.
5. **(Optional) Seed the database** with your local data:
   ```bash
   # Railway CLI: brew install railway (Mac), then:
   railway login
   railway link    # pick your project
   railway volume cp data/listings.db /app/data/listings.db
   ```
   Skip this and the app just starts fresh and re-scrapes — totally fine.
6. **Get your public URL:** Railway → service → **Settings → Networking → Generate Domain**. Share that link.

> **⚠️ Rightmove may block cloud IPs.** Property sites sometimes refuse data-centre IPs. After deploying, check Railway logs — if the scraper errors but works fine locally, that's why. Workaround: keep the *scraper* on your home machine and host only the *dashboard* on Railway, with the local scraper pushing listings up via a small `POST /ingest` endpoint (not built yet). TfL calls are fine from the cloud.

> **Privacy:** a Railway URL is public to anyone with the link (no logins). The link is long and unguessable — enough for a small private group. For more, see `docs/next-steps.html` for a simple "secret path sets a cookie" gate.

> **SQLite** is fine for a handful of people. If you hit "database is locked" with many simultaneous users, Railway has a one-click Postgres add-on; swap `sqlite3` for `psycopg2` in `db/database.py`.

---

## 🧩 Project structure

```
london_flat_hunting/
├── scraper/rightmove.py   # Scraping, removal check, date fetching
├── travel/tfl.py          # TfL API, parallel calls, rate limiter
├── travel/geocoder.py     # Postcode → lat/lon fallback
├── db/database.py         # SQLite schema, migrations, queries
├── web/app.py             # Flask routes, scoring, filtering
├── web/templates/
│   ├── index.html         # Card dashboard
│   └── map.html           # Leaflet map
├── config.py              # All tuneable parameters ← start here
├── main.py                # Entry point
├── data/listings.db       # SQLite database (gitignored)
├── .env                   # TFL_API_KEY (gitignored)
└── docs/                  # HTML project documentation
```

---

## 🧯 Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| No listings appear | Give the first scrape a few minutes; check the terminal for `[scraper]` errors. A wrong `location_id` or too-narrow price range returns nothing. |
| Commute times all blank | Missing/invalid `TFL_API_KEY`, or destinations outside London's network. Check `.env` (local) or the Railway variable (cloud). |
| `__NEXT_DATA__ not found` | Rightmove changed their page structure, or your IP is blocked. Retry later; if persistent, `scraper/rightmove.py` needs updating. |
| Everything filtered out | `AVAIL_CUTOFF_DAYS` too tight or `MAX_COMMUTE_MINUTES` too strict — loosen them in `config.py`. |
| Wrong names in the picker | Edit `FLATMATES` in `config.py` and restart. |

**The minimum you must change to make it yours:**

1. `.env` — your own `TFL_API_KEY`
2. `config.py` → `DESTINATIONS` — where *you* commute to
3. `config.py` → `SEARCH` — your price range and `location_id`
4. `config.py` → `FLATMATES` — your people (or just yourself)

Everything else has sensible defaults.

---

## 📄 More docs

The `docs/` folder has HTML write-ups: what's built (`what-we-built.html`), running & configuring (`running.html`), the original plan (`plan.html`), and the roadmap (`next-steps.html`).
