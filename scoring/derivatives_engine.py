"""
Derivatives Engine (Funding / Open Interest / CVD Proxy)

Türev piyasası konumlanmasını setup yönüyle karşılaştırır ve
Atlas Score'a sınırlı, açıklanabilir bir bonus/ceza üretir.

Mantık (kurumsal bakış):

    Funding:
        Bullish setup + negatif funding  -> shortlar ödüyor, squeeze yakıtı (+)
        Bullish setup + aşırı pozitif    -> kalabalık long, ters risk (-)
        (bearish için simetrik)

    Open Interest değişimi (bir önceki taramaya göre, journal'dan):
        OI artıyor + fiyat yönle uyumlu  -> yeni para trendi onaylıyor (+)
        OI artıyor + fiyat yöne ters     -> ters taraf birikiyor, sweep/squeeze adayı (+küçük)
        OI düşüyor                       -> pozisyon kapanışı, ilgi azalıyor (0/-)

    CVD proxy (1h mumlardan işaretli hacim toplamı, setup engine hesaplar):
        Yönle uyumlu delta               -> agresif taraf bizimle (+)
        Yöne ters delta                  -> divergence, dikkat (-)

Toplam bonus [-8, +12] aralığına sıkıştırılır; tek başına
setup üretmez, sadece mevcut confluence'ı güçlendirir/zayıflatır.
"""


FUNDING_EXTREME = 0.0005
FUNDING_NEUTRAL = 0.0001

OI_CHANGE_SIGNIFICANT_PERCENT = 1.0

DERIVATIVES_BONUS_MIN = -8
DERIVATIVES_BONUS_MAX = 12


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_funding_direction(direction, funding_rate):
    funding = to_float(funding_rate)

    if funding is None:
        return 0, "Funding verisi yok"

    if abs(funding) <= FUNDING_NEUTRAL:
        return 2, "Funding nötr — kalabalık pozisyon baskısı yok"

    if direction == "BULLISH":
        if funding < 0:
            return 6, "Funding negatif — shortlar ödüyor, squeeze yakıtı"
        if funding >= FUNDING_EXTREME:
            return -5, "Funding aşırı pozitif — kalabalık long riski"
        return 0, "Funding hafif pozitif"

    if direction == "BEARISH":
        if funding > 0:
            return 6, "Funding pozitif — longlar ödüyor, düşüş yakıtı"
        if funding <= -FUNDING_EXTREME:
            return -5, "Funding aşırı negatif — kalabalık short riski"
        return 0, "Funding hafif negatif"

    return 0, "Yön belirsiz, funding değerlendirilmedi"


def score_oi_change(direction, oi_change_percent, price_change_percent):
    if oi_change_percent is None:
        return 0, "OI değişimi yok (ilk tarama veya veri eksik)"

    if abs(oi_change_percent) < OI_CHANGE_SIGNIFICANT_PERCENT:
        return 0, f"OI değişimi önemsiz ({round(oi_change_percent, 2)}%)"

    price_up = (price_change_percent or 0) > 0
    oi_up = oi_change_percent > 0

    if oi_up:
        price_aligned = (direction == "BULLISH" and price_up) or (
            direction == "BEARISH" and not price_up
        )

        if price_aligned:
            return 5, f"OI artıyor (+{round(oi_change_percent, 2)}%) ve fiyat yönle uyumlu — yeni para onaylıyor"

        return 3, f"OI artıyor (+{round(oi_change_percent, 2)}%) fakat fiyat ters — karşı taraf birikiyor, squeeze adayı"

    return -2, f"OI düşüyor ({round(oi_change_percent, 2)}%) — pozisyon kapanışı, ilgi azalıyor"


def score_cvd_proxy(direction, cvd_proxy):
    cvd = to_float(cvd_proxy)

    if cvd is None or cvd == 0:
        return 0, "CVD proxy verisi yok"

    if direction == "BULLISH" and cvd > 0:
        return 4, "CVD proxy pozitif — agresif alıcı bizimle"

    if direction == "BEARISH" and cvd < 0:
        return 4, "CVD proxy negatif — agresif satıcı bizimle"

    return -3, "CVD proxy setup yönüyle çelişiyor (divergence)"


def calculate_oi_change_percent(current_oi, previous_oi):
    current = to_float(current_oi)
    previous = to_float(previous_oi)

    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / previous) * 100


def calculate_derivatives_score(item, previous_metrics=None):
    """
    item             : pipeline item'ı (funding_rate, open_interest,
                       trend_direction, cvd_proxy, price_change_percent_20 içerir)
    previous_metrics : journal'dan gelen önceki tarama metrikleri
                       {"open_interest": ..., "funding_rate": ...} veya None

    Dönüş: item'a merge edilecek alanlar.
    """
    direction = item.get("trend_direction", "NEUTRAL")

    reasons = []
    total = 0

    funding_score, funding_reason = score_funding_direction(
        direction=direction,
        funding_rate=item.get("funding_rate"),
    )
    total += funding_score
    reasons.append(f"Derivatives: {funding_reason}")

    previous_oi = (previous_metrics or {}).get("open_interest")
    oi_change_percent = calculate_oi_change_percent(
        current_oi=item.get("open_interest"),
        previous_oi=previous_oi,
    )

    oi_score, oi_reason = score_oi_change(
        direction=direction,
        oi_change_percent=oi_change_percent,
        price_change_percent=item.get("price_change_percent_20"),
    )
    total += oi_score
    reasons.append(f"Derivatives: {oi_reason}")

    cvd_score, cvd_reason = score_cvd_proxy(
        direction=direction,
        cvd_proxy=item.get("cvd_proxy"),
    )
    total += cvd_score
    reasons.append(f"Derivatives: {cvd_reason}")

    bonus = max(DERIVATIVES_BONUS_MIN, min(DERIVATIVES_BONUS_MAX, total))

    return {
        "derivatives_bonus": bonus,
        "derivatives_reasons": reasons,
        "oi_change_percent": round(oi_change_percent, 4) if oi_change_percent is not None else None,
    }
