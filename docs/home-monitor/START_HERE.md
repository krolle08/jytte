# Start here

1. Unzip, put the folder where you keep projects, for example `~/dev/home-monitor`.
2. Optional, look at the PoC: `cd ~/dev/home-monitor/poc && python3 -m http.server 8080`, open http://localhost:8080/home-monitor.html
3. Start Claude Code in the folder:

```
cd ~/dev/home-monitor
git init && git add -A && git commit -m "Home Monitor PoC handoff"
claude
```

`CLAUDE.md` is read automatically. Paste this as your first message:

```
Read CLAUDE.md, docs/ARCHITECTURE.md and docs/ROADMAP.md, then open poc/home-monitor.html and the screenshots.
Do roadmap step 0 and step 1 only. Before step 1, ask me the open decisions that block it, one message, short.
Do not start any live adapter yet.
```

Start with steps 0 and 1 because they are safe: no credentials, no behavior change.
