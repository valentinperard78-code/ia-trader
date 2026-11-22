"""Tests hors ligne : données synthétiques, aucune connexion nécessaire.
Lancer depuis la racine :  python -m tests.test_offline
"""
import json
import math
import random
import shutil
import tempfile
import time
from pathlib import Path

from bot import backtest, indicators, run, sources
from bot.strategies import STRATEGIES

random.seed(7)


def synth(n=800, start=100.0, step=14400):
    """Marché synthétique : phases calmes, cassures, tendances, chutes."""
    out, p, t0 = [], start, int(time.time()) - n * step
    for i in range(n):
        phase = (i // 120) % 4
        drift = [0.0, 0.004, -0.003, 0.001][phase]
        vol = [0.004, 0.015, 0.02, 0.01][phase]
        o = p
        p = max(0.01, p * math.exp(drift + random.gauss(0, vol)))
        h, l = max(o, p) * (1 + abs(random.gauss(0, vol / 2))), min(o, p) * (1 - abs(random.gauss(0, vol / 2)))
        v = 1000 * (3 if phase == 1 and i % 120 < 10 else 1) * (1 + random.random())
        out.append({"t": t0 + i * step, "o": o, "h": h, "l": l, "c": p, "v": v})
    return out


def test_indicators():
    c = [float(x) for x in range(1, 101)]
    e = indicators.ema(c, 20)
    assert e[18] is None and abs(e[19] - 10.5) < 1e-9
    r = indicators.rsi(c)
    assert r[-1] == 100
    mid, up, lo, bw = indicators.bollinger([5.0] * 30)
    assert bw[-1] == 0 and up[-1] == lo[-1] == 5.0
    print("ok indicateurs")


def test_backtest():
    data = synth()
    for key, s in STRATEGIES.items():
        r = backtest.run(data, s)
        assert r["trades"] >= 1, (key, r)
        assert 0 <= r["max_dd_pct"] <= 100
        print(f"ok backtest {key}: {r}")


def test_live(tmp):
    data = {"XXBTZEUR": synth(300, 60000), "XETHZEUR": synth(300, 3000), "SOLEUR": synth(300, 150)}
    clock = {"i": 200}

    def fake_ohlc(pair, interval):
        return data[pair][: clock["i"]]

    sources.ohlc = fake_ohlc
    sources.tickers = lambda pairs: {p: {"price": data[p][clock["i"]]["c"], "vol24_eur": 1e6} for p in pairs if p in data}
    sources.fear_greed = lambda: {"value": 12, "label": "peur extrême"}
    sources.news = lambda: ([{"t": int(time.time()), "source": "Test", "title": "Bitcoin crash: 90% down", "link": "a", "alarm": True},
                             {"t": int(time.time()), "source": "Test2", "title": "Exchange hacked", "link": "b", "alarm": True}], 7)
    sources.trump_posts = lambda: []
    sources.whales = lambda: {"updated": int(time.time()), "traders": 30, "coins": {"BTC": {"long": 5e6, "short": 1e6, "nb": 12, "bias": 0.667}}}
    run.time.sleep = lambda s: None

    # 1er tour : alarme -> pause
    run.main()
    st = json.loads(run.STATE.read_text())
    assert st["status"] == "en pause", st["status"]
    assert any(e["type"] == "pause" for e in st["events"])
    # on lève la pause et on fait tourner 90 tours
    for k in range(90):
        st = json.loads(run.STATE.read_text())
        st["pause_until"] = 0
        run.STATE.write_text(json.dumps(st))
        sources.news = lambda: ([], 7)
        clock["i"] = 200 + k
        run.main()
    st = json.loads(run.STATE.read_text())
    inv = sum(p["cost"] for p in st["positions"])
    assert abs(st["cash"] + sum(p["value"] for p in st["positions"]) - st["equity"]) < 0.05
    assert st["cash"] >= -1e-6 and len(st["positions"]) <= 3
    print(f"ok live : capital {st['equity']} €, {len(st['trades'])} ventes, {len(st['positions'])} positions, investi {inv:.2f} €")

    # arrêt d'urgence manuel
    cfg = json.loads((run.ROOT / "config.json").read_text())
    cfg["arret_urgence"] = True
    (run.ROOT / "config.json").write_text(json.dumps(cfg))
    run.main()
    st = json.loads(run.STATE.read_text())
    assert st["status"] == "arrêt d'urgence" and not st["positions"]
    cfg["arret_urgence"] = False
    (run.ROOT / "config.json").write_text(json.dumps(cfg))
    run.main()
    st = json.loads(run.STATE.read_text())
    assert st["status"] != "arrêt d'urgence"
    print("ok arrêt d'urgence (déclenché puis levé)")


if __name__ == "__main__":
    test_indicators()
    test_backtest()
    real_root = run.ROOT
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(real_root / "config.json", tmp / "config.json")
    run.ROOT, run.STATE, run.SCAN = tmp, tmp / "docs/data/state.json", tmp / "docs/data/scan.json"
    test_live(tmp)
    print("TOUS LES TESTS PASSENT")
