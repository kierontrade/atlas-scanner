"""
Yeni motorların offline testleri (API çağrısı yok, sentetik mum verisi).

Çalıştırma: python test_offline_engines.py
"""

from datetime import datetime, timezone
from pathlib import Path

from scoring.derivatives_engine import calculate_derivatives_score
from storage import journal
from strategy.entry_sequence import analyze_entry_sequence
from strategy.risk_engine import calculate_position_plan
from strategy.session_engine import get_session_context
from strategy.smc.cisd_engine import detect_cisd


def candle(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, "time": None}


def build_bullish_sweep_scenario():
    """
    0-18  : yatay range (98'de belirgin bir swing low bırakır, index 12)
    19-21 : düşüş serisi, 21. mum 98 swing low'unu süpürüp üstünde kapanır
    22    : bullish displacement (CISD seviyesi 101.0'ı da kırar)
    23    : devam mumu (FVG bırakır, MSS onayı)
    24    : FVG'ye geri çekilme (entry zone aktif)
    """
    klines = []

    for i in range(19):
        if i == 12:
            klines.append(candle(100.5, 100.9, 98.0, 100.4))
        elif i % 2 == 0:
            klines.append(candle(100.2, 101.3, 99.6, 101.0))
        else:
            klines.append(candle(101.0, 101.6, 99.9, 100.2))

    klines.append(candle(101.0, 101.1, 100.0, 100.3))  # 19 bearish
    klines.append(candle(100.3, 100.4, 99.7, 99.9))    # 20 bearish
    klines.append(candle(99.9, 100.0, 97.5, 98.3))     # 21 sweep (98 altına sark, üstünde kapan)
    klines.append(candle(98.3, 101.4, 98.2, 101.2))    # 22 displacement + CISD (>101.0)
    klines.append(candle(101.2, 101.9, 100.3, 101.7))  # 23 devam (21 ile FVG: 100.0-100.3) + MSS
    klines.append(candle(101.7, 101.8, 100.05, 100.2)) # 24 FVG içine geri çekilme

    return klines


def test_entry_sequence_full_chain():
    klines = build_bullish_sweep_scenario()
    result = analyze_entry_sequence(klines, direction="BULLISH")

    assert result["sweep_event"] is not None, "Sweep bulunamadı"
    assert result["sweep_event"]["index"] == 21, f"Sweep yanlış mumda: {result['sweep_event']}"
    assert result["displacement_index"] == 22, f"Displacement yanlış: {result['displacement_index']}"
    assert result["has_cisd"], "CISD bulunamadı"
    assert result["has_mss"], "MSS bulunamadı"
    assert result["sequence_state"] == "ENTRY_ZONE_ACTIVE", f"State: {result['sequence_state']}"
    assert result["sequence_score"] == 48, f"Score: {result['sequence_score']}"

    print("✓ entry_sequence: tam zincir (SWEPT->DISPLACED->CONFIRMED->ZONE) doğru")


def test_entry_sequence_idle_without_sweep():
    # Zikzaklı yükselen trend — swing low'lar oluşur ama hiçbiri süpürülmez
    klines = []

    for i in range(30):
        base = i * 0.3

        if i % 4 == 3:
            klines.append(candle(101.0 + base, 101.1 + base, 99.2 + base, 99.4 + base))
        else:
            klines.append(candle(100.3 + base, 101.5 + base, 100.2 + base, 101.2 + base))

    result = analyze_entry_sequence(klines, direction="BULLISH")

    assert result["sequence_state"] == "IDLE", f"State: {result['sequence_state']}"
    assert "sweep" in result["timing_advice"].lower() or "Likidite" in result["timing_advice"]

    print("✓ entry_sequence: sweep yokken IDLE + 'erken girme' tavsiyesi")


def test_cisd_engine():
    klines = build_bullish_sweep_scenario()
    result = detect_cisd(klines, direction="BULLISH", anchor_index=21)

    assert result["cisd_level"] == 101.0, f"CISD seviyesi: {result['cisd_level']}"
    assert result["has_cisd"], "CISD onaylanmalıydı"
    assert result["confirm_index"] == 22

    print("✓ cisd_engine: seri açılışı ve kırılım doğru")


def test_session_engine():
    ny = get_session_context(datetime(2026, 7, 2, 13, 0, tzinfo=timezone.utc))
    assert ny["session_name"] == "NY_AM_KZ" and ny["session_bonus"] == 5

    off = get_session_context(datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc))
    assert off["session_name"] == "OFF_HOURS" and off["session_bonus"] == -3

    asia = get_session_context(datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc))
    assert asia["session_name"] == "ASIA" and asia["session_bonus"] == 0

    print("✓ session_engine: killzone / off-hours sınıflandırması doğru")


def test_derivatives_engine():
    # Bullish setup + negatif funding + pozitif CVD -> pozitif bonus
    item = {
        "trend_direction": "BULLISH",
        "funding_rate": -0.0004,
        "open_interest": 1_050_000,
        "cvd_proxy": 500.0,
        "price_change_percent_20": 2.0,
    }
    previous = {"open_interest": 1_000_000}

    result = calculate_derivatives_score(item, previous_metrics=previous)

    assert result["derivatives_bonus"] > 0, f"Bonus: {result['derivatives_bonus']}"
    assert result["oi_change_percent"] == 5.0, f"OI değişimi: {result['oi_change_percent']}"
    assert len(result["derivatives_reasons"]) == 3

    # Kalabalık long + ters CVD -> negatif bonus
    crowded = {
        "trend_direction": "BULLISH",
        "funding_rate": 0.0008,
        "open_interest": None,
        "cvd_proxy": -500.0,
    }
    result_crowded = calculate_derivatives_score(crowded, previous_metrics=None)

    assert result_crowded["derivatives_bonus"] < 0, f"Bonus: {result_crowded['derivatives_bonus']}"

    print("✓ derivatives_engine: funding/OI/CVD skorlaması doğru")


def test_journal():
    journal.DB_PATH = Path("data") / "test_journal.db"

    if journal.DB_PATH.exists():
        journal.DB_PATH.unlink()

    journal.init_db()

    item = {
        "symbol": "TEST-USDT",
        "setup_status": "READY",
        "trend_direction": "BULLISH",
        "atlas_score": 80,
        "entry": 100.0,
        "stop": 95.0,
        "target": 110.0,
        "rr": 2.0,
        "entry_state": "AT_ENTRY",
        "trigger_status": "TRIGGER_READY",
        "entry_sequence_state": "ENTRY_ZONE_ACTIVE",
        "open_interest": 1_000_000,
        "funding_rate": 0.0001,
        "current_price": 100.0,
    }

    scan_id = journal.record_scan(
        passed_items=[item],
        failed_count=0,
        session_name="NY_AM_KZ",
        counts={"ready": 1, "watch": 0, "wait": 0},
    )
    assert scan_id == 1

    previous = journal.get_previous_metrics("TEST-USDT")
    assert previous["open_interest"] == 1_000_000

    outcomes = journal.resolve_open_setups({"TEST-USDT": 111.0})
    assert outcomes["tp"] == 1, f"Outcomes: {outcomes}"

    stats = journal.get_outcome_stats()
    assert stats[0]["sequence_state"] == "ENTRY_ZONE_ACTIVE"
    assert stats[0]["win_rate_percent"] == 100.0

    journal.DB_PATH.unlink()

    print("✓ journal: kayıt, OI geçmişi, outcome etiketleme, istatistik doğru")


def test_risk_engine():
    item = {
        "trend_direction": "BULLISH",
        "entry": 100.0,
        "stop": 98.0,
        "target": 106.0,
        "target_source": "RECENT_HIGH",
        "target_candidates": [
            {"price": 103.0, "source": "SUPPLY_ZONE_LOW"},
            {"price": 106.0, "source": "RECENT_HIGH"},
            {"price": 109.0, "source": "BUY_SIDE_LIQUIDITY"},
            {"price": 97.0, "source": "IGNORED_BELOW_ENTRY"},
        ],
    }

    plan = calculate_position_plan(item, balance=1000, risk_percent=1, max_leverage=10)

    # risk 10 USDT / stop mesafesi 2 -> 5 coin -> 500 USDT notional -> kaldıraçsız
    assert plan["plan_side"] == "LONG"
    assert plan["plan_risk_usdt"] == 10.0
    assert plan["plan_quantity"] == 5.0
    assert plan["plan_notional_usdt"] == 500.0
    assert plan["plan_leverage"] == 1
    assert [level["price"] for level in plan["plan_tp_levels"]] == [103.0, 106.0, 109.0]

    # dar stop -> notional bakiyeyi aşar -> kaldıraç önerilir
    tight = dict(item, stop=99.8)
    plan_tight = calculate_position_plan(tight, balance=1000, risk_percent=1, max_leverage=10)

    assert plan_tight["plan_notional_usdt"] == 5000.0
    assert plan_tight["plan_leverage"] == 5
    assert plan_tight["plan_margin_usdt"] == 1000.0

    print("✓ risk_engine: pozisyon boyutu, kaldıraç ve TP kademeleri doğru")


if __name__ == "__main__":
    test_entry_sequence_full_chain()
    test_entry_sequence_idle_without_sweep()
    test_cisd_engine()
    test_session_engine()
    test_derivatives_engine()
    test_journal()
    test_risk_engine()
    print("\nTüm offline testler geçti ✓")
