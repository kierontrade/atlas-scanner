from scanner.bingx import get_klines


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    ema_value = sum(values[:period]) / period

    for price in values[period:]:
        ema_value = (price - ema_value) * multiplier + ema_value

    return ema_value


def calculate_timeframe_trend(symbol, interval):
    klines = get_klines(symbol, interval=interval, limit=100)

    closes = [to_float(k["close"]) for k in klines if to_float(k["close"]) is not None]

    if len(closes) < 50:
        return {
            "interval": interval,
            "score": 0,
            "direction": "UNKNOWN",
            "reason": "Yetersiz mum verisi",
        }

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)

    current_close = closes[-1]
    previous_close = closes[-10]

    score = 0
    reasons = []

    if current_close > ema20:
        score += 25
        reasons.append("Fiyat EMA20 üstünde")

    if current_close > ema50:
        score += 25
        reasons.append("Fiyat EMA50 üstünde")

    if ema20 and ema50 and ema20 > ema50:
        score += 25
        reasons.append("EMA20 EMA50 üstünde")

    if current_close > previous_close:
        score += 25
        reasons.append("Son 10 mum momentum yukarı")

    if score >= 75:
        direction = "BULLISH"
    elif score <= 25:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {
        "interval": interval,
        "score": score,
        "direction": direction,
        "close": current_close,
        "ema20": ema20,
        "ema50": ema50,
        "reasons": reasons,
    }


def calculate_trend_score(symbol):
    daily = calculate_timeframe_trend(symbol, "1d")
    four_hour = calculate_timeframe_trend(symbol, "4h")
    one_hour = calculate_timeframe_trend(symbol, "1h")

    total_score = (
        daily["score"] * 0.4
        + four_hour["score"] * 0.4
        + one_hour["score"] * 0.2
    )

    if total_score >= 75:
        direction = "BULLISH"
    elif total_score <= 25:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {
        "symbol": symbol,
        "trend_score": round(total_score, 2),
        "trend_direction": direction,
        "daily": daily,
        "four_hour": four_hour,
        "one_hour": one_hour,
    }