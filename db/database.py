from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "listings.db"


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(owner_name: str = None):
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                url           TEXT UNIQUE NOT NULL,
                rightmove_id  TEXT,
                title         TEXT,
                price_pcm     INTEGER,
                bedrooms      INTEGER,
                postcode      TEXT,
                lat           REAL,
                lon           REAL,
                description   TEXT,
                photo_url     TEXT,
                date_listed   TEXT,
                date_scraped  TEXT,
                status           TEXT DEFAULT 'new',
                is_removed       INTEGER DEFAULT 0,
                available_from   TEXT,
                has_home_office  INTEGER DEFAULT 0,
                enriched         INTEGER DEFAULT 0,
                agent_name       TEXT,
                is_btr           INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS travel_times (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id       INTEGER NOT NULL,
                destination      TEXT NOT NULL,
                mode             TEXT NOT NULL,
                departure_time   TEXT,
                duration_minutes INTEGER,
                FOREIGN KEY (listing_id) REFERENCES listings(id),
                UNIQUE (listing_id, destination, mode)
            );

            CREATE TABLE IF NOT EXISTS votes (
                listing_id  INTEGER NOT NULL,
                user_name   TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'new',
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (listing_id, user_name),
                FOREIGN KEY (listing_id) REFERENCES listings(id)
            );

            CREATE TABLE IF NOT EXISTS comments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id  INTEGER NOT NULL,
                user_name   TEXT NOT NULL,
                body        TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (listing_id) REFERENCES listings(id)
            );
        """)
        # Migrate existing DBs that predate the is_removed column
        cols = [r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()]
        if "is_removed" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN is_removed INTEGER DEFAULT 0")
        if "available_from" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN available_from TEXT")
        if "has_home_office" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN has_home_office INTEGER DEFAULT 0")
        if "enriched" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN enriched INTEGER DEFAULT 0")
        if "agent_name" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN agent_name TEXT")
        if "is_btr" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN is_btr INTEGER DEFAULT 0")
        # Fix weekly prices that were stored without conversion (all are < 1500 in our search range)
        conn.execute(
            "UPDATE listings SET price_pcm = ROUND(price_pcm * 4.3) WHERE price_pcm < 1500"
        )
        # One-time migration: copy global shortlisted/rejected into votes for the app owner
        if owner_name:
            vote_count = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
            if vote_count == 0:
                conn.execute(
                    "INSERT OR IGNORE INTO votes (listing_id, user_name, status) "
                    "SELECT id, ?, status FROM listings WHERE status IN ('shortlisted', 'rejected')",
                    (owner_name,),
                )


def upsert_listing(data: dict) -> tuple[int, bool]:
    """Insert listing if new. Returns (id, is_new)."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM listings WHERE url = ?", (data["url"],)
        ).fetchone()
        if existing:
            # Refresh fields that can change or improve since we first saw it:
            # the re-list date, availability, and the home-office detection
            # (now derived from key features, so re-evaluate existing rows too).
            conn.execute(
                """UPDATE listings SET
                       date_listed = :date_listed,
                       available_from = :available_from,
                       description = :description,
                       has_home_office = :has_home_office,
                       agent_name = :agent_name,
                       is_btr = :is_btr
                   WHERE id = :id""",
                {
                    "date_listed": data["date_listed"],
                    "available_from": data.get("available_from"),
                    "description": data.get("description"),
                    "has_home_office": data.get("has_home_office", 0),
                    "agent_name": data.get("agent_name"),
                    "is_btr": data.get("is_btr", 0),
                    "id": existing["id"],
                },
            )
            return existing["id"], False
        cursor = conn.execute(
            """INSERT INTO listings
               (url, rightmove_id, title, price_pcm, bedrooms, postcode,
                lat, lon, description, photo_url, date_listed, date_scraped,
                available_from, has_home_office, agent_name, is_btr)
               VALUES
               (:url, :rightmove_id, :title, :price_pcm, :bedrooms, :postcode,
                :lat, :lon, :description, :photo_url, :date_listed, :date_scraped,
                :available_from, :has_home_office, :agent_name, :is_btr)""",
            data,
        )
        return cursor.lastrowid, True


def mark_removed(listing_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE listings SET is_removed = 1 WHERE id = ?", (listing_id,))


def update_available_from(listing_id: int, iso_date: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE listings SET available_from = ? WHERE id = ?", (iso_date, listing_id)
        )


def save_travel_time(listing_id, destination, mode, departure_time, duration_minutes):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO travel_times
               (listing_id, destination, mode, departure_time, duration_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (listing_id, destination, mode, departure_time, duration_minutes),
        )


def get_all_listings():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM listings WHERE is_removed = 0 ORDER BY date_scraped DESC"
        ).fetchall()


def get_active_listing_urls() -> list[tuple[int, str]]:
    """Returns (id, url) for all non-removed listings, for removal checking."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, url FROM listings WHERE is_removed = 0"
        ).fetchall()
    return [(r["id"], r["url"]) for r in rows]


def get_all_travel_times_bulk() -> dict:
    """Returns {listing_id: {(destination, mode): duration_minutes}}."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM travel_times").fetchall()
    result = {}
    for row in rows:
        lid = row["listing_id"]
        if lid not in result:
            result[lid] = {}
        result[lid][(row["destination"], row["mode"])] = row["duration_minutes"]
    return result


def update_listing_status(listing_id: int, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE listings SET status = ? WHERE id = ?", (status, listing_id)
        )


def clear_failed_transit_listings():
    """Delete travel time rows for listings where TfL returned None for all work transit
    modes (API glitch). This queues them for recalculation on the next pass."""
    with get_conn() as conn:
        # Find listing IDs that have travel time rows but both work transit columns are NULL
        failed = conn.execute("""
            SELECT DISTINCT l.id FROM listings l
            JOIN travel_times t ON t.listing_id = l.id
            WHERE l.is_removed = 0
            AND NOT EXISTS (
                SELECT 1 FROM travel_times t2
                WHERE t2.listing_id = l.id
                AND t2.destination IN ('your_work', 'lisa')
                AND t2.mode IN ('transit_no_bus', 'transit_all')
                AND t2.duration_minutes IS NOT NULL
            )
        """).fetchall()
        ids = [r["id"] for r in failed]
        if ids:
            conn.execute(
                f"DELETE FROM travel_times WHERE listing_id IN ({','.join('?'*len(ids))})",
                ids,
            )
        return len(ids)


def listings_needing_travel_times():
    with get_conn() as conn:
        return conn.execute(
            """SELECT l.* FROM listings l
               WHERE l.lat IS NOT NULL
               AND l.is_removed = 0
               AND NOT EXISTS (
                   SELECT 1 FROM travel_times t WHERE t.listing_id = l.id
               )
               ORDER BY l.date_scraped DESC"""
        ).fetchall()


def upsert_vote(listing_id: int, user_name: str, status: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO votes (listing_id, user_name, status)
               VALUES (?, ?, ?)
               ON CONFLICT(listing_id, user_name) DO UPDATE SET status=excluded.status, created_at=datetime('now')""",
            (listing_id, user_name, status),
        )


def get_votes_bulk() -> dict:
    """Returns {listing_id: {user_name: status}}."""
    with get_conn() as conn:
        rows = conn.execute("SELECT listing_id, user_name, status FROM votes").fetchall()
    result: dict = {}
    for row in rows:
        lid = row["listing_id"]
        if lid not in result:
            result[lid] = {}
        result[lid][row["user_name"]] = row["status"]
    return result


def add_comment(listing_id: int, user_name: str, body: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO comments (listing_id, user_name, body) VALUES (?, ?, ?)",
            (listing_id, user_name, body),
        )


def get_comments(listing_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, user_name, body, created_at FROM comments WHERE listing_id = ? ORDER BY created_at ASC",
            (listing_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_comments_bulk() -> dict:
    """Returns {listing_id: [comment_dicts]} sorted oldest-first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, listing_id, user_name, body, created_at FROM comments ORDER BY created_at ASC"
        ).fetchall()
    result: dict = {}
    for row in rows:
        lid = row["listing_id"]
        if lid not in result:
            result[lid] = []
        result[lid].append(dict(row))
    return result
