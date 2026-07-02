from scanner.bingx import get_klines
from strategy.entry_sequence import analyze_entry_sequence, empty_sequence


MIN_VALID_RR = 1.3
MAX_REALISTIC_RR = 6.0
MIN_STOP_DISTANCE_PERCENT = 0.45

READY_DISTANCE_PERCENT = 1.0
WATCH_NEAR_DISTANCE_PERCENT = 3.0
TRIGGER_READY_DISTANCE_PERCENT = 0.30
TRIGGER_ARMED_DISTANCE_PERCENT = 0.80
ENTRY_MISSED_BUFFER_PERCENT = 0.20

# Tarama modları — entry mesafesi HER İKİ modda da aynıdır (sniper mesafe);
# esneyen şey skorlama/setup koşullarıdır:
#   STRICT   -> onay eşiği 55, sweep şart, trend nötrse setup yok.
#   FLEXIBLE -> onay eşiği 40, sweep şart değil (puan vermeye devam eder),
#               trend nötrse SMC yönü devralır. Amaç günde ~10 sinyalle
#               istatistik biriktirmek (demo). Mod data/user_config.json'dan okunur.
SCAN_MODES = {
    "STRICT": {
        "trigger_ready_distance": TRIGGER_READY_DISTANCE_PERCENT,
        "trigger_armed_distance": TRIGGER_ARMED_DISTANCE_PERCENT,
        "confirmation_min": 55,
        "require_sweep_for_ready": True,
        "use_smc_direction_fallback": False,
    },
    "FLEXIBLE": {
        "trigger_ready_distance": TRIGGER_READY_DISTANCE_PERCENT,
        "trigger_armed_distance": TRIGGER_ARMED_DISTANCE_PERCENT,
        "confirmation_min": 40,
        "require_sweep_for_ready": False,
        "use_smc_direction_fallback": True,
    },
}


def get_scan_mode_params():
    from config.user_config import get_scan_mode

    mode = get_scan_mode()
    return mode, SCAN_MODES.get(mode, SCAN_MODES["STRICT"])

DEFAULT_INTERVAL = "1h"
DEFAULT_LIMIT = 100
RECENT_RANGE_LOOKBACK = 50

LONG_ENTRY_RANGE_RATIO = 0.25
SHORT_ENTRY_RANGE_RATIO = 0.25
STOP_BUFFER_PERCENT = 0.35

BASE_STRUCTURE_SCORE = 10
STOP_STRUCTURE_SCORE = 15
TARGET_STRUCTURE_SCORE = 15
SMC_ALIGNMENT_SCORE = 15
SMC_ZONE_SCORE = 10
SMC_LIQUIDITY_SCORE = 10
MTF_SETUP_SCORE = 10

RANGE_SETUP_CAP = 58
RANGE_READY_ALLOWED = False

SOFT_CONFLICT_CAP = 58
MEDIUM_CONFLICT_CAP = 52
HARD_CONFLICT_CAP = 45


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


def calculate_cvd_proxy(normalized_klines, lookback=20):
    """
    İşaretli hacim toplamı (CVD yaklaşığı):
    yeşil mum hacmi +, kırmızı mum hacmi - sayılır.
    Gerçek tick delta'sı değildir ama agresif taraf eğilimini gösterir.
    """
    recent = normalized_klines[-lookback:]
    total = 0.0

    for candle in recent:
        volume = candle.get("volume") or 0

        if candle["close"] > candle["open"]:
            total += volume
        elif candle["close"] < candle["open"]:
            total -= volume

    return round(total, 4)


def calculate_price_change_percent(normalized_klines, lookback=20):
    recent = normalized_klines[-lookback:]

    if len(recent) < 2 or not recent[0]["close"]:
        return None

    first = recent[0]["close"]
    last = recent[-1]["close"]

    return round(((last - first) / first) * 100, 4)


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


def stop_distance_percent(entry, stop):
    if not entry or not stop:
        return 999

    return abs((entry - stop) / entry) * 100


def classify_rr(rr):
    if rr < MIN_VALID_RR:
        return "LOW"

    if rr <= 4:
        return "VALID"

    if rr <= MAX_REALISTIC_RR:
        return "HIGH"

    return "OUTLIER"


def score_rr(rr):
    rr_quality = classify_rr(rr)

    if rr_quality == "OUTLIER":
        return 35

    if rr >= 4:
        return 45

    if rr >= 3:
        return 42

    if rr >= 2:
        return 35

    if rr >= 1.5:
        return 20

    if rr >= 1.3:
        return 10

    return 0


def get_direction_from_structure(structure):
    if not structure:
        return "NEUTRAL"

    if structure.startswith("BULLISH"):
        return "BULLISH"

    if structure.startswith("BEARISH"):
        return "BEARISH"

    return "NEUTRAL"


def get_smc_direction(smc, structure):
    if smc:
        direction = smc.get("smc_direction")

        if direction:
            return direction

    return get_direction_from_structure(structure)


def normalize_mtf_bias(mtf_bias):
    if not mtf_bias:
        return "UNKNOWN"

    if mtf_bias in ("BULLISH", "BULLISH_WEAK"):
        return "BULLISH"

    if mtf_bias in ("BEARISH", "BEARISH_WEAK"):
        return "BEARISH"

    if mtf_bias == "NEUTRAL":
        return "NEUTRAL"

    return "UNKNOWN"


def is_range_structure(structure):
    return get_direction_from_structure(structure) == "NEUTRAL"

def classify_entry_state(trend_direction, current_price, entry):
    if not current_price or not entry:
        return "UNKNOWN"

    buffer_value = entry * (ENTRY_MISSED_BUFFER_PERCENT / 100)

    if trend_direction == "BULLISH":
        if current_price < entry - buffer_value:
            return "MISSED_ENTRY"

        if abs(current_price - entry) <= buffer_value:
            return "AT_ENTRY"

        return "WAITING_FOR_ENTRY"

    if trend_direction == "BEARISH":
        if current_price > entry + buffer_value:
            return "MISSED_ENTRY"

        if abs(current_price - entry) <= buffer_value:
            return "AT_ENTRY"

        return "WAITING_FOR_ENTRY"

    return "UNKNOWN"

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


def is_valid_price(value):
    return value is not None and value > 0


def zone_mid(zone):
    if not zone:
        return None

    mid = to_float(zone.get("mid"))
    if mid:
        return mid

    low = to_float(zone.get("low"))
    high = to_float(zone.get("high"))

    if low is None or high is None:
        return None

    return (low + high) / 2


def extract_zone_price(zone, side):
    if not zone:
        return None

    low = to_float(zone.get("low"))
    high = to_float(zone.get("high"))
    mid = zone_mid(zone)

    if side == "LOW":
        return low

    if side == "HIGH":
        return high

    return mid


def add_level(levels, price, source, level_type):
    price = to_float(price)

    if not is_valid_price(price):
        return

    levels.append(
        {
            "price": price,
            "source": source,
            "type": level_type,
        }
    )


def build_target_levels(trend_direction, recent_high, recent_low, smc):
    levels = []

    if trend_direction == "BULLISH":
        add_level(levels, recent_high, "RECENT_HIGH", "SWING_TARGET")

        if smc:
            add_level(levels, extract_zone_price(smc.get("supply_zone"), "LOW"), "SUPPLY_ZONE_LOW", "ZONE_TARGET")
            add_level(levels, extract_zone_price(smc.get("active_bpr"), "HIGH"), "ACTIVE_BPR_HIGH", "IMBALANCE_TARGET")
            add_level(levels, extract_zone_price(smc.get("active_fvg"), "HIGH"), "ACTIVE_FVG_HIGH", "IMBALANCE_TARGET")
            add_level(levels, extract_zone_price(smc.get("active_ifvg"), "HIGH"), "ACTIVE_IFVG_HIGH", "IMBALANCE_TARGET")

            for pool in smc.get("liquidity_pools", []):
                if pool.get("type") == "BUY_SIDE_LIQUIDITY":
                    add_level(levels, pool.get("price"), "BUY_SIDE_LIQUIDITY", "LIQUIDITY_TARGET")

    elif trend_direction == "BEARISH":
        add_level(levels, recent_low, "RECENT_LOW", "SWING_TARGET")

        if smc:
            add_level(levels, extract_zone_price(smc.get("demand_zone"), "HIGH"), "DEMAND_ZONE_HIGH", "ZONE_TARGET")
            add_level(levels, extract_zone_price(smc.get("active_bpr"), "LOW"), "ACTIVE_BPR_LOW", "IMBALANCE_TARGET")
            add_level(levels, extract_zone_price(smc.get("active_fvg"), "LOW"), "ACTIVE_FVG_LOW", "IMBALANCE_TARGET")
            add_level(levels, extract_zone_price(smc.get("active_ifvg"), "LOW"), "ACTIVE_IFVG_LOW", "IMBALANCE_TARGET")

            for pool in smc.get("liquidity_pools", []):
                if pool.get("type") == "SELL_SIDE_LIQUIDITY":
                    add_level(levels, pool.get("price"), "SELL_SIDE_LIQUIDITY", "LIQUIDITY_TARGET")

    return levels


def choose_target(trend_direction, entry, stop, target_levels):
    candidates = []

    for level in target_levels:
        price = level["price"]

        if trend_direction == "BULLISH" and price <= entry:
            continue

        if trend_direction == "BEARISH" and price >= entry:
            continue

        rr = (
            calculate_rr_long(entry, stop, price)
            if trend_direction == "BULLISH"
            else calculate_rr_short(entry, stop, price)
        )

        if rr <= 0:
            continue

        item = dict(level)
        item["rr"] = rr
        item["rr_quality"] = classify_rr(rr)
        candidates.append(item)

    if not candidates:
        return None

    valid = [item for item in candidates if item["rr"] >= MIN_VALID_RR]

    if valid:
        valid.sort(
            key=lambda item: (
                item["rr_quality"] != "OUTLIER",
                item["rr"] <= MAX_REALISTIC_RR,
                item["rr"],
            ),
            reverse=True,
        )
        return valid[0]

    candidates.sort(key=lambda item: item["rr"], reverse=True)
    return candidates[0]


def calculate_buffer(price):
    return price * (STOP_BUFFER_PERCENT / 100)


def enforce_min_stop_distance(trend_direction, entry, stop):
    min_distance = entry * (MIN_STOP_DISTANCE_PERCENT / 100)
    current_distance = abs(entry - stop)

    if current_distance >= min_distance:
        return stop, False

    if trend_direction == "BULLISH":
        return entry - min_distance, True

    if trend_direction == "BEARISH":
        return entry + min_distance, True

    return stop, False


def build_entry_stop_target(trend_direction, recent_high, recent_low, smc):
    range_size = recent_high - recent_low

    if range_size <= 0:
        return None

    if trend_direction == "BULLISH":
        entry = recent_low + (range_size * LONG_ENTRY_RANGE_RATIO)

        demand_zone = smc.get("demand_zone") if smc else None
        demand_low = extract_zone_price(demand_zone, "LOW")
        stop_base = demand_low if is_valid_price(demand_low) and demand_low < entry else recent_low
        stop = stop_base - calculate_buffer(stop_base)

    elif trend_direction == "BEARISH":
        entry = recent_high - (range_size * SHORT_ENTRY_RANGE_RATIO)

        supply_zone = smc.get("supply_zone") if smc else None
        supply_high = extract_zone_price(supply_zone, "HIGH")
        stop_base = supply_high if is_valid_price(supply_high) and supply_high > entry else recent_high
        stop = stop_base + calculate_buffer(stop_base)

    else:
        return None

    stop, stop_adjusted = enforce_min_stop_distance(
        trend_direction=trend_direction,
        entry=entry,
        stop=stop,
    )

    target_levels = build_target_levels(
        trend_direction=trend_direction,
        recent_high=recent_high,
        recent_low=recent_low,
        smc=smc,
    )

    target = choose_target(
        trend_direction=trend_direction,
        entry=entry,
        stop=stop,
        target_levels=target_levels,
    )

    if not target:
        return None

    rr = (
        calculate_rr_long(entry, stop, target["price"])
        if trend_direction == "BULLISH"
        else calculate_rr_short(entry, stop, target["price"])
    )

    return {
        "entry": entry,
        "stop": stop,
        "target": target["price"],
        "rr": rr,
        "rr_quality": classify_rr(rr),
        "stop_distance_percent": stop_distance_percent(entry, stop),
        "stop_adjusted": stop_adjusted,
        "target_source": target["source"],
        "target_type": target["type"],
        "target_candidates": target_levels,
    }


def is_smc_aligned(trend_direction, smc):
    if not smc:
        return False

    smc_direction = smc.get("smc_direction") or get_direction_from_structure(
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


def get_conflict_severity(trend_direction, structure, smc):
    smc_direction = get_smc_direction(smc, structure)
    mtf_bias = get_mtf_bias(smc)
    mtf_direction = normalize_mtf_bias(mtf_bias)
    mtf_alignment = get_mtf_alignment(smc)

    if trend_direction == "NEUTRAL":
        return {
            "level": "NONE",
            "reason": "Trend nötr",
        }

    if smc_direction == "NEUTRAL":
        return {
            "level": "RANGE",
            "reason": "SMC range / nötr",
        }

    trend_smc_conflict = trend_direction != smc_direction
    mtf_supports_smc = mtf_direction == smc_direction
    mtf_supports_trend = mtf_direction == trend_direction

    if not trend_smc_conflict:
        if mtf_supports_trend or mtf_alignment in ("FULL_ALIGNMENT", "WEAK_ALIGNMENT"):
            return {
                "level": "NONE",
                "reason": "Trend, SMC ve MTF uyumlu",
            }

        if mtf_direction == "NEUTRAL":
            return {
                "level": "NONE",
                "reason": "Trend ve SMC uyumlu, MTF nötr",
            }

        return {
            "level": "SOFT",
            "reason": "Trend ve SMC uyumlu fakat MTF kararsız/ters",
        }

    if mtf_supports_smc and mtf_alignment == "FULL_ALIGNMENT":
        return {
            "level": "HARD",
            "reason": "Trend tersine SMC + MTF full alignment var",
        }

    if mtf_supports_smc and mtf_alignment == "WEAK_ALIGNMENT":
        return {
            "level": "MEDIUM",
            "reason": "Trend ile SMC çelişiyor, MTF SMC tarafını zayıf destekliyor",
        }

    if mtf_supports_smc:
        return {
            "level": "MEDIUM",
            "reason": "Trend ile SMC çelişiyor, MTF SMC tarafını destekliyor",
        }

    if mtf_direction == "NEUTRAL":
        return {
            "level": "SOFT",
            "reason": "Trend ile SMC çelişiyor fakat MTF nötr",
        }

    if mtf_supports_trend:
        return {
            "level": "SOFT",
            "reason": "Trend ile SMC çelişiyor fakat MTF trendi destekliyor",
        }

    return {
        "level": "MEDIUM",
        "reason": "Trend ile SMC çelişiyor ve MTF belirsiz",
    }


def get_trigger_confirmation_score(trend_direction, smc):
    if not smc:
        return 0, []

    score = 0
    reasons = []

    displacement = smc.get("displacement", {})
    choch = smc.get("choch")
    bos = smc.get("bos")
    mtf_bias = get_mtf_bias(smc)
    mtf_alignment = get_mtf_alignment(smc)

    if is_liquidity_sweep_valid(trend_direction, smc):
        score += 35
        reasons.append("Trigger: Yönle uyumlu liquidity sweep var")

    if displacement.get("has_displacement") and displacement.get("direction") == trend_direction:
        score += 30
        reasons.append("Trigger: Yönle uyumlu displacement var")

    if trend_direction == "BULLISH" and choch == "BULLISH_CHOCH":
        score += 25
        reasons.append("Trigger: Bullish CHoCH var")

    if trend_direction == "BEARISH" and choch == "BEARISH_CHOCH":
        score += 25
        reasons.append("Trigger: Bearish CHoCH var")

    if trend_direction == "BULLISH" and bos == "BULLISH_BOS":
        score += 20
        reasons.append("Trigger: Bullish BOS var")

    if trend_direction == "BEARISH" and bos == "BEARISH_BOS":
        score += 20
        reasons.append("Trigger: Bearish BOS var")

    if mtf_bias == trend_direction:
        score += 15
        reasons.append("Trigger: MTF tam yönde")

    elif mtf_bias == f"{trend_direction}_WEAK":
        score += 8
        reasons.append("Trigger: MTF zayıf yönde")

    elif mtf_alignment == "MTF_NEUTRAL":
        score += 5
        reasons.append("Trigger: MTF nötr, ters baskı yok")

    return score, reasons


def calculate_trigger(
    trend_direction,
    setup_status,
    entry_distance,
    conflict,
    smc,
    sequence=None,
    mode_params=None,
):
    reasons = []
    trigger_score = 0
    trigger_status = "NO_TRIGGER"

    if mode_params is None:
        _, mode_params = get_scan_mode_params()

    ready_distance = mode_params["trigger_ready_distance"]
    armed_distance = mode_params["trigger_armed_distance"]
    confirmation_min = mode_params["confirmation_min"]
    require_sweep = mode_params["require_sweep_for_ready"]

    if setup_status == "WAIT":
        return {
            "trigger_status": "NO_TRIGGER",
            "trigger_score": 0,
            "trigger_reasons": ["Setup WAIT olduğu için trigger aranmadı"],
        }

    if conflict.get("level") in ("HARD", "MEDIUM"):
        return {
            "trigger_status": "NO_TRIGGER",
            "trigger_score": 0,
            "trigger_reasons": ["Conflict seviyesi yüksek olduğu için trigger kapalı"],
        }

    confirmation_score, confirmation_reasons = get_trigger_confirmation_score(
        trend_direction=trend_direction,
        smc=smc,
    )

    sequence = sequence or empty_sequence()
    sequence_state = sequence.get("sequence_state", "NOT_EVALUATED")

    confirmation_score += sequence.get("sequence_score", 0)
    confirmation_reasons.extend(sequence.get("sequence_reasons", []))

    proximity_bonus = 0

    if entry_distance <= ready_distance:
        proximity_bonus = 20
    elif entry_distance <= armed_distance:
        proximity_bonus = 10

    final_confirmation_score = confirmation_score + proximity_bonus

    # Sniper disiplini (STRICT): likidite alınmadan TRIGGER_READY verilmez.
    sequence_blocks_ready = require_sweep and sequence_state in ("IDLE",)

    if (
        entry_distance <= ready_distance
        and final_confirmation_score >= confirmation_min
        and sequence_blocks_ready
    ):
        trigger_status = "TRIGGER_ARMED"
        trigger_score = min(75, 40 + int(final_confirmation_score / 2))
        reasons.append(
            "Confirmation yeterli fakat liquidity sweep yok — READY sweep sonrasına ertelendi"
        )
        reasons.extend(confirmation_reasons)

    elif entry_distance <= ready_distance and final_confirmation_score >= confirmation_min:
        trigger_status = "TRIGGER_READY"
        trigger_score = min(100, 80 + int(final_confirmation_score / 5))
        reasons.append("Fiyat entry bölgesinde ve yeterli confirmation var")
        reasons.extend(confirmation_reasons)

    elif entry_distance <= armed_distance:
        trigger_status = "TRIGGER_ARMED"
        trigger_score = min(75, 40 + int(final_confirmation_score / 2))
        reasons.append("Fiyat entry bölgesine çok yakın")
        reasons.extend(confirmation_reasons)

    elif entry_distance <= WATCH_NEAR_DISTANCE_PERCENT:
        trigger_status = "TRIGGER_WATCH"
        trigger_score = min(45, 20 + int(final_confirmation_score / 3))
        reasons.append("Fiyat entry bölgesine yaklaşıyor")
        reasons.extend(confirmation_reasons)

    else:
        reasons.append("Fiyat trigger mesafesinde değil")

    return {
        "trigger_status": trigger_status,
        "trigger_score": trigger_score,
        "trigger_reasons": reasons,
    }


def apply_trigger_to_status(setup_status, trigger_status, entry_state=None):
    if setup_status == "WAIT":
        return "WAIT"

    if entry_state == "MISSED_ENTRY":
        return "WAIT"

    if trigger_status == "TRIGGER_READY":
        return "READY"

    if setup_status == "READY" and trigger_status != "TRIGGER_READY":
        return "WATCH"

    return setup_status


def build_wait_result(
    setup_type,
    reason,
    current_price,
    entry=None,
    stop=None,
    target=None,
    rr=0,
    entry_distance=None,
    sequence=None,
    cvd_proxy=None,
    price_change_percent_20=None,
):
    sequence = sequence or empty_sequence()

    return {
        "entry_sequence_state": sequence.get("sequence_state"),
        "entry_sequence_score": sequence.get("sequence_score", 0),
        "entry_sequence_reasons": sequence.get("sequence_reasons", []),
        "has_cisd": sequence.get("has_cisd", False),
        "has_mss": sequence.get("has_mss", False),
        "timing_advice": sequence.get("timing_advice"),
        "cvd_proxy": cvd_proxy,
        "price_change_percent_20": price_change_percent_20,
        "setup_score": 0,
        "setup_type": setup_type,
        "setup_status": "WAIT",
        "current_price": current_price,
        "entry": round(entry, 6) if entry is not None else current_price,
        "stop": round(stop, 6) if stop is not None else None,
        "target": round(target, 6) if target is not None else None,
        "rr": round(rr, 2),
        "rr_quality": classify_rr(rr),
        "stop_distance_percent": None,
        "stop_adjusted": False,
        "entry_distance_percent": round(entry_distance, 2) if entry_distance is not None else None,
        "entry_state": "UNKNOWN",
        "target_source": None,
        "target_type": None,
        "conflict_level": None,
        "conflict_reason": reason,
        "trigger_status": "NO_TRIGGER",
        "trigger_score": 0,
        "trigger_reasons": [reason],
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


def apply_conflict_severity(score, setup_status, conflict, reasons):
    level = conflict["level"]
    reason = conflict["reason"]

    if level == "NONE":
        reasons.append(reason)
        return score, setup_status, reasons

    if level == "RANGE":
        score = min(score, RANGE_SETUP_CAP)
        if setup_status == "READY":
            setup_status = "WATCH"
        reasons.append(reason)
        return score, setup_status, reasons

    if level == "SOFT":
        score = min(score, SOFT_CONFLICT_CAP)
        if setup_status == "READY":
            setup_status = "WATCH"
        reasons.append(reason)
        return score, setup_status, reasons

    if level == "MEDIUM":
        score = min(score, MEDIUM_CONFLICT_CAP)
        setup_status = "WATCH"
        reasons.append(reason)
        return score, setup_status, reasons

    if level == "HARD":
        score = min(score, HARD_CONFLICT_CAP)
        setup_status = "WAIT"
        reasons.append(reason)
        return score, setup_status, reasons

    reasons.append(f"Bilinmeyen conflict seviyesi: {level}")
    return score, setup_status, reasons


def calculate_setup_score(symbol, trend_direction, structure="RANGE", smc=None):
    scan_mode, mode_params = get_scan_mode_params()

    # Esnek mod: trend nötrse ama SMC yapısı net yön gösteriyorsa
    # SMC yönü devralınır — setup üretimi trend kararsızlığına takılmaz.
    direction_fallback = False

    if mode_params["use_smc_direction_fallback"] and trend_direction == "NEUTRAL":
        smc_direction = get_smc_direction(smc, structure)

        if smc_direction in ("BULLISH", "BEARISH"):
            trend_direction = smc_direction
            direction_fallback = True

    klines = get_klines(symbol, interval=DEFAULT_INTERVAL, limit=DEFAULT_LIMIT)
    normalized = normalize_klines(klines)
    levels = get_recent_high_low(klines)

    recent_high = levels["recent_high"]
    recent_low = levels["recent_low"]
    current_price = levels["last_close"]

    sequence = analyze_entry_sequence(normalized, direction=trend_direction)
    cvd_proxy = calculate_cvd_proxy(normalized)
    price_change_percent_20 = calculate_price_change_percent(normalized)

    setup_prices = build_entry_stop_target(
        trend_direction=trend_direction,
        recent_high=recent_high,
        recent_low=recent_low,
        smc=smc,
    )

    if not setup_prices:
        return build_wait_result(
            setup_type="WAIT_INVALID_SETUP_PRICES",
            reason="Entry/stop/target üretilemedi",
            current_price=current_price,
            sequence=sequence,
            cvd_proxy=cvd_proxy,
            price_change_percent_20=price_change_percent_20,
        )

    entry = setup_prices["entry"]
    stop = setup_prices["stop"]
    target = setup_prices["target"]
    rr = setup_prices["rr"]
    rr_quality = setup_prices["rr_quality"]

    if trend_direction == "BULLISH":
        setup_type = "LONG_LIMIT_ZONE"
    elif trend_direction == "BEARISH":
        setup_type = "SHORT_LIMIT_ZONE"
    else:
        return build_wait_result(
            setup_type="WAIT",
            reason="Trend yönü net değil",
            current_price=current_price,
            sequence=sequence,
            cvd_proxy=cvd_proxy,
            price_change_percent_20=price_change_percent_20,
        )

    entry_distance = distance_percent(current_price, entry)

    entry_state = classify_entry_state(
        trend_direction=trend_direction,
        current_price=current_price,
        entry=entry,
    )

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
            sequence=sequence,
            cvd_proxy=cvd_proxy,
            price_change_percent_20=price_change_percent_20,
        )

    score = 0
    reasons = []

    if direction_fallback:
        reasons.append(
            f"Trend nötr — SMC yönü ({trend_direction}) referans alındı (esnek mod)"
        )

    rr_score = score_rr(rr)
    score += rr_score
    reasons.append(f"Gerçek RR hesaplandı: {round(rr, 2)} ({rr_quality})")

    if setup_prices.get("stop_adjusted"):
        reasons.append("Stop minimum mesafe kuralına göre genişletildi")

    score += BASE_STRUCTURE_SCORE
    reasons.append("Setup yapısı geçerli")

    score += STOP_STRUCTURE_SCORE
    reasons.append(
        f"Stop yapısı uygun | Mesafe: {round(setup_prices['stop_distance_percent'], 2)}%"
    )

    score += TARGET_STRUCTURE_SCORE
    reasons.append(f"Hedef yapısı uygun: {setup_prices['target_source']}")

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

    conflict = get_conflict_severity(
        trend_direction=trend_direction,
        structure=structure,
        smc=smc,
    )

    score, setup_status, reasons = apply_conflict_severity(
        score=score,
        setup_status=setup_status,
        conflict=conflict,
        reasons=reasons,
    )

    trigger = calculate_trigger(
        trend_direction=trend_direction,
        setup_status=setup_status,
        entry_distance=entry_distance,
        conflict=conflict,
        smc=smc,
        sequence=sequence,
        mode_params=mode_params,
    )

    setup_status = apply_trigger_to_status(
        setup_status=setup_status,
        trigger_status=trigger["trigger_status"],
        entry_state=entry_state,
    )

    if entry_state == "MISSED_ENTRY":
        reasons.append("Entry bölgesi kaçmış/delinmiş olduğu için setup WAIT yapıldı")

    if trigger["trigger_status"] == "TRIGGER_READY":
        score = min(score + 10, 100)
        reasons.append("Trigger READY olduğu için setup READY yapıldı")

    return {
        "setup_score": min(score, 100),
        "setup_type": setup_type,
        "setup_status": setup_status,
        "current_price": current_price,
        "entry": round(entry, 6),
        "stop": round(stop, 6),
        "target": round(target, 6),
        "rr": round(rr, 2),
        "rr_quality": rr_quality,
        "stop_distance_percent": round(setup_prices["stop_distance_percent"], 2),
        "stop_adjusted": setup_prices["stop_adjusted"],
        "entry_distance_percent": round(entry_distance, 2),
        "entry_state": entry_state,
        "target_source": setup_prices["target_source"],
        "target_type": setup_prices["target_type"],
        "target_candidates": setup_prices["target_candidates"],
        "conflict_level": conflict["level"],
        "conflict_reason": conflict["reason"],
        "trigger_status": trigger["trigger_status"],
        "trigger_score": trigger["trigger_score"],
        "trigger_reasons": trigger["trigger_reasons"],
        "scan_mode": scan_mode,
        "trade_direction": trend_direction,
        "direction_fallback": direction_fallback,
        "entry_sequence_state": sequence.get("sequence_state"),
        "entry_sequence_score": sequence.get("sequence_score", 0),
        "entry_sequence_reasons": sequence.get("sequence_reasons", []),
        "has_cisd": sequence.get("has_cisd", False),
        "has_mss": sequence.get("has_mss", False),
        "sequence_zone": sequence.get("sequence_zone"),
        "timing_advice": sequence.get("timing_advice"),
        "cvd_proxy": cvd_proxy,
        "price_change_percent_20": price_change_percent_20,
        "setup_reasons": reasons,
    }