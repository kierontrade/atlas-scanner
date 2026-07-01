import requests

BASE_URL = "https://api.coingecko.com/api/v3"


def get_top_coins(limit=250):
    endpoint = "/coins/markets"
    url = BASE_URL + endpoint

    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    return response.json()