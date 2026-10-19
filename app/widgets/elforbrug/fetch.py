"""Elforbrug - metering data from Eloverblik. NOT-READY STUB ONLY.

This file must never grow an HTTP client.

`manifest.yaml` sets `source: n8n`, so the real read is
`deploy/n8n/workflows/elforbrug.json` and the data arrives by
`POST /widgets/elforbrug/state`. The Eloverblik refresh token lives in
n8n's encrypted credential store; Jytte holds no energy credential and
no Python client that could use one. A fetcher here would be a second
path to the same data with a different trust boundary, which is the
arrangement `bank`, `email` and `calendar` already avoid.

What the n8n workflow produces, and therefore what the page expects:

    ready           bool
    meters          [{id, address, type, unit}]
    days            [{date, kwh_x1000, kwh, cost_oere, cost_kr}]
    total_kwh       string, the period total
    period          {from, to}
    expected_minutes  1440 - declared so /poc/systems can judge it

Consumption is stored as **integer thousandths of a kWh**
(`kwh_x1000`), the same no-floats rule the money columns follow.
Eloverblik reports to three decimals, so nothing is lost.

SETUP, WHICH ONLY THE ACCOUNT HOLDER CAN DO
1. Log in at eloverblik.dk with MitID.
2. Top right, under your name: create a **refresh token**. It is valid
   for a year.
3. Put it in n8n as an HTTP Header Auth credential named
   `eloverblik`, header `Authorization`, value `Bearer <token>`.
4. Activate the workflow.

Step 2 is yours. This project never mints a credential or picks its
own scopes, even when asked to.
"""
from __future__ import annotations


async def fetch() -> dict:
    return {
        "ready": False,
        "reason": ("afventer foerste push fra n8n-workflowet 'elforbrug'. "
                   "Opret et refresh token paa eloverblik.dk og laeg det "
                   "i n8n som credential 'eloverblik'."),
        "source": "n8n",
        "meters": [],
        "days": [],
        "total_kwh": None,
        "period": {},
    }


# async, like every other widget's. registry.refresh awaits
# summary_fn unconditionally, so a sync one raises
# "object str can't be used in 'await' expression" and takes the
# whole refresh down with it.
async def summary(data: dict) -> str:
    if not data.get("ready"):
        return "elforbrug: afventer Eloverblik-token"
    n = len(data.get("days") or [])
    return f"elforbrug: {data.get('total_kwh', '?')} kWh over {n} dage"
