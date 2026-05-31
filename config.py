import os
from dotenv import load_dotenv

load_dotenv()

TFL_API_KEY = os.getenv("TFL_API_KEY", "")

DESTINATIONS = {
    "your_work": {
        "name": "Your work",
        "short": "MATS",
        "address": "71 Central Street, EC1V",
        "lat": 51.5254,
        "lon": -0.0907,
        "depart_time": "0900",
    },
    "lisa": {
        "name": "LISA",
        "short": "LISA",
        "address": "25 Holywell Row, EC2A 4XE",
        "lat": 51.5210,
        "lon": -0.0796,
        "depart_time": "0700",
    },
    "kings_cross": {
        "name": "King's Cross",
        "short": "KX",
        "address": "King's Cross Station, N1C 4TB",
        "lat": 51.5308,
        "lon": -0.1238,
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
    "max_price": 3300,
    "min_bedrooms": 2,
    "location_id": "REGION^87490",  # Greater London
}

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
