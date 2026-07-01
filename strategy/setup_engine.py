from scanner.bingx import get_klines


MIN_VALID_RR = 1.5
READY_DISTANCE_PERCENT = 1.0
WATCH_NEAR_DISTANCE_PERCENT = 3.0

DEFAULT_INTERVAL = "1h"
DEFAULT_LIMIT = 100
RECENT_RANGE_LOOKBACK = 50

LONG_ENTRY_RANGE_RATIO = 0.25
SHORT_ENTRY_RANGE_RATIO = 0.25
STOP_RANGE_RATIO = 0.10

BASE_STRUCTURE_SCORE = 10
STOP_STRUCTURE_SCORE = 15
TARGET_STRUCTURE_SCORE = 15
SMC_ALIGNMENT_SCORE = 15
SMC_ZONE_SCORE = 10
SMC_LIQUIDITY_SCORE = 10
MTF_SETUP_SCORE = 10

RANGE_SETUP_CAP = 60
RANGE_READY_ALLOWED = False

STRUCTURE_CONFLICT_SOFT_CAP = 55
STRUCTURE_CONFLICT_HARD_SCORE = 70

MTF_CONFLICT_SETUP_CAP = 65
MTF_STRONG_CONFLICT_SETUP_CAP = 50


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


def get_recent_high_low(klines, lookback=RECENT_RANGE_LOOKBACK):
    normalized = normalize_klines(klines)
    recent = normalized[-lookback:]

    highs = [item["high"] for item in recent]
    lows = [item["low"] for item in recent]
    closes = [item["close"] for item in recent]

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


def get_smc_direction_from_structure(structure):
    if structure.startswith("BULLISH"):
        return "BULLISH"

    if structure.startswith("BEARISH"):
        return "BEARISH"

    return "NEUTRAL"


def has_structure_conflict(trend_direction, structure):
    smc_direction = get_smc_direction_from_structure(structure)

    if trend_direction == "BULLISH" and smc_direction == "BEARISH":
        return True

    if trend_direction == "BEARISH" and smc_direction == "BULLISH":
        return True

    return False


def is_range_structure(structure):
    return structure == "RANGE" or get_smc_direction_from_structure(structure) == "NEUTRAL"


def score_entry_distance(entry_distance):
    if entry_distance <= READY_DISTANCE_PERCENT:
        return 30, "READY", "Fiyat entry bölgesine çok yakın"

    if entry_distance <= WATCH_NEAR_DISTANCE_PERCENT:
        return 15, "WATCH", "Fiyat entry bölgesine yaklaşıyor"

    return 0, "WATCH", "Fiyat entry bölgesinden uzak, izleme"


def is_price_inside_zone(price, zone):
    if not zone:
        return False

    low = to_float(zone.get("low"))
    high = to_float(zone.get("high"))

    if low is None or high is None:
        return False

    return low <= price <= high


def is_smc_aligned(trend_direction, smc):
    if not smc:
        return False

    smc_direction = smc.get("smc_direction") or get_smc_direction_from_structure(
        smc.get("structure", "RANGE")
    )

    return trend_direction == smc_direction


def is_premium_discount_valid(trend_direction, smc):
    premium_discount = smc.get("premium_discount", {}) if smc else {}
    price_zone = premium_discount.get("price_zone")

    if trend_direction == "BULLISH" and price_zone == "DISCOUNT":
        return True

    if trend_direction == "BEARISH" and price_zone == "PREMIUM":
        return True

    return False


def is_liquidity_sweep_valid(trend_direction, smc):
    liquidity_sweep = smc.get("liquidity_sweep") if smc else None

    if not liquidity_sweep:
        return False

    sweep_type = liquidity_sweep.get("type")

    if trend_direction == "BULLISH" and sweep_type == "SELL_SIDE_SWEEP":
        return True

    if trend_direction == "BEARISH" and sweep_type == "BUY_SIDE_SWEEP":
        return True

    return False


def get_smc_entry_zone(trend_direction, smc):
    if not smc:
        return None

    if trend_direction == "BULLISH":
        return smc.get("demand_zone") or smc.get("order_block")

    if trend_direction == "BEARISH":
        return smc.get("supply_zone") or smc.get("order_block")

    return None


def calculate_smc_setup_bonus(trend_direction, current_price, smc):
    score = 0
    reasons = []

    if not smc:
        return score, reasons

    if is_smc_aligned(trend_direction, smc):
        score += SMC_ALIGNMENT_SCORE
        reasons.append("Trend ile SMC yönü uyumlu")

    if is_premium_discount_valid(trend_direction, smc):
        score += SMC_ZONE_SCORE
        reasons.append("Premium/Discount bölgesi işlem yönüyle uyumlu")

    if is_liquidity_sweep_valid(trend_direction, smc):
        score += SMC_LIQUIDITY_SCORE
        reasons.append("Likidite sweep işlem yönünü destekliyor")

    entry_zone = get_smc_entry_zone(trend_direction, smc)

    if is_price_inside_zone(current_price, entry_zone):
        score += SMC_ZONE_SCORE
        reasons.append("Fiyat SMC entry zone içinde")

    return score, reasons


def get_mtf_bias(smc):
    if not smc:
        return "UNKNOWN"

    return smc.get("mtf_bias") or smc.get("mtf_context", {}).get("mtf_bias", "UNKNOWN")


def get_mtf_alignment(smc):
    if not smc:
        return "UNKNOWN"

    alignment = smc.get("mtf_alignment")

    if alignment:
        return alignment

    return (
        smc.get("mtf_context", {})
        .get("mtf_alignment", {})
        .get("alignment", "UNKNOWN")
    )


def is_opposite_mtf_bias(trend_direction, mtf_bias):
    if trend_direction == "BULLISH" and mtf_bias == "BEARISH":
        return True

    if trend_direction == "BEARISH" and mtf_bias == "BULLISH":
        return True

    return False


def is_weak_opposite_mtf_bias(trend_direction, mtf_bias):
    if trend_direction == "BULLISH" and mtf_bias == "BEARISH_WEAK":
        return True

    if trend_direction == "BEARISH" and mtf_bias == "BULLISH_WEAK":
        return True

    return False


def calculate_mtf_setup_bonus(trend_direction, smc):
    score = 0
    reasons = []

    mtf_bias = get_mtf_bias(smc)
    mtf_alignment = get_mtf_alignment(smc)

    if mtf_bias == trend_direction:
        score += MTF_SETUP_SCORE
        reasons.append(f"MTF bias trend yönüyle tam uyumlu: {mtf_bias}")

    elif mtf_bias == f"{trend_direction}_WEAK":
        score += int(MTF_SETUP_SCORE / 2)
        reasons.append(f"MTF bias trend yönüyle zayıf uyumlu: {mtf_bias}")

    elif mtf_alignment == "MTF_CONFLICT":
        reasons.append(f"MTF trend ile çelişiyor: {mtf_bias}")

    elif mtf_bias == "NEUTRAL":
        reasons.append("MTF bias nötr")

    else:
        reasons.append(f"MTF bias: {mtf_bias}")

    return score, reasons


def build_wait_result(
    setup_type,
    reason,
    current_price,
    entry=None,
    stop=None,
    target=None,
    rr=0,
    entry_distance=None,
):
    return {
        "setup_score": 0,
        "setup_type": setup_type,
        "setup_status": "WAIT",
        "current_price": current_price,
        "entry": round(entry, 6) if entry is not None else current_price,
        "stop": round(stop, 6) if stop is not None else None,
        "target": round(target, 6) if target is not None else None,
        "rr": round(rr, 2),
        "entry_distance_percent": round(entry_distance, 2) if entry_distance is not None else None,
        "setup_reasons": [reason],
    }


def apply_range_safety(score, setup_status, structure, reasons):
    if not is_range_structure(structure):
        return score, setup_status, reasons

    score = min(score, RANGE_SETUP_CAP)
    reasons.append("SMC RANGE olduğu için setup skoru sınırlandı")

    if setup_status == "READY" and not RANGE_READY_ALLOWED:
        setup_status = "WATCH"
        reasons.append("SMC RANGE olduğu için READY yerine WATCH olarak işaretlendi")

    return score, setup_status, reasons


def apply_structure_conflict_safety(score, setup_status, trend_direction, structure, smc, reasons):
    if not has_structure_conflict(trend_direction, structure):
        return score, setup_status, reasons

    smc_score = smc.get("smc_score", 0) if smc else 0
    mtf_bias = get_mtf_bias(smc)

    if smc_score >= STRUCTURE_CONFLICT_HARD_SCORE and is_opposite_mtf_bias(trend_direction, mtf_bias):
        score = 0
        setup_status = "WAIT"
        reasons.append("Güçlü SMC + güçlü MTF ters conflict nedeniyle setup WAIT yapıldı")
        return score, setup_status, reasons

    score = min(score, STRUCTURE_CONFLICT_SOFT_CAP)

    if setup_status == "READY":
        setup_status = "WATCH"

    reasons.append("Trend ile SMC yapısı çelişiyor, setup WATCH seviyesine indirildi")

    return score, setup_status, reasons


def apply_mtf_safety(score, setup_status, trend_direction, smc, reasons):
    mtf_bias = get_mtf_bias(smc)

    if is_opposite_mtf_bias(trend_direction, mtf_bias):
        score = min(score, MTF_STRONG_CONFLICT_SETUP_CAP)
        if setup_status == "READY":
            setup_status = "WATCH"
        reasons.append("Güçlü MTF conflict nedeniyle setup sınırlandı")

    elif is_weak_opposite_mtf_bias(trend_direction, mtf_bias):
        score = min(score, MTF_CONFLICT_SETUP_CAP)
        if setup_status == "READY":
            setup_status = "WATCH"
        reasons.append("Zayıf MTF conflict nedeniyle setup WATCH seviyesine indirildi")

    return score, setup_status, reasons


def calculate_setup_score(symbol, trend_direction, structure="RANGE", smc=None):
    klines = get_klines(symbol, interval=DEFAULT_INTERVAL, limit=DEFAULT_LIMIT)
    levels = get_recent_high_low(klines)

    recent_high = levels["recent_high"]
    recent_low = levels["recent_low"]
    current_price = levels["last_close"]

    range_size = recent_high - recent_low

    if range_size <= 0:
        return build_wait_result(
            setup_type="WAIT_INVALID_RANGE",
            reason="Geçersiz fiyat aralığı",
            current_price=current_price,
        )

    if trend_direction == "BULLISH":
        setup_type = "LONG_LIMIT_ZONE"
        entry = recent_low + (range_size * LONG_ENTRY_RANGE_RATIO)
        stop = recent_low - (range_size * STOP_RANGE_RATIO)
        target = recent_high
        rr = calculate_rr_long(entry, stop, target)

    elif trend_direction == "BEARISH":
        setup_type = "SHORT_LIMIT_ZONE"
        entry = recent_high - (range_size * SHORT_ENTRY_RANGE_RATIO)
        stop = recent_high + (range_size * STOP_RANGE_RATIO)
        target = recent_low
        rr = calculate_rr_short(entry, stop, target)

    else:
        return build_wait_result(
            setup_type="WAIT",
            reason="Trend yönü net değil",
            current_price=current_price,
        )

    entry_distance = distance_percent(current_price, entry)

    if rr < MIN_VALID_RR:
        return build_wait_result(
            setup_type="WAIT_RR_LOW",
            reason="RR düşük",
            current_price=current_price,
            entry=entry,
            stop=stop,
            target=target,
            rr=rr,
            entry_distance=entry_distance,
        )

    score = 0
    reasons = []

    rr_score = score_rr(rr)
    score += rr_score
    reasons.append("RR uygun")

    score += BASE_STRUCTURE_SCORE
    reasons.append("Setup yapısı geçerli")

    score += STOP_STRUCTURE_SCORE
    reasons.append("Stop yapısı uygun")

    score += TARGET_STRUCTURE_SCORE
    reasons.append("Hedef yapısı uygun")

    smc_bonus, smc_reasons = calculate_smc_setup_bonus(
        trend_direction=trend_direction,
        current_price=current_price,
        smc=smc,
    )
    score += smc_bonus
    reasons.extend(smc_reasons)

    mtf_bonus, mtf_reasons = calculate_mtf_setup_bonus(
        trend_direction=trend_direction,
        smc=smc,
    )
    score += mtf_bonus
    reasons.extend(mtf_reasons)

    distance_score, setup_status, distance_reason = score_entry_distance(entry_distance)
    score += distance_score
    reasons.append(distance_reason)

    score, setup_status, reasons = apply_range_safety(
        score=score,
        setup_status=setup_status,
        structure=structure,
        reasons=reasons,
    )

    score, setup_status, reasons = apply_structure_conflict_safety(
        score=score,
        setup_status=setup_status,
        trend_direction=trend_direction,
        structure=structure,
        smc=smc,
        reasons=reasons,
    )

    score, setup_status, reasons = apply_mtf_safety(
        score=score,
        setup_status=setup_status,
        trend_direction=trend_direction,
        smc=smc,
        reasons=reasons,
    )

    return {
        "setup_score": min(score, 100),
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