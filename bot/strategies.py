"""Les deux stratégies du bot.

- « Départ après calme » : le prix dort (bandes de Bollinger très serrées),
  puis il casse vers le haut avec du volume -> achat. On sort quand le
  mouvement s'essouffle (retour sous la moyenne 20).
- « Suivi de tendance » : tendance haussière confirmée (EMA20 > EMA50 qui monte),
  achat quand le prix repasse au-dessus de l'EMA20 après un petit creux.
  On sort quand le prix casse l'EMA50.

Chaque stratégie a aussi un stop-loss et un stop suiveur en multiples d'ATR
(la volatilité moyenne), gérés par le moteur.
"""

WARMUP = 130  # bougies nécessaires avant de pouvoir décider


def _ok(*vals):
    return all(v is not None for v in vals)


def _percentile(vals, p):
    s = sorted(v for v in vals if v is not None)
    if not s:
        return None
    k = (len(s) - 1) * p / 100
    f = int(k)
    return s[f] if f == len(s) - 1 else s[f] + (s[f + 1] - s[f]) * (k - f)


class CalmBreakout:
    key = "calme"
    label = "Départ après calme"
    stop_atr = 2.0
    trail_atr = 3.0

    @staticmethod
    def entry(ind, i):
        if i < WARMUP:
            return False
        c, up, bw, v, v20 = ind["c"], ind["bb_up"], ind["bb_bw"], ind["v"], ind["vol20"]
        if not _ok(up[i], bw[i], v20[i]):
            return False
        recent = [x for x in bw[i - 5:i] if x is not None]
        p20 = _percentile(bw[i - 120:i], 20)
        if not recent or p20 is None:
            return False
        squeeze = min(recent) <= p20
        return squeeze and c[i] > up[i] and c[i] > c[i - 1] and v[i] > 1.2 * v20[i]

    @staticmethod
    def exit(ind, i):
        return _ok(ind["bb_mid"][i]) and ind["c"][i] < ind["bb_mid"][i]


class TrendFollow:
    key = "tendance"
    label = "Suivi de tendance"
    stop_atr = 2.5
    trail_atr = 3.5

    @staticmethod
    def entry(ind, i):
        if i < WARMUP:
            return False
        c, e20, e50, r = ind["c"], ind["ema20"], ind["ema50"], ind["rsi"]
        if not _ok(e20[i], e50[i], e50[i - 5], e20[i - 1], r[i]):
            return False
        trend = e20[i] > e50[i] and e50[i] > e50[i - 5]
        reclaim = c[i - 1] <= e20[i - 1] and c[i] > e20[i]
        return trend and reclaim and 50 <= r[i] <= 70

    @staticmethod
    def exit(ind, i):
        return _ok(ind["ema50"][i]) and ind["c"][i] < ind["ema50"][i]


STRATEGIES = {s.key: s for s in (CalmBreakout, TrendFollow)}
