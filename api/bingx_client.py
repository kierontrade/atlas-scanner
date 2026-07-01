import requests
import httpx

BASE_URL = "https://open-api.bingx.com"


def public_get(endpoint, params=None, timeout=10):
    url = BASE_URL + endpoint
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()

    data = response.json()

    if data.get("code") != 0:
        raise Exception(f"BingX API hatası: {data}")

    return data.get("data")


async def async_public_get(client, endpoint, params=None):
    url = BASE_URL + endpoint
    response = await client.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if data.get("code") != 0:
        raise Exception(f"BingX API hatası: {data}")

    return data.get("data")


def create_async_client():
    return httpx.AsyncClient(timeout=15)