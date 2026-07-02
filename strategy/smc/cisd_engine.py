"""
CISD (Change In State of Delivery) Engine

Bullish CISD:
    Sweep'i yapan ardışık bearish (down-close) mum serisinin
    İLK mumunun açılışı, sonraki bir mumun kapanışıyla yukarı kırılırsa
    teslimat durumu değişmiştir (satıcı teslimatı -> alıcı teslimatı).

Bearish CISD: simetrik olarak bullish serinin ilk açılışı aşağı kırılır.

Sadece kapanmış mum kullanılır, repaint yoktur.
"""


def find_delivery_series_open(klines, anchor_index, bearish=True):
    """
    anchor_index'te biten ardışık aynı yönlü mum serisinin
    ilk mumunun açılışını döndürür.

    bearish=True  -> close < open serisi (bullish CISD referansı)
    bearish=False -> close > open serisi (bearish CISD referansı)
    """
    if anchor_index < 0 or anchor_index >= len(klines):
        return None

    series_open = None
    index = anchor_index

    while index >= 0:
        candle = klines[index]

        is_match = (
            candle["close"] < candle["open"]
            if bearish
            else candle["close"] > candle["open"]
        )

        if not is_match:
            break

        series_open = candle["open"]
        index -= 1

    return series_open


def detect_cisd(klines, direction, anchor_index):
    """
    anchor_index: seriyi bitiren mum (genellikle sweep mumu).
    direction: setup yönü ("BULLISH" / "BEARISH").

    Dönüş:
        has_cisd       : bool
        cisd_level     : kırılması gereken seviye (seri ilk açılışı)
        confirm_index  : CISD'yi onaylayan mumun indexi (yoksa None)
    """
    result = {
        "has_cisd": False,
        "cisd_level": None,
        "confirm_index": None,
    }

    if direction not in ("BULLISH", "BEARISH"):
        return result

    if anchor_index is None or anchor_index >= len(klines):
        return result

    bearish_series = direction == "BULLISH"

    series_open = find_delivery_series_open(
        klines,
        anchor_index=anchor_index,
        bearish=bearish_series,
    )

    if series_open is None:
        return result

    result["cisd_level"] = round(series_open, 8)

    for index in range(anchor_index + 1, len(klines)):
        close = klines[index]["close"]

        if direction == "BULLISH" and close > series_open:
            result["has_cisd"] = True
            result["confirm_index"] = index
            return result

        if direction == "BEARISH" and close < series_open:
            result["has_cisd"] = True
            result["confirm_index"] = index
            return result

    return result
