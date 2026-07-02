"""
Journal Engine (Persistence Layer)

Her taramanın çıktısını SQLite'a kaydeder. Üç amaç:

1) OI/funding geçmişi -> Derivatives Engine bir önceki taramayla
   karşılaştırma yapabilsin (OI delta).
2) Setup geçmişi -> READY olan her setup sonraki taramalarda
   TP/SL'e ulaştı mı diye otomatik etiketlenir (outcome tracking).
3) İstatistik -> hangi confluence kombinasyonunun (sequence state,
   trigger, MTF...) gerçek başarı oranı ne; gelecekteki Probability
   Engine'in eğitim verisi burada birikir.

DB: data/atlas_journal.db (stdlib sqlite3, ek bağımlılık yok)
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


DB_PATH = Path("data") / "atlas_journal.db"

OUTCOME_EXPIRE_DAYS = 7


@contextmanager
def _db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                session_name TEXT,
                ready_count INTEGER,
                watch_count INTEGER,
                wait_count INTEGER,
                failed_count INTEGER
            );

            CREATE TABLE IF NOT EXISTS setups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                setup_status TEXT,
                trend_direction TEXT,
                atlas_score REAL,
                entry REAL,
                stop REAL,
                target REAL,
                rr REAL,
                entry_state TEXT,
                trigger_status TEXT,
                sequence_state TEXT,
                flags_json TEXT,
                outcome TEXT,
                outcome_at TEXT,
                outcome_price REAL,
                FOREIGN KEY (scan_id) REFERENCES scans (id)
            );

            CREATE TABLE IF NOT EXISTS metrics_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                open_interest REAL,
                funding_rate REAL,
                price REAL,
                FOREIGN KEY (scan_id) REFERENCES scans (id)
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_symbol
                ON metrics_history (symbol, id);

            CREATE INDEX IF NOT EXISTS idx_setups_open
                ON setups (outcome, symbol);
            """
        )


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_previous_metrics(symbol):
    """
    Sembol için en son kaydedilmiş metrikleri döndürür.
    Tarama sırasında çağrıldığında bu her zaman BİR ÖNCEKİ taramadır
    (mevcut tarama henüz record_scan ile yazılmamıştır).
    """
    with _db() as conn:
        row = conn.execute(
            """
            SELECT open_interest, funding_rate, price, created_at
            FROM metrics_history
            WHERE symbol = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()

    if not row:
        return None

    return {
        "open_interest": row["open_interest"],
        "funding_rate": row["funding_rate"],
        "price": row["price"],
        "recorded_at": row["created_at"],
    }


def _build_flags(item):
    return {
        "sequence_state": item.get("entry_sequence_state"),
        "has_cisd": item.get("has_cisd"),
        "has_mss": item.get("has_mss"),
        "trigger_status": item.get("trigger_status"),
        "trigger_score": item.get("trigger_score"),
        "conflict_level": item.get("conflict_level"),
        "structure": item.get("structure"),
        "smc_direction": item.get("smc_direction"),
        "mtf_bias": item.get("mtf_bias"),
        "mtf_alignment": item.get("mtf_alignment"),
        "session_name": item.get("session_name"),
        "derivatives_bonus": item.get("derivatives_bonus"),
        "oi_change_percent": item.get("oi_change_percent"),
        "funding_rate": item.get("funding_rate"),
        "market_quality_score": item.get("market_quality_score"),
        "trend_score": item.get("trend_score"),
        "smc_score": item.get("smc_score"),
        "setup_score": item.get("setup_score"),
        "rr_quality": item.get("rr_quality"),
        "entry_distance_percent": item.get("entry_distance_percent"),
    }


def record_scan(passed_items, failed_count, session_name, counts):
    """
    Tarama sonucunu journal'a yazar ve scan_id döndürür.
    passed_items: hard filter'ı geçen tüm item'lar.
    counts: {"ready": n, "watch": n, "wait": n}
    """
    now = _now_iso()

    with _db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO scans (created_at, session_name, ready_count, watch_count, wait_count, failed_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                session_name,
                counts.get("ready", 0),
                counts.get("watch", 0),
                counts.get("wait", 0),
                failed_count,
            ),
        )
        scan_id = cursor.lastrowid

        for item in passed_items:
            conn.execute(
                """
                INSERT INTO setups (
                    scan_id, created_at, symbol, setup_status, trend_direction,
                    atlas_score, entry, stop, target, rr, entry_state,
                    trigger_status, sequence_state, flags_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    now,
                    item.get("symbol"),
                    item.get("setup_status"),
                    item.get("trend_direction"),
                    _to_float(item.get("atlas_score")),
                    _to_float(item.get("entry")),
                    _to_float(item.get("stop")),
                    _to_float(item.get("target")),
                    _to_float(item.get("rr")),
                    item.get("entry_state"),
                    item.get("trigger_status"),
                    item.get("entry_sequence_state"),
                    json.dumps(_build_flags(item), ensure_ascii=False),
                ),
            )

            conn.execute(
                """
                INSERT INTO metrics_history (scan_id, created_at, symbol, open_interest, funding_rate, price)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    now,
                    item.get("symbol"),
                    _to_float(item.get("open_interest")),
                    _to_float(item.get("funding_rate")),
                    _to_float(item.get("current_price") or item.get("last_price")),
                ),
            )

    return scan_id


def resolve_open_setups(price_map):
    """
    Sonucu belirlenmemiş READY setup'ları günceller.

    price_map: {symbol: güncel fiyat}

    Kurallar (15 dk'lık tarama aralığında muhafazakar yaklaşım):
        - Önce stop kontrol edilir (SL_HIT), sonra target (TP_HIT).
        - OUTCOME_EXPIRE_DAYS geçen açık setup EXPIRED olur.

    Dönüş: {"tp": n, "sl": n, "expired": n}
    """
    resolved = {"tp": 0, "sl": 0, "expired": 0}
    now = _now_iso()
    expire_before = (
        datetime.now(timezone.utc) - timedelta(days=OUTCOME_EXPIRE_DAYS)
    ).isoformat()

    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, created_at, trend_direction, entry, stop, target
            FROM setups
            WHERE outcome IS NULL AND setup_status = 'READY'
            """
        ).fetchall()

        for row in rows:
            price = _to_float(price_map.get(row["symbol"]))
            outcome = None

            if row["created_at"] < expire_before:
                outcome = "EXPIRED"

            elif price is not None and row["stop"] and row["target"]:
                if row["trend_direction"] == "BULLISH":
                    if price <= row["stop"]:
                        outcome = "SL_HIT"
                    elif price >= row["target"]:
                        outcome = "TP_HIT"

                elif row["trend_direction"] == "BEARISH":
                    if price >= row["stop"]:
                        outcome = "SL_HIT"
                    elif price <= row["target"]:
                        outcome = "TP_HIT"

            if outcome:
                conn.execute(
                    """
                    UPDATE setups
                    SET outcome = ?, outcome_at = ?, outcome_price = ?
                    WHERE id = ?
                    """,
                    (outcome, now, price, row["id"]),
                )

                if outcome == "TP_HIT":
                    resolved["tp"] += 1
                elif outcome == "SL_HIT":
                    resolved["sl"] += 1
                else:
                    resolved["expired"] += 1

    return resolved


def get_outcome_stats():
    """
    Sequence state bazında gerçek başarı oranları.
    Gelecekteki Probability Engine'in ilk veri kaynağı.
    """
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT
                sequence_state,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'TP_HIT' THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'SL_HIT' THEN 1 ELSE 0 END) AS losses
            FROM setups
            WHERE outcome IN ('TP_HIT', 'SL_HIT')
            GROUP BY sequence_state
            """
        ).fetchall()

    stats = []

    for row in rows:
        decided = (row["wins"] or 0) + (row["losses"] or 0)
        win_rate = (row["wins"] / decided * 100) if decided else 0

        stats.append(
            {
                "sequence_state": row["sequence_state"],
                "total": row["total"],
                "wins": row["wins"],
                "losses": row["losses"],
                "win_rate_percent": round(win_rate, 1),
            }
        )

    return stats
