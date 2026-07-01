from scanner.bingx import get_klines

from strategy.smc.structure_engine import detect_structure_from_swings, merge_structure
from strategy.smc.swing_detector import find_swings
from strategy.smc.utils import normalize_klines


MTF_TIMEFRAMES = [
    {
        "name": "1D",
        "interval": "1d",
        "limit": 150,
        "external_left": 3,
        "external_right": 3,
        "internal_left": 1,
        "internal_right": 1,
    },
    {
        "name": "4H",
        "interval": "4h",
        "limit": 150,
        "external_left": 3,
        "external_right": 3,
        "internal_left": 1,
        "internal_right": 1,
    },
    {
        "name": "1H",
        "interval": "1h",
        "limit": 150,
        "external_left": 3,
        "external_right": 3,
        "internal_left": 1,
        "internal_right": 1,
    },
    {
        "name": "15M",
        "interval": "15m",
        "limit": 150,
        "external_left": 3,
        "external_right": 3,
        "internal_left": 1,
        "internal_right": 1,
    },
]


def empty_timeframe_result(name, interval, reason):
    return {
        "timeframe": name,
        "interval": interval,
        "structure": "RANGE",
        "direction": "NEUTRAL",
        "structure_source": None,
        "external_structure": "RANGE",
        "external_direction": "NEUTRAL",
        "internal_structure": "RANGE",
        "internal_direction": "NEUTRAL",
        "bos": None,
        "choch": None,
        "last_broken_level": None,
        "last_close": None,
        "reason": reason,
    }


def analyze_timeframe(symbol, config):
    name = config["name"]
    interval = config["interval"]

    try:
        raw_klines = get_klines(
            symbol,
            interval=interval,
            limit=config["limit"],
        )
    except Exception as exc:
        return empty_timeframe_result(
            name=name,
            interval=interval,
            reason=f"Kline alınamadı: {exc}",
        )

    klines = normalize_klines(raw_klines)

    if len(klines) < 20:
        return empty_timeframe_result(
            name=name,
            interval=interval,
            reason="Yetersiz mum verisi",
        )

    external_highs, external_lows = find_swings(
        klines,
        left=config["external_left"],
        right=config["external_right"],
    )

    internal_highs, internal_lows = find_swings(
        klines,
        left=config["internal_left"],
        right=config["internal_right"],
    )

    if not internal_highs or not internal_lows:
        return empty_timeframe_result(
            name=name,
            interval=interval,
            reason="Internal swing bulunamadı",
        )

    external_result = detect_structure_from_swings(
        klines=klines,
        swing_highs=external_highs,
        swing_lows=external_lows,
        label=f"{name}_EXTERNAL",
    )

    internal_result = detect_structure_from_swings(
        klines=klines,
        swing_highs=internal_highs,
        swing_lows=internal_lows,
        label=f"{name}_INTERNAL",
    )

    merged = merge_structure(
        external_result=external_result,
        internal_result=internal_result,
    )

    return {
        "timeframe": name,
        "interval": interval,
        "structure": merged["structure"],
        "direction": merged["smc_direction"],
        "structure_source": merged["structure_source"],
        "external_structure": merged["external_structure"],
        "external_direction": merged["external_direction"],
        "internal_structure": merged["internal_structure"],
        "internal_direction": merged["internal_direction"],
        "bos": merged["bos"],
        "choch": merged["choch"],
        "last_broken_level": merged["last_broken_level"],
        "last_close": klines[-1]["close"],
        "reason": None,
    }


def count_directions(timeframes):
    counts = {
        "BULLISH": 0,
        "BEARISH": 0,
        "NEUTRAL": 0,
    }

    for item in timeframes:
        direction = item.get("direction", "NEUTRAL")

        if direction not in counts:
            direction = "NEUTRAL"

        counts[direction] += 1

    return counts


def calculate_mtf_bias(timeframes):
    counts = count_directions(timeframes)

    bullish = counts["BULLISH"]
    bearish = counts["BEARISH"]

    if bullish >= 3 and bullish > bearish:
        return "BULLISH"

    if bearish >= 3 and bearish > bullish:
        return "BEARISH"

    if bullish > bearish:
        return "BULLISH_WEAK"

    if bearish > bullish:
        return "BEARISH_WEAK"

    return "NEUTRAL"


def calculate_mtf_alignment(current_direction, mtf_bias):
    if current_direction == "NEUTRAL":
        return {
            "aligned": False,
            "alignment": "CURRENT_NEUTRAL",
        }

    if mtf_bias == current_direction:
        return {
            "aligned": True,
            "alignment": "FULL_ALIGNMENT",
        }

    if mtf_bias == f"{current_direction}_WEAK":
        return {
            "aligned": True,
            "alignment": "WEAK_ALIGNMENT",
        }

    if mtf_bias == "NEUTRAL":
        return {
            "aligned": False,
            "alignment": "MTF_NEUTRAL",
        }

    return {
        "aligned": False,
        "alignment": "MTF_CONFLICT",
    }


def detect_mtf_context(symbol, current_direction="NEUTRAL"):
    if not symbol:
        return {
            "mtf_enabled": False,
            "mtf_bias": "UNKNOWN",
            "mtf_alignment": {
                "aligned": False,
                "alignment": "NO_SYMBOL",
            },
            "mtf_direction_counts": {
                "BULLISH": 0,
                "BEARISH": 0,
                "NEUTRAL": 0,
            },
            "timeframes": [],
        }

    timeframes = []

    for config in MTF_TIMEFRAMES:
        timeframes.append(
            analyze_timeframe(
                symbol=symbol,
                config=config,
            )
        )

    mtf_bias = calculate_mtf_bias(timeframes)
    mtf_alignment = calculate_mtf_alignment(
        current_direction=current_direction,
        mtf_bias=mtf_bias,
    )

    return {
        "mtf_enabled": True,
        "mtf_bias": mtf_bias,
        "mtf_alignment": mtf_alignment,
        "mtf_direction_counts": count_directions(timeframes),
        "timeframes": timeframes,
    }