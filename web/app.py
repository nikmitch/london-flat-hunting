from __future__ import annotations
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from db.database import (
    get_all_listings,
    get_all_travel_times_bulk,
    update_listing_status,
    upsert_vote,
    get_votes_bulk,
    add_comment,
    get_comments,
    get_comments_bulk,
)
from config import DESTINATIONS, TRAVEL_MODES, MAX_COMMUTE_MINUTES, AVAIL_IDEAL_DAYS, AVAIL_CUTOFF_DAYS, FLATMATES

app = Flask(__name__)
PER_PAGE = 30


def _worst_work_commute(flat_tt: dict) -> int | None:
    """Worst commute to either work destination.
    Prefers transit_no_bus; falls back to transit_all when TfL can't route without buses.
    Returns None only when no transit data exists at all (uncalculated or total API failure)."""
    if not flat_tt:
        return None

    def _work_time(dest_key: str) -> int | None:
        no_bus = flat_tt.get((dest_key, "transit_no_bus"))
        if no_bus is not None:
            return no_bus
        return flat_tt.get((dest_key, "transit_all"))

    vals = [_work_time("your_work"), _work_time("lisa")]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _parse_available(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _avail_penalty(raw: str) -> float | None:
    """Returns None if listing should be rejected (available too far in future).
    Returns a score penalty: 0 if within ideal window, up to +10 if later.
    Thresholds are relative to today, so they slide forward automatically."""
    dt = _parse_available(raw)
    today = datetime.now()
    if dt is None:
        return 0  # date unknown — show with no penalty
    days_until = (dt - today).days
    if days_until > AVAIL_CUTOFF_DAYS:
        return None  # too far out — reject
    if days_until <= AVAIL_IDEAL_DAYS:
        return 0    # ideal window
    # Linear penalty between ideal and cutoff
    return ((days_until - AVAIL_IDEAL_DAYS) / (AVAIL_CUTOFF_DAYS - AVAIL_IDEAL_DAYS)) * 10


def _best_score(flat_tt: dict, price_pcm: int, bedrooms: int, available_from: str) -> float:
    """Lower = better.
    Components:
      - Commute (worst of the two work legs) — weight 2
      - Price normalised 0–1 across £2500–£3300 — weight 8
      - Bedroom penalty: +15 if only 2 beds
      - Availability penalty: 0 if ideal window, up to +10 if later (but still within cutoff)
    """
    commute = _worst_work_commute(flat_tt) or 999
    price_norm = ((price_pcm or 3300) - 2500) / 800
    bed_penalty = 15 if (bedrooms or 0) < 3 else 0
    avail_penalty = _avail_penalty(available_from) or 0
    return commute * 2 + price_norm * 8 + bed_penalty + avail_penalty


def build_listings(status_filter: str, sort_by: str, page: int,
                   current_user: str, all_votes: dict, all_comments: dict):
    raw = get_all_listings()
    all_tt = get_all_travel_times_bulk()

    shown = []
    calculating = 0
    rejected_commute = 0
    rejected_avail = 0

    for row in raw:
        listing = dict(row)
        lid = listing["id"]
        flat_tt = all_tt.get(lid, {})
        worst = _worst_work_commute(flat_tt)

        if worst is None:
            calculating += 1
            continue

        if worst > MAX_COMMUTE_MINUTES:
            rejected_commute += 1
            continue

        # Availability filter
        avail_pen = _avail_penalty(listing.get("available_from", "") or "")
        if avail_pen is None:
            rejected_avail += 1
            continue

        # Per-user vote (fall back to global status when no user set)
        listing_votes = all_votes.get(lid, {})
        my_vote = listing_votes.get(current_user, "new") if current_user else listing["status"]
        listing["votes"] = listing_votes
        listing["my_vote"] = my_vote
        listing["comments"] = all_comments.get(lid, [])
        listing["comment_count"] = len(listing["comments"])

        # Status filtering
        if current_user:
            if status_filter == "shortlisted" and my_vote != "shortlisted":
                continue
            if status_filter == "active" and my_vote == "rejected":
                continue
            if status_filter == "consensus":
                # Show listings where every voter shortlisted it (≥2 votes, no rejections)
                votes_list = list(listing_votes.values())
                if len(votes_list) < 2 or any(v != "shortlisted" for v in votes_list):
                    continue
        else:
            if status_filter == "shortlisted" and listing["status"] != "shortlisted":
                continue
            if status_filter in ("active", "consensus") and listing["status"] == "rejected":
                continue

        tt = {}
        for dest_key in DESTINATIONS:
            tt[dest_key] = {}
            for mode_key in TRAVEL_MODES:
                tt[dest_key][mode_key] = flat_tt.get((dest_key, mode_key))

        # Available-from display
        avail_dt = _parse_available(listing.get("available_from", "") or "")
        listing["available_from_display"] = (
            "Available now" if avail_dt and avail_dt <= datetime.now() else
            avail_dt.strftime("%-d %b %Y") if avail_dt else "Date unknown"
        )
        listing["avail_ideal"] = avail_pen == 0

        listing["tt"] = tt
        listing["worst_work_mins"] = worst
        listing["score"] = _best_score(flat_tt, listing["price_pcm"] or 3300, listing["bedrooms"] or 0, listing.get("available_from", "") or "")

        # Days on market
        days_on = None
        is_new_listing = False
        raw_date = listing.get("date_listed", "")
        if raw_date:
            try:
                listed_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                days_on = (datetime.now(timezone.utc) - listed_dt).days
                is_new_listing = days_on <= 2
            except ValueError:
                pass
        listing["days_on_market"] = days_on
        listing["is_new_listing"] = is_new_listing

        shown.append(listing)

    if sort_by == "price":
        shown.sort(key=lambda x: x["price_pcm"] or 0)
    elif sort_by == "commute":
        shown.sort(key=lambda x: x["worst_work_mins"])
    else:  # "best" default
        shown.sort(key=lambda x: x["score"])

    total = len(shown)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PER_PAGE
    page_listings = shown[offset: offset + PER_PAGE]

    return page_listings, total, total_pages, page, calculating, rejected_commute, rejected_avail


@app.route("/")
def index():
    status_filter = request.args.get("status", "active")
    sort_by = request.args.get("sort", "best")
    page = request.args.get("page", 1, type=int)
    current_user = request.cookies.get("flatmate", "")

    all_votes = get_votes_bulk()
    all_comments = get_comments_bulk()

    listings, total, total_pages, page, calculating, rejected_commute, rejected_avail = build_listings(
        status_filter, sort_by, page, current_user, all_votes, all_comments
    )

    return render_template(
        "index.html",
        listings=listings,
        destinations=DESTINATIONS,
        modes=TRAVEL_MODES,
        status_filter=status_filter,
        sort_by=sort_by,
        page=page,
        total_pages=total_pages,
        total=total,
        calculating=calculating,
        rejected_commute=rejected_commute,
        rejected_avail=rejected_avail,
        current_user=current_user,
        flatmates=FLATMATES,
    )


@app.route("/map")
def map_view():
    status_filter = request.args.get("status", "active")
    return render_template(
        "map.html",
        status_filter=status_filter,
        destinations=DESTINATIONS,
        modes=TRAVEL_MODES,
        flatmates=FLATMATES,
    )


@app.route("/api/listings.json")
def listings_json():
    """GeoJSON FeatureCollection of all qualifying listings for the map."""
    status_filter = request.args.get("status", "active")
    current_user = request.cookies.get("flatmate", "")

    raw = get_all_listings()
    all_tt = get_all_travel_times_bulk()
    all_votes = get_votes_bulk()
    all_comments = get_comments_bulk()
    features = []

    for row in raw:
        listing = dict(row)
        lid = listing["id"]
        flat_tt = all_tt.get(lid, {})
        worst = _worst_work_commute(flat_tt)

        if worst is None or worst > MAX_COMMUTE_MINUTES:
            continue
        avail_pen = _avail_penalty(listing.get("available_from", "") or "")
        if avail_pen is None:
            continue
        if not listing["lat"] or not listing["lon"]:
            continue

        listing_votes = all_votes.get(lid, {})
        my_vote = listing_votes.get(current_user, "new") if current_user else listing["status"]

        if status_filter == "shortlisted":
            if current_user and my_vote != "shortlisted":
                continue
            if not current_user and listing["status"] != "shortlisted":
                continue
        elif status_filter != "all":
            # "active" — hide rejected
            if current_user and my_vote == "rejected":
                continue
            if not current_user and listing["status"] == "rejected":
                continue

        avail_dt = _parse_available(listing.get("available_from", "") or "")
        avail_display = (
            "Available now" if avail_dt and avail_dt <= datetime.now() else
            avail_dt.strftime("%-d %b %Y") if avail_dt else "Date unknown"
        )

        color = "#2ecc71" if worst <= 20 else "#f39c12" if worst <= 30 else "#e74c3c"

        # Build flat travel time dict keyed as "dest__mode" for JSON serialisation
        tt_flat = {}
        for dest_key in DESTINATIONS:
            for mode_key in TRAVEL_MODES:
                val = flat_tt.get((dest_key, mode_key))
                tt_flat[f"{dest_key}__{mode_key}"] = val

        days_on = None
        raw_date = listing.get("date_listed", "")
        if raw_date:
            try:
                listed_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                days_on = (datetime.now(timezone.utc) - listed_dt).days
            except ValueError:
                pass

        avail_ideal = (_avail_penalty(listing.get("available_from", "") or "") or 0) == 0

        # Recent comments (last 2) for popup preview
        listing_comments = all_comments.get(lid, [])
        recent_comments = listing_comments[-2:] if listing_comments else []

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [listing["lon"], listing["lat"]]},
            "properties": {
                "id": lid,
                "title": listing["title"],
                "price": listing["price_pcm"],
                "bedrooms": listing["bedrooms"],
                "postcode": listing["postcode"],
                "worst_commute": worst,
                "available": avail_display,
                "avail_ideal": avail_ideal,
                "days_on": days_on,
                "status": listing["status"],
                "my_vote": my_vote,
                "votes": listing_votes,
                "recent_comments": recent_comments,
                "url": listing["url"],
                "photo_url": listing["photo_url"] or "",
                "color": color,
                "tt": tt_flat,
            },
        })

    return jsonify({"type": "FeatureCollection", "features": features})


@app.route("/action/<int:listing_id>", methods=["POST"])
def action(listing_id):
    """Legacy endpoint — updates global status. Kept for backward compat."""
    status = request.json.get("status")
    if status in ("shortlisted", "rejected", "new"):
        update_listing_status(listing_id, status)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400


@app.route("/vote/<int:listing_id>", methods=["POST"])
def vote(listing_id):
    data = request.json or {}
    user = data.get("user", "").strip()
    status = data.get("status")
    if not user or user not in FLATMATES:
        return jsonify({"ok": False, "error": "Invalid user"}), 400
    if status not in ("shortlisted", "rejected", "new"):
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    upsert_vote(listing_id, user, status)
    return jsonify({"ok": True})


@app.route("/comment/<int:listing_id>", methods=["POST"])
def post_comment(listing_id):
    data = request.json or {}
    user = data.get("user", "").strip()
    body = data.get("body", "").strip()
    if not user or user not in FLATMATES:
        return jsonify({"ok": False, "error": "Invalid user"}), 400
    if not body:
        return jsonify({"ok": False, "error": "Empty comment"}), 400
    add_comment(listing_id, user, body)
    return jsonify({"ok": True})


@app.route("/comments/<int:listing_id>")
def listing_comments(listing_id):
    return jsonify(get_comments(listing_id))
