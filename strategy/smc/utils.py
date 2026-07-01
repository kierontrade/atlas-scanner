def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_candle(candle):
    return {
        "open": to_float(candle.get("open")),
        "high": to_float(candle.get("high")),
        "low": to_float(candle.get("low")),
        "close": to_float(candle.get("close")),
        "volume": to_float(candle.get("volume", 0)),
        "time": candle.get("time") or candle.get("openTime") or candle.get("timestamp"),
    }


def normalize_klines(klines):
    normalized = []

    for candle in klines:
        item = normalize_candle(candle)

        if (
            item["open"] is None
            or item["high"] is None
            or item["low"] is None
            or item["close"] is None
        ):
            continue

        normalized.append(item)

    return normalized


def is_close_level(price_a, price_b, tolerance_percent):
    if price_a is None or price_b is None or price_b == 0:
        return False

    distance = abs((price_a - price_b) / price_b) * 100
    return distance <= tolerance_percent


def get_structure_direction(structure):
    if structure in ("BULLISH_STRUCTURE", "BULLISH_BOS", "BULLISH_CHOCH"):
        return "BULLISH"

    if structure in ("BEARISH_STRUCTURE", "BEARISH_BOS", "BEARISH_CHOCH"):
        return "BEARISH"

    return "NEUTRAL"