"""FEAT-002: data behind the Home Hub pages.

AC-07 bank rows from the real rule files, AC-09 maintenance write-back,
plus the cron and URL helpers the pages lean on.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import kategori  # noqa: E402
from app.hub import maintenance, sources, store, views  # noqa: E402


class _W:
    def __init__(self, name, data):
        self.name, self._data = name, data
        self.title, self.source, self.refresh_minutes = name, "n8n", None

    async def latest(self):
        return {"data": self._data, "last_success_at": None, "consecutive_failures": 0}


class _Reg:
    def __init__(self, widgets):
        self._w = {w.name: w for w in widgets}

    def get(self, name):
        return self._w.get(name)

    def list(self):
        return list(self._w.values())


@pytest.fixture
def rules(monkeypatch):
    monkeypatch.setattr(kategori, "CATS_PATH", REPO / "config" / "udgiftskategorier.yml")
    monkeypatch.setattr(kategori, "RULES_PATH", REPO / "config" / "kategoriregler.yml")


def test_kind_is_reported(rules):
    book = kategori.load()
    hit = kategori.categorise({"text": "NETTO 4711 Sydhavn", "amount_oere": -41200}, book)
    assert hit["matched"] and hit["line"] > 0 and hit["kind"] in ("tekst", "ord", "regex")
    miss = kategori.categorise({"text": "Zzqx unknown shop", "amount_oere": -100}, book)
    assert not miss["matched"] and miss["line"] == 0


def test_bank_rows(rules, monkeypatch):
    monkeypatch.setenv("JYTTE_SITE", "personal")
    today = datetime.now(timezone.utc).date().isoformat()
    tx = [{"date": today, "text": "NETTO 4711 Sydhavn", "amount_oere": -41200},
          {"date": today, "text": "Zzqx unknown shop", "amount_oere": -12000},
          {"date": today, "text": "Loen", "counterparty": "Arbejdsgiver", "amount_oere": 4250000}]
    reg = _Reg([_W("bank", {"ready": True, "transactions": tx, "accounts": []})])
    pg = asyncio.run(views.build_bank(views.Ctx(registry=reg)))
    by = {r.cells[0]: r for r in pg.rows}
    netto = by["NETTO 4711 Sydhavn"]
    assert netto.cells[3].startswith("linje ") and netto.tag in ("Fast", "Variabel")
    unk = by["Zzqx unknown shop"]
    assert unk.cells[2] == "Ukategoriseret" and unk.tag == "Ukategoriseret"
    assert views.GREY_BG in unk.cell_styles[2]
    uncat = next(s for s in pg.stats if s.label == "Ukategoriseret")
    assert uncat.value == "120 kr." and uncat.sub.startswith("1 ")
    # the suggestion is offered for the uncategorised row only, as text
    d = pg.details[unk.detail_key]
    assert "kategori: <vaelg>" in d.body and d.actions[0].copy


def test_maintenance_done_writes_back(tmp_path, monkeypatch):
    monkeypatch.setenv("JYTTE_TASKS_PATH", str(tmp_path))
    folder = tmp_path / maintenance.FOLDER
    folder.mkdir()
    text = ("---\ntype: maintenance\nstatus: open\ndue: 2026-06-18\nrecurs: monthly\n"
            "system: Docker Host\n---\n# Update Docker containers\nCheck for new versions\n")
    f = folder / "update-docker.md"
    f.write_text(text, encoding="utf-8")
    items = maintenance.load(date(2026, 6, 20))["items"]
    assert len(items) == 1 and items[0]["overdue"]
    maintenance.write_status(items[0]["id"], "done", date(2026, 6, 20))
    after = f.read_text(encoding="utf-8")
    assert "status: done" in after and "done: 2026-06-20" in after
    # everything outside the lines it owns is byte for byte the same
    assert after.replace("status: done\n", "status: open\n").replace("done: 2026-06-20\n", "") == text
    maintenance.write_status(items[0]["id"], "undo", date(2026, 6, 20))
    assert f.read_text(encoding="utf-8") == text


def test_maintenance_refuses_paths_outside_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("JYTTE_TASKS_PATH", str(tmp_path))
    (tmp_path / maintenance.FOLDER).mkdir()
    (tmp_path / "secret.md").write_text("---\ntype: maintenance\n---\n", encoding="utf-8")
    with pytest.raises(ValueError):
        maintenance.write_status("..~secret", "done")


def test_next_cron():
    after = datetime(2026, 6, 19, 15, 7, tzinfo=timezone.utc)   # 17:07 in Copenhagen
    nxt = sources.next_cron("*/15 * * * *", after)
    assert nxt is not None and nxt.astimezone(sources.TZ).minute == 15
    daily = sources.next_cron("0 2 * * *", after)
    assert daily.astimezone(sources.TZ).hour == 2
    assert sources.next_cron("0 0 L * *", after) is None


def test_safe_url():
    assert store.safe_url("javascript:alert(1)") is None
    assert store.safe_url("docs.n8n.io") == "https://docs.n8n.io"
    assert store.safe_url("http://x.lan/a") == "http://x.lan/a"


def test_kr_is_whole_kroner_from_oere():
    assert views.kr(1234500) == "12.345 kr."
    assert views.kr(-41200) == "-412 kr."
    assert views.kr(320000, sign=True) == "+3.200 kr."
