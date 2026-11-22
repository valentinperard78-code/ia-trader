"""Un « tour » du bot. GitHub Actions le lance toutes les 15 minutes.

1. lit le marché (actus, Trump, Peur & Avidité, baleines)
2. met à jour le portefeuille simulé avec les vrais prix Kraken
3. gère les positions (stop-loss, stop suiveur, signaux de sortie)
4. vérifie l'arrêt d'urgence
5. cherche de nouveaux achats sur les cryptos retenues par le scan
6. écrit tout dans docs/data/state.json pour le tableau de bord
"""
import json
import time
from pathlib import Path

from . import sources
from .indicators import compute_all
from .strategies import STRATEGIES, WARMUP

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "docs" / "data" / "state.json"
SCAN = ROOT / "docs" / "data" / "scan.json"

FALLBACK = [{"coin": "BTC", "pair": "XXBTZEUR", "strategy": "tendance"},
            {"coin": "ETH", "pair": "XETHZEUR", "strategy": "tendance"},
            {"coin": "SOL", "pair": "SOLEUR", "strategy": "tendance"}]


def eur(x):
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def px_fmt(x):
    d = 2 if x >= 1 else 6
    return f"{x:,.{d}f} €".replace(",", " ").replace(".", ",")


def new_state(cfg, now):
    b = float(cfg["budget_eur"])
    return {
        "started": now, "reset_id": cfg.get("reset_id"), "budget": b, "cash": b,
        "positions": [], "trades": [], "events": [], "equity_history": [[now, b]],
        "last_signal": {}, "market": {}, "pause_until": 0, "pause_reason": "",
        "emergency": False, "seen_alarms": [],
    }


def log(state, now, kind, text):
    state["events"].insert(0, {"t": now, "type": kind, "text": text})
    del state["events"][300:]
    print(f"[{kind}] {text}")


def equity_of(state, prices):
    return state["cash"] + sum(p["qty"] * prices.get(p["pair"], p["last_price"]) for p in state["positions"])


def sell(state, cfg, pos, price, now, reason):
    fee, slip = cfg["frais_pct"] / 100, cfg["glissement_pct"] / 100
    proceeds = pos["qty"] * price * (1 - slip) * (1 - fee)
    pnl = proceeds - pos["cost"]
    state["cash"] += proceeds
    state["positions"].remove(pos)
    state["trades"].insert(0, {
        "coin": pos["coin"], "strategy": pos["strategy"], "entry_time": pos["entry_time"], "exit_time": now,
        "entry_price": pos["entry_price"], "exit_price": price, "cost": round(pos["cost"], 2),
        "proceeds": round(proceeds, 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl / pos["cost"] * 100, 2),
        "reason": reason,
    })
    del state["trades"][200:]
    signe = "+" if pnl >= 0 else ""
    log(state, now, "vente", f"VENTE {pos['coin']} à {px_fmt(price)} ({reason}) : {signe}{eur(pnl)}")


def buy(state, cfg, coin, pair, strat, price, atr, amount, now, why):
    fee, slip = cfg["frais_pct"] / 100, cfg["glissement_pct"] / 100
    fill = price * (1 + slip)
    qty = amount * (1 - fee) / fill
    state["cash"] -= amount
    state["positions"].append({
        "coin": coin, "pair": pair, "strategy": strat.key, "qty": qty, "entry_price": fill,
        "entry_time": now, "cost": amount, "stop": fill - strat.stop_atr * atr, "high": fill,
        "atr": atr, "last_price": price,
    })
    log(state, now, "achat", f"ACHAT {coin} à {px_fmt(fill)} pour {eur(amount)} — {strat.label} ({why})")


def update_market(state, cfg, now):
    m = state.setdefault("market", {})
    try:
        m["fng"] = sources.fear_greed()
    except Exception as e:
        print("fng:", e)
    try:
        items, ok = sources.news()
        m["news"], m["news_sources_ok"] = items[:40], ok
    except Exception as e:
        print("news:", e)
    try:
        m["trump"] = sources.trump_posts()
    except Exception as e:
        print("trump:", e)
    if now - m.get("whales", {}).get("updated", 0) > 2 * 3600:
        try:
            m["whales"] = sources.whales()
        except Exception as e:
            print("whales:", e)

    # Alerte : plusieurs actus alarmantes récentes, ou post de Trump qui touche le marché
    seen = set(state.get("seen_alarms", []))
    fresh = [n for n in m.get("news", []) if n.get("alarm") and now - n["t"] < 3 * 3600 and n["link"] not in seen]
    trump_hot = [p for p in m.get("trump", []) if p.get("market") and now - p["t"] < 3600 and p["link"] not in seen]
    hours = cfg.get("pause_apres_alerte_heures", 2)
    reason = None
    if len(fresh) >= 2:
        reason = f"les actus s'affolent : « {fresh[0]['title'][:90]} » ({fresh[0]['source']})"
    elif trump_hot:
        reason = f"Trump vient de poster sur le marché : « {trump_hot[0]['title'][:90]} »"
    if reason:
        state["pause_until"] = now + hours * 3600
        state["pause_reason"] = reason
        log(state, now, "pause", f"Pause des achats pendant {hours} h — {reason}")
    state["seen_alarms"] = list(seen | {x["link"] for x in fresh + trump_hot})[-500:]


def candidates(cfg):
    if SCAN.exists():
        sel = json.loads(SCAN.read_text()).get("selected", [])
        if sel:
            return sel[: int(cfg.get("nb_candidats_suivis", 20))], True
    return FALLBACK, False


def main():
    now = int(time.time())
    cfg = json.loads((ROOT / "config.json").read_text())
    interval = int(cfg.get("unite_bougies_minutes", 240))

    state = json.loads(STATE.read_text()) if STATE.exists() else None
    if not state or state.get("reset_id") != cfg.get("reset_id"):
        state = new_state(cfg, now)
        log(state, now, "info", f"Jour 0 : le bot démarre avec {eur(state['budget'])}. Objectif : {eur(cfg['objectif_eur'])}.")

    update_market(state, cfg, now)

    cands, from_scan = candidates(cfg)
    if not from_scan:
        print("Pas encore de scan : suivi de BTC, ETH et SOL en attendant.")
    held = {p["pair"] for p in state["positions"]}
    pairs = sorted(held | {c["pair"] for c in cands})
    prices = {k: v["price"] for k, v in sources.tickers(pairs).items()}
    # Kraken renvoie parfois un autre nom de paire : on retombe sur le dernier prix connu
    for p in state["positions"]:
        if p["pair"] in prices:
            p["last_price"] = prices[p["pair"]]

    # ---- Gestion des positions ouvertes ----
    for pos in list(state["positions"]):
        price = prices.get(pos["pair"])
        if price is None:
            continue
        strat = STRATEGIES[pos["strategy"]]
        pos["high"] = max(pos["high"], price)
        pos["stop"] = max(pos["stop"], pos["high"] - strat.trail_atr * pos["atr"])
        if price <= pos["stop"]:
            gain = price >= pos["entry_price"]
            sell(state, cfg, pos, price, now, "stop suiveur, gain sécurisé" if gain else "stop-loss")
            continue
        try:
            ind = compute_all(sources.ohlc(pos["pair"], interval))
            time.sleep(1.1)
            if strat.exit(ind, len(ind["c"]) - 1):
                sell(state, cfg, pos, price, now, "le mouvement s'essouffle")
        except Exception as e:
            print("ohlc", pos["coin"], e)

    # ---- Arrêt d'urgence ----
    eq = equity_of(state, prices)
    limit = state["budget"] * (1 - cfg["perte_max_avant_arret_pct"] / 100)
    if cfg.get("arret_urgence") or eq <= limit:
        if not state["emergency"]:
            why = "demandé à la main" if cfg.get("arret_urgence") else f"capital sous {eur(limit)}"
            for pos in list(state["positions"]):
                sell(state, cfg, pos, prices.get(pos["pair"], pos["last_price"]), now, "arrêt d'urgence")
            state["emergency"] = True
            state["emergency_manual"] = bool(cfg.get("arret_urgence"))
            log(state, now, "urgence", f"ARRÊT D'URGENCE ({why}) : tout est vendu, le bot ne trade plus.")
    elif state["emergency"] and state.get("emergency_manual"):
        # arrêt manuel levé dans config.json -> le bot repart
        state["emergency"] = False
        state["emergency_manual"] = False
        log(state, now, "info", "Arrêt d'urgence levé : le bot reprend.")
    # un arrêt automatique (trop de pertes) reste actif jusqu'à un nouveau reset_id

    # ---- Nouveaux achats ----
    paused = state["pause_until"] > now or cfg.get("pause_manuelle")
    slots = int(cfg["positions_max"]) - len(state["positions"])
    whales = state["market"].get("whales", {}).get("coins", {})
    if not state["emergency"] and not paused and slots > 0:
        eq = equity_of(state, prices)
        for c in cands:
            if slots <= 0:
                break
            if c["pair"] in {p["pair"] for p in state["positions"]} or c["pair"] not in prices:
                continue
            strat = STRATEGIES[c["strategy"]]
            try:
                candles = sources.ohlc(c["pair"], interval)
                time.sleep(1.1)
            except Exception as e:
                print("ohlc", c["coin"], e)
                continue
            if len(candles) <= WARMUP:
                continue
            ind = compute_all(candles)
            i = len(candles) - 1
            if candles[i]["t"] <= state["last_signal"].get(c["coin"], 0):
                continue
            if not strat.entry(ind, i):
                continue
            state["last_signal"][c["coin"]] = candles[i]["t"]
            w = whales.get(c["coin"])
            if w and w["bias"] < -0.5:
                log(state, now, "info", f"Signal sur {c['coin']} ignoré : les baleines sont massivement vendeuses ({int(-w['bias']*100)} %).")
                continue
            amount = min(state["cash"], eq / int(cfg["positions_max"]))
            if amount < cfg["ordre_min_eur"]:
                break
            why = "baleines acheteuses" if w and w["bias"] > 0.3 else "signal technique"
            buy(state, cfg, c["coin"], c["pair"], strat, prices[c["pair"]], ind["atr"][i], amount, now, why)
            slots -= 1

    # ---- Sauvegarde ----
    eq = equity_of(state, prices)
    state["equity_history"].append([now, round(eq, 2)])
    del state["equity_history"][:-6000]
    status = "arrêt d'urgence" if state["emergency"] else ("en pause" if paused else "en marche")
    for p in state["positions"]:
        p["value"] = round(p["qty"] * p["last_price"], 2)
        p["pnl"] = round(p["value"] - p["cost"], 2)
        p["pnl_pct"] = round(p["pnl"] / p["cost"] * 100, 2)
    day = int((now - state["started"]) // 86400)
    state.update({
        "updated_at": now, "equity": round(eq, 2), "pnl": round(eq - state["budget"], 2),
        "pnl_pct": round((eq / state["budget"] - 1) * 100, 2), "status": status, "day": day,
        "config": {k: cfg.get(k) for k in ("nom_du_bot", "mode", "budget_eur", "objectif_eur", "positions_max",
                                            "perte_max_avant_arret_pct", "github_repo", "frais_pct")},
        "watching": [{"coin": c["coin"], "strategy": c["strategy"]} for c in cands],
    })
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False))
    print(f"Capital : {eur(eq)} | statut : {status} | positions : {len(state['positions'])}")


if __name__ == "__main__":
    main()
