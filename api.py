"""The Ember API, read-only, over the standard library only.

Everything the plugin knows comes from one Ember deployment's public ``/api/solana/*`` routes
(https://embercurve.fun by default): the markets list, one coin, its holders, trades and fee ledger, the
live tape, the FOMO traders board and the quote tokens. No key, no wallet, no write.

Responses are cached for a few seconds per path so a turn that calls three tools makes one request per
route, and every call carries a timeout so a slow venue never stalls the agent.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_SITE = "https://embercurve.fun"
USER_AGENT = "ember-radar/0.1 (Hermes Agent plugin)"


class EmberError(Exception):
    """A readable failure: the venue did not answer, or answered with something that is not Ember."""


def _site_origin(url: str) -> str:
    """``https://embercurve.fun/`` or ``…/api/solana`` → ``https://embercurve.fun``."""
    u = (url or DEFAULT_SITE).strip().rstrip("/")
    if u.endswith("/api/solana"):
        u = u[: -len("/api/solana")]
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


class EmberApi:
    def __init__(self, site: str = DEFAULT_SITE, timeout: float = 8.0):
        self.site = _site_origin(site)
        self.base = self.site + "/api/solana"
        self.timeout = timeout
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    # ----------------------------------------------------------------------------- transport
    def get(self, path: str, *, ttl: float = 5.0, timeout: float | None = None) -> Any:
        """GET ``/api/solana<path>`` as JSON, cached for ``ttl`` seconds."""
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(path)
            if hit and now - hit[0] < ttl:
                return hit[1]
        req = urllib.request.Request(self.base + path, headers={"accept": "application/json", "user-agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:  # noqa: S310 — https/http to the configured Ember site only
                raw = r.read()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read(300).decode("utf-8", "replace")
            except Exception:
                pass
            raise EmberError(f"{self.site} answered {e.code} for {path}{(': ' + body) if body else ''}") from None
        except urllib.error.URLError as e:
            raise EmberError(f"{self.site} is not reachable ({getattr(e, 'reason', e)})") from None
        except TimeoutError:
            raise EmberError(f"{self.site} took too long to answer {path}") from None
        except Exception as e:  # a reset, a bad TLS handshake…
            raise EmberError(f"{self.site} failed on {path}: {e}") from None
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            raise EmberError(f"{self.site} did not answer {path} with JSON (is this an Ember site?)") from None
        with self._lock:
            self._cache[path] = (now, data)
            if len(self._cache) > 256:  # a long session asking about many coins
                oldest = sorted(self._cache.items(), key=lambda kv: kv[1][0])[:64]
                for k, _ in oldest:
                    self._cache.pop(k, None)
        return data

    # ----------------------------------------------------------------------------- routes
    def markets(self, *, timeout: float | None = None) -> dict:
        """``{economics, totals, markets:[row…]}`` — every coin on the venue with price, cap, curve progress, volume,
        fees, holders, the fee module and a 24-point spark."""
        d = self.get("/markets", ttl=5.0, timeout=timeout)
        if not isinstance(d, dict) or not isinstance(d.get("markets"), list):
            raise EmberError(f"{self.site}/api/solana/markets has no markets list (is this an Ember site?)")
        return d

    def market(self, mint: str) -> dict | None:
        d = self.get(f"/market/{urllib.parse.quote(mint)}", ttl=5.0)
        return d.get("market") if isinstance(d, dict) else None

    def holders(self, mint: str, page: int = 0) -> dict:
        return self.get(f"/holders/{urllib.parse.quote(mint)}?page={int(page)}", ttl=15.0)

    def trades(self, mint: str, limit: int = 50) -> dict:
        return self.get(f"/trades/{urllib.parse.quote(mint)}?limit={int(limit)}", ttl=5.0)

    def candles(self, mint: str, tf: str = "1h", limit: int = 24) -> list:
        d = self.get(f"/candles/{urllib.parse.quote(mint)}?tf={urllib.parse.quote(tf)}&limit={int(limit)}", ttl=30.0)
        return d.get("candles", []) if isinstance(d, dict) else []

    def fees(self, pool: str) -> dict:
        return self.get(f"/fees/pool/{urllib.parse.quote(pool)}", ttl=15.0)

    def feed(self) -> list:
        d = self.get("/feed?poll=1", ttl=3.0)
        return d.get("events", []) if isinstance(d, dict) else []

    def fomo_board(self) -> dict:
        return self.get("/fomo/board", ttl=15.0)

    def quotes(self) -> dict:
        return self.get("/quotes", ttl=120.0)

    def payouts(self, limit: int = 50) -> list:
        d = self.get(f"/payouts?limit={int(limit)}", ttl=10.0)
        return d.get("payouts", []) if isinstance(d, dict) else []

    def status(self) -> dict:
        return self.get("/status", ttl=10.0)

    # ----------------------------------------------------------------------------- lookups
    def resolve(self, ref: str, rows: list[dict] | None = None) -> dict | None:
        """A coin by mint, pool, ``$SYMBOL``, symbol or a unique name prefix/substring (case-insensitive)."""
        q = (ref or "").strip()
        if not q:
            return None
        rows = rows if rows is not None else self.markets()["markets"]
        for r in rows:
            if q == r.get("mint") or q == r.get("pool"):
                return r
        s = q.lstrip("$").lower()
        same = [r for r in rows if str(r.get("symbol", "")).lower() == s]
        if len(same) == 1:
            return same[0]
        if len(same) > 1:  # two coins with one ticker: the one with the most volume is what people mean
            return max(same, key=lambda r: float(r.get("volume24hUsd") or 0))
        named = [r for r in rows if str(r.get("name", "")).lower() == s]
        if len(named) == 1:
            return named[0]
        starts = [r for r in rows if str(r.get("name", "")).lower().startswith(s) or str(r.get("symbol", "")).lower().startswith(s)]
        if len(starts) == 1:
            return starts[0]
        within = [r for r in rows if s in str(r.get("name", "")).lower()]
        if len(within) == 1:
            return within[0]
        if len(q) >= 32 and q.isalnum():  # a mint the list does not carry (hidden, or brand new): ask for it alone
            try:
                return self.market(q)
            except EmberError:
                return None
        return None

    def coin_url(self, row: dict) -> str:
        route = row.get("route") or f"/t/{row.get('mint', '')}"
        return self.site + route
