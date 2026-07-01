MAX_RANGE_SCORE = 32
MAX_CONFLICT_SCORE = 45
MAX_MTF_CONFLICT_SCORE = 55

NEAR_ZONE_PERCENT = 1.25


def score_structure(structure):
    if structure in ("BULLISH_CHOCH", "BEARISH_CHOCH"):
        return 28

    if structure in ("BULLISH_BOS", "BEARISH_BOS"):
        return 24

    if structure in ("BULLISH_STRUCTURE", "BEARISH_STRUCTURE"):
        return 14

    return 5


def is_near_zone(current_price, zone, max_distance_percent=NEAR_ZONE_PERCENT):
    if not current_price or not zone:
        return False

    high = zone.get("high")
    low = zone.get("low")
    mid = zone.get("mid")

    if high is None or low is None:
        return False

    if low <= current_price <= high:
        return True

    reference = mid or ((high + low) / 2)

    if reference == 0:
        return False

    distance = abs((current_price - reference) / reference) * 100
    return distance <= max_distance_percent


def is_premium_discount_aligned(direction, premium_discount):
    price_zone = premium_discount.get("price_zone")

    if direction == "BULLISH" and price_zone == "DISCOUNT":
        return True

    if direction == "BEARISH" and price_zone == "PREMIUM":
        return True

    return False


def is_sweep_aligned(direction, liquidity_sweep):
    if not liquidity_sweep:
        return False

    sweep_type = liquidity_sweep.get("type")

    if direction == "BULLISH" and sweep_type == "SELL_SIDE_SWEEP":
        return True

    if direction == "BEARISH" and sweep_type == "BUY_SIDE_SWEEP":
        return True

    return False


def is_displacement_aligned(direction, displacement):
    if not displacement or not displacement.get("has_displacement"):
        return False

    return displacement.get("direction") == direction


def is_fvg_aligned(direction, active_fvg):
    if not active_fvg:
        return False

    if direction == "BULLISH" and active_fvg.get("type") == "BULLISH_FVG":
        return True

    if direction == "BEARISH" and active_fvg.get("type") == "BEARISH_FVG":
        return True

    return False


def is_ifvg_aligned(direction, active_ifvg):
    if not active_ifvg:
        return False

    if direction == "BULLISH" and active_ifvg.get("type") == "BULLISH_IFVG":
        return True

    if direction == "BEARISH" and active_ifvg.get("type") == "BEARISH_IFVG":
        return True

    return False


def calculate_structure_alignment_score(structure_result):
    external_direction = structure_result.get("external_direction")
    internal_direction = structure_result.get("internal_direction")

    if external_direction == "NEUTRAL" or internal_direction == "NEUTRAL":
        return 0, ["External/internal structure uyumu nötr"]

    if external_direction == internal_direction:
        return 6, ["External/internal structure uyumlu"]

    return -8, ["External/internal structure çelişkili"]


def calculate_fvg_score(direction, fvg, current_price):
    active_fvg = fvg.get("active_fvg")

    if not active_fvg:
        return 0, []

    if not is_fvg_aligned(direction, active_fvg):
        return 0, ["Aktif FVG yönle uyumlu değil"]

    if active_fvg.get("inverted"):
        return 0, ["Aktif FVG invert olmuş, klasik FVG puanı verilmedi"]

    if active_fvg.get("mitigated"):
        if is_near_zone(current_price, active_fvg):
            return 3, ["Mitigated ama fiyat yakın aktif FVG bulundu"]

        return 1, ["Mitigated FVG bulundu, düşük puan verildi"]

    if is_near_zone(current_price, active_fvg):
        return 8, ["Yönle uyumlu, unmitigated ve fiyata yakın FVG bulundu"]

    return 5, ["Yönle uyumlu unmitigated FVG bulundu"]


def calculate_ifvg_score(direction, ifvg, current_price):
    active_ifvg = ifvg.get("active_ifvg")

    if not active_ifvg:
        return 0, []

    if not is_ifvg_aligned(direction, active_ifvg):
        return 0, ["Aktif IFVG yönle uyumlu değil"]

    if is_near_zone(current_price, active_ifvg):
        return 8, ["Yönle uyumlu ve fiyata yakın IFVG bulundu"]

    return 3, ["Yönle uyumlu IFVG bulundu fakat fiyat uzak"]


def calculate_bpr_score(bpr, current_price):
    active_bpr = bpr.get("active_bpr")

    if not active_bpr:
        return 0, []

    if is_near_zone(current_price, active_bpr):
        return 6, ["Fiyata yakın Balanced Price Range bulundu"]

    return 2, ["Balanced Price Range bulundu fakat fiyat uzak"]


def has_internal_external_conflict(structure_result):
    external_direction = structure_result.get("external_direction")
    internal_direction = structure_result.get("internal_direction")

    if external_direction == "NEUTRAL" or internal_direction == "NEUTRAL":
        return False

    return external_direction != internal_direction


def calculate_mtf_score(direction, mtf_context):
    if not mtf_context or not mtf_context.get("mtf_enabled"):
        return 0, ["MTF context aktif değil"], False

    mtf_bias = mtf_context.get("mtf_bias", "UNKNOWN")
    mtf_alignment = mtf_context.get("mtf_alignment", {})
    alignment = mtf_alignment.get("alignment")

    if direction == "NEUTRAL":
        return 0, ["SMC yönü nötr olduğu için MTF puanı verilmedi"], False

    if alignment == "FULL_ALIGNMENT":
        return 8, [f"MTF tam uyumlu: {mtf_bias}"], False

    if alignment == "WEAK_ALIGNMENT":
        return 4, [f"MTF zayıf uyumlu: {mtf_bias}"], False

    if alignment == "MTF_CONFLICT":
        return -10, [f"MTF conflict: {mtf_bias}"], True

    if alignment == "MTF_NEUTRAL":
        return 0, ["MTF bias nötr"], False

    return 0, [f"MTF alignment: {alignment}"], False


def calculate_smc_score(
    structure_result,
    order_block,
    breaker_block,
    mitigation,
    supply_demand,
    premium_discount,
    equal_levels,
    liquidity_pools,
    liquidity_sweep,
    fvg,
    ifvg,
    bpr,
    displacement,
    mtf_context=None,
    current_price=None,
):
    score = 0
    reasons = []

    structure = structure_result["structure"]
    direction = structure_result["smc_direction"]

    score += score_structure(structure)
    reasons.extend(structure_result["structure_reasons"])

    alignment_score, alignment_reasons = calculate_structure_alignment_score(structure_result)
    score += alignment_score
    reasons.extend(alignment_reasons)

    if order_block:
        score += 8
        reasons.append("Yöne uygun order block bulundu")

    if mitigation.get("mitigated"):
        score += 6
        reasons.append("Order block mitigation aldı")

    if breaker_block:
        score += 8
        reasons.append("Breaker block oluştu")

    if supply_demand.get("supply_zone") and supply_demand.get("demand_zone"):
        score += 4
        reasons.append("Supply/Demand bölgeleri çıkarıldı")

    if premium_discount.get("price_zone") in ("PREMIUM", "DISCOUNT"):
        if is_premium_discount_aligned(direction, premium_discount):
            score += 8
            reasons.append(f"Fiyat yönle uyumlu {premium_discount['price_zone']} bölgesinde")
        else:
            score += 1
            reasons.append(f"Fiyat {premium_discount['price_zone']} bölgesinde fakat yön avantajı zayıf")

    if equal_levels.get("equal_highs") or equal_levels.get("equal_lows"):
        score += 4
        reasons.append("Equal high/low likiditesi bulundu")

    if liquidity_pools:
        score += 3
        reasons.append("Likidite havuzu bulundu")

    if liquidity_sweep:
        if is_sweep_aligned(direction, liquidity_sweep):
            score += 8
            reasons.append("Yönle uyumlu likidite sweep tespit edildi")
        else:
            score += 2
            reasons.append("Likidite sweep var fakat yön uyumu zayıf")

    fvg_score, fvg_reasons = calculate_fvg_score(direction, fvg, current_price)
    score += fvg_score
    reasons.extend(fvg_reasons)

    ifvg_score, ifvg_reasons = calculate_ifvg_score(direction, ifvg, current_price)
    score += ifvg_score
    reasons.extend(ifvg_reasons)

    bpr_score, bpr_reasons = calculate_bpr_score(bpr, current_price)
    score += bpr_score
    reasons.extend(bpr_reasons)

    if is_displacement_aligned(direction, displacement):
        score += 6
        reasons.append("Yönle uyumlu displacement bulundu")

    mtf_score, mtf_reasons, mtf_conflict = calculate_mtf_score(direction, mtf_context)
    score += mtf_score
    reasons.extend(mtf_reasons)

    if has_internal_external_conflict(structure_result):
        score = min(score, MAX_CONFLICT_SCORE)
        reasons.append("External/internal çelişki nedeniyle SMC skoru sınırlandı")

    if mtf_conflict:
        score = min(score, MAX_MTF_CONFLICT_SCORE)
        reasons.append("MTF conflict nedeniyle SMC skoru sınırlandı")

    if direction == "NEUTRAL":
        score = min(score, 40)
        reasons.append("SMC yönü nötr olduğu için skor sınırlandı")

    if structure == "RANGE":
        score = min(score, MAX_RANGE_SCORE)
        reasons.append("Range yapısı nedeniyle SMC skoru sınırlandı")

    return max(0, min(score, 100)), reasons