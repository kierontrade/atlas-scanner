def _zone_mid(high, low):
    return round((high + low) / 2, 8)


def _is_price_inside_zone(price, zone):
    if not zone:
        return False

    return zone["low"] <= price <= zone["high"]


def _is_zone_mitigated(klines, zone, start_index):
    for candle in klines[start_index + 1:]:
        if candle["low"] <= zone["high"] and candle["high"] >= zone["low"]:
            return True

    return False


def _is_zone_inverted(klines, zone, start_index):
    for candle in klines[start_index + 1:]:
        if zone["type"] == "BULLISH_FVG":
            if candle["close"] < zone["low"]:
                return True

        if zone["type"] == "BEARISH_FVG":
            if candle["close"] > zone["high"]:
                return True

    return False


def detect_fvg(klines, lookback=100):
    bullish_fvgs = []
    bearish_fvgs = []

    recent = klines[-lookback:]

    if len(recent) < 3:
        return {
            "bullish_fvgs": [],
            "bearish_fvgs": [],
            "active_fvg": None,
        }

    offset = len(klines) - len(recent)

    for index in range(2, len(recent)):
        first = recent[index - 2]
        third = recent[index]

        source_index = offset + index

        if first["high"] < third["low"]:
            high = third["low"]
            low = first["high"]

            zone = {
                "type": "BULLISH_FVG",
                "high": round(high, 8),
                "low": round(low, 8),
                "mid": _zone_mid(high, low),
                "source_index": source_index,
            }

            zone["mitigated"] = _is_zone_mitigated(klines, zone, source_index)
            zone["inverted"] = _is_zone_inverted(klines, zone, source_index)

            bullish_fvgs.append(zone)

        if first["low"] > third["high"]:
            high = first["low"]
            low = third["high"]

            zone = {
                "type": "BEARISH_FVG",
                "high": round(high, 8),
                "low": round(low, 8),
                "mid": _zone_mid(high, low),
                "source_index": source_index,
            }

            zone["mitigated"] = _is_zone_mitigated(klines, zone, source_index)
            zone["inverted"] = _is_zone_inverted(klines, zone, source_index)

            bearish_fvgs.append(zone)

    active_fvg = None

    all_fvgs = bullish_fvgs + bearish_fvgs
    unmitigated = [zone for zone in all_fvgs if not zone.get("mitigated")]

    if unmitigated:
        active_fvg = sorted(
            unmitigated,
            key=lambda item: item["source_index"],
            reverse=True,
        )[0]
    elif all_fvgs:
        active_fvg = sorted(
            all_fvgs,
            key=lambda item: item["source_index"],
            reverse=True,
        )[0]

    return {
        "bullish_fvgs": bullish_fvgs[-5:],
        "bearish_fvgs": bearish_fvgs[-5:],
        "active_fvg": active_fvg,
    }


def detect_ifvg(fvg):
    inverse_fvgs = []

    for zone in fvg.get("bullish_fvgs", []):
        if zone.get("inverted"):
            inverse_fvgs.append(
                {
                    "type": "BEARISH_IFVG",
                    "high": zone["high"],
                    "low": zone["low"],
                    "mid": zone["mid"],
                    "source_index": zone["source_index"],
                    "origin": "BULLISH_FVG",
                }
            )

    for zone in fvg.get("bearish_fvgs", []):
        if zone.get("inverted"):
            inverse_fvgs.append(
                {
                    "type": "BULLISH_IFVG",
                    "high": zone["high"],
                    "low": zone["low"],
                    "mid": zone["mid"],
                    "source_index": zone["source_index"],
                    "origin": "BEARISH_FVG",
                }
            )

    active_ifvg = None

    if inverse_fvgs:
        active_ifvg = sorted(
            inverse_fvgs,
            key=lambda item: item["source_index"],
            reverse=True,
        )[0]

    return {
        "inverse_fvgs": inverse_fvgs[-5:],
        "active_ifvg": active_ifvg,
    }


def detect_bpr(fvg):
    bprs = []

    bullish_fvgs = fvg.get("bullish_fvgs", [])
    bearish_fvgs = fvg.get("bearish_fvgs", [])

    for bullish in bullish_fvgs:
        for bearish in bearish_fvgs:
            overlap_high = min(bullish["high"], bearish["high"])
            overlap_low = max(bullish["low"], bearish["low"])

            if overlap_low < overlap_high:
                bprs.append(
                    {
                        "type": "BPR",
                        "high": round(overlap_high, 8),
                        "low": round(overlap_low, 8),
                        "mid": _zone_mid(overlap_high, overlap_low),
                        "bullish_fvg_index": bullish["source_index"],
                        "bearish_fvg_index": bearish["source_index"],
                        "source_index": max(
                            bullish["source_index"],
                            bearish["source_index"],
                        ),
                    }
                )

    active_bpr = None

    if bprs:
        active_bpr = sorted(
            bprs,
            key=lambda item: item["source_index"],
            reverse=True,
        )[0]

    return {
        "bprs": bprs[-5:],
        "active_bpr": active_bpr,
    }


def detect_displacement(klines, lookback=20):
    if len(klines) < lookback + 1:
        return {
            "has_displacement": False,
            "direction": "NEUTRAL",
            "body_ratio": 0,
            "range_expansion": 0,
        }

    recent = klines[-lookback:]
    last = klines[-1]

    ranges = [
        abs(candle["high"] - candle["low"])
        for candle in recent[:-1]
        if candle["high"] > candle["low"]
    ]

    if not ranges:
        return {
            "has_displacement": False,
            "direction": "NEUTRAL",
            "body_ratio": 0,
            "range_expansion": 0,
        }

    avg_range = sum(ranges) / len(ranges)
    last_range = last["high"] - last["low"]
    body = abs(last["close"] - last["open"])

    if last_range <= 0:
        return {
            "has_displacement": False,
            "direction": "NEUTRAL",
            "body_ratio": 0,
            "range_expansion": 0,
        }

    body_ratio = body / last_range
    range_expansion = last_range / avg_range if avg_range > 0 else 0

    has_displacement = range_expansion >= 1.5 and body_ratio >= 0.55

    if not has_displacement:
        direction = "NEUTRAL"
    elif last["close"] > last["open"]:
        direction = "BULLISH"
    else:
        direction = "BEARISH"

    return {
        "has_displacement": has_displacement,
        "direction": direction,
        "body_ratio": round(body_ratio, 4),
        "range_expansion": round(range_expansion, 4),
    }