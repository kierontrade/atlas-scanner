"""
ATLAS GLOBAL SETTINGS
Bu dosya sistemin bütün ayarlarını içerir.
"""

# ----------------------------
# Coin Universe
# ----------------------------

MIN_MARKET_CAP = 300_000_000

COINGECKO_TOP_COINS = 250

# ----------------------------
# Quality Score
# ----------------------------

QUALITY_A = 85
QUALITY_B = 75
QUALITY_C = 65

# ----------------------------
# Scanner
# ----------------------------

SCAN_INTERVAL_MINUTES = 15

# ----------------------------
# Trading
# ----------------------------

MAX_OPEN_TRADES = 3

RISK_PER_TRADE = 1

MIN_RR = 2

# Demo/gerçek hesap bakiyesi (USDT) — pozisyon boyutu bundan hesaplanır
ACCOUNT_BALANCE_USDT = 1000

# Önerilecek maksimum kaldıraç
MAX_LEVERAGE = 10

# ----------------------------
# Timeframes
# ----------------------------

HIGHER_TIMEFRAME = "1d"

MIDDLE_TIMEFRAME = "4h"

ENTRY_TIMEFRAME = "1h"