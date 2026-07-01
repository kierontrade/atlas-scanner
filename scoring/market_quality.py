def score_market_cap(market_cap):
    if market_cap >= 50_000_000_000:
        return 15
    if market_cap >= 10_000_000_000:
        return 13
    if market_cap >= 3_000_000_000:
        return 11
    if market_cap >= 1_000_000_000:
        return 8
    if market_cap >= 300_000_000:
        return 5
    return 0


def score_rank(rank):
    if not rank:
        return 0

    if rank <= 10:
        return 10
    if rank <= 25:
        return 8
    if rank <= 50:
        return 6
    if rank <= 100:
        return 4
    if rank <= 250:
        return 2

    return 0


def score_volume_usd(volume_usd):
    try:
        volume_usd = float(volume_usd)
    except (TypeError, ValueError):
        return 0

    if volume_usd >= 1_000_000_000:
        return 15
    if volume_usd >= 300_000_000:
        return 12
    if volume_usd >= 100_000_000:
        return 9
    if volume_usd >= 30_000_000:
        return 6
    if volume_usd >= 10_000_000:
        return 3

    return 0


def calculate_market_quality(item):
    market_cap_score = score_market_cap(item.get("market_cap", 0))
    rank_score = score_rank(item.get("rank"))
    volume_score = score_volume_usd(item.get("volume_usd_24h"))

    total_score = (
        market_cap_score
        + volume_score
        + item.get("score_open_interest", 0)
        + item.get("score_funding", 0)
        + item.get("score_spread", 0)
        + item.get("score_atr", 0)
        + rank_score
        + item.get("score_orderbook_depth", 0)
        + item.get("score_data_quality", 0)
    )

    return {
        **item,
        "score_market_cap": market_cap_score,
        "score_rank": rank_score,
        "score_volume": volume_score,
        "market_quality_score": total_score,
    }