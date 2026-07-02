"""
Risk Engine

READY sinyalini uygulanabilir bir işlem planına çevirir:

    - Pozisyon büyüklüğü: sabit risk modeli.
      risk_usdt = bakiye * risk% -> stop'a vurursa kaybedilecek tutar sabittir.
      miktar = risk_usdt / |entry - stop|
    - Kaldıraç: notional bakiyeyi aşıyorsa gereken minimum kaldıraç
      önerilir, MAX_LEVERAGE ile sınırlanır.
    - TP kademeleri: setup'ın target_candidates listesinden entry'ye
      göre sıralanmış en fazla 3 gerçek seviye (uydurma yüzde değil,
      SMC hedefleri).

Emir GÖNDERMEZ. Sadece plan üretir; işlemi kullanıcı (demo/gerçek) girer.
"""

from config.settings import (
    MAX_LEVERAGE,
    RISK_PER_TRADE,
)


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_tp_levels(direction, entry, target_candidates, max_levels=3):
    """
    target_candidates: setup engine'in ürettiği seviye listesi.
    Entry'nin ilerisindeki seviyeler yakından uzağa TP1..TP3 olur.
    """
    if not target_candidates:
        return []

    valid = []

    for level in target_candidates:
        price = to_float(level.get("price"))

        if price is None:
            continue

        if direction == "BULLISH" and price > entry:
            valid.append({"price": price, "source": level.get("source")})

        if direction == "BEARISH" and price < entry:
            valid.append({"price": price, "source": level.get("source")})

    valid.sort(key=lambda item: item["price"], reverse=(direction == "BEARISH"))

    seen = set()
    unique = []

    for level in valid:
        key = round(level["price"], 8)

        if key in seen:
            continue

        seen.add(key)
        unique.append(level)

    return unique[:max_levels]


def calculate_position_plan(
    item,
    balance=None,
    risk_percent=RISK_PER_TRADE,
    max_leverage=MAX_LEVERAGE,
):
    """
    item: setup item'ı (entry, stop, target, trend_direction,
    target_candidates içermeli).

    balance None ise data/user_config.json'daki güncel bakiye kullanılır
    (arayüzden anlık değiştirilebilir).

    Dönüş: item'a merge edilecek plan alanları veya geçersizse None.
    """
    if balance is None:
        from config.user_config import get_balance

        balance = get_balance()

    entry = to_float(item.get("entry"))
    stop = to_float(item.get("stop"))
    direction = item.get("trade_direction") or item.get("trend_direction")

    if not entry or not stop or direction not in ("BULLISH", "BEARISH"):
        return None

    stop_distance = abs(entry - stop)

    if stop_distance <= 0:
        return None

    risk_usdt = balance * (risk_percent / 100)
    quantity = risk_usdt / stop_distance
    notional = quantity * entry

    leverage = 1

    if notional > balance:
        leverage = min(max_leverage, -(-notional // balance))  # ceil

    margin_required = notional / leverage

    tp_levels = build_tp_levels(
        direction=direction,
        entry=entry,
        target_candidates=item.get("target_candidates") or [],
    )

    if not tp_levels and to_float(item.get("target")):
        tp_levels = [{"price": to_float(item.get("target")), "source": item.get("target_source")}]

    return {
        "plan_side": "LONG" if direction == "BULLISH" else "SHORT",
        "plan_risk_usdt": round(risk_usdt, 2),
        "plan_risk_percent": risk_percent,
        "plan_quantity": round(quantity, 6),
        "plan_notional_usdt": round(notional, 2),
        "plan_leverage": int(leverage),
        "plan_margin_usdt": round(margin_required, 2),
        "plan_tp_levels": [
            {"price": round(level["price"], 6), "source": level["source"]}
            for level in tp_levels
        ],
    }
