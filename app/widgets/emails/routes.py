"""Drawer detail route for the emails widget.

Reads the CACHED widget state (no live IMAP call on drawer open) and finds
the email by (bucket, uid). This keeps clicks instant and avoids hitting
the mailbox on every interaction.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()


@router.get("/detail", response_class=HTMLResponse)
async def detail(request: Request, uid: str, bucket: str):
    templates = request.app.state.templates
    row = await db.read_state("emails")
    data = json.loads(row["payload"]) if row and row.get("payload") else {}
    mails = (data.get("buckets") or {}).get(bucket) or []
    email = next((m for m in mails if str(m.get("uid")) == str(uid)), None)
    labels = {"trustworks": "Trustworks", "dagrofa": "Dagrofa", "private": "Private"}
    return templates.TemplateResponse(
        "emails/detail.html",
        {
            "request": request,
            "email": email,
            "bucket": bucket,
            "bucket_label": labels.get(bucket, bucket),
        },
    )
