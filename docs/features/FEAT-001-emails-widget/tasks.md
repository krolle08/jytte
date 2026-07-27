# Tasks - FEAT-001

- [ ] T1 `manifest.yaml` (name: emails, title: Emails, refresh_minutes: 10, expose_mcp: true)
- [ ] T2 `fetch.py` - env-gated IMAP fetch via `asyncio.to_thread`, classify, normalize, `summary()`
- [ ] T3 Attachment detection helper (Content-Disposition based) + urgency helper
- [ ] T4 `card.html` - three-column buckets, per-email fields + checkmark, `data-ts`
- [ ] T5 `detail.html` + `routes.py` `GET /detail`
- [ ] T6 `mcp.py` - `emails_summary`
- [ ] T7 `.card-emails` grid slot + column CSS in `app/static/styles.css`
- [ ] T8 `.env.example` - EMAIL_* names (no values)
- [ ] T9 `CLAUDE.md`
- [ ] T10 `tests/test_emails.py` (classify, attachment, urgency, unconfigured, no-secret)
- [ ] T11 Boot smoke: `python -c "import app.main"` + docker build
