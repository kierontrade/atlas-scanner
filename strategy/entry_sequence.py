"""
Entry Sequence Engine (Sniper Entry State Machine)

Kurumsal giriş tek bir koşul değil, sıralı bir olay dizisidir:

    IDLE -> SWEPT -> DISPLACED -> CONFIRMED -> ENTRY_ZONE_ACTIVE

    SWEPT             : Likidite (eski swing / equal low-high) süpürüldü
    DISPLACED         : Sweep sonrası ters yönde displacement mumu geldi
    CONFIRMED         : CISD veya MSS ile teslimat/yapı değişimi onaylandı
    ENTRY_ZONE_ACTIVE : Sweep hareketinin ürettiği zone (FVG/OB) içinde
                        veya çok yakınında fiyat var

Sadece kapanmış mumlar kullanılır. Repaint yoktur.
Her aşama trigger confirmation skoruna katkı verir ve
timing_advice alanı "şu an girme / bekle" tavsiyesini üretir.
"""

from strategy.smc.cisd_engine import detect_cisd
from strategy.smc.swing_detector import find_swings


SEQUENCE_LOOKBACK = 40
SWEEP_TOLERANCE_PERCENT = 0.05
DISPLACEMENT_RANGE_EXPANSION = 1.5
DISPLACEMENT_BODY_RATIO = 0.55
DISPLACEMENT_AVG_WINDOW = 20
ZONE_NEAR_PERCENT = 0.35

SWEPT_SCORE = 12
DISPLACED_SCORE = 12
CONFIRMED_SCORE = 14
ZONE_ACTIVE_SCORE = 10

TIMING_ADVICE = {
    "IDLE": "Likidite henüz alınmadı — sweep bekleniyor, erken girme",
    "SWEPT": "Sweep geldi — displacement onayı bekleniyor",
    "DISPLACED": "Displacement var — CISD/MSS onayı bekleniyor",
    "CONFIRMED": "Onay tamam — fiyatın entry zone'a dönüşü bekleniyor",
    "ENTRY_ZONE_ACTIVE": "Sniper entry koşulları aktif",
    "NOT_EVALUATED": "Sequence değerlendirilemedi",
}


def empty_sequence(reason="Yetersiz veri"):
    return {
        "sequence_state": "NOT_EVALUATED",
        "sequence_score": 0,
        "sweep_event": None,
        "displacement_index": None,
        "has_cisd": False,
        "has_mss": False,
        "sequence_zone": None,
        "sequence_reasons": [reason],
        "timing_advice": TIMING_ADVICE["NOT_EVALUATED"],
    }


def find_sweep_event(klines, direction, swing_highs, swing_lows, lookback=SEQUENCE_LOOKBACK):
    """
    Son `lookback` mum içinde yönle uyumlu likidite süpürmesini arar.

    BULLISH setup -> sell-side sweep: mum low'u eski bir swing low'un
    altına sarkar ama kapanış seviyenin üzerinde kalır.
    BEARISH setup -> buy-side sweep (simetrik).

    Birden fazla aday varsa EKSTREM noktayı alan mum seçilir
    (bullish: en düşük low, bearish: en yüksek high) — gerçek sweep,
    likiditenin uç noktasının alındığı yerdir; sonradan minör seviyeleri
    delen displacement mumu sweep sayılmaz.
    """
    start = max(1, len(klines) - lookback)
    candidates = []

    references = swing_lows if direction == "BULLISH" else swing_highs

    for index in range(start, len(klines)):
        candle = klines[index]

        for swing in references:
            if swing["index"] >= index:
                continue

            level = swing["price"]
            tolerance = level * (SWEEP_TOLERANCE_PERCENT / 100)

            if direction == "BULLISH":
                swept = candle["low"] < level - tolerance and candle["close"] > level
            else:
                swept = candle["high"] > level + tolerance and candle["close"] < level

            if swept:
                candidates.append(
                    {
                        "index": index,
                        "level": round(level, 8),
                        "swing_index": swing["index"],
                        "extreme": candle["low"] if direction == "BULLISH" else candle["high"],
                        "type": "SELL_SIDE_SWEEP" if direction == "BULLISH" else "BUY_SIDE_SWEEP",
                    }
                )

    if not candidates:
        return None

    if direction == "BULLISH":
        return min(candidates, key=lambda item: (item["extreme"], -item["index"]))

    return max(candidates, key=lambda item: (item["extreme"], item["index"]))


def find_displacement_after(klines, direction, start_index):
    """
    start_index sonrasında yönle uyumlu displacement mumu arar.
    Displacement: ortalama range'in en az 1.5 katı range + %55 gövde.
    """
    for index in range(start_index + 1, len(klines)):
        window_start = max(0, index - DISPLACEMENT_AVG_WINDOW)
        window = klines[window_start:index]

        ranges = [
            candle["high"] - candle["low"]
            for candle in window
            if candle["high"] > candle["low"]
        ]

        if not ranges:
            continue

        avg_range = sum(ranges) / len(ranges)
        candle = klines[index]
        candle_range = candle["high"] - candle["low"]

        if candle_range <= 0 or avg_range <= 0:
            continue

        body_ratio = abs(candle["close"] - candle["open"]) / candle_range
        expansion = candle_range / avg_range

        if expansion < DISPLACEMENT_RANGE_EXPANSION or body_ratio < DISPLACEMENT_BODY_RATIO:
            continue

        if direction == "BULLISH" and candle["close"] > candle["open"]:
            return index

        if direction == "BEARISH" and candle["close"] < candle["open"]:
            return index

    return None


def detect_mss_after(klines, direction, sweep_index, swing_highs, swing_lows):
    """
    MSS (Market Structure Shift):
    Sweep sonrasında, sweep ÖNCESİNDE oluşmuş en yakın internal swing'in
    ters yönde kırılması.

    BULLISH: sweep öncesi son swing high, sweep sonrası bir kapanışla aşılır.
    """
    references = swing_highs if direction == "BULLISH" else swing_lows

    prior = [swing for swing in references if swing["index"] < sweep_index]

    if not prior:
        return False

    level = prior[-1]["price"]

    for index in range(sweep_index + 1, len(klines)):
        close = klines[index]["close"]

        if direction == "BULLISH" and close > level:
            return True

        if direction == "BEARISH" and close < level:
            return True

    return False


def find_sequence_zone(klines, direction, sweep_index):
    """
    Sweep hareketinin ürettiği giriş bölgesi:

    1) Sweep sonrası oluşan yönlü FVG (öncelik)
    2) Yoksa displacement öncesi son ters renkli mum (order block)

    Zone, sweep'e sebep-sonuç ilişkisiyle bağlıdır; "en yakın rastgele OB" değildir.
    """
    for index in range(len(klines) - 1, sweep_index + 1, -1):
        first = klines[index - 2]
        third = klines[index]

        if direction == "BULLISH" and first["high"] < third["low"]:
            return {
                "type": "SEQUENCE_FVG",
                "low": round(first["high"], 8),
                "high": round(third["low"], 8),
                "mid": round((first["high"] + third["low"]) / 2, 8),
                "source_index": index,
            }

        if direction == "BEARISH" and first["low"] > third["high"]:
            return {
                "type": "SEQUENCE_FVG",
                "low": round(third["high"], 8),
                "high": round(first["low"], 8),
                "mid": round((third["high"] + first["low"]) / 2, 8),
                "source_index": index,
            }

    for index in range(len(klines) - 2, sweep_index - 1, -1):
        candle = klines[index]

        if direction == "BULLISH" and candle["close"] < candle["open"]:
            return {
                "type": "SEQUENCE_ORDER_BLOCK",
                "low": round(candle["low"], 8),
                "high": round(candle["high"], 8),
                "mid": round((candle["low"] + candle["high"]) / 2, 8),
                "source_index": index,
            }

        if direction == "BEARISH" and candle["close"] > candle["open"]:
            return {
                "type": "SEQUENCE_ORDER_BLOCK",
                "low": round(candle["low"], 8),
                "high": round(candle["high"], 8),
                "mid": round((candle["low"] + candle["high"]) / 2, 8),
                "source_index": index,
            }

    return None


def is_price_in_or_near_zone(price, zone):
    if not zone or not price:
        return False

    buffer_value = zone["mid"] * (ZONE_NEAR_PERCENT / 100)

    return (zone["low"] - buffer_value) <= price <= (zone["high"] + buffer_value)


def analyze_entry_sequence(klines, direction, lookback=SEQUENCE_LOOKBACK):
    """
    Ana giriş noktası.

    klines   : normalize edilmiş mumlar (dict listesi)
    direction: setup yönü ("BULLISH" / "BEARISH")

    Dönüş: sequence_state, sequence_score, timing_advice ve tüm ara bulgular.
    """
    if direction not in ("BULLISH", "BEARISH"):
        return empty_sequence(reason="Yön NEUTRAL, sequence aranmadı")

    if len(klines) < DISPLACEMENT_AVG_WINDOW + 5:
        return empty_sequence()

    swing_highs, swing_lows = find_swings(klines, left=1, right=1)

    if not swing_highs or not swing_lows:
        return empty_sequence(reason="Internal swing bulunamadı")

    reasons = []
    state = "IDLE"
    score = 0

    sweep_event = find_sweep_event(
        klines,
        direction=direction,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        lookback=lookback,
    )

    displacement_index = None
    has_cisd = False
    has_mss = False
    sequence_zone = None

    if not sweep_event:
        reasons.append("Sequence: Yönle uyumlu liquidity sweep bulunamadı")
    else:
        state = "SWEPT"
        score += SWEPT_SCORE
        reasons.append(
            f"Sequence: {sweep_event['type']} @ {sweep_event['level']} (mum #{sweep_event['index']})"
        )

        sweep_index = sweep_event["index"]

        displacement_index = find_displacement_after(
            klines,
            direction=direction,
            start_index=sweep_index,
        )

        if displacement_index is not None:
            state = "DISPLACED"
            score += DISPLACED_SCORE
            reasons.append(f"Sequence: Sweep sonrası displacement (mum #{displacement_index})")

        cisd = detect_cisd(klines, direction=direction, anchor_index=sweep_index)
        has_cisd = cisd["has_cisd"]

        has_mss = detect_mss_after(
            klines,
            direction=direction,
            sweep_index=sweep_index,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
        )

        if state == "DISPLACED" and (has_cisd or has_mss):
            state = "CONFIRMED"
            score += CONFIRMED_SCORE

            if has_cisd:
                reasons.append(f"Sequence: CISD onayı (seviye {cisd['cisd_level']})")
            if has_mss:
                reasons.append("Sequence: MSS onayı (internal yapı ters yönde kırıldı)")

        elif has_cisd or has_mss:
            reasons.append("Sequence: CISD/MSS var fakat displacement eksik")

        if state == "CONFIRMED":
            sequence_zone = find_sequence_zone(
                klines,
                direction=direction,
                sweep_index=sweep_index,
            )

            current_price = klines[-1]["close"]

            if sequence_zone and is_price_in_or_near_zone(current_price, sequence_zone):
                state = "ENTRY_ZONE_ACTIVE"
                score += ZONE_ACTIVE_SCORE
                reasons.append(
                    f"Sequence: Fiyat {sequence_zone['type']} içinde/yakınında"
                )
            elif sequence_zone:
                reasons.append(
                    f"Sequence: Zone hazır ({sequence_zone['type']}), fiyat dönüşü bekleniyor"
                )
            else:
                reasons.append("Sequence: Onay var fakat net zone üretilemedi")

    return {
        "sequence_state": state,
        "sequence_score": score,
        "sweep_event": sweep_event,
        "displacement_index": displacement_index,
        "has_cisd": has_cisd,
        "has_mss": has_mss,
        "sequence_zone": sequence_zone,
        "sequence_reasons": reasons,
        "timing_advice": TIMING_ADVICE[state],
    }
