"""Ember Radar — Ember (embercurve.fun), the Solana launchpad, inside Hermes.

Ten read-only tools over Ember's public API, a per-profile watchlist whose notable moves are whispered to the
model at the start of a turn (``pre_llm_call``), an ``/ember`` slash command, an Automation Blueprint for a
daily brief and two bundled skills. No keys, no wallet, nothing written anywhere but the plugin's own data dir.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from . import fmt, schemas, tools, watch

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).parent
_pulse_lock = threading.Lock()
_pulse_last_try = 0.0


# --------------------------------------------------------------------------------------------- the pulse hook
def _pulse_hook(session_id: str = "", user_message: str = "", is_first_turn: bool = False, platform: str = "", **_: Any):
    """At most once per cooldown, when the watchlist has coins: one short block of what moved. Never slows a turn
    by more than the venue timeout (3 s) and never raises."""
    global _pulse_last_try
    if not tools.setting("pulse", True):
        return None
    try:
        cooldown = max(1, int(fmt.num(tools.setting("pulse_cooldown_min", 30), 30))) * 60
        now = time.time()
        with _pulse_lock:
            if now - _pulse_last_try < 20:  # two sessions sharing the profile: one fetch, not two
                return None
            _pulse_last_try = now
        if now - watch.last_pulse_at() < cooldown:
            return None
        if not watch.entries():
            return None
        lines, _rows = tools.pulse_lines(mark=True, timeout=3.0)
        if not lines:
            return None
        text = "Ember Radar — on the user's Ember watchlist since they last looked:\n" + "\n".join(f"- {ln}" for ln in lines[:8])
        text += "\nMention this briefly if it is relevant to what they ask; ember_pulse has the details."
        return {"context": text}
    except Exception as e:  # noqa: BLE001 — a hook must never break the turn
        logger.debug("ember-radar pulse skipped: %s", e)
        return None


# --------------------------------------------------------------------------------------------- /ember
def _cmd(raw_args: str, **_: Any) -> str:
    """/ember · /ember <coin> · /ember watch <coin> [note] · /ember unwatch <coin> · /ember list · /ember pulse · /ember feed · /ember fomo · /ember pairs [q]"""
    import json

    parts = (raw_args or "").strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    def j(s: str) -> dict:
        return json.loads(s)

    try:
        if sub in ("", "top", "trending", "new", "movers", "graduating", "fees"):
            d = j(tools.ember_markets({"sort": sub or "trending", "limit": 8}))
            if "error" in d:
                return f"Ember: {d['error']}"
            v = d["venue"]
            head = f"Ember · {v['coins']} coins ({v['graduated']} graduated) · 24h volume {v['volume_24h']} · fees {v['fees_24h']} · paid out all-time {v['paid_out_all_time']}"
            lines = [head, f"{(sub or 'trending').capitalize()}:"]
            for c in d["coins"]:
                lines.append(
                    f"  {c['symbol']:<8} {c['price']:>12}  {c['change_24h']:>8}  cap {c['mcap']:>8}  vol {c['volume_24h']:>8}  {c['pair']:<7} {c['curve']}  · {c['fees_go_to'].split(' (')[0]}"
                )
            lines.append("/ember <coin> for a card · /ember watch <coin> · /ember pulse · /ember feed · /ember fomo · /ember pairs")
            return "\n".join(lines)
        if sub == "help":
            return _cmd.__doc__ or ""
        if sub in ("watch", "add"):
            if not rest:
                return "Usage: /ember watch <coin> [note]"
            bits = rest.split(None, 1)
            d = j(tools.ember_watch({"action": "add", "coin": bits[0], "note": bits[1] if len(bits) > 1 else ""}))
            if "error" in d:
                return f"Ember: {d['error']}"
            a = d["added"]
            return f"Watching {a['symbol']} ({a['name']}, {a['pair']}) at {a['now']['price']}, cap {a['now']['mcap']}, curve {a['now']['curve']}. Watchlist: {', '.join(d['watching'])}."
        if sub in ("unwatch", "remove", "rm"):
            if not rest:
                return "Usage: /ember unwatch <coin>"
            d = j(tools.ember_watch({"action": "remove", "coin": rest}))
            if "error" in d:
                return f"Ember: {d['error']}"
            return f"Removed {', '.join(d['removed'])}. Watchlist: {', '.join(d['watching']) or 'empty'}."
        if sub in ("list", "watchlist", "ls"):
            d = j(tools.ember_watch({"action": "list"}))
            if not d.get("watching"):
                return "Your Ember watchlist is empty. /ember watch <coin> adds one."
            lines = ["Your Ember watchlist:"]
            for w in d["watching"]:
                lines.append(
                    f"  {w['symbol']:<8} {w.get('price', '—'):>12}  24h {w.get('change_24h', '—'):>8}  since added {w.get('since_added', '—'):>8}  cap {w.get('mcap', '—'):>8}  {w.get('curve', '')}"
                    + (f"  · {w['note']}" if w.get("note") else "")
                )
            return "\n".join(lines)
        if sub == "pulse":
            d = j(tools.ember_pulse({}))
            if "error" in d:
                return f"Ember: {d['error']}"
            if not d.get("watching"):
                return "Your Ember watchlist is empty. /ember watch <coin> adds one."
            return "Ember pulse:\n" + "\n".join(f"  - {ln}" for ln in d["changes"])
        if sub in ("feed", "tape"):
            d = j(tools.ember_feed({"limit": 12, **({"kind": rest} if rest else {})}))
            if "error" in d:
                return f"Ember: {d['error']}"
            return "Ember tape:\n" + "\n".join(f"  {e['when']:>7}  {e.get('text') or e['what']}" for e in d["events"]) if d["events"] else "The tape is quiet."
        if sub in ("fomo", "fomode", "board"):
            d = j(tools.ember_fomo_board({"limit": 8}))
            if "error" in d:
                return f"Ember: {d['error']}"
            t = d["totals"]
            lines = [f"fomode 👀 · {t['coins']} coins for {t['traders']} traders · paid {t['paid_to_traders_all_time']} all-time, {t['paid_24h']} in 24h"]
            for tr in d["traders"]:
                lines.append(
                    f"  @{tr['handle']:<14} {tr.get('followers', '—'):>7} followers  paid {tr['paid_all_time']:>8} ({tr['paid_24h']} 24h)  coins: {', '.join(c['symbol'] for c in tr['coins']) or '—'}"
                )
            return "\n".join(lines)
        if sub in ("pairs", "stocks"):
            d = j(tools.ember_pairs({"query": rest, "limit": 25}))
            if "error" in d:
                return f"Ember: {d['error']}"
            lines = [f"Ember pairs · {d['pairs_total']} ({', '.join(f'{k} {v}' for k, v in d['by_group'].items())})" + (f" · matching {rest!r}: {d['matched']}" if rest else "")]
            for p in d["pairs"]:
                lines.append(f"  {p['ticker']:<9} {p.get('price', '—'):>10}  {p.get('name', '')}  · {p.get('provider', '')}")
            return "\n".join(lines)
        # anything else: a coin
        d = j(tools.ember_coin({"coin": raw_args.strip()}))
        if "error" in d:
            return f"Ember: {d['error']}"
        c = d["coin"]
        m = c.get("module") or {}
        lines = [
            f"{c['name']} ({c['symbol']}) · {c['pair']} pair · {c['url']}",
            f"  price {c['price']} ({c['change_24h']} 24h, {c.get('low_24h', '—')}–{c.get('high_24h', '—')}) · cap {c['mcap']} · {c['curve']}",
            f"  24h: volume {c['volume_24h']} · fees {c['fees_24h']} · {c['trades_24h']} trades · {c['holders']} holders · age {c['age']}",
            f"  fees: {c['tax']} → {m.get('what', c['fees_go_to'])}"
            + (f", every {m['every']}" if m.get("every") else "")
            + (f", {m['rounds_paid']} rounds paid" if m.get("rounds_paid") else "")
            + (f", next {m['next_run']}" if m.get("next_run") else ""),
        ]
        if c.get("all_time"):
            at = c["all_time"]
            lines.append(f"  all-time: fees {at['fees']} · paid out {at['paid_out']} · volume {at['volume']}")
        if c.get("description"):
            lines.append(f"  “{c['description']}”")
        if c.get("curated_note"):
            lines.append(f"  curated: {c['curated_note']}")
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return f"Ember: {type(e).__name__}: {e}"


# --------------------------------------------------------------------------------------------- register
def register(ctx) -> None:
    # settings (plugins.entries.ember-radar.settings.*)
    get = getattr(ctx, "get_config", None)
    site = None
    settings: dict[str, Any] = {}
    if callable(get):
        try:
            site = get("api_url", default=None)
            settings = {
                "pulse": get("pulse", default=True),
                "pulse_min_move_pct": fmt.num(get("pulse_min_move_pct", default=15.0), 15.0),
                "pulse_cooldown_min": int(fmt.num(get("pulse_cooldown_min", default=30), 30)),
            }
        except Exception as e:  # noqa: BLE001 — defaults are fine
            logger.debug("ember-radar: settings not readable (%s); using defaults", e)
    tools.configure(site or None, **settings)

    for schema in schemas.ALL:
        name = schema["name"]
        ctx.register_tool(name=name, toolset="ember", schema=schema, handler=tools.HANDLERS[name], emoji="🔥", description=schema["description"].split(". ")[0] + ".")

    ctx.register_hook("pre_llm_call", _pulse_hook)

    ctx.register_command(
        "ember",
        handler=_cmd,
        description="Ember: trending coins, a coin's card, your watchlist, the tape, fomode, pairs",
        args_hint="[coin | watch <coin> | unwatch <coin> | list | pulse | feed | fomo | pairs <q>]",
    )

    # skills: ember-radar:ember-research, ember-radar:ember-brief
    reg_skill = getattr(ctx, "register_skill", None)
    if callable(reg_skill):
        skills_dir = _PLUGIN_DIR / "skills"
        if skills_dir.is_dir():
            for child in sorted(skills_dir.iterdir()):
                md = child / "SKILL.md"
                if child.is_dir() and md.exists():
                    try:
                        reg_skill(child.name, md)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("ember-radar: skill %s not registered: %s", child.name, e)

    # a fill-in-the-blanks automation: the Ember daily brief
    reg_bp = getattr(ctx, "register_automation_blueprint", None)
    if callable(reg_bp):
        try:
            reg_bp(
                "brief",
                title="Ember daily brief",
                description="Every day: new launches, graduations, the biggest movers, the biggest payouts to holders and what moved on your Ember watchlist.",
                category="general",
                schedule_template="{minute} {hour} * * *",
                prompt_template=(
                    "Write today's Ember brief with the Ember Radar tools, under 200 words. Use ember_markets sort=new "
                    "limit=6 for launches of the last 24h, ember_markets sort=movers limit=5 for the biggest movers, "
                    "ember_markets sort=graduating limit=3 for coins about to graduate, ember_feed kind=holders limit=10 "
                    "for the biggest holder payouts and ember_pulse for my watchlist. Lead with what matters most, give "
                    "each coin its pair and its URL, and skip empty sections. Tone: {tone}."
                ),
                slots=[
                    {"name": "time", "type": "time", "label": "What time?", "default": "09:00"},
                    {"name": "tone", "type": "enum", "label": "Tone", "default": "plain", "options": ["plain", "degen", "analyst"], "strict": False},
                    {"name": "deliver", "type": "enum", "label": "Where to deliver?", "default": "origin", "options": ["origin", "local"], "strict": False},
                ],
                skills=["ember-radar:ember-brief"],
                tags=["crypto", "daily", "solana"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("ember-radar: blueprint not registered: %s", e)

    logger.info("ember-radar: %d tools on %s", len(schemas.ALL), tools.api().site)
