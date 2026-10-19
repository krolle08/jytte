"""Bank widget - n8n-sourced, deliberately without a local fetcher.

The open-banking read lives in `deploy/n8n/workflows/bank.json` and the
result arrives via `POST /widgets/bank/state`.

**Jytte never holds a bank credential.** The aggregator's secret pair
lives in n8n's encrypted credential store. Nothing in this process, and
nothing an agent can reach, can call the bank. That is the same rule
`email` and `calendar` follow, and the reason this widget is
`source: n8n` with no Python client here.

Do NOT grow an HTTP client in this file. A second fetcher would give the
widget two sources of truth that silently disagree, and it would put a
bank credential inside the process that renders HTML.

`fetch()` exists only because `registry._load()` does a bare
`getattr(fetch_mod, "fetch")`, and to give the card an honest payload
before the first push.
"""
from __future__ import annotations


def _kr(oere: int) -> str:
    """Danish formatting for a minor-unit integer: 1234500 -> "12.345,00"."""
    s = f"{abs(int(oere)) / 100:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if int(oere) < 0 else "") + s


async def fetch() -> dict:
    """Return the not-ready placeholder. Never performs I/O."""
    return {
        "ready": False,
        "reason": "afventer foerste push fra n8n-workflowet 'bank'",
        "source": "n8n",
        "accounts": [],
        "transactions": [],
        "totals": {},
    }


async def summary(data: dict) -> str:
    """One-line card summary. Also used by the chat context and
    `registry.summaries()`, so keep it short and factual."""
    if not isinstance(data, dict) or not data.get("ready"):
        return "bank: afventer foerste n8n-push"

    accounts = data.get("accounts") or []
    totals = data.get("totals") or {}
    if not accounts:
        return "bank: forbundet, men ingen konti delt"

    parts = [f"{_kr(int(totals.get('balance_oere') or 0))} kr paa {len(accounts)} konti"]

    out30 = int(totals.get("out_30d_oere") or 0)
    if out30:
        parts.append(f"{_kr(out30)} ud sidste 30 dage")

    # Staleness matters more here than anywhere else in the app: an
    # open-banking consent expires after 90 days and the fetch starts
    # failing silently from the bank's side, not n8n's.
    stale = int(data.get("stale_days") or 0)
    if stale >= 2:
        parts.append(f"saldo {stale} dage gammel")

    return "bank: " + " :: ".join(parts)
