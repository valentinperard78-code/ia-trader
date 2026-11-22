"""Indicateurs techniques, en Python pur (aucune dépendance)."""
import math


def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def sma(values, n):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(highs, lows, closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    prev = sum(trs[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(closes)):
        prev = (prev * (n - 1) + trs[i]) / n
        out[i] = prev
    return out


def bollinger(closes, n=20, k=2.0):
    mid = sma(closes, n)
    up = [None] * len(closes)
    lo = [None] * len(closes)
    bw = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        up[i], lo[i] = m + k * sd, m - k * sd
        bw[i] = (up[i] - lo[i]) / m if m else None
    return mid, up, lo, bw


def compute_all(candles):
    """candles = liste de dicts {t,o,h,l,c,v}. Renvoie un dict de séries."""
    o = [c["o"] for c in candles]
    h = [c["h"] for c in candles]
    l = [c["l"] for c in candles]
    c = [c["c"] for c in candles]
    v = [x["v"] for x in candles]
    mid, up, lo, bw = bollinger(c)
    return {
        "t": [x["t"] for x in candles], "o": o, "h": h, "l": l, "c": c, "v": v,
        "ema20": ema(c, 20), "ema50": ema(c, 50), "rsi": rsi(c), "atr": atr(h, l, c),
        "bb_mid": mid, "bb_up": up, "bb_lo": lo, "bb_bw": bw, "vol20": sma(v, 20),
    }
