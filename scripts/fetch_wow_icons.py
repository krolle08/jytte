"""Download the WoW icons the POC notes reference into app/static/wow/icons/.

Run on the host, before `docker compose up -d --build jytte`:

    python scripts/fetch_wow_icons.py

The icons are Blizzard's and gitignored because the repo is public, so a
fresh clone has none. This reads every note in
app/poc/wowforever_notes/, takes the icon names the page will ask for,
and fetches only the ones missing. Stdlib only.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.poc import wowforever as wf  # noqa: E402

CDN = "https://wow.zamimg.com/images/wow/icons/large/{}.jpg"


def main() -> int:
    wf.ICON_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {wf.FALLBACK_ICON}
    for f in wf.note_files():
        wanted |= wf.icon_names(wf.load(f))
    missing = sorted(n for n in wanted if not (wf.ICON_DIR / f"{n}.jpg").is_file())
    failed = []
    for n in missing:
        try:
            with urllib.request.urlopen(CDN.format(n), timeout=15) as r:
                (wf.ICON_DIR / f"{n}.jpg").write_bytes(r.read())
        except OSError as e:
            failed.append(f"{n} ({e})")
    print(f"{len(wanted)} referenced, {len(missing) - len(failed)} downloaded, "
          f"{len(wanted) - len(missing)} already present")
    for f in failed:
        print("FAILED", f)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
