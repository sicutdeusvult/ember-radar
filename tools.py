"""Tool handlers: ``(args: dict, **kwargs) -> str`` (a JSON string), never raising.

Every handler shapes Ember's rows into something a model reads in one pass: formatted dollars and percents,
ages instead of timestamps, the module in words, and the page URL so the user can be sent to the coin.
"""

from __future__ import annotations

import json
import time
from typing import Any

from . import fmt, watch
from .api import DEFAULT_SITE, EmberApi, EmberError

_api = EmberApi(DEFAULT_SITE)
_settings: dict[str, Any] = {"pulse": True, "pulse_min_move_pct": 15.0, "pulse_cooldown_min": 30}


def configure(site: str | None = None, **settings: Any) -> None:
    """Called from register(): the Ember site to read and the pulse settings."""
    global _api
    if site and EmberApi(site).site != _api.site:
        _api = EmberApi(site)
    for k, v in settings.items():
        if v is not None:
            _settings[k] = v


def api() -> EmberApi:
    return _api


def setting(key: str, default: Any = None) -> Any:
    return _settings.get(key, default)


def _ok(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _err(message: str, **extra: Any) -> str:
    return json.dumps({"error": message, **extra}, ensure_ascii=False)


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _guard(fn):
    """Every handler: catch everything, answer JSON."""

    def wrapped(args: dict | None = None, **kwargs: Any) -> str:
        try:
            return fn(dict(args or {}), **kwargs)
        except EmberError as e:
            return _err(str(e), site=_api.site)
        except Exception as e:  # noqa: BLE001 — a handler must never raise into the agent loop
            return _err(f"ember-radar failed: {type(e).__name__}: {e}")

    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


# ------------------------------------------------------------------------------------------------ shaping
def _trend(r: dict) -> float | None:
    t = r.get("trendPct")
    if t is None:
        return fmt.trend_from_spark(r.get("spark"))
    return fmt.num(t)


def _module_words(r: dict) -> dict:
    m = r.get("module") or {}
    mode = str(r.get("mode") or m.get("mode") or "")
    out = {"mode": mode, "what": fmt.mode_label(mode)}
    if m.get("intervalMin"):
        out["every"] = f"{int(fmt.num(m['intervalMin']))}m"
    if fmt.num(m.get("rounds")):
        out["rounds_paid"] = int(fmt.num(m["rounds"]))
    if m.get("lastRunAt"):
        out["last_run"] = fmt.ago(m["lastRunAt"])
    if m.get("nextRunAt"):
        out["next_run"] = fmt.in_(m["nextRunAt"])
    if fmt.num(m.get("lastRecipients")):
        out["last_recipients"] = int(fmt.num(m["lastRecipients"]))
    if fmt.num(m.get("emptyRounds")):
        out["empty_rounds"] = int(fmt.num(m["emptyRounds"]))
    if r.get("holdersBps") is not None and mode == "holders":
        out["share_to_holders"] = f"{fmt.num(r['holdersBps']) / 100:.0f}% of the creator side"
    if r.get("dipPct"):
        out["buys_below_24h_high_by"] = f"{fmt.num(r['dipPct']):.0f}%"
    if r.get("fomo"):
        f = r["fomo"] if isinstance(r["fomo"], dict) else {}
        if f.get("handle"):
            out["trader"] = f"@{f['handle']}"
        if r.get("fomoFlame"):
            out["flame"] = r["fomoFlame"]
    if r.get("basketAssets"):
        out["basket"] = r["basketAssets"]
    return out


def brief(r: dict, now: float | None = None) -> dict:
    """One line of a list."""
    now = now or time.time()
    d = {
        "name": r.get("name"),
        "symbol": r.get("symbol"),
        "mint": r.get("mint"),
        "pair": r.get("quoteTicker"),
        "price": fmt.usd(r.get("priceUsd")),
        "mcap": fmt.usd(r.get("marketCapUsd")),
        "change_24h": fmt.pct(_trend(r)),
        "volume_24h": fmt.usd(r.get("volume24hUsd")),
        "fees_24h": fmt.usd(r.get("fees24hUsd")),
        "trades_24h": int(fmt.num(r.get("trades24h", r.get("trades")))),
        "holders": int(fmt.num(r.get("holders"))),
        "fees_go_to": fmt.mode_label(r.get("mode")),
        "age": fmt.age(r.get("createdAt"), now),
        "url": _api.coin_url(r),
    }
    if r.get("graduated"):
        d["curve"] = "graduated"
    elif fmt.num(r.get("progress")) >= 0.999:
        d["curve"] = "100% — graduating"
    else:
        d["curve"] = f"{fmt.num(r.get('progress')) * 100:.0f}% to graduation"
    if r.get("curated"):
        d["curated"] = True
    if r.get("featured"):
        d["featured"] = True
    return d


def full(r: dict, economics: dict | None = None, now: float | None = None) -> dict:
    now = now or time.time()
    d = brief(r, now)
    spark = r.get("spark") if isinstance(r.get("spark"), list) else []
    pts = [fmt.num(x) for x in spark if fmt.num(x) > 0]
    d.update(
        {
            "pool": r.get("pool"),
            "pair_mint": r.get("quoteMint"),
            "pair_price": fmt.usd(r.get("quoteUsd")),
            "price_in_pair": fmt.qty(fmt.num(r.get("priceUsd")) / fmt.num(r.get("quoteUsd")), r.get("quoteTicker")) if fmt.num(r.get("quoteUsd")) > 0 else None,
            "price_usd_raw": fmt.num(r.get("priceUsd")),
            "mcap_usd_raw": fmt.num(r.get("marketCapUsd")),
            "tax": f"{fmt.num(r.get('feeBps')) / 100:g}% per trade",
            "graduation_cap": fmt.usd(r.get("graduateUsd")),
            "pair_in_pool": fmt.qty(r.get("quoteReserve"), r.get("quoteTicker"))
            + (f" of {fmt.qty(r.get('migrationThreshold'))} to graduate" if not r.get("graduated") and r.get("migrationThreshold") else ""),
            "trades_total": int(fmt.num(r.get("tradesTotal", r.get("trades")))),
            "last_trade": (f"{r.get('lastTradeSide')} {fmt.ago(r.get('lastTradeAt'), now)}" if r.get("lastTradeAt") else None),
            "high_24h": fmt.usd(max(pts)) if pts else None,
            "low_24h": fmt.usd(min(pts)) if pts else None,
            "module": _module_words(r),
            "created": fmt.ago(r.get("createdAt"), now),
            "creator": r.get("creator"),
            "description": r.get("description") or None,
            "links": {k: v for k, v in (r.get("links") or {}).items() if v} or None,
            "image": r.get("image") or None,
        }
    )
    if r.get("curatedNote"):
        d["curated_note"] = r["curatedNote"]
    at = r.get("allTime") or {}
    if at:
        d["all_time"] = {
            k: v
            for k, v in {
                "fees": fmt.usd(at.get("feesUsd")),
                "paid_out": fmt.usd(at.get("paidUsd")),
                "volume": fmt.usd(at.get("volumeUsd")),
                "rounds": int(fmt.num(at.get("rounds"))),
                "by_kind": {k: fmt.usd(v) for k, v in (at.get("byKindUsd") or {}).items() if fmt.num(v) > 0} or None,
            }.items()
            if v is not None
        }
    if r.get("airdropPct"):
        d["airdrop"] = f"{fmt.num(r['airdropPct']):g}% of supply"
    if r.get("shield"):
        d["shield"] = r["shield"]
    if r.get("gravity"):
        d["gravity"] = r["gravity"]
    if r.get("splits"):
        d["fee_splits"] = r["splits"]
    if economics:
        share = (economics.get("shareByMode") or {}).get(str(r.get("mode") or ""), {})
        split = economics.get("feeSplit") or {}
        if share or split:
            d["fee_split"] = {
                "of_each_trade_tax": {
                    "meteora": f"{fmt.num(split.get('meteoraPct')):g}%" if split else None,
                    "creator_or_module": f"{fmt.num(share.get('pctOfTax')):g}%" if share else (f"{fmt.num(split.get('creatorPct')):g}%" if split else None),
                    "platform": f"{fmt.num(split.get('platformPct')):g}%" if split else None,
                },
            }
            if economics.get("cashback", {}).get("enabled"):
                d["fee_split"]["trader_cashback"] = f"{fmt.num(economics['cashback'].get('shareOfTax')) * 100:g}% of the tax back to the trader"
    return {k: v for k, v in d.items() if v is not None}


def totals_line(data: dict, rows: list[dict]) -> dict:
    t = data.get("totals") or {}
    graduated = sum(1 for r in rows if r.get("graduated"))
    return {
        "coins": len(rows),
        "graduated": graduated,
        "on_the_curve": len(rows) - graduated,
        "volume_24h": fmt.usd(sum(fmt.num(r.get("volume24hUsd")) for r in rows)),
        "fees_24h": fmt.usd(sum(fmt.num(r.get("fees24hUsd")) for r in rows)),
        "paid_out_all_time": fmt.usd(t.get("paidUsd")),
        "paid_by_kind": {k: fmt.usd(v) for k, v in (t.get("byKindUsd") or {}).items() if fmt.num(v) > 0} or None,
        "payout_rounds": {k: int(fmt.num(v)) for k, v in (t.get("rounds") or {}).items() if fmt.num(v) > 0} or None,
        "wallets_paid": int(fmt.num(t.get("recipients"))) or None,
        "lotto_winners": int(fmt.num(t.get("winners"))) or None,
        "tokens_burned": fmt.count(t.get("burnedTokens")) if fmt.num(t.get("burnedTokens")) else None,
        "since": fmt.ago(t.get("since")) if t.get("since") else None,
        "site": _api.site,
    }


# ------------------------------------------------------------------------------------------------ sorts and filters
_SORTS = {
    "trending": lambda r: (fmt.num(r.get("volume24hUsd")) * (1.25 if time.time() - fmt.num(r.get("createdAt")) < 86400 else 1.0), fmt.num(r.get("trades24h"))),
    "new": lambda r: fmt.num(r.get("createdAt")),
    "oldest": lambda r: -fmt.num(r.get("createdAt")),
    "graduating": lambda r: fmt.num(r.get("progress")),
    "movers": lambda r: _trend(r) if _trend(r) is not None else -1e9,
    "volume": lambda r: fmt.num(r.get("volume24hUsd")),
    "mcap": lambda r: fmt.num(r.get("marketCapUsd")),
    "fees": lambda r: fmt.num(r.get("fees24hUsd")),
    "holders": lambda r: fmt.num(r.get("holders")),
}


def _is_stock_pair(r: dict, qmap: dict) -> bool:
    """The quote list says so; without it, the tickers tokenized stocks carry (NVDAx, SPCXpre)."""
    g = (qmap.get(r.get("quoteMint")) or {}).get("group")
    if g:
        return g == "stocks"
    t = str(r.get("quoteTicker") or "")
    return t.upper() not in ("USDC", "SOL") and t.lower().endswith(("x", "pre"))


def _is_crypto_pair(r: dict, qmap: dict) -> bool:
    g = (qmap.get(r.get("quoteMint")) or {}).get("group")
    if g:
        return g in ("crypto", "base")
    return str(r.get("quoteTicker") or "").upper() in ("SOL", "USDC") or not _is_stock_pair(r, qmap)


_GROUPS = {"stocks": _is_stock_pair, "crypto": _is_crypto_pair}


def _quote_map() -> dict:
    try:
        return {q.get("mint"): q for q in (_api.quotes().get("quotes") or [])}
    except Exception:
        return {}


def select(rows: list[dict], *, sort: str = "trending", pair: str = "", mode: str = "", graduated: bool | None = None, query: str = "", limit: int = 10) -> list[dict]:
    out = rows
    if pair:
        p = pair.strip().lower()
        if p in _GROUPS:
            qmap = _quote_map()
            out = [r for r in out if _GROUPS[p](r, qmap)]
        else:
            out = [r for r in out if str(r.get("quoteTicker", "")).lower() == p or str(r.get("quoteMint", "")) == pair.strip()]
    if mode:
        m = mode.strip().lower()
        out = [r for r in out if str(r.get("mode", "")).lower() == m]
    if graduated is not None:
        out = [r for r in out if bool(r.get("graduated")) == bool(graduated)]
    if query:
        q = query.strip().lstrip("$").lower()
        out = [r for r in out if q in str(r.get("name", "")).lower() or q in str(r.get("symbol", "")).lower()]
    key = _SORTS.get((sort or "trending").lower(), _SORTS["trending"])
    if (sort or "").lower() == "graduating":
        out = [r for r in out if not r.get("graduated")]
    out = sorted(out, key=key, reverse=True)
    return out[:limit]


# ------------------------------------------------------------------------------------------------ handlers
@_guard
def ember_markets(args: dict, **_: Any) -> str:
    data = _api.markets()
    rows = data["markets"]
    limit = _int(args.get("limit"), 10, 1, 25)
    graduated = args.get("graduated")
    if isinstance(graduated, str):
        graduated = {"true": True, "false": False}.get(graduated.lower())
    picked = select(
        rows,
        sort=str(args.get("sort") or "trending"),
        pair=str(args.get("pair") or ""),
        mode=str(args.get("mode") or ""),
        graduated=graduated if isinstance(graduated, bool) else None,
        query=str(args.get("query") or ""),
        limit=limit,
    )
    now = time.time()
    return _ok(
        venue=totals_line(data, rows),
        sort=str(args.get("sort") or "trending"),
        matched=len(picked),
        coins=[brief(r, now) for r in picked],
        warming=bool(data.get("warming")) or None,
        hint="ember_coin gives one coin's whole card; ember_watch adds one to the watchlist.",
    )


def _coin(args: dict, rows: list[dict] | None = None) -> dict | None:
    ref = str(args.get("coin") or args.get("mint") or args.get("symbol") or "").strip()
    if not ref:
        return None
    return _api.resolve(ref, rows)


@_guard
def ember_coin(args: dict, **_: Any) -> str:
    data = _api.markets()
    r = _coin(args, data["markets"])
    if not r:
        return _err(f"No coin on {_api.site} matches {args.get('coin')!r}. ember_markets with query= finds coins by name.")
    return _ok(coin=full(r, data.get("economics")))


@_guard
def ember_holders(args: dict, **_: Any) -> str:
    r = _coin(args)
    if not r:
        return _err(f"No coin matches {args.get('coin')!r}.")
    page = _int(args.get("page"), 0, 0, 500)
    h = _api.holders(r["mint"], page)
    holders = h.get("holders") or []
    top = [
        {
            "rank": x.get("rank"),
            "wallet": x.get("owner"),
            "share": fmt.pct(fmt.num(x.get("share")) * 100, signed=False, digits=2),
            "tokens": fmt.count(x.get("amount")),
            **({"tag": x["tag"]} if x.get("tag") else {}),
        }
        for x in holders
    ]
    top10 = sum(fmt.num(x.get("share")) for x in holders[:10]) * 100 if page == 0 else None
    return _ok(
        coin={"name": r.get("name"), "symbol": r.get("symbol"), "mint": r.get("mint"), "url": _api.coin_url(r)},
        holders_total=int(fmt.num(h.get("total"))),
        exact_count=bool(h.get("exact")),
        page=page,
        pages=int(fmt.num(h.get("pages"))),
        top10_share=(fmt.pct(top10, signed=False) if top10 is not None else None),
        concentration=(None if top10 is None else ("high" if top10 >= 40 else "moderate" if top10 >= 20 else "spread out")),
        holders=top,
        as_of=fmt.ago(h.get("at")),
        note="Pool, DEX and lending vaults are program accounts and are not listed as holders.",
    )


@_guard
def ember_trades(args: dict, **_: Any) -> str:
    r = _coin(args)
    if not r:
        return _err(f"No coin matches {args.get('coin')!r}.")
    limit = _int(args.get("limit"), 25, 1, 100)
    t = _api.trades(r["pool"], limit)
    trades = (t.get("trades") or [])[:limit]
    q_usd = fmt.num(r.get("quoteUsd"))
    now = time.time()
    rows = []
    buys = sells = 0.0
    nb = ns = 0
    for x in trades:
        usd = fmt.num(x.get("quoteAmount")) * q_usd
        side = str(x.get("side") or "")
        if side == "buy":
            buys += usd
            nb += 1
        elif side == "sell":
            sells += usd
            ns += 1
        base = fmt.num(x.get("baseAmount"))
        price = (fmt.num(x.get("quoteAmount")) / base * q_usd) if base > 0 else None
        rows.append(
            {
                "side": side,
                "usd": fmt.usd(usd),
                "tokens": fmt.count(base),
                "price": fmt.usd(price) if price else None,
                "wallet": fmt.short(x.get("trader")),
                "when": fmt.ago(x.get("timestamp"), now),
                "tx": x.get("signature"),
            }
        )
    span = (fmt.num(trades[0].get("timestamp")) - fmt.num(trades[-1].get("timestamp"))) if len(trades) > 1 else 0
    return _ok(
        coin={"name": r.get("name"), "symbol": r.get("symbol"), "pair": r.get("quoteTicker"), "url": _api.coin_url(r)},
        window=(f"last {len(trades)} trades over {fmt.age(now - span, now)}" if span > 0 else f"last {len(trades)} trades"),
        buys={"count": nb, "usd": fmt.usd(buys)},
        sells={"count": ns, "usd": fmt.usd(sells)},
        net_flow=fmt.usd(buys - sells),
        trades=rows,
        empty_note=(None if trades else "No trades recorded yet for this coin on the venue's tape."),
    )


@_guard
def ember_fees(args: dict, **_: Any) -> str:
    r = _coin(args)
    if not r:
        return _err(f"No coin matches {args.get('coin')!r}.")
    limit = _int(args.get("limit"), 10, 1, 50)
    f = _api.fees(r["pool"])
    q_usd = fmt.num(f.get("quoteUsd") or r.get("quoteUsd"))
    tick = f.get("quoteTicker") or r.get("quoteTicker")
    now = time.time()
    pays = []
    for p in (f.get("payouts") or [])[:limit]:
        amt = fmt.num(p.get("amount"))
        row = {"kind": p.get("kind") or p.get("mode"), "when": fmt.ago(p.get("at"), now), "amount": fmt.qty(amt, tick), "usd": fmt.usd(amt * q_usd)}
        if p.get("recipients"):
            row["recipients"] = int(fmt.num(p["recipients"]))
        if p.get("burned"):
            row["tokens_burned"] = fmt.count(p["burned"])
        if p.get("round") is not None:
            row["round"] = p["round"]
        if p.get("winner") or p.get("winners"):
            row["winners"] = p.get("winners") or p.get("winner")
        if p.get("signature"):
            row["tx"] = p["signature"]
        pays.append(row)
    return _ok(
        coin={"name": r.get("name"), "symbol": r.get("symbol"), "pair": tick, "fees_go_to": fmt.mode_label(r.get("mode")), "url": _api.coin_url(r)},
        tax=f"{fmt.num(f.get('taxBps') or r.get('feeBps')) / 100:g}% per trade",
        accrued_unclaimed={
            "amount": fmt.qty(f.get("platformAccrued"), tick),
            "usd": fmt.usd(f.get("platformAccruedUsd") if f.get("platformAccruedUsd") is not None else fmt.num(f.get("platformAccrued")) * q_usd),
        },
        claimed_so_far=fmt.qty(f.get("claimedByPlatform"), tick),
        creator={
            "paid": fmt.usd(f.get("paidToCreatorUsd") if f.get("paidToCreatorUsd") is not None else fmt.num(f.get("paidToCreator")) * q_usd),
            "pending": fmt.usd(f.get("creatorPendingFromPlatformUsd") if f.get("creatorPendingFromPlatformUsd") is not None else fmt.num(f.get("creatorPendingFromPlatform")) * q_usd),
            "wallet": f.get("creator") or r.get("creator"),
        },
        module=_module_words(r),
        mode_stats=f.get("modeStats") or None,
        recent_payouts=pays,
        payouts_listed=len(pays),
    )


_KIND_WORDS = {
    "holders": "holder payout",
    "burn": "buyback & burn",
    "lotto": "lotto draw",
    "bounty": "bounty",
    "dip": "dip buy",
    "launch": "launch",
    "buy": "buy",
    "sell": "sell",
    "graduate": "graduation",
    "payout": "payout",
    "perp": "perp",
}


@_guard
def ember_feed(args: dict, **_: Any) -> str:
    events = _api.feed()
    kind = str(args.get("kind") or "").strip().lower()
    minutes = _int(args.get("minutes"), 0, 0, 100000) if args.get("minutes") is not None else 0
    limit = _int(args.get("limit"), 30, 1, 100)
    now = time.time()
    coin_ref = str(args.get("coin") or "").strip()
    mint = None
    if coin_ref:
        r = _api.resolve(coin_ref)
        if not r:
            return _err(f"No coin matches {coin_ref!r}.")
        mint = r.get("mint")
    out = []
    for e in sorted(events, key=lambda e: fmt.num(e.get("at")), reverse=True):
        if kind and str(e.get("kind", "")).lower() != kind:
            continue
        if mint and e.get("mint") != mint:
            continue
        if minutes and now - fmt.num(e.get("at")) > minutes * 60:
            continue
        out.append(
            {
                "when": fmt.ago(e.get("at"), now),
                "kind": e.get("kind"),
                "what": _KIND_WORDS.get(str(e.get("kind")), e.get("kind")),
                "coin": e.get("symbol"),
                "usd": fmt.usd(e.get("usd")) if e.get("usd") else None,
                "text": e.get("text"),
                "wallet": fmt.short(e.get("wallet")) if e.get("wallet") else None,
                "mint": e.get("mint"),
                "url": (_api.site + e["route"]) if e.get("route") else None,
            }
        )
        if len(out) >= limit:
            break
    kinds: dict[str, int] = {}
    for e in events:
        kinds[str(e.get("kind"))] = kinds.get(str(e.get("kind")), 0) + 1
    return _ok(
        site=_api.site,
        events=[{k: v for k, v in x.items() if v is not None} for x in out],
        matched=len(out),
        tape_size=len(events),
        kinds_on_tape=kinds,
        note=(None if events else "The tape is empty right now."),
    )


@_guard
def ember_fomo_board(args: dict, **_: Any) -> str:
    b = _api.fomo_board()
    limit = _int(args.get("limit"), 10, 1, 50)
    traders = []
    for t in (b.get("traders") or [])[:limit]:
        coins = []
        for c in t.get("coins") or []:
            coins.append(
                {
                    "symbol": c.get("symbol"),
                    "name": c.get("name"),
                    "mint": c.get("mint"),
                    "mcap": fmt.usd(c.get("marketCapUsd")),
                    "paid_to_trader": fmt.usd(c.get("paidUsd")),
                    "paid_24h": fmt.usd(c.get("paid24hUsd")),
                    "graduated": bool(c.get("graduated")) or None,
                    "flame": c.get("flame") or c.get("fomoFlame") or None,
                    "url": (_api.site + c["route"]) if c.get("route") else None,
                }
            )
        traders.append(
            {
                "handle": t.get("handle"),
                "name": t.get("name"),
                "x": t.get("x"),
                "followers": fmt.count(t.get("followers")) if t.get("followers") else None,
                "clan": t.get("clan"),
                "pnl": fmt.usd(t.get("pnl")) if t.get("pnl") is not None else None,
                "wallet": t.get("wallet"),
                "paid_all_time": fmt.usd(t.get("paidUsd")),
                "paid_24h": fmt.usd(t.get("paid24hUsd")),
                "coins": [{k: v for k, v in c.items() if v is not None} for c in coins],
            }
        )
    tot = b.get("totals") or {}
    return _ok(
        paused=bool(b.get("paused")) or None,
        totals={
            "coins": int(fmt.num(tot.get("coins"))),
            "traders": int(fmt.num(tot.get("traders"))),
            "graduated": int(fmt.num(tot.get("graduated"))),
            "paid_to_traders_all_time": fmt.usd(tot.get("paidUsd")),
            "paid_24h": fmt.usd(tot.get("paid24hUsd")),
            "volume_24h": fmt.usd(tot.get("volume24hUsd")),
            "market_cap": fmt.usd(tot.get("marketCapUsd")),
            "holders": int(fmt.num(tot.get("holders"))),
        },
        trader_share=(f"{fmt.num(b.get('shareBps')) / 100:g}% of the creator side goes to the trader" if b.get("shareBps") else None),
        traders=[{k: v for k, v in t.items() if v is not None} for t in traders],
        as_of=fmt.ago(b.get("computedAt")),
        board_url=_api.site + "/fomo",
    )


@_guard
def ember_pairs(args: dict, **_: Any) -> str:
    q = _api.quotes()
    quotes = q.get("quotes") or []
    group = str(args.get("group") or "all").lower()
    query = str(args.get("query") or "").strip().lower()
    limit = _int(args.get("limit"), 40, 1, 200)
    rows = []
    for x in quotes:
        if x.get("enabled") is False:
            continue
        if group != "all" and str(x.get("group", "")).lower() != group:
            continue
        if query and not any(query in str(x.get(k, "")).lower() for k in ("ticker", "name", "provider", "mint")):
            continue
        rows.append(
            {
                "ticker": x.get("ticker"),
                "name": x.get("name"),
                "group": x.get("group"),
                "provider": x.get("provider"),
                "price": fmt.usd(x.get("usdPrice")) if x.get("usdPrice") else None,
                "mint": x.get("mint"),
            }
        )
    groups: dict[str, int] = {}
    for x in quotes:
        if x.get("enabled") is not False:
            groups[str(x.get("group"))] = groups.get(str(x.get("group")), 0) + 1
    e = q.get("economics") or {}
    econ = {
        "fee_tiers": [f"{fmt.num(m.get('bps')) / 100:g}%" + (" (default)" if m.get("default") else "") for m in e.get("feeModes") or []] or None,
        "graduation_caps": [fmt.usd(v) for v in e.get("graduateOptions") or []] or None,
        "opening_cap": fmt.usd(e.get("openUsd")) if e.get("openUsd") else None,
        "supply": fmt.count(e.get("totalSupply")) if e.get("totalSupply") else None,
        "fee_split": (
            {
                "meteora": f"{fmt.num(e['feeSplit'].get('meteoraPct')):g}%",
                "creator_or_module": f"{fmt.num(e['feeSplit'].get('creatorPct')):g}%",
                "platform": f"{fmt.num(e['feeSplit'].get('platformPct')):g}%",
            }
            if e.get("feeSplit")
            else None
        ),
        "modules": (({k: v.get("blurb") for k, v in ((e.get("modes") or {}).get("list") or {}).items()} or None) if not query else None),
    }
    return _ok(
        site=_api.site,
        pairs_total=sum(groups.values()),
        by_group=groups,
        matched=len(rows),
        pairs=[{k: v for k, v in r.items() if v is not None} for r in rows[:limit]],
        launch_economics={k: v for k, v in econ.items() if v is not None},
        launch_url=_api.site + "/launch",
    )


@_guard
def ember_watch(args: dict, **_: Any) -> str:
    action = str(args.get("action") or "list").lower()
    if action == "clear":
        return _ok(cleared=watch.clear(), watching=[])
    if action in ("add", "remove"):
        ref = str(args.get("coin") or "").strip()
        if not ref:
            return _err("Which coin? Give its symbol, name or mint.")
        if action == "remove":
            ent = [e for e in watch.entries() if ref.lstrip("$").lower() in (e.get("symbol", "").lower(), e.get("name", "").lower(), e.get("mint"))]
            if not ent:
                return _err(f"{ref!r} is not on the watchlist.", watching=[e.get("symbol") for e in watch.entries()])
            for e in ent:
                watch.remove(e["mint"])
            return _ok(removed=[e.get("symbol") for e in ent], watching=[e.get("symbol") for e in watch.entries()])
        r = _api.resolve(ref)
        if not r:
            return _err(f"No coin on {_api.site} matches {ref!r}.")
        e = watch.add(r, note=str(args.get("note") or ""))
        return _ok(
            added={
                "symbol": e["symbol"],
                "name": e["name"],
                "mint": e["mint"],
                "pair": e.get("pair"),
                "note": e.get("note") or None,
                "now": {"price": fmt.usd(r.get("priceUsd")), "mcap": fmt.usd(r.get("marketCapUsd")), "curve": "graduated" if r.get("graduated") else f"{fmt.num(r.get('progress')) * 100:.0f}%"},
            },
            watching=[x.get("symbol") for x in watch.entries()],
            pulse=("on: Hermes will mention moves past the threshold at the start of a turn" if setting("pulse", True) else "off (plugin setting)"),
        )
    # list
    ents = watch.entries()
    if not ents:
        return _ok(watching=[], hint="ember_watch action=add coin=<symbol> adds a coin.")
    rows_by_mint = {}
    try:
        rows_by_mint = {r.get("mint"): r for r in _api.markets()["markets"]}
    except EmberError:
        pass
    now = time.time()
    items = []
    for e in ents:
        r = rows_by_mint.get(e["mint"])
        item = {"symbol": e.get("symbol"), "name": e.get("name"), "mint": e["mint"], "pair": e.get("pair"), "note": e.get("note") or None, "watched_for": fmt.age(e.get("added_at"), now)}
        if r:
            s = e.get("snapshot") or {}
            p0 = fmt.num(s.get("priceUsd"))
            item.update(
                {
                    "price": fmt.usd(r.get("priceUsd")),
                    "mcap": fmt.usd(r.get("marketCapUsd")),
                    "change_24h": fmt.pct(_trend(r)),
                    "since_added": fmt.pct((fmt.num(r.get("priceUsd")) / p0 - 1) * 100) if p0 > 0 else None,
                    "curve": "graduated" if r.get("graduated") else f"{fmt.num(r.get('progress')) * 100:.0f}%",
                    "url": _api.coin_url(r),
                }
            )
        items.append({k: v for k, v in item.items() if v is not None})
    return _ok(watching=items, count=len(items))


def pulse_lines(min_move_pct: float | None = None, *, mark: bool = True, timeout: float | None = None) -> tuple[list[str], list[dict]]:
    """Shared by the tool and the hook: (notable changes, current rows of the watched coins)."""
    ents = watch.entries()
    if not ents:
        return [], []
    rows = _api.markets(timeout=timeout)["markets"]
    by = {r.get("mint"): r for r in rows}
    lines = watch.pulse(rows, min_move_pct=float(min_move_pct if min_move_pct is not None else setting("pulse_min_move_pct", 15.0)), mark=mark)
    return lines, [by[e["mint"]] for e in ents if e["mint"] in by]


@_guard
def ember_pulse(args: dict, **_: Any) -> str:
    ents = watch.entries()
    if not ents:
        return _ok(watching=[], changes=[], hint="The watchlist is empty. ember_watch action=add coin=<symbol> adds a coin.")
    mm = args.get("min_move_pct")
    lines, rows = pulse_lines(float(mm) if mm is not None else None, mark=True)
    now = time.time()
    return _ok(
        changes=lines or ["Nothing notable since the last look."],
        watching=[
            {
                "symbol": r.get("symbol"),
                "price": fmt.usd(r.get("priceUsd")),
                "change_24h": fmt.pct(_trend(r)),
                "mcap": fmt.usd(r.get("marketCapUsd")),
                "curve": "graduated" if r.get("graduated") else f"{fmt.num(r.get('progress')) * 100:.0f}%",
                "holders": int(fmt.num(r.get("holders"))),
                "last_trade": fmt.ago(r.get("lastTradeAt"), now) if r.get("lastTradeAt") else None,
                "url": _api.coin_url(r),
            }
            for r in rows
        ],
        threshold=f"{float(mm) if mm is not None else setting('pulse_min_move_pct', 15.0):g}%",
    )


HANDLERS = {
    "ember_markets": ember_markets,
    "ember_coin": ember_coin,
    "ember_holders": ember_holders,
    "ember_trades": ember_trades,
    "ember_fees": ember_fees,
    "ember_feed": ember_feed,
    "ember_fomo_board": ember_fomo_board,
    "ember_pairs": ember_pairs,
    "ember_watch": ember_watch,
    "ember_pulse": ember_pulse,
}
