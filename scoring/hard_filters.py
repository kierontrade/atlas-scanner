MIN_MARKET_CAP = 300_000_000
MAX_FUNDING_ABS = 0.001
MAX_SPREAD_PERCENT = 0.05
MIN_VOLUME_USD_24H = 10_000_000


def passes_hard_filters(item):
    reasons = []

    market_cap = item.get("market_cap") or 0

    try:
        volume_usd_24h = float(item.get("volume_usd_24h") or 0)
    except ValueError:
        volume_usd_24h = 0

    try:
        funding_rate = abs(float(item.get("funding_rate") or 0))
    except ValueError:
        funding_rate = 999

    try:
        spread_percent = float(item.get("spread_percent") or 999)
    except ValueError:
        spread_percent = 999

    if market_cap < MIN_MARKET_CAP:
        reasons.append("Market cap düşük")

    if volume_usd_24h < MIN_VOLUME_USD_24H:
        reasons.append("24H USD hacim düşük")

    if funding_rate > MAX_FUNDING_ABS:
        reasons.append("Funding aşırı")

    if spread_percent > MAX_SPREAD_PERCENT:
        reasons.append("Spread yüksek")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }