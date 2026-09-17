"""Build public quote snapshots; never replace missing prices with zero."""
import json
import math
import time
from pathlib import Path
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor

SYMBOLS = ("TSLA", "MSFT", "NVDA", "SPCX")
SITE = "https://william12304.github.io/stock-dashboard/quotes.json"


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def percent(price, base):
    return (price / base - 1) * 100 if number(price) and number(base) and base > 0 else None


def normalize(result, now):
    meta = result["meta"]
    price = meta.get("regularMarketPrice")
    stamp = meta.get("regularMarketTime")
    if not number(price) or price <= 0 or not number(stamp):
        raise ValueError("Missing regular quote")
    periods = meta.get("currentTradingPeriod", {})
    regular = periods.get("regular", {})
    previous = meta.get("previousClose", meta.get("chartPreviousClose"))
    change = meta.get("regularMarketChangePercent")
    if not number(change):
        change = percent(price, previous)
    quote = {"price": price, "changePercent": change, "time": stamp}
    output = {"symbol": meta["symbol"], "currency": meta.get("currency", "USD"),
              "regular": quote, "pre": None, "post": None, "fetchedAt": now,
              "status": "ok", "marketState": "closed"}
    for session in ("pre", "regular", "post"):
        period = periods.get(session, {})
        if period.get("start", 0) <= now < period.get("end", 0):
            output["marketState"] = session
    timestamps = result.get("timestamp", [])
    closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close", [])
    for session in ("pre", "post"):
        period = periods.get(session, {})
        points = [(t, p) for t, p in zip(timestamps, closes)
                  if number(t) and number(p) and p > 0
                  and period.get("start", 0) <= t < period.get("end", 0) and t <= now]
        if not points:
            continue
        timestamp, extended_price = max(points)
        # Before the opening bell, meta.regularMarketPrice is yesterday's close.
        # Once regular trading starts, previousClose is the premarket baseline.
        base = price if session == "post" or stamp < regular.get("start", 0) else previous
        output[session] = {"price": extended_price, "changePercent": percent(extended_price, base),
                           "time": timestamp}
    return output


def request_json(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def fetch(symbol):
    for host in ("query1", "query2"):
        try:
            data = request_json(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d&includePrePost=true")
            result = data["chart"]["result"][0]
            if result["meta"]["symbol"] != symbol:
                raise ValueError("Symbol mismatch")
            return symbol, normalize(result, int(time.time()))
        except Exception as error:
            print(f"{symbol}: {host} unavailable ({type(error).__name__})", flush=True)
    return symbol, None


def main():
    try:
        previous = request_json(SITE).get("quotes", {})
    except Exception:
        previous = {}
    quotes = {}
    successes = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for symbol, quote in pool.map(fetch, SYMBOLS):
            if quote:
                successes += 1
            else:
                quote = previous.get(symbol, {"symbol": symbol, "regular": None, "pre": None, "post": None})
                quote["status"] = "unavailable"
            quotes[symbol] = quote
    if not successes:
        raise SystemExit("All quote requests failed; preserve the previously deployed site.")
    output = {"generatedAt": int(time.time()), "source": "Yahoo Finance", "quotes": quotes}
    Path("quotes.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Updated {successes}/{len(SYMBOLS)} symbols")


if __name__ == "__main__":
    main()
