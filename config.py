import os
from dotenv import load_dotenv

load_dotenv()

TFL_API_KEY = os.getenv("TFL_API_KEY", "")

DESTINATIONS = {
    "your_work": {
        "name": "Your work",
        "short": "MATS",
        "address": "71 Central Street, EC1V 8AB",
        "lat": 51.52532,
        "lon": -0.09643,
        "depart_time": "0900",
    },
    "lisa": {
        "name": "LISA",
        "short": "LISA",
        "address": "25 Holywell Row, EC2A 4XE",
        "lat": 51.52299,
        "lon": -0.08217,
        "depart_time": "0700",
    },
    "kings_cross": {
        "name": "King's Cross",
        "short": "KX",
        "address": "King's Cross Station, N1C 4TB",
        "lat": 51.53106,
        "lon": -0.12465,
        "depart_time": "1900",
    },
}

TRAVEL_MODES = {
    "walking":       {"tfl_mode": "walking",                                                          "label": "Walk"},
    "cycling":       {"tfl_mode": "cycle",                                                            "label": "Cycle"},
    "transit_no_bus":{"tfl_mode": "tube,dlr,overground,elizabeth-line,national-rail",                 "label": "Transit"},
    "transit_all":   {"tfl_mode": "tube,dlr,overground,elizabeth-line,national-rail,bus",             "label": "+Bus"},
}

SEARCH = {
    "min_price": 2500,
    "max_price": 5000,
    "min_bedrooms": 2,   # 2-beds are scraped but only shown if they have a home office
    "max_bedrooms": 4,
    "location_id": "REGION^87490",  # Greater London
}

# Bounding box applied immediately after scraping — properties outside this box
# are dropped before DB insert, saving TfL API calls on unreachable areas.
# All three work destinations are in EC1/EC2; this keeps roughly a 4-mile radius
# around them while cutting out all of West London, outer South, far North/East.
GEO_BOUNDS = {
    "lat_min": 51.465,   # ~Peckham / Bermondsey
    "lat_max": 51.595,   # ~Walthamstow / Stoke Newington
    "lon_min": -0.160,   # ~Caledonian Road / Islington (cuts out West London)
    "lon_max":  0.020,   # ~Hackney Wick / Whitechapel
}

# Bounds for the dashboard price slider (and price-score normalisation)
PRICE_FLOOR = 2500
PRICE_CEILING = 5000

# A 2-bed flat is only worth considering if one room can serve as a home office.
# These patterns are matched (case-insensitive) against the listing's key features
# and summary to set the `has_home_office` flag. Kept deliberately tight to avoid
# false positives from agent boilerplate ("moments from offices", "Post Office").
HOME_OFFICE_PATTERNS = [
    r"home[\s-]*office",
    r"\bstudy\b",
    r"work[\s-]*from[\s-]*home",
    r"home[\s-]*working",
    r"(?<!post[\s-])\boffice\b",    # "office" but not "Post Office"
    r"third\s+reception",           # an extra reception room in a 2-bed
]

# Letting-agent vetting — a coworker who knows London agents graded them.
# Matched (case-insensitive regex) against the agent's brand trading name. First
# match wins. Tiers: "ok" (green), "mid" (amber), "avoid" (red). Shown only on
# cards/popups for listings that pass the filters — never re-evaluated against
# already-rejected ones.
AGENT_RATINGS = [
    (r"knight\s*frank",   "ok",    "Least bad of the big agents"),
    (r"chestertons",      "ok",    "Branch-dependent, usually OK"),
    (r"black\s*katz",     "avoid", "Avoid — known bad"),
    (r"foxtons",          "mid",   "Mid"),
    (r"dexters",          "mid",   "Mid"),
    (r"savills",          "mid",   "Annoying — poor service for established tenants"),
    (r"winkworth",        "mid",   "Franchise-dependent"),
]
# Fallback applied when a listing is a new-build build-to-rent and no specific
# agent rating matched. Built-to-rents are usually not worthwhile (transient
# student-heavy tenancies, inconsistent standards, even pricey KX ones had issues).
BTR_RATING = ("avoid", "New-build build-to-rent — usually not worthwhile")

# Tube/rail line opinions (from the same coworker). Matched against the line
# names TfL reports for each work commute. "good" lines earn a green badge,
# "bad" lines a red one — shown only on listings that pass the filters.
# Keys are matched case-insensitively as a substring of the TfL line name.
LINE_RATINGS = [
    ("elizabeth", "good", "Elizabeth line — fast & air-conditioned"),
    ("northern",  "bad",  "Northern line — busy, hot, no air-con"),
]

# Names shown in the "who are you?" picker — update these to match your group
FLATMATES = ["Nik", "Jennifer", "Luis", "Demelza"]

MAX_COMMUTE_MINUTES = 30
SCRAPE_INTERVAL_MINUTES = 60

# Move-in window — defined as days from today so thresholds stay correct
# regardless of when you're running the app.
# Ideal:   available within 12 days of today  (equiv. now → 5 Jun from 24 May)
# Cutoff:  available within 49 days of today  (equiv. 12 Jul from 24 May)
# Anything available further out than AVAIL_CUTOFF_DAYS is filtered out entirely.
# Listings available after the ideal window but before the cutoff get a score penalty.
AVAIL_IDEAL_DAYS = 12    # available by ideal date = no penalty
AVAIL_CUTOFF_DAYS = 49   # available after this = rejected
