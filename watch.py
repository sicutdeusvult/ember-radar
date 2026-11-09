"""The watchlist and its pulse.

A JSON file in the plugin's data directory (``<HERMES_HOME>/plugin-data/ember-radar/watchlist.json``, per
profile, kept across plugin updates). Every entry remembers the coin as it was when it was added or last
reported (price, cap, curve progress, graduated, holders, payout rounds), so a pulse can say what moved since.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import fmt

PLUGIN_NAME = "ember-radar"
_lock = threading.RLock()


def data_dir() -> Path:
    """Hermes' per-plugin data root, or the equivalent path when the helper is not importable (tests)."""
    try:
        from plugins.plugin_storage import plugin_data_dir  # type: ignore

        return Path(plugin_data_dir(PLUGIN_NAME))
    except Exception:
        home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
        p = Path(home) / "plugin-data" / PLUGIN_NAME
        p.mkdir(parents=True, exist_ok=True)
        return p


def _file() -> Path:
    return data_dir() / "watchlist.json"


def load() -> dict:
    with _lock:
        try:
            d = json.loads(_file().read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("coins"), dict):
                return d
        except FileNotFoundError:
            pass
        except Exception:
            pass  # a malformed file is treated as empty, never as a crash; the next save replaces it
        return {"coins": {}, "last_pulse_at": 0}


def save(d: dict) -> None:
    with _lock:
        f = _file()
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, f)


def snapshot(row: dict, now: float | None = None) -> dict:
    """What a pulse compares against."""
    module = row.get("module") or {}
    return {
        "at": int(now or time.time()),
        "priceUsd": fmt.num(row.get("priceUsd")),
        "marketCapUsd": fmt.num(row.get("marketCapUsd")),
        "progress": fmt.num(row.get("progress")),
        "graduated": bool(row.get("graduated")),
        "holders": int(fmt.num(row.get("holders"))),
        "rounds": int(fmt.num(module.get("rounds"))),
        "volume24hUsd": fmt.num(row.get("volume24hUsd")),
    }


def add(row: dict, note: str = "") -> dict:
    d = load()
    mint = row["mint"]
    entry = d["coins"].get(mint) or {"added_at": int(time.time())}
    entry.update(
        {
            "mint": mint,
            "symbol": row.get("symbol", ""),
            "name": row.get("name", ""),
            "pair": row.get("quoteTicker", ""),
            "note": note or entry.get("note", ""),
            "snapshot": entry.get("snapshot") or snapshot(row),
        }
    )
    d["coins"][mint] = entry
    save(d)
    return entry


def remove(mint: str) -> bool:
    d = load()
    gone = d["coins"].pop(mint, None) is not None
    if gone:
        save(d)
    return gone


def clear() -> int:
    d = load()
    n = len(d["coins"])
    d["coins"] = {}
    save(d)
    return n


def entries() -> list[dict]:
    return sorted(load()["coins"].values(), key=lambda e: e.get("added_at", 0))


# ----------------------------------------------------------------------------------------------- pulse
def changes(entry: dict, row: dict, *, min_move_pct: float) -> list[str]:
    """Readable differences between the stored snapshot and the live row. Empty when nothing is notable."""
    s = entry.get("snapshot") or {}
    out: list[str] = []
    sym = row.get("symbol") or entry.get("symbol") or "?"
    p0, p1 = fmt.num(s.get("priceUsd")), fmt.num(row.get("priceUsd"))
    if p0 > 0 and p1 > 0:
        move = (p1 / p0 - 1) * 100
        if abs(move) >= min_move_pct:
            out.append(f"{sym} {fmt.pct(move)} since {fmt.ago(s.get('at'))} ({fmt.usd(p0)} → {fmt.usd(p1)}, cap {fmt.usd(row.get('marketCapUsd'))})")
    if bool(row.get("graduated")) and not s.get("graduated"):
        out.append(f"{sym} graduated: it left the curve for its own DAMM v2 pool")
    elif not row.get("graduated"):
        g0, g1 = fmt.num(s.get("progress")) * 100, fmt.num(row.get("progress")) * 100
        if g1 >= 90 > g0:
            out.append(f"{sym} is {g1:.0f}% of the way to graduation")
    r0, r1 = int(fmt.num(s.get("rounds"))), int(fmt.num((row.get("module") or {}).get("rounds")))
    if r1 > r0:
        n = r1 - r0
        out.append(
            f"{sym} paid {n} {fmt.mode_label(row.get('mode')).split(' (')[0].lower()} round{'s' if n != 1 else ''} ({fmt.count((row.get('module') or {}).get('lastRecipients'))} wallets in the last one)"
        )
    h0, h1 = int(fmt.num(s.get("holders"))), int(fmt.num(row.get("holders")))
    if h0 > 0 and h1 > 0 and abs(h1 - h0) / h0 >= 0.10:
        out.append(f"{sym} holders {h0:,} → {h1:,}")
    return out


def pulse(rows: list[dict], *, min_move_pct: float, mark: bool = True) -> list[str]:
    """One line per notable change across the watchlist; refreshes the snapshots of the coins it reported."""
    d = load()
    if not d["coins"]:
        return []
    by_mint = {r.get("mint"): r for r in rows}
    lines: list[str] = []
    now = time.time()
    for mint, entry in d["coins"].items():
        row = by_mint.get(mint)
        if not row:
            continue
        diff = changes(entry, row, min_move_pct=min_move_pct)
        if diff:
            lines.extend(diff)
            if mark:
                entry["snapshot"] = snapshot(row, now)
    if mark and lines:
        d["last_pulse_at"] = int(now)
    if mark:
        save(d)
    return lines


def last_pulse_at() -> float:
    return fmt.num(load().get("last_pulse_at"))
