from scanner.bingx import get_funding_rate, get_order_book


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


symbol = "BTC-USDT"

print("Funding testi:", symbol)
funding = get_funding_rate(symbol)
print(funding)

print("\nOrder book testi:", symbol)
order_book = get_order_book(symbol)
spread = calculate_spread(order_book)
print(spread)