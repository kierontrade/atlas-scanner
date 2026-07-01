import os
from datetime import datetime


def _safe(value, default="-"):
    if value is None:
        return default

    if value == "":
        return default

    return value


def _fmt_num(value, digits=2):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return _safe(value)


def _fmt_zone(zone):
    if not zone:
        return "-"

    return (
        f"{zone.get('type', '-')}"
        f" | Low: {_fmt_num(zone.get('low'))}"
        f" | High: {_fmt_num(zone.get('high'))}"
    )


def _fmt_block(block):
    if not block:
        return "-"

    return (
        f"{block.get('type', '-')}"
        f" | Low: {_fmt_num(block.get('low'))}"
        f" | High: {_fmt_num(block.get('high'))}"
        f" | Mid: {_fmt_num(block.get('mid'))}"
    )


def _fmt_premium_discount(data):
    if not data:
        return "-"

    return (
        f"{data.get('price_zone', '-')}"
        f" | Low: {_fmt_num(data.get('range_low'))}"
        f" | Eq: {_fmt_num(data.get('equilibrium'))}"
        f" | High: {_fmt_num(data.get('range_high'))}"
    )


def _fmt_mitigation(data):
    if not data:
        return "-"

    return (
        f"Mitigated: {data.get('mitigated', False)}"
        f" | Type: {_safe(data.get('mitigation_type'))}"
    )


def _fmt_liquidity_pools(pools):
    if not pools:
        return "-"

    formatted = []

    for pool in pools[:5]:
        formatted.append(
            f"{pool.get('type', '-')} @ {_fmt_num(pool.get('price'))}"
        )

    return ", ".join(formatted)


def _fmt_equal_levels(levels):
    if not levels:
        return "-"

    prices = []

    for level in levels[:5]:
        prices.append(str(_fmt_num(level.get("price"))))

    return ", ".join(prices)


def _fmt_sweep(sweep):
    if not sweep:
        return "-"

    return f"{sweep.get('type', '-')} @ {_fmt_num(sweep.get('price'))}"


def _fmt_displacement(displacement):
    if not displacement:
        return "-"

    return (
        f"Has: {displacement.get('has_displacement', False)}"
        f" | Direction: {_safe(displacement.get('direction'))}"
        f" | Body Ratio: {_fmt_num(displacement.get('body_ratio'), 4)}"
        f" | Range Expansion: {_fmt_num(displacement.get('range_expansion'), 4)}"
    )


def _fmt_reasons(reasons):
    if not reasons:
        return [" -"]

    return [f" - {reason}" for reason in reasons[:14]]


def write_atlas_report(
    candidates,
    ready=None,
    watch=None,
    wait=None,
    failed=None,
    stats=None,
    output_path="reports/atlas_report.txt",
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    ready = ready or []
    watch = watch or []
    wait = wait or []
    failed = failed or []
    stats = stats or {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []

    lines.append("=" * 80)
    lines.append("ATLAS SCANNER REPORT")
    lines.append("Atlas Score V2 / SMC V5")
    lines.append("=" * 80)
    lines.append(f"Generated At: {now}")
    lines.append("")

    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Total Candidates       : {len(candidates or [])}")
    lines.append(f"READY                  : {len(ready)}")
    lines.append(f"WATCH                  : {len(watch)}")
    lines.append(f"WAIT                   : {len(wait)}")
    lines.append(f"Market Quality Failed  : {len(failed)}")

    if stats:
        lines.append("")
        lines.append("SCANNER STATS")
        lines.append("-" * 80)

        for key, value in stats.items():
            lines.append(f"{key}: {value}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("READY")
    lines.append("=" * 80)

    if not ready:
        lines.append("No READY setups.")
    else:
        for item in ready:
            lines.extend(_format_candidate(item))

    lines.append("")
    lines.append("=" * 80)
    lines.append("WATCH")
    lines.append("=" * 80)

    if not watch:
        lines.append("No WATCH setups.")
    else:
        for item in watch:
            lines.extend(_format_candidate(item))

    lines.append("")
    lines.append("=" * 80)
    lines.append("WAIT")
    lines.append("=" * 80)

    if not wait:
        lines.append("No WAIT setups.")
    else:
        for item in wait:
            lines.extend(_format_candidate(item))

    lines.append("")
    lines.append("=" * 80)
    lines.append("MARKET QUALITY FAILED")
    lines.append("=" * 80)

    if not failed:
        lines.append("No failed markets.")
    else:
        for item in failed[:100]:
            symbol = item.get("symbol", "-")
            reasons = item.get("hard_filter_reasons") or item.get("reasons") or []
            reason_text = ", ".join(reasons) if isinstance(reasons, list) else str(reasons)

            lines.append(f"- {symbol} | Reason: {_safe(reason_text)}")

    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"✓ Rapor oluşturuldu: {output_path}")


def _format_candidate(item):
    symbol = item.get("symbol", "-")
    direction = item.get("direction", item.get("trend_direction", "-"))
    status = item.get("setup_status", item.get("status", "-"))
    setup_type = item.get("setup_type", item.get("type", "-"))

    atlas_score = _fmt_num(item.get("atlas_score", item.get("score", 0)))
    atlas_raw_score = _fmt_num(item.get("atlas_raw_score", 0))
    mqs = _fmt_num(item.get("market_quality_score", item.get("mqs", 0)))
    trend_score = _fmt_num(item.get("trend_score", 0))
    setup_score = _fmt_num(item.get("setup_score", 0))
    smc_score = _fmt_num(item.get("smc_score", 0))

    entry = _fmt_num(item.get("entry"))
    stop = _fmt_num(item.get("stop"))
    target = _fmt_num(item.get("target"))
    rr = _fmt_num(item.get("rr"))
    entry_distance = _fmt_num(item.get("entry_distance_percent"))

    smc = item.get("smc", {}) or {}

    lines = []

    lines.append("")
    lines.append(f"- {symbol}")
    lines.append(f"  Status             : {status}")
    lines.append(f"  Direction          : {direction}")
    lines.append(f"  Setup Type         : {setup_type}")
    lines.append(f"  Atlas Score        : {atlas_score}")
    lines.append(f"  Atlas Raw Score    : {atlas_raw_score}")
    lines.append(f"  MQS                : {mqs}")
    lines.append(f"  Trend Score        : {trend_score}")
    lines.append(f"  Setup Score        : {setup_score}")
    lines.append("  Setup Reasons:")
    lines.extend(_fmt_reasons(item.get("setup_reasons")))
    lines.append(f"  SMC Score          : {smc_score}")
    lines.append(f"  Entry              : {entry}")
    lines.append(f"  Stop               : {stop}")
    lines.append(f"  Target             : {target}")
    lines.append(f"  RR                 : {rr}")
    lines.append(f"  Entry Distance %   : {entry_distance}")

    if smc:
        lines.append("")
        lines.append("  SMC V5")
        lines.append(f"  Structure          : {_safe(smc.get('structure'))}")
        lines.append(f"  SMC Direction      : {_safe(smc.get('smc_direction'))}")
        lines.append(f"  Structure Source   : {_safe(smc.get('structure_source'))}")
        lines.append(f"  BOS                : {_safe(smc.get('bos'))}")
        lines.append(f"  CHoCH              : {_safe(smc.get('choch'))}")
        lines.append(f"  Broken Level       : {_safe(smc.get('last_broken_level'))}")

        lines.append("")
        lines.append("  External Structure")
        lines.append(f"  External Structure : {_safe(smc.get('external_structure'))}")
        lines.append(f"  External Direction : {_safe(smc.get('external_direction'))}")
        lines.append(f"  External BOS       : {_safe(smc.get('external_bos'))}")
        lines.append(f"  External CHoCH     : {_safe(smc.get('external_choch'))}")
        lines.append(f"  External Broken    : {_safe(smc.get('external_last_broken_level'))}")

        lines.append("")
        lines.append("  Internal Structure")
        lines.append(f"  Internal Structure : {_safe(smc.get('internal_structure'))}")
        lines.append(f"  Internal Direction : {_safe(smc.get('internal_direction'))}")
        lines.append(f"  Internal BOS       : {_safe(smc.get('internal_bos'))}")
        lines.append(f"  Internal CHoCH     : {_safe(smc.get('internal_choch'))}")
        lines.append(f"  Internal Broken    : {_safe(smc.get('internal_last_broken_level'))}")

        lines.append("")
        lines.append("  SMC Zones / Liquidity")
        lines.append(f"  Order Block        : {_fmt_block(smc.get('order_block'))}")
        lines.append(f"  Breaker Block      : {_fmt_block(smc.get('breaker_block'))}")
        lines.append(f"  Mitigation         : {_fmt_mitigation(smc.get('mitigation'))}")
        lines.append(f"  Supply Zone        : {_fmt_zone(smc.get('supply_zone'))}")
        lines.append(f"  Demand Zone        : {_fmt_zone(smc.get('demand_zone'))}")
        lines.append(f"  Premium/Discount   : {_fmt_premium_discount(smc.get('premium_discount'))}")
        lines.append(f"  Equal Highs        : {_fmt_equal_levels(smc.get('equal_highs'))}")
        lines.append(f"  Equal Lows         : {_fmt_equal_levels(smc.get('equal_lows'))}")
        lines.append(f"  Liquidity Pools    : {_fmt_liquidity_pools(smc.get('liquidity_pools'))}")
        lines.append(f"  Liquidity Sweep    : {_fmt_sweep(smc.get('liquidity_sweep'))}")

        lines.append("")
        lines.append("  SMC Imbalance")
        lines.append(f"  Active FVG         : {_fmt_zone(smc.get('active_fvg'))}")
        lines.append(f"  Active IFVG        : {_fmt_zone(smc.get('active_ifvg'))}")
        lines.append(f"  Active BPR         : {_fmt_zone(smc.get('active_bpr'))}")
        lines.append(f"  Displacement       : {_fmt_displacement(smc.get('displacement'))}")

        lines.append("  SMC Reasons:")
        lines.extend(_fmt_reasons(smc.get("smc_reasons")))

    return lines