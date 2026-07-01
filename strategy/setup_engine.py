from scanner.bingx import get_klines


MIN_VALID_RR = 1.5
READY_DISTANCE_PERCENT = 1.0
WATCH_NEAR_DISTANCE_PERCENT = 3.0


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_recent_high_low(klines, lookback=50):
    recent = klines[-lookback:]

    highs = [to_float(k["high"]) for k in recent]
    lows = [to_float(k["low"]) for k in recent]
    closes = [to_float(k["close"]) for k in recent]

    return {
        "recent_high": max(highs),
        "recent_low": min(lows),
        "last_close": closes[-1],
    }


def calculate_rr_long(entry, stop, target):
    risk = entry - stop
    reward = target - entry
    if risk <= 0:
        return 0
    return reward / risk


def calculate_rr_short(entry, stop, target):
    risk = stop - entry
    reward = entry - target
    if risk <= 0:
        return 0
    return reward / risk


def distance_percent(price, entry):
    if not price or not entry:
        return 999
    return abs((price - entry) / entry) * 100


def score_rr(rr):
    if rr >= 3:
        return 50
    if rr >= 2:
        return 40
    if rr >= 1.5:
        return 20
    return 0


def has_structure_conflict(trend_direction, structure):
    if trend_direction == "BULLISH" and structure.startswith("BEARISH"):
        return True

    if trend_direction == "BEARISH" and structure.startswith("BULLISH"):
        return True

    return False


def score_entry_distance(entry_distance):
    if entry_distance <= READY_DISTANCE_PERCENT:
        return 30, "READY", "Fiyat entry bölgesine çok yakın"
    if entry_distance <= WATCH_NEAR_DISTANCE_PERCENT:
        return 15, "WATCH_NEAR", "Fiyat entry bölgesine yaklaşıyor"
    return 0, "WATCH", "Fiyat entry bölgesinden uzak, izleme"


def calculate_setup_score(symbol, trend_direction, structure="RANGE"):
    klines = get_klines(symbol, interval="1h", limit=100)

    levels = get_recent_high_low(klines)
    recent_high = levels["recent_high"]
    recent_low = levels["recent_low"]
    current_price = levels["last_close"]

    if has_structure_conflict(trend_direction, structure):
        return {
            "setup_score": 0,
            "setup_type": "WAIT_STRUCTURE_CONFLICT",
            "setup_status": "WAIT",
            "current_price": current_price,
            "entry": current_price,
            "stop": None,
            "target": None,
            "rr": 0,
            "entry_distance_percent": None,
            "setup_reasons": ["Trend ile SMC yapısı çelişiyor"],
        }

    range_size = recent_high - recent_low

    if range_size <= 0:
        return {
            "setup_score": 0,
            "setup_type": "WAIT_INVALID_RANGE",
            "setup_status": "WAIT",
            "current_price": current_price,
            "entry": current_price,
            "stop": None,
            "target": None,
            "rr": 0,
            "entry_distance_percent": None,
            "setup_reasons": ["Geçersiz fiyat aralığı"],
        }

    if trend_direction == "BULLISH":
        setup_type = "LONG_LIMIT_ZONE"
        entry = recent_low + (range_size * 0.25)
        stop = recent_low - (range_size * 0.10)
        target = recent_high
        rr = calculate_rr_long(entry, stop, target)

    elif trend_direction == "BEARISH":
        setup_type = "SHORT_LIMIT_ZONE"
        entry = recent_high - (range_size * 0.25)
        stop = recent_high + (range_size * 0.10)
        target = recent_low
        rr = calculate_rr_short(entry, stop, target)

    else:
        return {
            "setup_score": 0,
            "setup_type": "WAIT",
            "setup_status": "WAIT",
            "current_price": current_price,
            "entry": current_price,
            "stop": None,
            "target": None,
            "rr": 0,
            "entry_distance_percent": None,
            "setup_reasons": ["Trend yönü net değil"],
        }

    entry_distance = distance_percent(current_price, entry)

    if rr < MIN_VALID_RR:
        return {
            "setup_score": 0,
            "setup_type": "WAIT_RR_LOW",
            "setup_status": "WAIT",
            "current_price": current_price,
            "entry": round(entry, 6),
            "stop": round(stop, 6),
            "target": round(target, 6),
            "rr": round(rr, 2),
            "entry_distance_percent": round(entry_distance, 2),
            "setup_reasons": ["RR düşük"],
        }

    score = 0
    reasons = []

    score += score_rr(rr)
    reasons.append("RR uygun")

    score += 15
    reasons.append("Stop yapısı uygun")

    score += 15
    reasons.append("Hedef yapısı uygun")

    distance_score, setup_status, distance_reason = score_entry_distance(entry_distance)
    score += distance_score
    reasons.append(distance_reason)

    return {
        "setup_score": score,
        "setup_type": setup_type,
        "setup_status": setup_status,
        "current_price": current_price,
        "entry": round(entry, 6),
        "stop": round(stop, 6),
        "target": round(target, 6),
        "rr": round(rr, 2),
        "entry_distance_percent": round(entry_distance, 2),
        "setup_reasons": reasons,
    }