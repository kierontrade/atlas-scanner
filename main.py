import asyncio

from scanner.bingx import (
    get_swap_contracts,
    get_24h_tickers,
    filter_usdt_contracts,
    save_json,
)
from scanner.coingecko import get_top_coins
from scoring.matcher import match_contracts_with_coins
from scoring.async_market_metrics import get_market_metrics_bulk
from scoring.hard_filters import passes_hard_filters
from scoring.market_quality import calculate_market_quality
from strategy.trend_engine import calculate_trend_score
from strategy.setup_engine import calculate_setup_score
from strategy.smc_engine import detect_structure
from reports.report_writer import write_atlas_report


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


def apply_score_caps(score, setup_status, setup_type, trend_direction):
    if setup_type == "WAIT_STRUCTURE_CONFLICT":
        return min(score, 40)

    if setup_status == "WAIT":
        return min(score, 50)

    if trend_direction == "NEUTRAL":
        return min(score, 50)

    return score


def calculate_atlas_score(
    mqs,
    trend_score,
    setup_score,
    smc_score,
    setup_status,
    setup_type,
    trend_direction,
):
    score = raw_atlas_score(
        mqs,
        trend_score,
        setup_score,
        smc_score,
    )

    return apply_score_caps(
        score,
        setup_status,
        setup_type,
        trend_direction,
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
        "| RR:",
        item["rr"],
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


def build_stats(contracts, usdt_contracts, matched_contracts, passed):
    return {
        "total_futures": len(contracts),
        "usdt_futures": len(usdt_contracts),
        "matched": len(matched_contracts),
        "passed": len(passed),
    }


def main():
    print("=" * 50)
    print("ATLAS SCANNER V1")
    print("Atlas Score V2 / SMC V5")
    print("=" * 50)

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

            item["atlas_raw_score"] = raw_atlas_score(
                item.get("market_quality_score", 0),
                item.get("trend_score", 0),
                item.get("setup_score", 0),
                item.get("smc_score", 0),
            )

            item["atlas_score"] = calculate_atlas_score(
                item.get("market_quality_score", 0),
                item.get("trend_score", 0),
                item.get("setup_score", 0),
                item.get("smc_score", 0),
                item.get("setup_status"),
                item.get("setup_type"),
                item.get("trend_direction"),
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

        save_json(passed, "atlas_candidates.json")
        save_json(ready, "atlas_ready.json")
        save_json(watch, "atlas_watch.json")
        save_json(wait, "atlas_wait.json")
        save_json(failed, "market_quality_failed.json")

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
        for item in ready[:10]:
            print_candidate(item)

        print("\n🟡 WATCH adayları:")
        for item in watch[:10]:
            print_candidate(item)

        print("\n⚪ WAIT adayları:")
        for item in wait[:10]:
            print_candidate(item)

    except Exception as e:
        print("\n❌ Hata oluştu:")
        print(e)


if __name__ == "__main__":
    main()