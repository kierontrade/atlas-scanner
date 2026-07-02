"""
Kullanıcı ayarları (çalışma anında değiştirilebilir, kalıcı).

settings.py EXE'nin içine gömüldüğü için değişiklik yeniden derleme
gerektirir. Bu modül ise data/user_config.json'a yazar: arayüzden
bakiye ve tarama modu değiştirildiğinde anında etki eder ve
uygulama yeniden açıldığında hatırlanır.
"""

import json
from pathlib import Path

from config.settings import ACCOUNT_BALANCE_USDT


CONFIG_PATH = Path("data") / "user_config.json"

VALID_MODES = ("STRICT", "FLEXIBLE")

DEFAULTS = {
    "balance_usdt": ACCOUNT_BALANCE_USDT,
    "scan_mode": "FLEXIBLE",
}


def load_user_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        data = {}

    merged = dict(DEFAULTS)
    merged.update({key: value for key, value in data.items() if key in DEFAULTS})

    return merged


def save_user_config(**updates):
    config = load_user_config()
    config.update({key: value for key, value in updates.items() if key in DEFAULTS})

    CONFIG_PATH.parent.mkdir(exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)

    return config


def get_balance():
    try:
        balance = float(load_user_config()["balance_usdt"])
        return balance if balance > 0 else ACCOUNT_BALANCE_USDT
    except (TypeError, ValueError):
        return ACCOUNT_BALANCE_USDT


def get_scan_mode():
    mode = str(load_user_config()["scan_mode"]).upper()
    return mode if mode in VALID_MODES else "FLEXIBLE"
