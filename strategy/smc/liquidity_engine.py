from strategy.smc.utils import is_close_level


def detect_equal_high_low(
    swing_highs,
    swing_lows,
    lookback=80,
    tolerance_percent=0.15,
):
    equal_highs = []
    equal_lows = []

    recent_highs = swing_highs[-lookback:]
    recent_lows = swing_lows[-lookback:]

    for index in range(1, len(recent_highs)):
        current = recent_highs[index]
        previous = recent_highs[index - 1]

        if is_close_level(current["price"], previous["price"], tolerance_percent):
            equal_highs.append(
                {
                    "price": round((current["price"] + previous["price"]) / 2, 8),
                    "first_index": previous["index"],
                    "second_index": current["index"],
                }
            )

    for index in range(1, len(recent_lows)):
        current = recent_lows[index]
        previous = recent_lows[index - 1]

        if is_close_level(current["price"], previous["price"], tolerance_percent):
            equal_lows.append(
                {
                    "price": round((current["price"] + previous["price"]) / 2, 8),
                    "first_index": previous["index"],
                    "second_index": current["index"],
                }
            )

    return {
        "equal_highs": equal_highs[-5:],
        "equal_lows": equal_lows[-5:],
    }


def detect_liquidity_pool(equal_levels):
    pools = []

    for level in equal_levels.get("equal_highs", []):
        pools.append(
            {
                "type": "BUY_SIDE_LIQUIDITY",
                "price": level["price"],
                "source": "EQUAL_HIGHS",
            }
        )

    for level in equal_levels.get("equal_lows", []):
        pools.append(
            {
                "type": "SELL_SIDE_LIQUIDITY",
                "price": level["price"],
                "source": "EQUAL_LOWS",
            }
        )

    return pools[-10:]


def detect_liquidity_sweep(klines, liquidity_pools, tolerance_percent=0.05):
    if len(klines) < 2:
        return None

    last = klines[-1]

    for pool in liquidity_pools:
        price = pool["price"]
        tolerance = price * (tolerance_percent / 100)

        if pool["type"] == "BUY_SIDE_LIQUIDITY":
            if last["high"] > price + tolerance and last["close"] < price:
                return {
                    "type": "BUY_SIDE_SWEEP",
                    "price": price,
                }

        if pool["type"] == "SELL_SIDE_LIQUIDITY":
            if last["low"] < price - tolerance and last["close"] > price:
                return {
                    "type": "SELL_SIDE_SWEEP",
                    "price": price,
                }

    return None