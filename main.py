import argparse
import asyncio
import logging
import time
from pathlib import Path

from config.settings import SCAN_INTERVAL_MINUTES
from strategy.risk_engine import calculate_position_plan
from scanner.bingx import (
    get_swap_contracts,
    get_24h_tickers,
    filter_usdt_contracts,
    save_json,
)
from scanner.coingecko import get_top_coins
from scoring.matcher import match_contracts_with_coins
from scoring.async_market_metrics import get_market_metrics_bulk
from scoring.derivatives_engine import calculate_derivatives_score
from scoring.hard_filters import passes_hard_filters
from scoring.market_quality import calculate_market_quality
from storage import journal
from strategy.session_engine import get_session_context
from strategy.trend_engine import calculate_trend_score
from strategy.setup_engine import calculate_setup_score
from strategy.smc_engine import detect_structure
from reports.report_writer import write_atlas_report


def setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "atlas.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger("atlas")


CONFLICT_WATCH_SCORE_CAP = 62
RANGE_WATCH_SCORE_CAP = 58
MTF_CONFLICT_SCORE_CAP = 60


def get_ticker_map(tickers):
    return {
        ticker.get("symbol"): ticker
        for ticker in tickers
        if ticker.get("symbol")
    }


def calculate_volume_usd(volume, last_price):
    try:
        return float(volume) * float(last_price)
    except (TypeError, ValueError):
        return 0


def raw_atlas_score(mqs, trend_score, setup_score, smc_score):
    return round(
        (mqs * 0.20)
        + (trend_score * 0.25)
        + (setup_score * 0.30)
        + (smc_score * 0.25),
        2,
    )

def calculate_trigger_bonus(trigger_status):
    if trigger_status == "TRIGGER_READY":
        return 8

    if trigger_status == "TRIGGER_ARMED":
        return 4

    if trigger_status == "TRIGGER_WATCH":
        return 1

    return 0

def get_smc_direction(structure):
    if not structure:
        return "NEUTRAL"

    if structure.startswith("BULLISH"):
        return "BULLISH"

    if structure.startswith("BEARISH"):
        return "BEARISH"

    return "NEUTRAL"


def has_trend_smc_conflict(trend_direction, structure):
    smc_direction = get_smc_direction(structure)

    if trend_direction == "BULLISH" and smc_direction == "BEARISH":
        return True

    if trend_direction == "BEARISH" and smc_direction == "BULLISH":
        return True

    return False


def is_range_structure(structure):
    return get_smc_direction(structure) == "NEUTRAL"


def has_mtf_conflict(item):
    return item.get("mtf_alignment") == "MTF_CONFLICT"


def apply_score_caps(score, item):
    setup_status = item.get("setup_status")
    setup_type = item.get("setup_type")
    trend_direction = item.get("trend_direction")
    structure = item.get("structure", "RANGE")

    if setup_type == "WAIT_STRUCTURE_CONFLICT":
        return min(score, 40)

    if setup_status == "WAIT":
        return min(score, 50)

    if trend_direction == "NEUTRAL":
        return min(score, 50)

    if setup_status == "WATCH" and has_trend_smc_conflict(trend_direction, structure):
        return min(score, CONFLICT_WATCH_SCORE_CAP)

    if setup_status == "WATCH" and is_range_structure(structure):
        return min(score, RANGE_WATCH_SCORE_CAP)

    if setup_status == "WATCH" and has_mtf_conflict(item):
        return min(score, MTF_CONFLICT_SCORE_CAP)

    return score


def calculate_atlas_score(item, session_context=None):
    score = raw_atlas_score(
        item.get("market_quality_score", 0),
        item.get("trend_score", 0),
        item.get("setup_score", 0),
        item.get("smc_score", 0),
    )

    bonus_reasons = []

    trigger_bonus = calculate_trigger_bonus(item.get("trigger_status"))
    score += trigger_bonus

    if trigger_bonus:
        bonus_reasons.append(f"Trigger bonusu: +{trigger_bonus}")

    derivatives_bonus = item.get("derivatives_bonus", 0) or 0
    score += derivatives_bonus

    if derivatives_bonus:
        sign = "+" if derivatives_bonus > 0 else ""
        bonus_reasons.append(f"Derivatives bonusu: {sign}{derivatives_bonus}")

    if session_context:
        session_bonus = session_context.get("session_bonus", 0)
        score += session_bonus

        if session_bonus:
            sign = "+" if session_bonus > 0 else ""
            bonus_reasons.append(
                f"Session ({session_context.get('session_name')}): {sign}{session_bonus}"
            )

    item["atlas_bonus_reasons"] = bonus_reasons

    return apply_score_caps(
        score=round(score, 2),
        item=item,
    )


def print_candidate(item):
    print(
        "-",
        item["symbol"],
        "| Atlas:",
        item["atlas_score"],
        "| Status:",
        item.get("setup_status"),
        "| Type:",
        item.get("setup_type"),
        "| MQS:",
        item["market_quality_score"],
        "| Trend:",
        item["trend_score"],
        item["trend_direction"],
        "| SMC:",
        item.get("smc_score"),
        item.get("structure"),
        "| MTF:",
        item.get("mtf_bias"),
        item.get("mtf_alignment"),
        "| Trigger:",
        item.get("trigger_status"),
        item.get("trigger_score"),
        "| Seq:",
        item.get("entry_sequence_state"),
        "| TriggerReason:",
        " / ".join((item.get("trigger_reasons") or ["-"])[:3]),
        "| RR:",
        item["rr"],
        "| Price:",
        item.get("current_price"),
        "| EntryState:",
        item.get("entry_state"),
        "| Entry:",
        item.get("entry"),
        "| Stop:",
        item.get("stop"),
        "| TP:",
        item.get("target"),
        "| Uzaklık:",
        item.get("entry_distance_percent"),
        "%",
    )


def alert_sound():
    try:
        import winsound

        winsound.Beep(880, 350)
        winsound.Beep(1100, 350)
    except Exception:
        print("\a", end="")


def format_trade_card(item):
    """READY sinyalini BingX'e elle girilecek plan bloğuna çevirir."""
    tp_levels = item.get("plan_tp_levels") or []

    lines = []
    lines.append("┌" + "─" * 58)
    lines.append(f"│ 🟢 READY  {item['symbol']}  {item.get('plan_side', '-')}")
    lines.append(f"│ Atlas Score : {item.get('atlas_score')}  |  RR: {item.get('rr')}")
    lines.append("│")
    lines.append(f"│ Entry       : {item.get('entry')}")
    lines.append(f"│ Stop Loss   : {item.get('stop')}")

    for index, level in enumerate(tp_levels, start=1):
        lines.append(f"│ TP{index}         : {level['price']}  ({level['source']})")

    lines.append("│")
    lines.append(f"│ Miktar      : {item.get('plan_quantity')} coin")
    lines.append(f"│ Notional    : {item.get('plan_notional_usdt')} USDT")
    lines.append(f"│ Kaldıraç    : {item.get('plan_leverage')}x")
    lines.append(f"│ Marjin      : {item.get('plan_margin_usdt')} USDT")
    lines.append(
        f"│ Risk        : {item.get('plan_risk_usdt')} USDT "
        f"(%{item.get('plan_risk_percent')} — SL vurursa kayıp)"
    )
    lines.append("│")
    lines.append(f"│ Zamanlama   : {item.get('timing_advice')}")
    lines.append(f"│ Sequence    : {item.get('entry_sequence_state')}")

    for reason in (item.get("trigger_reasons") or [])[:4]:
        lines.append(f"│  ✓ {reason}")

    lines.append("└" + "─" * 58)

    return "\n".join(lines)


def print_trade_card(item):
    print("")
    print(format_trade_card(item))


def build_stats(contracts, usdt_contracts, matched_contracts, passed):
    return {
        "total_futures": len(contracts),
        "usdt_futures": len(usdt_contracts),
        "matched": len(matched_contracts),
        "passed": len(passed),
    }


def run_scan(alerted_setups):
    journal.init_db()

    session_context = get_session_context()
    print(
        f"\nSession: {session_context['session_name']} "
        f"(UTC {session_context['utc_hour']}:00) — {session_context['session_reason']}"
    )

    try:
        contracts = get_swap_contracts()
        tickers = get_24h_tickers()
        ticker_map = get_ticker_map(tickers)

        usdt_contracts = filter_usdt_contracts(contracts)

        coins = get_top_coins(limit=250)

        matched_contracts = match_contracts_with_coins(
            usdt_contracts,
            coins,
            min_market_cap=300_000_000,
        )

        symbols = [item["symbol"] for item in matched_contracts]

        print(f"\nParalel metrik çekiliyor: {len(symbols)} parite...")

        metrics_map = asyncio.run(
            get_market_metrics_bulk(
                symbols,
                batch_size=10,
            )
        )

        passed = []
        failed = []

        for item in matched_contracts:
            symbol = item["symbol"]

            ticker = ticker_map.get(symbol, {})

            item["last_price"] = ticker.get("lastPrice")
            item["volume_24h"] = ticker.get("volume")
            item["volume_usd_24h"] = calculate_volume_usd(
                item["volume_24h"],
                item["last_price"],
            )

            metrics = metrics_map.get(symbol, {})

            if metrics.get("metric_error"):
                item["hard_filter_passed"] = False
                item["hard_filter_reasons"] = [
                    f"Market metrics alınamadı: {metrics['metric_error']}"
                ]
                failed.append(item)
                continue

            item.update(metrics)

            filter_result = passes_hard_filters(item)

            item["hard_filter_passed"] = filter_result["passed"]
            item["hard_filter_reasons"] = filter_result["reasons"]

            if not filter_result["passed"]:
                failed.append(item)
                continue

            item = calculate_market_quality(item)

            trend = calculate_trend_score(symbol)
            item.update(trend)

            smc = detect_structure(symbol, "1h")
            item.update(smc)
            item["smc"] = smc

            setup = calculate_setup_score(
                symbol,
                item["trend_direction"],
                item.get("structure", "RANGE"),
                smc=smc,
            )
            item.update(setup)

            previous_metrics = journal.get_previous_metrics(symbol)
            derivatives = calculate_derivatives_score(
                item,
                previous_metrics=previous_metrics,
            )
            item.update(derivatives)

            item["session_name"] = session_context["session_name"]

            item["atlas_raw_score"] = raw_atlas_score(
                item.get("market_quality_score", 0),
                item.get("trend_score", 0),
                item.get("setup_score", 0),
                item.get("smc_score", 0),
            )

            item["atlas_score"] = calculate_atlas_score(
                item,
                session_context=session_context,
            )

            passed.append(item)

        passed.sort(
            key=lambda x: x.get("atlas_score", 0),
            reverse=True,
        )

        ready = [
            item
            for item in passed
            if item.get("setup_status") == "READY"
        ]

        watch = [
            item
            for item in passed
            if item.get("setup_status") == "WATCH"
        ]

        wait = [
            item
            for item in passed
            if item.get("setup_status") == "WAIT"
        ]

        # TP kademeleri ve pozisyon planı tüm kategoriler için hesaplanır
        # ki arayüzde WATCH/WAIT adayları da detaylı görünsün.
        for item in ready + watch + wait:
            plan = calculate_position_plan(item)

            if plan:
                item.update(plan)

        save_json(passed, "atlas_candidates.json")
        save_json(ready, "atlas_ready.json")
        save_json(watch, "atlas_watch.json")
        save_json(wait, "atlas_wait.json")
        save_json(failed, "market_quality_failed.json")

        price_map = {
            item["symbol"]: item.get("current_price") or item.get("last_price")
            for item in passed
        }
        outcomes = journal.resolve_open_setups(price_map)

        if any(outcomes.values()):
            print(
                f"\n📒 Journal: {outcomes['tp']} TP_HIT, "
                f"{outcomes['sl']} SL_HIT, {outcomes['expired']} EXPIRED olarak etiketlendi"
            )

        journal.record_scan(
            passed_items=passed,
            failed_count=len(failed),
            session_name=session_context["session_name"],
            counts={
                "ready": len(ready),
                "watch": len(watch),
                "wait": len(wait),
            },
        )

        outcome_stats = journal.get_outcome_stats()

        if outcome_stats:
            print("\n📊 Sequence bazlı gerçek başarı oranları (journal):")
            for stat in outcome_stats:
                print(
                    f"  {stat['sequence_state'] or 'UNKNOWN'}: "
                    f"%{stat['win_rate_percent']} "
                    f"({stat['wins']}W / {stat['losses']}L)"
                )

        stats = build_stats(
            contracts,
            usdt_contracts,
            matched_contracts,
            passed,
        )

        write_atlas_report(
            candidates=passed,
            ready=ready,
            watch=watch,
            wait=wait,
            failed=failed,
            stats=stats,
        )

        print("\n✓ Atlas tarama tamamlandı")
        print(f"Toplam futures: {len(contracts)}")
        print(f"USDT futures: {len(usdt_contracts)}")
        print(f"Market cap eşleşen: {len(matched_contracts)}")
        print(f"Hard Filter geçen: {len(passed)}")
        print(f"READY: {len(ready)}")
        print(f"WATCH: {len(watch)}")
        print(f"WAIT: {len(wait)}")

        print("\n🟢 READY adayları:")
        new_ready = False

        for item in ready[:10]:
            print_trade_card(item)

            alert_key = f"{item['symbol']}:{item.get('entry')}"

            if alert_key not in alerted_setups:
                alerted_setups.add(alert_key)
                new_ready = True

        if new_ready:
            alert_sound()

        print("\n🟡 WATCH adayları:")
        for item in watch[:10]:
            print_candidate(item)

        print("\n⚪ WAIT adayları:")
        for item in wait[:10]:
            print_candidate(item)

        return {
            "session": session_context,
            "stats": stats,
            "ready": ready,
            "watch": watch,
            "wait": wait,
            "failed_count": len(failed),
            "outcome_stats": outcome_stats,
            "new_ready": new_ready,
        }

    except Exception:
        logging.getLogger("atlas").exception("Tarama sırasında hata oluştu")
        print("\n❌ Hata oluştu — detay için logs/atlas.log dosyasına bak")
        return None


def main():
    parser = argparse.ArgumentParser(description="ATLAS SMC Scanner")
    parser.add_argument(
        "--loop",
        action="store_true",
        help=f"Sürekli mod: {SCAN_INTERVAL_MINUTES} dakikada bir tarar",
    )
    args = parser.parse_args()

    setup_logging()

    print("=" * 50)
    print("ATLAS SCANNER V1")
    print("Atlas Score V3 / SMC V5 / Entry Sequence V1")
    print("=" * 50)

    alerted_setups = set()

    if not args.loop:
        run_scan(alerted_setups)
        return

    print(f"\n♻ Sürekli mod aktif — her {SCAN_INTERVAL_MINUTES} dakikada bir tarama")
    print("Durdurmak için Ctrl+C\n")

    while True:
        run_scan(alerted_setups)

        next_scan = time.strftime(
            "%H:%M",
            time.localtime(time.time() + SCAN_INTERVAL_MINUTES * 60),
        )
        print(f"\n⏳ Sonraki tarama: {next_scan}")

        try:
            time.sleep(SCAN_INTERVAL_MINUTES * 60)
        except KeyboardInterrupt:
            print("\nATLAS durduruldu.")
            break


if __name__ == "__main__":
    main()