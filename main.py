import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from apscheduler.schedulers.background import BackgroundScheduler

from db.database import init_db, listings_needing_travel_times, save_travel_time, clear_failed_transit_listings
from scraper.rightmove import run_scrape, daily_listing_check
from travel.tfl import calculate_all_travel_times
from config import DESTINATIONS, SCRAPE_INTERVAL_MINUTES, FLATMATES
from web.app import app

TRAVEL_WORKERS = 5  # concurrent listings; 5×12 calls share the global rate limiter


def _calc_one(listing):
    times = calculate_all_travel_times(listing["lat"], listing["lon"])
    for (dest_key, mode_key), duration in times.items():
        save_travel_time(
            listing["id"],
            dest_key,
            mode_key,
            DESTINATIONS[dest_key]["depart_time"],
            duration,
        )
    return listing["title"]


def process_travel_times():
    pending = listings_needing_travel_times()
    if not pending:
        return
    print(f"[travel] {len(pending)} listings to calculate ({TRAVEL_WORKERS} workers)...")
    done = 0
    with ThreadPoolExecutor(max_workers=TRAVEL_WORKERS) as ex:
        futures = {ex.submit(_calc_one, listing): listing for listing in pending}
        for future in as_completed(futures):
            done += 1
            try:
                title = future.result()
                print(f"[travel] {done}/{len(pending)} done — {title}")
            except Exception as e:
                print(f"[travel] error: {e}")
    print("[travel] all done")


def scrape_and_update():
    run_scrape()
    cleared = clear_failed_transit_listings()
    if cleared:
        print(f"[travel] cleared {cleared} failed listings for retry")
    process_travel_times()


if __name__ == "__main__":
    print("=== London Flat Hunter ===")

    init_db(owner_name=FLATMATES[0] if FLATMATES else None)
    print("[db] initialised")

    bg = threading.Thread(target=scrape_and_update, daemon=True, name="scraper")
    bg.start()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scrape_and_update,
        "interval",
        minutes=SCRAPE_INTERVAL_MINUTES,
        id="scrape_job",
    )
    # Daily check: removal + fill missing available_from dates
    scheduler.add_job(
        daily_listing_check,
        "interval",
        hours=24,
        id="daily_check",
    )
    scheduler.start()
    print(f"[scheduler] scraper will run every {SCRAPE_INTERVAL_MINUTES} minutes")

    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"\n>>> Dashboard: http://localhost:{port}\n")

    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
        scheduler.shutdown()
        sys.exit(0)
