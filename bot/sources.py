"""Toutes les données extérieures, via des API publiques et gratuites (aucune clé).

- Prix : API publique Kraken
- Indice Peur & Avidité : alternative.me
- Actus : 7 flux RSS crypto (FR + EN)
- Posts de Trump : flux RSS public de Truth Social (trumpstruth.org)
- Baleines : meilleurs traders du classement Hyperliquid et leurs positions
"""
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

UA = {"User-Agent": "Mozilla/5.0 (IA-Trader simulation bot)"}
KRAKEN = "https://api.kraken.com/0/public"

NEWS_FEEDS = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Decrypt": "https://decrypt.co/feed",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/.rss/full/",
    "CryptoSlate": "https://cryptoslate.com/feed/",
    "Journal du Coin": "https://journalducoin.com/feed/",
    "Cryptoast": "https://cryptoast.fr/feed/",
}
TRUMP_FEED = "https://trumpstruth.org/feed"

# Noms Kraken -> noms courants
RENAME = {"XBT": "BTC", "XDG": "DOGE"}
EXCLUDE = {"USDT", "USDC", "DAI", "PYUSD", "EURT", "EURC", "EURR", "TUSD", "USDG", "RLUSD",
           "USDS", "USDE", "FDUSD", "USD", "GBP", "AUD", "CAD", "CHF", "JPY", "EUR", "PAXG", "XAUT"}

ALARM_WORDS = ["crash", "hack", "hacked", "exploit", "liquidat", "bankrupt", "collapse", "plunge",
               "sec sues", "ban ", "effondr", "piratage", "piraté", "faillite", "chute", "krach",
               "tariff", "droits de douane", "emergency", "urgence"]
TRUMP_WORDS = ["bitcoin", "crypto", "tariff", "fed", "rates", "dollar", "china", "taxe", "interest"]


def http_get(url, timeout=25, retries=3, data=None):
    last = None
    for k in range(retries):
        try:
            headers = dict(UA)
            body = None
            if data is not None:
                body = json.dumps(data).encode()
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # réseau capricieux : on réessaie
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def get_json(url, **kw):
    return json.loads(http_get(url, **kw))


# ---------------- Kraken ----------------

def kraken(path, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    d = get_json(f"{KRAKEN}/{path}" + (f"?{q}" if q else ""))
    if d.get("error"):
        raise RuntimeError(f"Kraken {path}: {d['error']}")
    return d["result"]


def eur_pairs():
    """Toutes les paires crypto/EUR actives sur Kraken."""
    out = []
    for key, p in kraken("AssetPairs").items():
        ws = p.get("wsname", "")
        if not ws.endswith("/EUR") or p.get("status", "online") != "online" or key.endswith(".d"):
            continue
        base = ws.split("/")[0]
        base = RENAME.get(base, base)
        if base in EXCLUDE or "." in base or (base.endswith("x") and base[:-1].isupper()):
            continue  # stablecoins, monnaies, actions tokenisées
        out.append({"pair": key, "coin": base})
    return out


def tickers(pairs):
    """Prix actuels + volume 24 h en EUR, par paquets."""
    out = {}
    for i in range(0, len(pairs), 40):
        chunk = pairs[i:i + 40]
        res = kraken("Ticker", pair=",".join(chunk))
        for k, t in res.items():
            price = float(t["c"][0])
            out[k] = {"price": price, "vol24_eur": float(t["v"][1]) * price}
        time.sleep(1.1)
    return out


def ohlc(pair, interval):
    """Bougies clôturées (la dernière, encore en cours, est retirée)."""
    res = kraken("OHLC", pair=pair, interval=interval)
    rows = next(v for k, v in res.items() if k != "last")
    candles = [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
                "c": float(r[4]), "v": float(r[6])} for r in rows]
    return candles[:-1]


# ---------------- Marché ----------------

FNG_FR = {"Extreme Fear": "peur extrême", "Fear": "peur", "Neutral": "neutre",
          "Greed": "avidité", "Extreme Greed": "avidité extrême"}


def fear_greed():
    d = get_json("https://api.alternative.me/fng/?limit=1")["data"][0]
    return {"value": int(d["value"]), "label": FNG_FR.get(d["value_classification"], d["value_classification"])}


def _parse_rss(raw, source, limit=15):
    items = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            ts = int(parsedate_to_datetime(pub).timestamp()) if pub else int(time.time())
        except Exception:
            ts = int(time.time())
        if not title:
            title = (it.findtext("description") or "").strip()[:200]
        items.append({"t": ts, "source": source, "title": title, "link": link})
        if len(items) >= limit:
            break
    return items


def news():
    items, ok = [], 0
    for name, url in NEWS_FEEDS.items():
        try:
            items += _parse_rss(http_get(url, retries=2), name)
            ok += 1
        except Exception:
            pass
    for it in items:
        low = it["title"].lower()
        it["alarm"] = any(w in low for w in ALARM_WORDS)
    items.sort(key=lambda x: -x["t"])
    return items, ok


def trump_posts():
    try:
        posts = _parse_rss(http_get(TRUMP_FEED, retries=2), "Truth Social", limit=10)
    except Exception:
        return []
    for p in posts:
        low = p["title"].lower()
        p["market"] = any(w in low for w in TRUMP_WORDS)
    return posts


# ---------------- Baleines (Hyperliquid) ----------------

def whales(top=30):
    """Positions agrégées des meilleurs traders du mois sur Hyperliquid."""
    lb = get_json("https://stats-data.hyperliquid.xyz/Mainnet/leaderboard", timeout=60)
    rows = []
    for r in lb.get("leaderboardRows", []):
        perf = dict(r.get("windowPerformances", []))
        month = perf.get("month", {})
        try:
            if float(r.get("accountValue", 0)) < 100_000:
                continue
            rows.append((float(month.get("pnl", 0)), r["ethAddress"]))
        except (TypeError, ValueError):
            continue
    rows.sort(reverse=True)
    coins = {}
    traders = 0
    for _, addr in rows[:top]:
        try:
            st = get_json("https://api.hyperliquid.xyz/info", data={"type": "clearinghouseState", "user": addr})
        except Exception:
            continue
        traders += 1
        for ap in st.get("assetPositions", []):
            p = ap.get("position", {})
            coin = p.get("coin")
            szi, val = float(p.get("szi", 0)), abs(float(p.get("positionValue", 0)))
            if not coin or szi == 0:
                continue
            c = coins.setdefault(coin, {"long": 0.0, "short": 0.0, "nb": 0})
            c["long" if szi > 0 else "short"] += val
            c["nb"] += 1
        time.sleep(0.2)
    for c in coins.values():
        tot = c["long"] + c["short"]
        c["bias"] = round((c["long"] - c["short"]) / tot, 3) if tot else 0
    return {"updated": int(time.time()), "traders": traders, "coins": coins}
