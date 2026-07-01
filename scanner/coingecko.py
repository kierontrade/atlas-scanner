import json
from pathlib import Path

from api.coingecko_client import get_top_coins


def save_coingecko_data(data, filename="coingecko_top_coins.json"):
    data_folder = Path("data")
    data_folder.mkdir(exist_ok=True)

    output_file = data_folder / filename

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"✓ CoinGecko verisi kaydedildi: {output_file}")