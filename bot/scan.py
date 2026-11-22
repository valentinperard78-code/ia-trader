"""Le grand scan : teste les 2 stratégies sur toutes les cryptos en euros de Kraken.

- 2 ans d'historique en bougies journalières (robustesse)
- ~4 mois en bougies de 4 h (le rythme réel du bot)
Une crypto n'est retenue que si une stratégie gagne sur les deux.
Lancé chaque dimanche par GitHub Actions (ou à la main).
"""
import json
import time
from pathlib import Path

from . import sources, backtest
from .strategies import STRATEGIES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "scan.json"
MIN_VOL_EUR = 50_000


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    interval = int(cfg.get("unite_bougies_minutes", 240))
    fee = cfg["frais_pct"] / 100
    slip = cfg["glissement_pct"] / 100

    pairs = sources.eur_pairs()
    print(f"{len(pairs)} paires crypto/EUR trouvées")
    tick = sources.tickers([p["pair"] for p in pairs])
    results, scanned = [], 0
    for p in pairs:
        t = tick.get(p["pair"])
        vol = t["vol24_eur"] if t else 0
        rec = {"coin": p["coin"], "pair": p["pair"], "vol24_eur": round(vol)}
        if vol < MIN_VOL_EUR:
            rec["skip"] = "volume trop faible"
            results.append(rec)
            continue
        try:
            daily = sources.ohlc(p["pair"], 1440)
            time.sleep(1.1)
            recent = sources.ohlc(p["pair"], interval)
            time.sleep(1.1)
        except Exception as e:
            rec["skip"] = f"erreur données: {e}"
            results.append(rec)
            continue
        scanned += 1
        rec["days"] = len(daily)
        best = None
        for key, strat in STRATEGIES.items():
            lr = backtest.run(daily, strat, fee, slip)
            sr = backtest.run(recent, strat, fee, slip)
            sc = backtest.score(lr, sr)
            rec[key] = {"2ans": lr, "recent": sr, "score": sc}
            if sc is not None and (best is None or sc > best[1]):
                best = (key, sc)
        if best:
            rec["strategy"], rec["score"] = best
        results.append(rec)
        print(f"  {p['coin']:>8}  {best}")

    selected = sorted([r for r in results if r.get("score")], key=lambda r: -r["score"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": int(time.time()),
        "total_pairs": len(pairs),
        "scanned": scanned,
        "selected": [{"coin": r["coin"], "pair": r["pair"], "strategy": r["strategy"], "score": r["score"],
                      "detail": r[r["strategy"]]} for r in selected],
        "all": results,
    }, ensure_ascii=False))
    print(f"Scan terminé : {scanned} cryptos analysées, {len(selected)} retenues")


if __name__ == "__main__":
    main()
