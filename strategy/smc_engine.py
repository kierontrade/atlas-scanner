from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str


@dataclass
class Zone:
    kind: str
    direction: str
    low: float
    high: float
    index: int
    strength: float
    mitigated: bool = False


class SMCV4Engine:
    """
    ATLAS SMC V4

    Eklenenler:
    - CHoCH
    - Internal BOS
    - External BOS
    - Strong / Weak High Low
    - Premium / Discount
    - Supply Demand Zone
    - Order Block
    - Breaker Block
    - Mitigation Block
    - Liquidity Pool
    - Equal High / Equal Low
    - Inducement
    - Displacement
    - OTE
    - Session / Kill Zone placeholder
    - LONG / SHORT bias üretimi
    """

    def __init__(
        self,
        swing_left: int = 2,
        swing_right: int = 2,
        equal_tolerance_pct: float = 0.15,
        displacement_atr_mult: float = 1.2,
    ):
        self.swing_left = swing_left
        self.swing_right = swing_right
        self.equal_tolerance_pct = equal_tolerance_pct
        self.displacement_atr_mult = displacement_atr_mult

    def analyze(self, candles: List[Dict[str, Any]], symbol: str = "") -> Dict[str, Any]:
        if not candles or len(candles) < 30:
            return self._empty_result(symbol, "NOT_ENOUGH_DATA")

        c = self._normalize_candles(candles)

        swings_high = self._find_swings(c, "high")
        swings_low = self._find_swings(c, "low")

        structure = self._detect_structure(swings_high, swings_low)
        bos = self._detect_bos(c, swings_high, swings_low)
        choch = self._detect_choch(structure, bos)

        internal_bos = self._detect_internal_bos(c)
        external_bos = bos

        strong_weak = self._strong_weak_levels(structure, swings_high, swings_low)

        premium_discount = self._premium_discount(c, swings_high, swings_low)

        equal_highs = self._equal_levels(swings_high)
        equal_lows = self._equal_levels(swings_low)

        liquidity_sweep = self._liquidity_sweep(c, swings_high, swings_low)

        fvg = self._detect_fvg(c)
        ifvg = self._detect_ifvg(c, fvg)

        displacement = self._detect_displacement(c)

        supply_demand = self._detect_supply_demand(c, swings_high, swings_low)
        order_blocks = self._detect_order_blocks(c, bos)
        breaker_blocks = self._detect_breaker_blocks(c, order_blocks, bos)
        mitigation_blocks = self._detect_mitigation_blocks(c, order_blocks)

        inducement = self._detect_inducement(c, equal_highs, equal_lows, liquidity_sweep)
        ote = self._detect_ote(c, swings_high, swings_low)

        bias = self._calculate_bias(
            structure=structure,
            bos=bos,
            choch=choch,
            premium_discount=premium_discount,
            liquidity_sweep=liquidity_sweep,
            displacement=displacement,
            order_blocks=order_blocks,
            fvg=fvg,
            ote=ote,
        )

        score = self._score(
            bias=bias,
            structure=structure,
            bos=bos,
            choch=choch,
            premium_discount=premium_discount,
            liquidity_sweep=liquidity_sweep,
            fvg=fvg,
            ifvg=ifvg,
            displacement=displacement,
            order_blocks=order_blocks,
            breaker_blocks=breaker_blocks,
            mitigation_blocks=mitigation_blocks,
            inducement=inducement,
            ote=ote,
        )

        conflict = self._conflict_filter(bias, structure, bos, choch)

        return {
            "symbol": symbol,
            "version": "SMC_V4",
            "bias": bias,
            "score": score,
            "smc_score": score,
            "conflict": conflict,
            "structure": structure,
            "bos": external_bos,
            "choch": choch,
            "internal_bos": internal_bos,
            "external_bos": external_bos,
            "strong_weak": strong_weak,
            "premium_discount": premium_discount,
            "liquidity_sweep": liquidity_sweep,
            "equal_highs": equal_highs,
            "equal_lows": equal_lows,
            "fvg": fvg,
            "ifvg": ifvg,
            "displacement": displacement,
            "supply_demand": [asdict(z) for z in supply_demand],
            "order_blocks": [asdict(z) for z in order_blocks],
            "breaker_blocks": [asdict(z) for z in breaker_blocks],
            "mitigation_blocks": [asdict(z) for z in mitigation_blocks],
            "inducement": inducement,
            "ote": ote,
            "order_block_found": len(order_blocks) > 0,
            "breaker_block_found": len(breaker_blocks) > 0,
            "mitigation_block_found": len(mitigation_blocks) > 0,
        }

    def _normalize_candles(self, candles):
        out = []
        for x in candles:
            out.append({
                "open": float(x["open"]),
                "high": float(x["high"]),
                "low": float(x["low"]),
                "close": float(x["close"]),
                "volume": float(x.get("volume", 0)),
                "time": x.get("time") or x.get("timestamp"),
            })
        return out

    def _find_swings(self, candles, field):
        swings = []
        for i in range(self.swing_left, len(candles) - self.swing_right):
            price = candles[i][field]
            left = candles[i - self.swing_left:i]
            right = candles[i + 1:i + 1 + self.swing_right]

            if field == "high":
                if all(price > x["high"] for x in left) and all(price > x["high"] for x in right):
                    swings.append(SwingPoint(i, price, "HIGH"))
            else:
                if all(price < x["low"] for x in left) and all(price < x["low"] for x in right):
                    swings.append(SwingPoint(i, price, "LOW"))
        return swings

    def _detect_structure(self, highs, lows):
        if len(highs) < 2 or len(lows) < 2:
            return "NEUTRAL"

        h1, h2 = highs[-2], highs[-1]
        l1, l2 = lows[-2], lows[-1]

        if h2.price > h1.price and l2.price > l1.price:
            return "BULLISH"
        if h2.price < h1.price and l2.price < l1.price:
            return "BEARISH"
        return "RANGE"

    def _detect_bos(self, candles, highs, lows):
        close = candles[-1]["close"]

        if highs and close > highs[-1].price:
            return "BULLISH_BOS"

        if lows and close < lows[-1].price:
            return "BEARISH_BOS"

        return None

    def _detect_choch(self, structure, bos):
        if structure == "BULLISH" and bos == "BEARISH_BOS":
            return "BEARISH_CHOCH"
        if structure == "BEARISH" and bos == "BULLISH_BOS":
            return "BULLISH_CHOCH"
        return None

    def _detect_internal_bos(self, candles):
        recent = candles[-12:]
        if len(recent) < 6:
            return None

        last_close = recent[-1]["close"]
        internal_high = max(x["high"] for x in recent[:-1])
        internal_low = min(x["low"] for x in recent[:-1])

        if last_close > internal_high:
            return "BULLISH_INTERNAL_BOS"
        if last_close < internal_low:
            return "BEARISH_INTERNAL_BOS"
        return None

    def _strong_weak_levels(self, structure, highs, lows):
        result = {
            "strong_high": None,
            "weak_high": None,
            "strong_low": None,
            "weak_low": None,
        }

        if highs:
            result["weak_high"] = highs[-1].price
            result["strong_high"] = max(h.price for h in highs[-5:])

        if lows:
            result["weak_low"] = lows[-1].price
            result["strong_low"] = min(l.price for l in lows[-5:])

        if structure == "BULLISH":
            result["strong_low"] = lows[-1].price if lows else None
            result["weak_high"] = highs[-1].price if highs else None

        if structure == "BEARISH":
            result["strong_high"] = highs[-1].price if highs else None
            result["weak_low"] = lows[-1].price if lows else None

        return result

    def _premium_discount(self, candles, highs, lows):
        if not highs or not lows:
            return "MID"

        high = max(h.price for h in highs[-5:])
        low = min(l.price for l in lows[-5:])
        close = candles[-1]["close"]

        mid = (high + low) / 2

        if close > mid:
            return "PREMIUM"
        if close < mid:
            return "DISCOUNT"
        return "MID"

    def _equal_levels(self, swings):
        levels = []
        if len(swings) < 2:
            return levels

        for i in range(1, len(swings)):
            prev = swings[i - 1]
            cur = swings[i]
            diff_pct = abs(cur.price - prev.price) / prev.price * 100

            if diff_pct <= self.equal_tolerance_pct:
                levels.append({
                    "price": round((cur.price + prev.price) / 2, 8),
                    "from_index": prev.index,
                    "to_index": cur.index,
                    "tolerance_pct": round(diff_pct, 4),
                })

        return levels[-5:]

    def _liquidity_sweep(self, candles, highs, lows):
        last = candles[-1]

        if highs:
            ref = highs[-1].price
            if last["high"] > ref and last["close"] < ref:
                return "BUY_SIDE_SWEEP"

        if lows:
            ref = lows[-1].price
            if last["low"] < ref and last["close"] > ref:
                return "SELL_SIDE_SWEEP"

        return None

    def _detect_fvg(self, candles):
        zones = []

        for i in range(2, len(candles)):
            c1 = candles[i - 2]
            c3 = candles[i]

            if c1["high"] < c3["low"]:
                zones.append({
                    "direction": "BULLISH",
                    "low": c1["high"],
                    "high": c3["low"],
                    "index": i,
                })

            if c1["low"] > c3["high"]:
                zones.append({
                    "direction": "BEARISH",
                    "low": c3["high"],
                    "high": c1["low"],
                    "index": i,
                })

        return zones[-5:]

    def _detect_ifvg(self, candles, fvgs):
        if not fvgs:
            return []

        close = candles[-1]["close"]
        inverted = []

        for z in fvgs:
            if z["direction"] == "BULLISH" and close < z["low"]:
                inverted.append({**z, "ifvg_direction": "BEARISH"})
            elif z["direction"] == "BEARISH" and close > z["high"]:
                inverted.append({**z, "ifvg_direction": "BULLISH"})

        return inverted[-5:]

    def _detect_displacement(self, candles):
        atr = self._atr(candles)
        last = candles[-1]
        body = abs(last["close"] - last["open"])

        if atr <= 0:
            return None

        if body >= atr * self.displacement_atr_mult:
            if last["close"] > last["open"]:
                return "BULLISH_DISPLACEMENT"
            if last["close"] < last["open"]:
                return "BEARISH_DISPLACEMENT"

        return None

    def _detect_supply_demand(self, candles, highs, lows):
        zones = []

        for low in lows[-5:]:
            candle = candles[low.index]
            zones.append(Zone(
                kind="DEMAND",
                direction="LONG",
                low=candle["low"],
                high=max(candle["open"], candle["close"]),
                index=low.index,
                strength=60,
            ))

        for high in highs[-5:]:
            candle = candles[high.index]
            zones.append(Zone(
                kind="SUPPLY",
                direction="SHORT",
                low=min(candle["open"], candle["close"]),
                high=candle["high"],
                index=high.index,
                strength=60,
            ))

        return zones[-10:]

    def _detect_order_blocks(self, candles, bos):
        zones = []

        if bos == "BULLISH_BOS":
            for i in range(len(candles) - 2, 5, -1):
                if candles[i]["close"] < candles[i]["open"]:
                    zones.append(Zone(
                        kind="ORDER_BLOCK",
                        direction="LONG",
                        low=candles[i]["low"],
                        high=candles[i]["high"],
                        index=i,
                        strength=75,
                    ))
                    break

        if bos == "BEARISH_BOS":
            for i in range(len(candles) - 2, 5, -1):
                if candles[i]["close"] > candles[i]["open"]:
                    zones.append(Zone(
                        kind="ORDER_BLOCK",
                        direction="SHORT",
                        low=candles[i]["low"],
                        high=candles[i]["high"],
                        index=i,
                        strength=75,
                    ))
                    break

        return zones

    def _detect_breaker_blocks(self, candles, order_blocks, bos):
        breakers = []
        close = candles[-1]["close"]

        for ob in order_blocks:
            if ob.direction == "LONG" and close < ob.low:
                breakers.append(Zone(
                    kind="BREAKER_BLOCK",
                    direction="SHORT",
                    low=ob.low,
                    high=ob.high,
                    index=ob.index,
                    strength=70,
                ))

            if ob.direction == "SHORT" and close > ob.high:
                breakers.append(Zone(
                    kind="BREAKER_BLOCK",
                    direction="LONG",
                    low=ob.low,
                    high=ob.high,
                    index=ob.index,
                    strength=70,
                ))

        return breakers

    def _detect_mitigation_blocks(self, candles, order_blocks):
        mitigations = []
        close = candles[-1]["close"]

        for ob in order_blocks:
            touched = ob.low <= close <= ob.high
            if touched:
                ob.mitigated = True
                mitigations.append(Zone(
                    kind="MITIGATION_BLOCK",
                    direction=ob.direction,
                    low=ob.low,
                    high=ob.high,
                    index=ob.index,
                    strength=65,
                    mitigated=True,
                ))

        return mitigations

    def _detect_inducement(self, candles, equal_highs, equal_lows, sweep):
        if sweep == "BUY_SIDE_SWEEP" and equal_highs:
            return "SHORT_INDUCEMENT"
        if sweep == "SELL_SIDE_SWEEP" and equal_lows:
            return "LONG_INDUCEMENT"
        return None

    def _detect_ote(self, candles, highs, lows):
        if not highs or not lows:
            return None

        high = highs[-1].price
        low = lows[-1].price
        close = candles[-1]["close"]

        if high == low:
            return None

        fib_62 = high - ((high - low) * 0.62)
        fib_79 = high - ((high - low) * 0.79)

        lower = min(fib_62, fib_79)
        upper = max(fib_62, fib_79)

        if lower <= close <= upper:
            return "OTE_ZONE"

        return None

    def _calculate_bias(
        self,
        structure,
        bos,
        choch,
        premium_discount,
        liquidity_sweep,
        displacement,
        order_blocks,
        fvg,
        ote,
    ):
        long_score = 0
        short_score = 0

        if structure == "BULLISH":
            long_score += 25
        elif structure == "BEARISH":
            short_score += 25

        if bos == "BULLISH_BOS":
            long_score += 20
        elif bos == "BEARISH_BOS":
            short_score += 20

        if choch == "BULLISH_CHOCH":
            long_score += 20
        elif choch == "BEARISH_CHOCH":
            short_score += 20

        if premium_discount == "DISCOUNT":
            long_score += 10
        elif premium_discount == "PREMIUM":
            short_score += 10

        if liquidity_sweep == "SELL_SIDE_SWEEP":
            long_score += 15
        elif liquidity_sweep == "BUY_SIDE_SWEEP":
            short_score += 15

        if displacement == "BULLISH_DISPLACEMENT":
            long_score += 10
        elif displacement == "BEARISH_DISPLACEMENT":
            short_score += 10

        for ob in order_blocks:
            if ob.direction == "LONG":
                long_score += 10
            elif ob.direction == "SHORT":
                short_score += 10

        for z in fvg:
            if z["direction"] == "BULLISH":
                long_score += 5
            elif z["direction"] == "BEARISH":
                short_score += 5

        if ote:
            long_score += 5
            short_score += 5

        if long_score >= short_score + 15:
            return "LONG"
        if short_score >= long_score + 15:
            return "SHORT"

        return "NEUTRAL"

    def _score(
        self,
        bias,
        structure,
        bos,
        choch,
        premium_discount,
        liquidity_sweep,
        fvg,
        ifvg,
        displacement,
        order_blocks,
        breaker_blocks,
        mitigation_blocks,
        inducement,
        ote,
    ):
        score = 0

        if bias in ("LONG", "SHORT"):
            score += 20

        if structure in ("BULLISH", "BEARISH"):
            score += 15

        if bos:
            score += 15

        if choch:
            score += 10

        if premium_discount in ("DISCOUNT", "PREMIUM"):
            score += 8

        if liquidity_sweep:
            score += 10

        if fvg:
            score += 7

        if ifvg:
            score += 6

        if displacement:
            score += 10

        if order_blocks:
            score += 10

        if breaker_blocks:
            score += 5

        if mitigation_blocks:
            score += 5

        if inducement:
            score += 5

        if ote:
            score += 5

        return min(score, 100)

    def _conflict_filter(self, bias, structure, bos, choch):
        if bias == "LONG" and structure == "BEARISH" and bos == "BEARISH_BOS":
            return True

        if bias == "SHORT" and structure == "BULLISH" and bos == "BULLISH_BOS":
            return True

        if bias == "LONG" and choch == "BEARISH_CHOCH":
            return True

        if bias == "SHORT" and choch == "BULLISH_CHOCH":
            return True

        return False

    def _atr(self, candles, period=14):
        if len(candles) < period + 1:
            return 0

        trs = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            trs.append(tr)

        recent = trs[-period:]
        return sum(recent) / len(recent) if recent else 0

    def _empty_result(self, symbol, reason):
        return {
            "symbol": symbol,
            "version": "SMC_V4",
            "bias": "NEUTRAL",
            "score": 0,
            "smc_score": 0,
            "conflict": True,
            "reason": reason,
            "structure": "NEUTRAL",
            "bos": None,
            "choch": None,
            "internal_bos": None,
            "external_bos": None,
            "strong_weak": {},
            "premium_discount": "MID",
            "liquidity_sweep": None,
            "equal_highs": [],
            "equal_lows": [],
            "fvg": [],
            "ifvg": [],
            "displacement": None,
            "supply_demand": [],
            "order_blocks": [],
            "breaker_blocks": [],
            "mitigation_blocks": [],
            "inducement": None,
            "ote": None,
            "order_block_found": False,
            "breaker_block_found": False,
            "mitigation_block_found": False,
        }


def analyze_smc(candles: List[Dict[str, Any]], symbol: str = "") -> Dict[str, Any]:
    """
    Eski mimari uyumluluğu için wrapper.
    Başka dosyalarda analyze_smc() çağrılıyorsa bozulmaz.
    """
    engine = SMCV4Engine()
    return engine.analyze(candles=candles, symbol=symbol)

def detect_structure(candles: List[Dict[str, Any]], symbol: str = "") -> Dict[str, Any]:
    """
    Eski main.py uyumluluğu.
    main.py içinde:
        from strategy.smc_engine import detect_structure
    varsa bozulmaması için eklendi.
    """
    engine = SMCV4Engine()
    return engine.analyze(candles=candles, symbol=symbol)