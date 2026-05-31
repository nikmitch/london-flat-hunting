from __future__ import annotations
import time
import threading
import requests
from config import TFL_API_KEY, DESTINATIONS, TRAVEL_MODES

TFL_BASE = "https://api.tfl.gov.uk/Journey/JourneyResults"

# Global rate limiter — 7 calls/sec = 420/min, safely under the 500/min cap.
# Shared across all threads so parallel workers don't collectively exceed it.
_rate_lock = threading.Lock()
_last_call_time = 0.0
_MIN_INTERVAL = 1.0 / 7


def _rate_limited_get(url: str, params: dict) -> requests.Response | None:
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        gap = _last_call_time + _MIN_INTERVAL - now
        if gap > 0:
            time.sleep(gap)
        _last_call_time = time.monotonic()
    try:
        return requests.get(url, params=params, timeout=15)
    except Exception as e:
        print(f"[tfl] request error: {e}")
        return None


def get_journey_time(
    from_lat: float, from_lon: float,
    to_lat: float, to_lon: float,
    time_str: str,
    modes: str,
) -> int | None:
    url = f"{TFL_BASE}/{from_lat},{from_lon}/to/{to_lat},{to_lon}"
    params = {
        "time": time_str,
        "timeIs": "Departing",
        "journeyPreference": "LeastTime",
        "mode": modes,
        "app_key": TFL_API_KEY,
    }
    resp = _rate_limited_get(url, params)
    if resp is None:
        return None
    if resp.status_code == 200:
        journeys = resp.json().get("journeys", [])
        if journeys:
            return journeys[0]["duration"]
    return None


def calculate_all_travel_times(lat: float, lon: float) -> dict:
    """Returns {(destination_key, mode_key): duration_minutes}.
    All 12 calls are made concurrently within thread pool limits."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tasks = []
    for dest_key, dest in DESTINATIONS.items():
        for mode_key, mode_info in TRAVEL_MODES.items():
            tasks.append((dest_key, mode_key, dest, mode_info))

    results = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {
            ex.submit(
                get_journey_time,
                lat, lon,
                t[2]["lat"], t[2]["lon"],
                t[2]["depart_time"],
                t[3]["tfl_mode"],
            ): (t[0], t[1])
            for t in tasks
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                print(f"[tfl] future error {key}: {e}")
                results[key] = None
    return results
