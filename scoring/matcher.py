BLACKLIST_BASES = {
    # Stablecoins
    "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD",

    # BingX non-crypto / CFD / emtia / endeks ürünleri
    "XAUT",
    "XAG",
    "GOLD",
    "SILVER",
    "OIL",
    "WTI",
    "BRENT",
    "NASDAQ",
    "SPX",
    "DJI",

    # Şüpheli / istemediğimiz pariteler
    "CC", "WLFI", "PI",
}


def symbol_to_base(symbol):
    return symbol.replace("-USDT", "").upper()


def build_coingecko_map(coins):
    coin_map = {}

    for coin in coins:
        symbol = coin.get("symbol", "").upper()

        if symbol and symbol not in coin_map:
            coin_map[symbol] = coin

    return coin_map


def match_contracts_with_coins(contracts, coins, min_market_cap=300_000_000):
    coin_map = build_coingecko_map(coins)
    matched = []

    for contract in contracts:
        symbol = contract.get("symbol", "")
        base = symbol_to_base(symbol)

        if base in BLACKLIST_BASES:
            continue

        if base.startswith("NCCO") or base.startswith("NCS"):
            continue

        coin = coin_map.get(base)

        if not coin:
            continue

        market_cap = coin.get("market_cap") or 0

        if market_cap < min_market_cap:
            continue

        matched.append({
            "symbol": symbol,
            "base": base,
            "name": coin.get("name"),
            "market_cap": market_cap,
            "rank": coin.get("market_cap_rank"),
            "coingecko_id": coin.get("id"),
        })

    return matched