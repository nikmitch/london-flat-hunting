from __future__ import annotations
import requests

_cache: dict[str, tuple[float, float] | None] = {}


def postcode_to_latlon(postcode: str) -> tuple[float, float] | None:
    key = postcode.strip().upper().replace(" ", "")
    if key in _cache:
        return _cache[key]
    try:
        resp = requests.get(
            f"https://api.postcodes.io/postcodes/{key}", timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()["result"]
            result = (data["latitude"], data["longitude"])
            _cache[key] = result
            return result
    except Exception as e:
        print(f"[geocoder] failed for {postcode}: {e}")
    _cache[key] = None
    return None
