"""The bank consent callback: where the authorization code lands.

Open banking consent ends at the bank's own login, so it cannot be
automated and should not be. What it leaves behind is one short-lived
`code` in a query string, delivered to a redirect URL registered with
the AIS provider. This module is that URL and nothing else.

Three rules it follows, each the reason a line here looks the way it
does:

1. **The code is never logged and never stored.** It is a bearer
   credential for the length of its life, and `app/widgets/bank/
   CLAUDE.md` already says Jytte holds no bank credential. It is
   rendered once, into the browser that was redirected here, and
   forgotten.
2. **Jytte does not exchange it.** The exchange needs an RS256 JWT
   signed with the application's private key. That key lives in n8n's
   encrypted credential store, which is the whole point of the
   `source: n8n` arrangement. Jytte hands the code over and stops.
3. **This page renders no shell.** Once a tunnel is in front of it,
   this path is reachable from the internet. The sidebar would carry
   balances, salary and task counts to anyone who guessed the URL, so
   the response is a standalone document that knows nothing.

Set `JYTTE_BANK_SESSION_WEBHOOK` to an n8n webhook to have the code
forwarded automatically. Without it the page shows the code so it can
be pasted into the session call by hand, which is the honest fallback
while the n8n side is still a GoCardless workflow.
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

log = logging.getLogger("jytte.bankauth")

router = APIRouter()

# No referrer, no cache, no indexing. A code in a URL has leaked out of
# three different products through the Referer header alone.
_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}

_PAGE = """<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Banksamtykke :: Jytte</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; background: #111114; color: #E8E6E1;
         font: 16px/1.55 ui-sans-serif, system-ui, sans-serif;
         display: flex; justify-content: center; }}
  main {{ max-width: 560px; padding: 48px 20px; width: 100%; }}
  h1 {{ font-size: 21px; margin: 0 0 6px; }}
  p {{ color: #B9B7B2; }}
  .ok {{ color: #96B7B9; }}
  .bad {{ color: #E3A08F; }}
  code, .code {{ font-family: ui-monospace, "IBM Plex Mono", monospace; }}
  .code {{ display: block; background: #17171B; border: 1px solid rgba(250,248,244,.12);
           border-radius: 8px; padding: 12px 14px; margin: 14px 0 6px;
           font-size: 13px; word-break: break-all; }}
  .meta {{ font-size: 12px; color: #86868F; }}
</style></head>
<body><main>
<h1 class="{tone}">{heading}</h1>
{body}
</main></body></html>
"""


class _RedactCallbackQuery(logging.Filter):
    """Keep the authorization code out of the access log.

    uvicorn logs the whole request line, query string included, so the
    code would be written to disk the moment the bank redirects -
    which is rule 3 in CLAUDE.md broken by a library nobody thought to
    check. The filter is scoped to this one path because this is the
    only URL in the project that carries a credential.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = getattr(record, "args", None)
        if isinstance(args, tuple) and len(args) == 5:
            path = args[2]
            if isinstance(path, str) and path.startswith("/bank/callback?"):
                record.args = (args[0], args[1], "/bank/callback?<redacted>",
                               args[3], args[4])
        return True


def install_log_filter() -> None:
    """Called from the lifespan, after uvicorn has configured its own
    loggers, so the filter cannot be replaced by that configuration."""
    logging.getLogger("uvicorn.access").addFilter(_RedactCallbackQuery())


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _page(heading: str, body: str, tone: str = "ok", status: int = 200):
    return HTMLResponse(
        _PAGE.format(heading=_esc(heading), body=body, tone=tone),
        status_code=status, headers=_HEADERS)


async def _forward(code: str, state: str) -> str | None:
    """Hand the code to n8n, which holds the signing key. Returns an
    error string, or None when n8n accepted it."""
    url = os.getenv("JYTTE_BANK_SESSION_WEBHOOK", "").strip()
    if not url:
        return "no-webhook"
    secret = os.getenv("JYTTE_INTERNAL_SECRET", "")
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, json={"code": code, "state": state},
                             headers={"X-Jytte-Internal-Secret": secret})
        if r.status_code >= 400:
            # The body may quote the code back at us, so only the status
            # goes anywhere near a log line.
            return f"n8n svarede {r.status_code}"
        return None
    except Exception as e:                      # noqa: BLE001
        return f"{type(e).__name__}"


@router.get("/bank/callback", response_class=HTMLResponse)
async def bank_callback(request: Request):
    """Landing point for the AIS provider's redirect.

    Registered with the provider as
    `https://<public host>/bank/callback`. Takes `code` and `state` on
    success, or `error` plus `error_description` when the consent was
    refused or expired mid-flow.
    """
    q = request.query_params
    code = (q.get("code") or "").strip()
    state = (q.get("state") or "").strip()
    err = (q.get("error") or "").strip()

    if err:
        # The provider's own text, escaped. Not logged: some providers
        # put identifiers in the description.
        log.warning("bank callback: provider returned an error")
        return _page(
            "Samtykket gik ikke igennem",
            f"<p>Udbyderen svarede <code>{_esc(err)}</code>.</p>"
            f"<p>{_esc(q.get('error_description') or 'Ingen yderligere forklaring.')}</p>"
            "<p class=meta>Start forloebet forfra. Koden er engangsbrug, "
            "saa et genbesoeg af denne side hjaelper ikke.</p>",
            tone="bad", status=400)

    if not code:
        # Someone opened the URL directly. Say so plainly rather than
        # 404, which reads as a broken redirect registration.
        return _page(
            "Ingen kode i adressen",
            "<p>Denne side er kun landingspunkt for banksamtykket. "
            "Den goer intet naar den aabnes direkte.</p>",
            tone="bad", status=400)

    log.info("bank callback: received an authorization code")
    problem = await _forward(code, state)

    if problem is None:
        return _page(
            "Samtykke modtaget",
            "<p>Koden er sendt videre til n8n, som veksler den til en "
            "session. Du kan lukke fanen.</p>"
            "<p class=meta>Jytte hverken gemmer eller logger koden.</p>")

    if problem == "no-webhook":
        return _page(
            "Kode modtaget - kopier den",
            "<p>Der er ingen n8n-webhook sat op endnu "
            "(<code>JYTTE_BANK_SESSION_WEBHOOK</code>), saa koden skal "
            "bruges manuelt. Den er engangsbrug og udloeber hurtigt.</p>"
            f"<span class=code>{_esc(code)}</span>"
            + (f"<p class=meta>state: <code>{_esc(state)}</code></p>"
               if state else "")
            + "<p class=meta>Jytte gemmer den ikke. Lukker du fanen, "
              "er den vaek, og samtykket skal startes forfra.</p>")

    return _page(
        "Kode modtaget, men n8n tog den ikke",
        f"<p>{_esc(problem)}. Koden staar herunder, saa forloebet ikke "
        "er spildt - den er engangsbrug og udloeber hurtigt.</p>"
        f"<span class=code>{_esc(code)}</span>",
        tone="bad")
