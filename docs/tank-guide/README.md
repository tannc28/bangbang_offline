# Tank guide

Generated pages: `www/tank-guide/` (served at `http://127.0.0.1:19083/tank-guide/`, linked from the homepage).
Never edit those HTML files by hand: edit the sources here and rebuild.

```bash
python3 docs/tank-guide/build.py
```

## Sources

| File | What |
|---|---|
| `build.py` | Reads stats/skills live from the game tables via `server/` code, merges notes and log, writes the pages |
| `notes/<tank_id>.json` | Hand-written analysis of one tank (schema below) |
| `balance-log.json` | Every balance change ever made, oldest first |

## Note schema (`notes/<tank_id>.json`)

Vietnamese prose; game/tech terms may stay English. Every claim must trace to the kit file or a table value.

```json
{
  "summary": "1–2 sentences: what the tank is and how it wins",
  "strengths": ["3–5 items, concrete numbers from the kit/tables"],
  "weaknesses": ["3–5 items"],
  "tips": ["3–4 items: how to play it"],
  "counters": ["2–4 items: how to beat it"],
  "counter_why": "Vietnamese for the native szOpposeIllustrate text",
  "against": "Vietnamese for szKillerTips, only when the native text is untranslated",
  "balance": {
    "status": "strong | ok | weak | review",
    "reason": "why, in one or two sentences",
    "suggestion": "optional: the concrete change you would make, or what to watch"
  },
  "evidence": ["file:function or Template id — the facts the verdict rests on"]
}
```

Status rubric: `strong` = kit gives an outsized edge (long hard-CC chains with burst/execute, near-permanent
immunity, uncapped sustain) and stats are not a drawback; `weak` = bottom-third stats and the kit does not
compensate; `review` = cannot judge from code alone, or code contradicts the skill description; `ok` otherwise.

## Balance log (`balance-log.json`)

Append one entry per change, then update that tank's note and rebuild:

```json
{"date": "YYYY-MM-DD", "tank_id": 10000056, "change": "Space cooldown after execute 1.5s → 2s",
 "reason": "why", "before": "1500 ms", "after": "2000 ms", "files": ["server/quanvu_actions.py"]}
```
