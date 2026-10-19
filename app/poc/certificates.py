"""POC: Certifikater.

Course and credential certificates - the ones you earn and want to find
again - read from `assets/certificates/`.

NOT X.509. The first file in the folder is
"Certificate-Technical Leadership Masterclass-Nichlas Madsen.png", a
course certificate, so this is a credentials wall and not a TLS expiry
monitor. Worth stating plainly, because "certificates" plus "monitoring"
reads as PKI to anyone arriving later, and the two share no code.

If TLS certificates ever land here too, they need a separate view:
different fields, different failure mode, different urgency. Do not
widen this one to cover both.

The filename is the only metadata there is. Rather than demanding a
sidecar JSON nobody will maintain, the parser reads the convention the
existing file already follows and degrades to the raw stem when a file
does not follow it:

    Certificate-<Title>-<Holder>.png
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DIR = "/jytte/assets/certificates"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DOC_SUFFIXES = {".pdf"}

# Certificate-<Title>-<Holder>. Tolerant of extra hyphens inside the
# title, because a course name regularly contains one.
_NAME = re.compile(r"^certificate\s*-\s*(?P<title>.+?)\s*-\s*(?P<holder>[^-]+)$", re.I)

# A four digit year anywhere in the stem, if the file carries one.
_YEAR = re.compile(r"(?:19|20)\d{2}")


def parse_name(stem: str) -> dict:
    """Filename -> {title, holder, year}. Pure, so it is testable."""
    s = " ".join(stem.replace("_", " ").split())
    year = (_YEAR.search(s) or [None])[0] if _YEAR.search(s) else None

    m = _NAME.match(s)
    if m:
        return {"title": m.group("title").strip(),
                "holder": m.group("holder").strip(),
                "year": year,
                "parsed": True}
    # No convention matched. Show the filename rather than inventing a
    # title; a wrong title is worse than an ugly one.
    return {"title": s, "holder": "", "year": year, "parsed": False}


def _folder() -> Path:
    return Path(os.getenv("JYTTE_CERTS_DIR") or DEFAULT_DIR)


def build() -> dict:
    folder = _folder()
    if not folder.is_dir():
        return {"ready": False,
                "reason": (f"mappen {folder} findes ikke - er "
                           "assets/certificates monteret ind?"),
                "certs": [], "counts": {}}

    certs = []
    unsupported = []
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        suf = p.suffix.lower()
        if suf not in IMAGE_SUFFIXES and suf not in DOC_SUFFIXES:
            unsupported.append(p.name)
            continue
        meta = parse_name(p.stem)
        st = p.stat()
        certs.append({
            **meta,
            "file": p.name,
            # Served by the route, not by StaticFiles: the folder is
            # mounted outside /jytte/app/static and a certificate is
            # personal, so it goes through a handler that only ever
            # serves a name it found in this listing.
            "url": f"/poc/certifikater/fil/{p.name}",
            "kind": "billede" if suf in IMAGE_SUFFIXES else "dokument",
            "suffix": suf.lstrip("."),
            "size_kb": round(st.st_size / 1024),
            "added": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                             .date().isoformat(),
        })

    certs.sort(key=lambda c: (c["added"], c["title"].lower()), reverse=True)

    return {
        "ready": True,
        "reason": "",
        "folder": str(folder),
        "certs": certs,
        "unsupported": unsupported,
        "counts": {
            "total": len(certs),
            "images": sum(1 for c in certs if c["kind"] == "billede"),
            "docs": sum(1 for c in certs if c["kind"] == "dokument"),
            "unparsed": sum(1 for c in certs if not c["parsed"]),
        },
    }


def resolve(name: str) -> Path | None:
    """Map a requested filename to a real file, or None.

    The check is membership in the listing, not string sanitising. A
    name that is not one of the files actually sitting in the folder
    does not resolve, so `..` and absolute paths have nothing to grab.
    """
    folder = _folder()
    if not folder.is_dir():
        return None
    for p in folder.iterdir():
        if p.is_file() and p.name == name:
            suf = p.suffix.lower()
            if suf in IMAGE_SUFFIXES or suf in DOC_SUFFIXES:
                return p
    return None
