from scanner.bingx import get_klines

from strategy.smc.imbalance_engine import (
    detect_bpr,
    detect_displacement,
    detect_fvg,
    detect_ifvg,
)
from strategy.smc.liquidity_engine import (
    detect_equal_high_low,
    detect_liquidity_pool,
    detect_liquidity_sweep,
)
from strategy.smc.mtf_engine import detect_mtf_context
from strategy.smc.orderblock_engine import (
    detect_breaker_block,
    detect_mitigation,
    find_order_block,
)
from strategy.smc.scoring_engine import calculate_smc_score
from strategy.smc.structure_engine import detect_structure_from_swings, merge_structure
from strategy.smc.swing_detector import find_swings
from strategy.smc.utils import normalize_klines


DEFAULT_INTERVAL = "1h"
DEFAULT_LIMIT = 150

EXTERNAL_SWING_LEFT = 3
EXTERNAL_SWING_RIGHT = 3
INTERNAL_SWING_LEFT = 1
INTERNAL_SWING_RIGHT = 1

RECENT_SWING_LOOKBACK = 60


def get_recent_swings(swing_highs, swing_lows, lookback=RECENT_SWING_LOOKBACK):
    return swing_highs[-lookback:], swing_lows[-lookback:]


def detect_supply_demand(swing_highs, swing_lows):
    if not swing_highs or not swing_lows:
        return {
            "supply_zone": None,
            "demand_zone": None,
        }

    last_high = swing_highs[-1]
    last_low = swing_lows[-1]

    return {
        "supply_zone": {
            "type": "SUPPLY",
            "high": round(last_high["price"], 8),
            "low": round(last_high["price"] * 0.995, 8),
            "source_index": last_high["index"],
        },
        "demand_zone": {
            "type": "DEMAND",
            "high": round(last_low["price"] * 1.005, 8),
            "low": round(last_low["price"], 8),
            "source_index": last_low["index"],
        },
    }


def detect_premium_discount(klines, swing_highs, swing_lows):
    if not swing_highs or not swing_lows:
        return {
            "range_high": None,
            "range_low": None,
            "equilibrium": None,
            "price_zone": "UNKNOWN",
        }

    recent_highs, recent_lows = get_recent_swings(swing_highs, swing_lows)

    range_high = max(item["price"] for item in recent_highs)
    range_low = min(item["price"] for item in recent_lows)
    equilibrium = (range_high + range_low) / 2

    last_close = klines[-1]["close"]

    if last_close > equilibrium:
        price_zone = "PREMIUM"
    elif last_close < equilibrium:
        price_zone = "DISCOUNT"
    else:
        price_zone = "EQUILIBRIUM"

    return {
        "range_high": round(range_high, 8),
        "range_low": round(range_low, 8),
        "equilibrium": round(equilibrium, 8),
        "price_zone": price_zone,
    }


def empty_result(symbol=None, interval=DEFAULT_INTERVAL, reason="Yetersiz mum verisi"):
    return {
        "symbol": symbol,
        "interval": interval,
        "structure": "RANGE",
        "smc_direction": "NEUTRAL",
        "structure_source": None,
        "external_structure": "RANGE",
        "external_direction": "NEUTRAL",
        "external_bos": None,
        "external_choch": None,
        "external_last_broken_level": None,
        "internal_structure": "RANGE",
        "internal_direction": "NEUTRAL",
        "internal_bos": None,
        "internal_choch": None,
        "internal_last_broken_level": None,
        "smc_score": 0,
        "bos": None,
        "choch": None,
        "last_broken_level": None,
        "order_block": None,
        "breaker_block": None,
        "mitigation": {
            "mitigated": False,
            "mitigation_type": None,
        },
        "supply_zone": None,
        "demand_zone": None,
        "premium_discount": {
            "range_high": None,
            "range_low": None,
            "equilibrium": None,
            "price_zone": "UNKNOWN",
        },
        "equal_highs": [],
        "equal_lows": [],
        "liquidity_pools": [],
        "liquidity_sweep": None,
        "bullish_fvgs": [],
        "bearish_fvgs": [],
        "active_fvg": None,
        "inverse_fvgs": [],
        "active_ifvg": None,
        "bprs": [],
        "active_bpr": None,
        "displacement": {
            "has_displacement": False,
            "direction": "NEUTRAL",
            "body_ratio": 0,
            "range_expansion": 0,
        },
        "mtf_context": {
            "mtf_enabled": False,
            "mtf_bias": "UNKNOWN",
            "mtf_alignment": {
                "aligned": False,
                "alignment": "EMPTY_RESULT",
            },
            "mtf_direction_counts": {
                "BULLISH": 0,
                "BEARISH": 0,
                "NEUTRAL": 0,
            },
            "timeframes": [],
        },
        "mtf_bias": "UNKNOWN",
        "mtf_alignment": "EMPTY_RESULT",
        "smc_reasons": [reason],
    }


def resolve_klines(symbol_or_klines, interval=DEFAULT_INTERVAL, limit=DEFAULT_LIMIT):
    if isinstance(symbol_or_klines, list):
        return symbol_or_klines, None

    symbol = symbol_or_klines
    klines = get_klines(symbol, interval=interval, limit=limit)

    return klines, symbol


def detect_structure(symbol_or_klines, interval=DEFAULT_INTERVAL, limit=DEFAULT_LIMIT):
    raw_klines, symbol = resolve_klines(symbol_or_klines, interval=interval, limit=limit)
    klines = normalize_klines(raw_klines)

    if len(klines) < 20:
        return empty_result(symbol=symbol, interval=interval)

    current_price = klines[-1]["close"]

    external_swing_highs, external_swing_lows = find_swings(
        klines,
        left=EXTERNAL_SWING_LEFT,
        right=EXTERNAL_SWING_RIGHT,
    )
    internal_swing_highs, internal_swing_lows = find_swings(
        klines,
        left=INTERNAL_SWING_LEFT,
        right=INTERNAL_SWING_RIGHT,
    )

    if not internal_swing_highs or not internal_swing_lows:
        return empty_result(
            symbol=symbol,
            interval=interval,
            reason="Internal swing high/low bulunamadı",
        )

    external_result = detect_structure_from_swings(
        klines=klines,
        swing_highs=external_swing_highs,
        swing_lows=external_swing_lows,
        label="EXTERNAL",
    )
    internal_result = detect_structure_from_swings(
        klines=klines,
        swing_highs=internal_swing_highs,
        swing_lows=internal_swing_lows,
        label="INTERNAL",
    )

    structure_result = merge_structure(
        external_result=external_result,
        internal_result=internal_result,
    )

    direction = structure_result["smc_direction"]

    order_block = find_order_block(klines, direction)
    mitigation = detect_mitigation(klines, order_block)
    breaker_block = detect_breaker_block(
        structure_result["structure"],
        order_block,
        mitigation,
    )

    structure_swing_highs = external_swing_highs or internal_swing_highs
    structure_swing_lows = external_swing_lows or internal_swing_lows

    supply_demand = detect_supply_demand(
        structure_swing_highs,
        structure_swing_lows,
    )
    premium_discount = detect_premium_discount(
        klines,
        structure_swing_highs,
        structure_swing_lows,
    )

    equal_levels = detect_equal_high_low(
        internal_swing_highs,
        internal_swing_lows,
    )
    liquidity_pools = detect_liquidity_pool(equal_levels)
    liquidity_sweep = detect_liquidity_sweep(klines, liquidity_pools)

    fvg = detect_fvg(klines)
    ifvg = detect_ifvg(fvg)
    bpr = detect_bpr(fvg)
    displacement = detect_displacement(klines)

    mtf_context = detect_mtf_context(
        symbol=symbol,
        current_direction=direction,
    )

    smc_score, smc_reasons = calculate_smc_score(
        structure_result=structure_result,
        order_block=order_block,
        breaker_block=breaker_block,
        mitigation=mitigation,
        supply_demand=supply_demand,
        premium_discount=premium_discount,
        equal_levels=equal_levels,
        liquidity_pools=liquidity_pools,
        liquidity_sweep=liquidity_sweep,
        fvg=fvg,
        ifvg=ifvg,
        bpr=bpr,
        displacement=displacement,
        mtf_context=mtf_context,
        current_price=current_price,
    )

    return {
        "symbol": symbol,
        "interval": interval,
        "structure": structure_result["structure"],
        "smc_direction": structure_result["smc_direction"],
        "structure_source": structure_result["structure_source"],
        "external_structure": structure_result["external_structure"],
        "external_direction": structure_result["external_direction"],
        "external_bos": structure_result["external_bos"],
        "external_choch": structure_result["external_choch"],
        "external_last_broken_level": structure_result["external_last_broken_level"],
        "internal_structure": structure_result["internal_structure"],
        "internal_direction": structure_result["internal_direction"],
        "internal_bos": structure_result["internal_bos"],
        "internal_choch": structure_result["internal_choch"],
        "internal_last_broken_level": structure_result["internal_last_broken_level"],
        "smc_score": smc_score,
        "bos": structure_result["bos"],
        "choch": structure_result["choch"],
        "last_broken_level": structure_result["last_broken_level"],
        "order_block": order_block,
        "breaker_block": breaker_block,
        "mitigation": mitigation,
        "supply_zone": supply_demand["supply_zone"],
        "demand_zone": supply_demand["demand_zone"],
        "premium_discount": premium_discount,
        "equal_highs": equal_levels["equal_highs"],
        "equal_lows": equal_levels["equal_lows"],
        "liquidity_pools": liquidity_pools,
        "liquidity_sweep": liquidity_sweep,
        "bullish_fvgs": fvg["bullish_fvgs"],
        "bearish_fvgs": fvg["bearish_fvgs"],
        "active_fvg": fvg["active_fvg"],
        "inverse_fvgs": ifvg["inverse_fvgs"],
        "active_ifvg": ifvg["active_ifvg"],
        "bprs": bpr["bprs"],
        "active_bpr": bpr["active_bpr"],
        "displacement": displacement,
        "mtf_context": mtf_context,
        "mtf_bias": mtf_context.get("mtf_bias"),
        "mtf_alignment": mtf_context.get("mtf_alignment", {}).get("alignment"),
        "smc_reasons": smc_reasons,
    }