# BangBang offline

## RULE: Every balance change is logged in the tank guide
Any change to a tank's stats or kit (`server/*_actions.py`, tank/skill/buff/effect template values,
bot behaviour that changes a tank's strength) must, in the same change:
1. Append an entry to `docs/tank-guide/balance-log.json` (date, tank_id, change, reason, before, after, files).
2. Update that tank's `docs/tank-guide/notes/<tank_id>.json` (strengths/weaknesses/balance verdict).
3. Rebuild: `python3 docs/tank-guide/build.py` and check the page at `http://127.0.0.1:19083/tank-guide/<tank_id>.html`.

Schema and rubric: `docs/tank-guide/README.md`. Never hand-edit `www/tank-guide/*.html`; it is generated.

## Running on Linux
`Choi_Ngay.bat` is Windows-only. Use `./play.sh` (one-click launcher: free port, waits for /health, opens the
browser, Ctrl+C stops; `--shortcut` adds an app-menu entry). Under the hood it runs:
`BB_DATABASE=$PWD/data/bangbang.sqlite3 BB_ACCELERATION=auto python3 -I -B -X utf8 server/app.py --bind 127.0.0.1 --port 19083 --native-port 49119 --enable-admin-buff --admin-key-file $PWD/data/admin_buff.key`

## Line endings
`.gitattributes` keeps exact bytes (`* -text`); some files are CRLF (e.g. `server/bot_setup.py`).
Preserve each file's existing newline style when editing.
