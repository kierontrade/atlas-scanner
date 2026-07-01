from strategy.smc.utils import get_structure_direction


def detect_structure_from_swings(klines, swing_highs, swing_lows, label):
    if len(klines) < 10 or not swing_highs or not swing_lows:
        return {
            "label": label,
            "structure": "RANGE",
            "direction": "NEUTRAL",
            "bos": None,
            "choch": None,
            "last_broken_level": None,
            "reasons": [f"{label}: Yeterli swing yapısı yok"],
        }

    last_close = klines[-1]["close"]
    previous_close = klines[-2]["close"]

    last_swing_high = swing_highs[-1]
    last_swing_low = swing_lows[-1]

    previous_swing_high = swing_highs[-2] if len(swing_highs) >= 2 else None
    previous_swing_low = swing_lows[-2] if len(swing_lows) >= 2 else None

    reasons = []
    bos = None
    choch = None
    structure = "RANGE"
    last_broken_level = None

    broke_high = previous_close <= last_swing_high["price"] and last_close > last_swing_high["price"]
    broke_low = previous_close >= last_swing_low["price"] and last_close < last_swing_low["price"]

    if previous_swing_high and previous_swing_low:
        higher_high = last_swing_high["price"] > previous_swing_high["price"]
        higher_low = last_swing_low["price"] > previous_swing_low["price"]
        lower_high = last_swing_high["price"] < previous_swing_high["price"]
        lower_low = last_swing_low["price"] < previous_swing_low["price"]

        if higher_high and higher_low:
            structure = "BULLISH_STRUCTURE"
            reasons.append(f"{label}: HH/HL yapısı oluştu")

        elif lower_high and lower_low:
            structure = "BEARISH_STRUCTURE"
            reasons.append(f"{label}: LH/LL yapısı oluştu")

    if broke_high:
        bos = "BULLISH_BOS"
        last_broken_level = last_swing_high["price"]

        if structure == "BEARISH_STRUCTURE":
            choch = "BULLISH_CHOCH"
            structure = "BULLISH_CHOCH"
            reasons.append(f"{label}: Bearish yapı yukarı kırıldı")
        else:
            structure = "BULLISH_BOS"
            reasons.append(f"{label}: Son swing high yukarı kırıldı")

    elif broke_low:
        bos = "BEARISH_BOS"
        last_broken_level = last_swing_low["price"]

        if structure == "BULLISH_STRUCTURE":
            choch = "BEARISH_CHOCH"
            structure = "BEARISH_CHOCH"
            reasons.append(f"{label}: Bullish yapı aşağı kırıldı")
        else:
            structure = "BEARISH_BOS"
            reasons.append(f"{label}: Son swing low aşağı kırıldı")

    if not reasons:
        reasons.append(f"{label}: Net BOS/CHOCH yok")

    return {
        "label": label,
        "structure": structure,
        "direction": get_structure_direction(structure),
        "bos": bos,
        "choch": choch,
        "last_broken_level": round(last_broken_level, 8) if last_broken_level else None,
        "reasons": reasons,
    }


def merge_structure(external_result, internal_result):
    external_direction = external_result["direction"]
    internal_direction = internal_result["direction"]

    reasons = []
    reasons.extend(external_result["reasons"])
    reasons.extend(internal_result["reasons"])

    if external_direction != "NEUTRAL":
        primary = external_result
        structure_source = "EXTERNAL"
    else:
        primary = internal_result
        structure_source = "INTERNAL"

    if external_direction != "NEUTRAL" and internal_direction != "NEUTRAL":
        if external_direction == internal_direction:
            reasons.append("External ve internal structure aynı yönde")
        else:
            reasons.append("External ve internal structure çelişiyor")

    if external_direction == "NEUTRAL" and internal_direction != "NEUTRAL":
        reasons.append("External range, internal structure referans alındı")

    if external_direction != "NEUTRAL" and internal_direction == "NEUTRAL":
        reasons.append("Internal range, external structure referans alındı")

    return {
        "structure": primary["structure"],
        "smc_direction": primary["direction"],
        "bos": primary["bos"],
        "choch": primary["choch"],
        "last_broken_level": primary["last_broken_level"],
        "structure_source": structure_source,
        "external_structure": external_result["structure"],
        "external_direction": external_result["direction"],
        "external_bos": external_result["bos"],
        "external_choch": external_result["choch"],
        "external_last_broken_level": external_result["last_broken_level"],
        "internal_structure": internal_result["structure"],
        "internal_direction": internal_result["direction"],
        "internal_bos": internal_result["bos"],
        "internal_choch": internal_result["choch"],
        "internal_last_broken_level": internal_result["last_broken_level"],
        "structure_reasons": reasons,
    }