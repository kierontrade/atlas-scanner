def find_swings(klines, left, right):
    swing_highs = []
    swing_lows = []

    if len(klines) < left + right + 1:
        return swing_highs, swing_lows

    for index in range(left, len(klines) - right):
        candle = klines[index]

        left_window = klines[index - left:index]
        right_window = klines[index + 1:index + right + 1]

        high = candle["high"]
        low = candle["low"]

        if all(high > item["high"] for item in left_window + right_window):
            swing_highs.append(
                {
                    "index": index,
                    "price": high,
                    "time": candle.get("time"),
                }
            )

        if all(low < item["low"] for item in left_window + right_window):
            swing_lows.append(
                {
                    "index": index,
                    "price": low,
                    "time": candle.get("time"),
                }
            )

    return swing_highs, swing_lows