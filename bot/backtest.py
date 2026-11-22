"""Moteur de backtest : rejoue une stratégie sur l'historique, frais compris."""
from .indicators import compute_all
from .strategies import WARMUP


def run(candles, strat, fee=0.004, slip=0.001):
    ind = compute_all(candles)
    n = len(candles)
    equity, peak, max_dd = 1.0, 1.0, 0.0
    trades = []
    pos = None
    pending_entry = pending_exit = False
    for i in range(WARMUP, n):
        o, h, l, c = ind["o"][i], ind["h"][i], ind["l"][i], ind["c"][i]
        a = ind["atr"][i - 1] or ind["atr"][i]
        # ordres décidés à la bougie précédente -> exécutés à l'ouverture
        if pending_entry and pos is None and a:
            px = o * (1 + slip)
            pos = {"entry": px, "stop": px - strat.stop_atr * a, "high": px, "atr": a}
            pending_entry = False
        if pending_exit and pos is not None:
            px = o * (1 - slip)
            r = px / pos["entry"] * (1 - fee) ** 2 - 1
            equity *= 1 + r
            trades.append(r)
            pos, pending_exit = None, False
        if pos is not None:
            if l <= pos["stop"]:
                px = min(o, pos["stop"]) * (1 - slip)
                r = px / pos["entry"] * (1 - fee) ** 2 - 1
                equity *= 1 + r
                trades.append(r)
                pos = None
            else:
                pos["high"] = max(pos["high"], h)
                pos["stop"] = max(pos["stop"], pos["high"] - strat.trail_atr * pos["atr"])
                if strat.exit(ind, i):
                    pending_exit = True
        elif strat.entry(ind, i):
            pending_entry = True
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    pf = (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else (9.99 if wins else 0)
    return {
        "return_pct": round((equity - 1) * 100, 2),
        "max_dd_pct": round(max_dd * 100, 2),
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "profit_factor": round(min(pf, 9.99), 2),
    }


def score(long_res, short_res):
    """Note robuste : il faut gagner sur 2 ans ET sur la période récente."""
    if long_res["trades"] < 4 or short_res["trades"] < 2:
        return None
    if long_res["return_pct"] <= 0 or short_res["return_pct"] <= 0:
        return None
    if long_res["profit_factor"] < 1.2:
        return None
    s = long_res["return_pct"] / (1 + long_res["max_dd_pct"]) + 0.5 * short_res["return_pct"] / (1 + short_res["max_dd_pct"])
    return round(s, 3)
