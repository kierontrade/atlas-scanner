from scanner.bingx import (
    get_funding_rate,
    get_order_book,
    get_open_interest,
    get_klines,
)


def calculate_spread(order_book):
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])

    if not bids or not asks:
        return None

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])

    spread = best_ask - best_bid
    spread_percent = (spread / best_bid) * 100

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "spread_percent": spread_percent,
    }


def calculate_order_book_depth(order_book):
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])

    bid_depth = sum(float(price) * float(qty) for price, qty in bids[:20])
    ask_depth = sum(float(price) * float(qty) for price, qty in asks[:20])

    total_depth = bid_depth + ask_depth

    return {
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "orderbook_depth": total_depth,
    }


def calculate_atr(klines, period=14):
    if not klines or len(klines) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(klines)):
        high = float(klines[i]["high"])
        low = float(klines[i]["low"])
        prev_close = float(klines[i - 1]["close"])

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

        true_ranges.append(tr)

    atr = sum(true_ranges[-period:]) / period
    last_close = float(klines[-1]["close"])
    atr_percent = (atr / last_close) * 100

    return {
        "atr": atr,
        "atr_percent": atr_percent,
    }


def score_funding_rate(funding_rate):
    try:
        funding_rate = abs(float(funding_rate))
    except (TypeError, ValueError):
        return 0

    if funding_rate <= 0.0001:
        return 10
    if funding_rate <= 0.0003:
        return 8
    if funding_rate <= 0.0007:
        return 5
    if funding_rate <= 0.001:
        return 2

    return 0


def score_spread(spread_percent):
    try:
        spread_percent = float(spread_percent)
    except (TypeError, ValueError):
        return 0

    if spread_percent <= 0.01:
        return 10
    if spread_percent <= 0.03:
        return 8
    if spread_percent <= 0.05:
        return 5
    if spread_percent <= 0.10:
        return 2

    return 0


def score_open_interest(open_interest_value):
    try:
        oi = float(open_interest_value)
    except (TypeError, ValueError):
        return 0

    if oi >= 1_000_000_000:
        return 15
    if oi >= 300_000_000:
        return 12
    if oi >= 100_000_000:
        return 9
    if oi >= 30_000_000:
        return 6
    if oi >= 10_000_000:
        return 3

    return 0


def score_atr(atr_percent):
    try:
        atr_percent = float(atr_percent)
    except (TypeError, ValueError):
        return 0

    if 1.0 <= atr_percent <= 5.0:
        return 10
    if 0.5 <= atr_percent < 1.0:
        return 7
    if 5.0 < atr_percent <= 8.0:
        return 6
    if 0.2 <= atr_percent < 0.5:
        return 3

    return 0


def score_orderbook_depth(depth):
    try:
        depth = float(depth)
    except (TypeError, ValueError):
        return 0

    if depth >= 50_000_000:
        return 10
    if depth >= 20_000_000:
        return 8
    if depth >= 5_000_000:
        return 6
    if depth >= 1_000_000:
        return 3

    return 0


def score_data_quality(item):
    fields = [
        item.get("market_cap"),
        item.get("volume_24h"),
        item.get("funding_rate"),
        item.get("spread_percent"),
        item.get("open_interest"),
        item.get("atr_percent"),
        item.get("orderbook_depth"),
    ]

    filled = sum(1 for field in fields if field not in [None, "", 0])

    if filled >= 7:
        return 5
    if filled >= 6:
        return 4
    if filled >= 5:
        return 3
    if filled >= 4:
        return 2

    return 0


def get_market_metrics(symbol):
    funding_data = get_funding_rate(symbol)
    order_book = get_order_book(symbol)
    open_interest_data = get_open_interest(symbol)
    klines = get_klines(symbol, interval="1h", limit=100)

    spread_data = calculate_spread(order_book)
    depth_data = calculate_order_book_depth(order_book)
    atr_data = calculate_atr(klines)

    funding_rate = funding_data.get("lastFundingRate") if funding_data else None
    spread_percent = spread_data.get("spread_percent") if spread_data else None

    open_interest = None
    if open_interest_data:
        open_interest = (
            open_interest_data.get("openInterest")
            or open_interest_data.get("openInterestValue")
            or open_interest_data.get("amount")
        )

    atr = atr_data.get("atr") if atr_data else None
    atr_percent = atr_data.get("atr_percent") if atr_data else None
    orderbook_depth = depth_data.get("orderbook_depth") if depth_data else None

    result = {
        "symbol": symbol,
        "funding_rate": funding_rate,
        "spread_percent": spread_percent,
        "open_interest": open_interest,
        "atr": atr,
        "atr_percent": atr_percent,
        "orderbook_depth": orderbook_depth,
        "score_funding": score_funding_rate(funding_rate),
        "score_spread": score_spread(spread_percent),
        "score_open_interest": score_open_interest(open_interest),
        "score_atr": score_atr(atr_percent),
        "score_orderbook_depth": score_orderbook_depth(orderbook_depth),
    }

    result["score_data_quality"] = score_data_quality(result)

    return result