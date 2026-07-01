def find_order_block(klines, direction, lookback=30):
    if len(klines) < lookback:
        return None

    recent = klines[-lookback:]

    if direction.startswith("BULLISH"):
        for index in range(len(recent) - 2, 0, -1):
            candle = recent[index]

            if candle["close"] < candle["open"]:
                return {
                    "type": "BULLISH_ORDER_BLOCK",
                    "high": round(candle["high"], 8),
                    "low": round(candle["low"], 8),
                    "mid": round((candle["high"] + candle["low"]) / 2, 8),
                    "source_index": len(klines) - lookback + index,
                }

    if direction.startswith("BEARISH"):
        for index in range(len(recent) - 2, 0, -1):
            candle = recent[index]

            if candle["close"] > candle["open"]:
                return {
                    "type": "BEARISH_ORDER_BLOCK",
                    "high": round(candle["high"], 8),
                    "low": round(candle["low"], 8),
                    "mid": round((candle["high"] + candle["low"]) / 2, 8),
                    "source_index": len(klines) - lookback + index,
                }

    return None


def detect_mitigation(klines, order_block):
    if not order_block:
        return {
            "mitigated": False,
            "mitigation_type": None,
        }

    last_close = klines[-1]["close"]
    last_low = klines[-1]["low"]
    last_high = klines[-1]["high"]

    touched = last_low <= order_block["high"] and last_high >= order_block["low"]

    if not touched:
        return {
            "mitigated": False,
            "mitigation_type": "UNMITIGATED",
        }

    if order_block["low"] <= last_close <= order_block["high"]:
        return {
            "mitigated": True,
            "mitigation_type": "INSIDE_ORDER_BLOCK",
        }

    return {
        "mitigated": True,
        "mitigation_type": "WICK_MITIGATION",
    }


def detect_breaker_block(structure, order_block, mitigation):
    if not order_block or not mitigation.get("mitigated"):
        return None

    if structure == "BULLISH_CHOCH" and order_block["type"] == "BEARISH_ORDER_BLOCK":
        return {
            "type": "BULLISH_BREAKER_BLOCK",
            "high": order_block["high"],
            "low": order_block["low"],
            "mid": order_block["mid"],
        }

    if structure == "BEARISH_CHOCH" and order_block["type"] == "BULLISH_ORDER_BLOCK":
        return {
            "type": "BEARISH_BREAKER_BLOCK",
            "high": order_block["high"],
            "low": order_block["low"],
            "mid": order_block["mid"],
        }

    return None