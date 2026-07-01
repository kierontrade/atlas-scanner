import os
from datetime import datetime


def _safe(value, default="-"):
    return default if value is None else value


def _fmt_num(value, digits=2):
    try:
        return round(float(value), digits)
    except Exception:
        return value


def write_atlas_report(
    candidates,
    ready=None,
    watch=None,
    wait=None,
    failed=None,
    stats=None,
    output_path="reports/atlas_report.txt",
):
    """
    Backward-compatible report writer.

    Eski çağrılar:
        write_atlas_report(candidates, ready, watch, wait, failed)

    Yeni çağrılar:
        write_atlas_report(candidates, ready, watch, wait, failed, stats)

    stats verilmezse hata vermez.
    """

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    ready = ready or []
    watch = watch or []
    wait = wait or []
    failed = failed or []
    stats = stats or {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("=" * 70)
    lines.append("ATLAS SCANNER REPORT")
    lines.append("Atlas Score V2 / SMC Compatible")
    lines.append("=" * 70)
    lines.append(f"Generated At: {now}")
    lines.append("")

    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"Total Candidates       : {len(candidates or [])}")
    lines.append(f"READY                  : {len(ready)}")
    lines.append(f"WATCH                  : {len(watch)}")
    lines.append(f"WAIT                   : {len(wait)}")
    lines.append(f"Market Quality Failed  : {len(failed)}")

    if stats:
        lines.append("")
        lines.append("SCANNER STATS")
        lines.append("-" * 70)
        for key, value in stats.items():
            lines.append(f"{key}: {value}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("READY")
    lines.append("=" * 70)

    if not ready:
        lines.append("No READY setups.")
    else:
        for item in ready:
            lines.extend(_format_candidate(item))

    lines.append("")
    lines.append("=" * 70)
    lines.append("WATCH")
    lines.append("=" * 70)

    if not watch:
        lines.append("No WATCH setups.")
    else:
        for item in watch:
            lines.extend(_format_candidate(item))

    lines.append("")
    lines.append("=" * 70)
    lines.append("WAIT")
    lines.append("=" * 70)

    if not wait:
        lines.append("No WAIT setups.")
    else:
        for item in wait:
            lines.extend(_format_candidate(item))

    lines.append("")
    lines.append("=" * 70)
    lines.append("MARKET QUALITY FAILED")
    lines.append("=" * 70)

    if not failed:
        lines.append("No failed markets.")
    else:
        for item in failed[:100]:
            symbol = item.get("symbol", "-")
            reason = item.get("reason", item.get("fail_reason", "-"))
            lines.append(f"- {symbol} | Reason: {reason}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✓ Rapor oluşturuldu: {output_path}")


def _format_candidate(item):
    symbol = item.get("symbol", "-")
    direction = item.get("direction", item.get("trend_direction", "-"))
    status = item.get("status", "-")
    setup_type = item.get("setup_type", item.get("type", "-"))

    atlas_score = _fmt_num(item.get("atlas_score", item.get("score", 0)))
    mqs = _fmt_num(item.get("market_quality_score", item.get("mqs", 0)))
    trend_score = _fmt_num(item.get("trend_score", 0))
    setup_score = _fmt_num(item.get("setup_score", 0))
    smc_score = _fmt_num(item.get("smc_score", 0))

    entry = _fmt_num(item.get("entry"))
    stop = _fmt_num(item.get("stop"))
    target = _fmt_num(item.get("target"))
    rr = _fmt_num(item.get("rr"))

    lines = []
    lines.append("")
    lines.append(f"- {symbol}")
    lines.append(f"  Status      : {status}")
    lines.append(f"  Direction   : {direction}")
    lines.append(f"  Type        : {setup_type}")
    lines.append(f"  Atlas Score : {atlas_score}")
    lines.append(f"  MQS         : {mqs}")
    lines.append(f"  Trend Score : {trend_score}")
    lines.append(f"  Setup Score : {setup_score}")
    lines.append(f"  SMC Score   : {smc_score}")
    lines.append(f"  Entry       : {entry}")
    lines.append(f"  Stop        : {stop}")
    lines.append(f"  Target      : {target}")
    lines.append(f"  RR          : {rr}")

    smc = item.get("smc", {})
    if smc:
        lines.append("  SMC:")
        lines.append(f"    Bias              : {_safe(smc.get('bias'))}")
        lines.append(f"    Structure         : {_safe(smc.get('structure'))}")
        lines.append(f"    BOS               : {_safe(smc.get('bos'))}")
        lines.append(f"    CHoCH             : {_safe(smc.get('choch'))}")
        lines.append(f"    Liquidity Sweep   : {_safe(smc.get('liquidity_sweep'))}")
        lines.append(f"    Premium/Discount  : {_safe(smc.get('premium_discount'))}")
        lines.append(f"    Order Block       : {_safe(smc.get('order_block_found'))}")
        lines.append(f"    Breaker Block     : {_safe(smc.get('breaker_block_found'))}")
        lines.append(f"    Mitigation Block  : {_safe(smc.get('mitigation_block_found'))}")

    return lines