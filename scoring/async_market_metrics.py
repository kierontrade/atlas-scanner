import asyncio

from api.bingx_client import create_async_client, async_public_get
from scanner.bingx import sort_klines_ascending
from scoring.market_metrics import (
    calculate_spread,
    calculate_order_book_depth,
    calculate_atr,
    score_funding_rate,
    score_spread,
    score_open_interest,
    score_atr,
    score_orderbook_depth,
    score_data_quality,
)


async def fetch_symbol_metrics(client, symbol):
    try:
        funding_task = async_public_get(
            client,
            "/openApi/swap/v2/quote/premiumIndex",
            params={"symbol": symbol},
        )

        order_book_task = async_public_get(
            client,
            "/openApi/swap/v2/quote/depth",
            params={"symbol": symbol, "limit": 20},
        )

        open_interest_task = async_public_get(
            client,
            "/openApi/swap/v2/quote/openInterest",
            params={"symbol": symbol},
        )

        klines_task = async_public_get(
            client,
            "/openApi/swap/v3/quote/klines",
            params={
                "symbol": symbol,
                "interval": "1h",
                "limit": 100,
            },
        )

        funding_data, order_book, open_interest_data, klines = await asyncio.gather(
            funding_task,
            order_book_task,
            open_interest_task,
            klines_task,
        )

        spread_data = calculate_spread(order_book)
        depth_data = calculate_order_book_depth(order_book)
        atr_data = calculate_atr(sort_klines_ascending(klines))

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

        return symbol, result

    except Exception as e:
        return symbol, {
            "symbol": symbol,
            "metric_error": str(e),
        }


async def get_market_metrics_bulk(symbols, batch_size=10):
    results = {}

    async with create_async_client() as client:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_results = await asyncio.gather(
                *(fetch_symbol_metrics(client, symbol) for symbol in batch)
            )

            for symbol, data in batch_results:
                results[symbol] = data

    return results