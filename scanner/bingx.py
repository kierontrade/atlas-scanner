import json
from pathlib import Path

from api.bingx_client import public_get


def get_swap_contracts():
    return public_get("/openApi/swap/v2/quote/contracts")


def get_24h_tickers():
    return public_get("/openApi/swap/v2/quote/ticker")


def get_funding_rate(symbol):
    return public_get(
        "/openApi/swap/v2/quote/premiumIndex",
        params={"symbol": symbol},
    )


def get_open_interest(symbol):
    return public_get(
        "/openApi/swap/v2/quote/openInterest",
        params={"symbol": symbol},
    )


def get_order_book(symbol, limit=20):
    return public_get(
        "/openApi/swap/v2/quote/depth",
        params={"symbol": symbol, "limit": limit},
    )


def _candle_time(candle):
    value = candle.get("time") or candle.get("openTime") or candle.get("timestamp")

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def sort_klines_ascending(klines):
    """
    BingX v3 kline endpoint'i mumları YENİDEN ESKİYE döndürür.
    Tüm motorlar (trend, SMC, sequence, ATR) mumları eskiden yeniye
    bekler; bu yüzden her kline verisi burada kronolojik sıralanır.
    """
    if not isinstance(klines, list) or len(klines) < 2:
        return klines

    return sorted(klines, key=_candle_time)


def get_klines(symbol, interval="1h", limit=100):
    klines = public_get(
        "/openApi/swap/v3/quote/klines",
        params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        },
    )

    return sort_klines_ascending(klines)


def filter_usdt_contracts(contracts):
    return [
        contract
        for contract in contracts
        if contract.get("symbol", "").endswith("-USDT")
    ]


def save_json(data, filename):
    data_folder = Path("data")
    data_folder.mkdir(exist_ok=True)

    output_file = data_folder / filename

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"✓ Kaydedildi: {output_file}")