def get_ticker_map(tickers):
    ticker_map = {}

    for ticker in tickers:
        symbol = ticker.get("symbol")
        if symbol:
            ticker_map[symbol] = ticker

    return ticker_map


def score_market_cap(market_cap):
    if market_cap >= 50_000_000_000:
        return 15
    if market_cap >= 10_000_000_000:
        return 13
    if market_cap >= 3_000_000_000:
        return 11
    if market_cap >= 1_000_000_000:
        return 8
    if market_cap >= 300_000_000:
        return 5
    return 0


def score_rank(rank):
    if not rank:
        return 0

    if rank <= 10:
        return 10
    if rank <= 25:
        return 8
    if rank <= 50:
        return 6
    if rank <= 100:
        return 4
    if rank <= 250:
        return 2

    return 0


def score_volume(volume):
    try:
        volume = float(volume)
    except (TypeError, ValueError):
        return 0

    if volume >= 50_000_000:
        return 15
    if volume >= 10_000_000:
        return 12
    if volume >= 3_000_000:
        return 9
    if volume >= 1_000_000:
        return 6
    if volume >= 300_000:
        return 3

    return 0


def score_data_quality(item, ticker):
    required_fields = [
        item.get("symbol"),
        item.get("market_cap"),
        item.get("rank"),
        ticker.get("lastPrice"),
        ticker.get("volume"),
    ]

    filled = sum(1 for field in required_fields if field not in [None, "", 0])

    if filled == 5:
        return 5
    if filled >= 4:
        return 3
    if filled >= 3:
        return 1
    return 0


def classify_score(score):
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 65:
        return "C"
    return "D"


def calculate_quality_scores(matched_contracts, tickers):
    ticker_map = get_ticker_map(tickers)
    scored = []

    for item in matched_contracts:
        symbol = item["symbol"]
        ticker = ticker_map.get(symbol, {})

        market_cap_score = score_market_cap(item.get("market_cap", 0))
        volume_score = score_volume(ticker.get("volume"))
        rank_score = score_rank(item.get("rank"))
        data_quality_score = score_data_quality(item, ticker)

        # V2'de henüz API'den çekmediğimiz alanlar
        open_interest_score = 0
        funding_score = 0
        spread_score = 0
        atr_score = 0
        orderbook_depth_score = 0

        total_score = (
            market_cap_score
            + volume_score
            + open_interest_score
            + funding_score
            + spread_score
            + atr_score
            + rank_score
            + orderbook_depth_score
            + data_quality_score
        )

        scored.append({
            **item,
            "last_price": ticker.get("lastPrice"),
            "volume_24h": ticker.get("volume"),

            "score_market_cap": market_cap_score,
            "score_volume": volume_score,
            "score_open_interest": open_interest_score,
            "score_funding": funding_score,
            "score_spread": spread_score,
            "score_atr": atr_score,
            "score_rank": rank_score,
            "score_orderbook_depth": orderbook_depth_score,
            "score_data_quality": data_quality_score,

            "quality_score": total_score,
            "quality_class": classify_score(total_score),
        })

    scored.sort(key=lambda x: x["quality_score"], reverse=True)

    return scored