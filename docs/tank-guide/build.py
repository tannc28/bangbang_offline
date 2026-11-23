"""Tank guide generator: game tables + hand notes + balance log -> static HTML.

Sources (single source of truth, all in this folder):
  notes/<tank_id>.json   hand-written analysis per tank (schema in README.md)
  balance-log.json       every balance change, newest last
Game data is read live from the SQLite tables through the server's own code,
so stats/skills always match the build that is running.

  python3 docs/tank-guide/build.py            # writes www/tank-guide/
  python3 docs/tank-guide/build.py --facts DIR # also dumps facts/<id>.json
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'www' / 'tank-guide'
sys.path.insert(0, str(ROOT / 'server'))
os.environ.setdefault('BB_DATABASE', str(ROOT / 'data' / 'bangbang.sqlite3'))

SLOTS = (('nSkill1', 'E'), ('nSkill4', 'R'), ('nSkill2', 'Space'), ('nSkill3', 'Nội tại'))
ROLE = {'1': 'Cận chiến', '2': 'Tầm trung', '3': 'Tầm xa'}
VCOLOR = {'strong': '#ef4444', 'ok': '#22c55e', 'weak': '#f59e0b', 'review': '#3b82f6'}
VERDICT = {'strong': ('Mạnh', 'bad'), 'ok': ('Cân bằng', 'ok'), 'weak': ('Yếu', 'warn'),
           'review': ('Cần theo dõi', 'info')}


# ---------------------------------------------------------------- game facts
def _translations():
    catalog = json.loads((ROOT / 'www/html5/m81331_locale_catalog.json').read_text(encoding='utf-8'))
    return catalog['translations']


def clean(text, tr=None):
    """Localized, markup-free display text from a native template string."""
    if not text:
        return ''
    if tr is not None:
        text = tr.get(text, text)
    text = text.replace('#ENTER#', '\n')
    text = re.sub(r'#PH_([^#]*?)_IC#', r'\1', text)
    text = re.sub(r'#COLOR_[^_#]*_', '', text)
    text = text.replace('_END#', '').replace('¬', '')
    text = re.sub(r'#[A-Z_]+#', '', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


def _images():
    """Original game art URLs: avatars by appearance id, micro icons, skill icons."""
    html5 = ROOT / 'www/html5'
    garage = json.loads((html5 / 'm8_garage_catalog.json').read_text(encoding='utf-8'))
    robo = json.loads((html5 / 'm7_robo_ui_catalog.json').read_text(encoding='utf-8'))
    newer = json.loads((html5 / 'm81319_tanks_catalog.json').read_text(encoding='utf-8'))
    assets = {k: v.get('url') for k, v in garage['assets'].items()}
    assets.update({k: v.get('url') for k, v in newer['assets'].items() if v.get('url') and k not in assets})
    portraits = {**newer['ui']['portraits'], **robo['portraits']}
    def avatar(external):
        row = portraits.get(str(external)) or {}
        source = row.get('source') or {}
        return source.get('url') or assets.get(source.get('logical')) or assets.get(row.get('logical'))
    def tank(tank_id):
        info = garage['tanks'].get(str(tank_id)) or {}
        externals = [(garage['levels'].get(f'{tank_id}:{lv}') or {}).get('externalId') for lv in (6, 1)]
        big = next((avatar(x) for x in externals if x and avatar(x)), None)
        micro = assets.get(info.get('microIcon'))
        return big or micro, micro or big
    def skill(skill_id):
        return assets.get((garage['skills'].get(f'{skill_id}:1') or {}).get('icon'))
    return tank, skill


def _num(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def collect():
    import logging
    logging.disable(logging.CRITICAL)
    from bot_setup import AI_TANKS
    from combat_data import table_row, tank_stats
    from battle_runtime import tank_action_classes
    import inspect
    tr = _translations()
    tank_art, skill_icon = _images()
    classes = tank_action_classes()
    tanks = []
    for tank_id in sorted(AI_TANKS):
        base = table_row('TankBaseTemplate_table.xml', nTankId=tank_id)
        lv6, lv1 = tank_stats(tank_id, 6), tank_stats(tank_id, 1)
        hp, armor, egarmor = _num(lv6['iHp']), _num(lv6['iArmor']), _num(lv6['iEgArmor'])
        atk, egatk = _num(lv6['iAttack']), _num(lv6['iEgAtk'])
        fire = _num(lv6['iFireInterv'], 1000)
        school = 'Vật lý' if atk >= egatk else 'Năng lượng'
        skills = []
        for column, slot in SLOTS:
            ident = _num(base.get(column))
            if not ident:
                continue
            try:
                row = table_row('SkillTemplate_table.xml', nId=ident)
            except ValueError:
                skills.append(dict(slot=slot, id=ident, name=f'(không có trong SkillTemplate: {ident})',
                                   cooldown_s=None, range=None, charges=None, desc=''))
                continue
            skills.append(dict(slot=slot, id=ident, name=clean(row.get('szName'), tr), icon=skill_icon(ident),
                               cooldown_s=round(_num(row.get('iCoolTime')) / 1000, 1) or None,
                               range=_num(row.get('iRange')) or None,
                               charges=_num(row.get('iStackCount')) if _num(row.get('iStackCount')) > 1 else None,
                               desc=clean(row.get('szDesc'), tr)))
        cls = classes.get(tank_id)
        avatar, micro = tank_art(tank_id)
        oppose = _num(base.get('nOpposeTankId'))
        tanks.append(dict(
            id=tank_id, name=clean(base.get('szName'), tr) or AI_TANKS[tank_id], avatar=avatar, micro=micro,
            title=clean(base.get('szDesc'), tr), tags=clean(base.get('szDescription'), tr),
            role=ROLE.get(base.get('nPosition'), ''), difficulty=_num(base.get('nHard')),
            stars=dict(damage=_num(base.get('nOutputStars')), survival=_num(base.get('nSurvivalStars')),
                       support=_num(base.get('nAssistStars'))),
            tips=clean(base.get('szTips'), tr), against=clean(base.get('szKillerTips'), tr),
            counter=dict(id=oppose, why=clean(base.get('szOpposeIllustrate'), tr)) if oppose else None,
            lv1=dict(hp=_num(lv1['iHp']), atk=max(_num(lv1['iAttack']), _num(lv1['iEgAtk']))),
            stats=dict(hp=hp, armor=armor, egarmor=egarmor, atk=max(atk, egatk), school=school,
                       pen=_num(lv6['iCentesis'] if atk >= egatk else lv6['iEgCtsis']),
                       fire_ms=fire, speed=_num(lv6['iSpeed']), range=_num(lv6['nFireRange']),
                       ehp=round(hp * ((300 + armor) + (300 + egarmor)) / 600),
                       atk_per_s=round(max(atk, egatk) * 1000 / fire)),
            skills=skills,
            kit_file=('server/' + Path(inspect.getfile(cls)).name) if cls else None))
    by_id = {t['id']: t for t in tanks}
    for t in tanks:
        if t['counter']:
            t['counter']['name'] = by_id.get(t['counter']['id'], {}).get('name', str(t['counter']['id']))
    # Percentile among all bot tanks (1.0 = best). Higher is better except fire_ms.
    for key, better_low in (('ehp', False), ('atk_per_s', False), ('speed', False),
                            ('range', False), ('hp', False), ('fire_ms', True)):
        values = sorted(t['stats'][key] for t in tanks)
        for t in tanks:
            v = t['stats'][key]
            below = sum(x < v for x in values) if not better_low else sum(x > v for x in values)
            t.setdefault('pct', {})[key] = round(below / (len(values) - 1), 3)
    for t in tanks:
        p = t['pct']
        t['stat_score'] = round(.4 * p['ehp'] + .4 * p['atk_per_s'] + .1 * p['speed'] + .1 * p['range'], 3)
    for rank, t in enumerate(sorted(tanks, key=lambda t: -t['stat_score']), 1):
        t['stat_rank'] = rank
    return tanks


# ---------------------------------------------------------------- notes/log
def load_notes():
    notes = {}
    for path in sorted((HERE / 'notes').glob('*.json')):
        notes[int(path.stem)] = json.loads(path.read_text(encoding='utf-8'))
    return notes


def load_log():
    path = HERE / 'balance-log.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


# ---------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0f1a1f;--panel:#16252c;--panel2:#1c3039;--ink:#eef6f7;--ink2:#a9c1c6;--line:#2b434d;
--accent:#ffd77a;--ok:#5fd38d;--warn:#f3b64a;--bad:#ff7a6b;--info:#6cb8ff}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f6f2e8;--panel:#fffdf7;--panel2:#f1eadb;
--ink:#1d2a2f;--ink2:#56666b;--line:#e0d6c2;--accent:#a06b00;--ok:#1d8a4c;--warn:#9a6400;--bad:#c0392b;--info:#1f6fb5}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 "Segoe UI",system-ui,Arial,sans-serif}
a{color:var(--info)}main{padding:20px clamp(16px,3vw,40px) 60px}
header.top{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:14px clamp(16px,3vw,40px);
background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
header.top .brand{font-weight:800;color:var(--accent);text-decoration:none}
h1{margin:.2em 0 .1em;font-size:28px}h2{margin:28px 0 10px;font-size:19px;color:var(--accent)}
.muted{color:var(--ink2)}.small{font-size:13px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:700;
border:1px solid currentColor;margin-right:6px}
.badge.ok{color:var(--ok)}.badge.warn{color:var(--warn)}.badge.bad{color:var(--bad)}.badge.info{color:var(--info)}
table{width:100%;border-collapse:collapse}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:13px;cursor:pointer;white-space:nowrap}td.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{height:6px;border-radius:3px;background:var(--panel2);overflow:hidden;min-width:60px}.bar>i{display:block;height:100%;background:var(--accent)}
.stars{color:var(--accent);letter-spacing:1px}ul{margin:.3em 0;padding-left:1.2em}li{margin:.2em 0}
.skill{border-left:3px solid var(--accent);padding:4px 0 4px 12px;margin:10px 0}
.skill .k{display:inline-block;min-width:54px;font-weight:800;color:var(--accent)}
.desc{white-space:pre-line;color:var(--ink2);font-size:14px}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.toolbar input,.toolbar select{background:var(--panel);
color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font:inherit}
.wrap{overflow-x:auto}.tank-link{font-weight:700;text-decoration:none}
.log{border-left:3px solid var(--info);padding:4px 0 4px 12px;margin:8px 0}
.card table td:first-child{white-space:nowrap}
.hero{display:flex;gap:18px;align-items:center}.hero img{width:120px;height:120px;object-fit:contain;
border-radius:16px;background:var(--panel2);border:1px solid var(--line)}
.skill{display:grid;grid-template-columns:48px 1fr;gap:12px;align-items:start}
.skill img,.skill .noicon{width:48px;height:48px;border-radius:8px;border:1px solid var(--line);background:var(--panel2)}
.badge{white-space:nowrap}td.tank{min-width:230px}td.nowrap{white-space:nowrap}
.intro{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-end}
.legend{display:flex;gap:6px;align-items:center;color:var(--ink2)}.legend i{width:16px;height:8px;border-radius:3px;display:inline-block;margin-left:8px}
.filters{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:14px 0;display:grid;gap:8px}
.fgroup{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.flabel{color:var(--ink2);font-size:12px;font-weight:700;
min-width:78px;display:inline-flex;gap:6px;align-items:center}
.filters input,.filters select{background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font:inherit}
.filters input{min-width:220px}
.chip{--c:#94a3b8;display:inline-flex;align-items:center;gap:4px;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:700;
color:var(--c);background:color-mix(in srgb,var(--c) 14%,transparent);border:1px solid color-mix(in srgb,var(--c) 45%,transparent);white-space:nowrap}
button.chip{cursor:pointer;font:inherit;font-size:12px;font-weight:700;padding:3px 11px}
button.chip small{opacity:.7;font-weight:600}
button.chip[aria-pressed="true"]{background:var(--c);color:#111;border-color:var(--c)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button,.ghost{background:transparent;color:var(--ink);border:0;padding:6px 12px;font:inherit;cursor:pointer}
.ghost{border:1px solid var(--line);border-radius:8px}.seg button[aria-pressed="true"]{background:var(--accent);color:#111;font-weight:700}
.hbar{display:grid;grid-template-columns:44px 1fr;gap:8px;align-items:center;min-width:120px}
.card .hbar{min-width:0;grid-template-columns:1fr}.hbar .v{text-align:right;font-variant-numeric:tabular-nums;font-size:13px}.hbar .bar{height:8px}
td.rank{font-weight:800;color:var(--c)}td.sum{max-width:360px}
.badge.ok{background:color-mix(in srgb,var(--ok) 15%,transparent)}.badge.bad{background:color-mix(in srgb,var(--bad) 15%,transparent)}
.badge.warn{background:color-mix(in srgb,var(--warn) 15%,transparent)}.badge.info{background:color-mix(in srgb,var(--info) 12%,transparent)}
.cards{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}
.tcard{display:grid;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;color:var(--ink);
text-decoration:none;transition:transform .12s,border-color .12s}.tcard:hover{transform:translateY(-2px);border-color:var(--accent)}
.tcard[hidden],tr[hidden]{display:none}.tc-top{display:flex;gap:12px;align-items:center}
.tc-top img{width:72px;height:72px;object-fit:contain;border-radius:12px;background:var(--panel2)}
.tc-top b{font-size:17px}.tc-stats{display:grid;grid-template-columns:52px 1fr;gap:4px 8px;font-size:12px;color:var(--ink2);align-items:center}
.micro{width:34px;height:34px;object-fit:contain;vertical-align:middle;margin-right:8px;border-radius:6px;background:var(--panel2)}
"""

SORT_JS = """
(()=>{const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const rows=$('#rows');if(!rows)return;const cards=$('#cardView'),KEY='tank-guide-filters';
const items=()=>[...rows.children,...cards.children];const picked={};let view='table';
const load=()=>{try{const v=JSON.parse(localStorage.getItem(KEY)||'{}');Object.assign(picked,v.picked||{});
view=v.view||'table';$('#sort').value=v.sort||'rank';}catch(e){}};
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify({picked,view,sort:$('#sort').value}))}catch(e){}};
function apply(){const q=$('#q').value.trim().toLowerCase();let shown=0;
 for(const el of items()){const d=el.dataset;let ok=!q||d.name.includes(q);
  for(const[g,vals]of Object.entries(picked)){if(!vals.length)continue;
   const have=g==='tags'?d.tags.split('|'):[d[g]];if(!vals.some(v=>have.includes(v)))ok=false;}
  el.hidden=!ok;if(ok&&el.tagName==='TR')shown++;}
 $('#shown').textContent='Đang hiện '+shown+'/'+rows.children.length+' tank';
 $$('.pick').forEach(b=>b.setAttribute('aria-pressed',(picked[b.dataset.group]||[]).includes(b.dataset.value)));
 $$('.seg [data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view===view));
 $('#tableView').hidden=view!=='table';cards.hidden=view!=='cards';save();}
function sort(){const k=$('#sort').value,asc=k==='rank'||k==='title';
 const cmp=(a,b)=>{const x=a.dataset[k],y=b.dataset[k];
  return k==='title'?x.localeCompare(y,'vi'):((asc?1:-1)*(parseFloat(x)-parseFloat(y))||a.dataset.rank-b.dataset.rank)};
 for(const box of[rows,cards])[...box.children].sort(cmp).forEach(el=>box.append(el));apply();}
$$('.pick').forEach(b=>b.onclick=()=>{const g=b.dataset.group,v=b.dataset.value,list=picked[g]||(picked[g]=[]);
 const i=list.indexOf(v);i<0?list.push(v):list.splice(i,1);apply();});
$$('.seg [data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;apply();});
$('#q').oninput=apply;$('#sort').onchange=sort;
$('#reset').onclick=()=>{for(const k in picked)delete picked[k];$('#q').value='';apply();};
load();sort();})();
"""


def e(text):
    return html.escape(str(text or ''))


def page(title, body, *, desc=''):
    return (f'<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Cache-Control" content="no-store">'
            f'<title>{e(title)}</title><meta name="description" content="{e(desc)}">'
            f'<style>{CSS}</style></head><body>'
            f'<header class="top"><a class="brand" href="/tank-guide/">Cẩm nang tank</a>'
            f'<a href="/html5/">Vào game</a><a href="/bots.html">Thiết lập trận bot</a>'
            f'<a href="/tank-guide/balance.html">Nhật ký cân bằng</a></header>'
            f'<main>{body}</main><script>{SORT_JS}</script></body></html>')


def stars(n):
    # 0 means the native table has no rating for this tank, not a zero score.
    return '★' * n + '☆' * max(0, 5 - n) if n else '<span class="muted">—</span>'


def verdict_badge(note):
    if not note or note.get('balance', {}).get('status') not in VERDICT:
        return '<span class="badge info">Chưa đánh giá</span>'
    label, tone = VERDICT[note['balance']['status']]
    return f'<span class="badge {tone}">{label}</span>'


def render_tank(t, note, log, by_id):
    s, p = t['stats'], t['pct']
    rows = [('Máu (HP)', s['hp'], p['hp'], ''), ('Máu hiệu dụng', s['ehp'], p['ehp'], 'HP tính cả giáp'),
            ('Công / giây', s['atk_per_s'], p['atk_per_s'], f"Công {s['atk']} {s['school'].lower()}, {s['fire_ms']} ms/phát"),
            ('Tốc độ chạy', s['speed'], p['speed'], ''), ('Tầm bắn', s['range'], p['range'], '')]
    stat_rows = ''.join(f'<tr><td>{a}{f"<div class=\"muted small\">{d}</div>" if d else ""}</td><td class="num">{b}</td><td style="width:45%">{bar(c)}</td></tr>'
                        for a, b, c, d in rows)
    skills = ''.join(
        f'<div class="skill">'
        f'{f"<img src=\"{e(k["icon"])}\" alt=\"\" loading=\"lazy\">" if k.get("icon") else "<span class=\"noicon\"></span>"}'
        f'<div><span class="k">{e(k["slot"])}</span><b>{e(k["name"])}</b>'
        f'<span class="muted small"> · {" · ".join(x for x in (f"hồi {k["cooldown_s"]}s" if k["cooldown_s"] else "", f"tầm {k["range"]}" if k["range"] else "", f"{k["charges"]} lần tích" if k["charges"] else "") if x)}</span>'
        f'<div class="desc">{e(k["desc"])}</div></div></div>' for k in t['skills'])
    n = note or {}
    def lst(key):
        items = n.get(key) or []
        return '<ul>' + ''.join(f'<li>{e(x)}</li>' for x in items) + '</ul>' if items else '<p class="muted">Chưa có.</p>'
    bal = n.get('balance') or {}
    counter = t['counter']
    counter_html = (f'<p><b>Khắc chế theo game gốc:</b> <a href="{counter["id"]}.html">{e(counter["name"])}</a>. '
                    f'{e(n.get("counter_why") or counter["why"])}</p>') if counter else ''
    against = n.get('against') or t['against']
    changes = [x for x in log if int(x.get('tank_id', 0)) == t['id']]
    log_html = ''.join(f'<div class="log"><b>{e(x["date"])}</b> · {e(x["change"])}'
                       f'<div class="muted small">{e(x.get("reason", ""))}</div></div>' for x in reversed(changes)) \
        or '<p class="muted">Chưa có thay đổi nào so với bản gốc.</p>'
    body = f"""
<p class="muted small"><a href="/tank-guide/">← Tất cả tank</a></p>
<div class="hero">{f'<img src="{e(t["avatar"])}" alt="{e(t["name"])}">' if t.get('avatar') else ''}<div>
<h1>{e(t['name'])}</h1>
<p>{verdict_badge(note)}<span class="badge info">{e(t['role'])}</span>
<span class="muted">{e(t['title'])}{' · ' + e(t['tags']) if t['tags'] else ''}</span></p></div></div>
<p>{e(n.get('summary', ''))}</p>
<div class="grid">
 <div class="card"><h2 style="margin-top:0">Đánh giá cân bằng</h2>
  <p>{verdict_badge(note)} {e(bal.get('reason', ''))}</p>
  {f'<p><b>Đề xuất:</b> {e(bal["suggestion"])}</p>' if bal.get('suggestion') else ''}</div>
 <div class="card"><h2 style="margin-top:0">Nhà làm game chấm</h2>
  <table><tr><td>Sát thương</td><td class="stars">{stars(t['stars']['damage'])}</td></tr>
  <tr><td>Sống sót</td><td class="stars">{stars(t['stars']['survival'])}</td></tr>
  <tr><td>Hỗ trợ</td><td class="stars">{stars(t['stars']['support'])}</td></tr>
  <tr><td>Độ khó</td><td class="stars">{stars(t['difficulty'])}</td></tr></table></div>
 <div class="card"><h2 style="margin-top:0">Chỉ số cấp 6</h2>
  <p class="muted small">Hạng chỉ số: {t['stat_rank']}/{len(by_id)} (chưa tính kỹ năng)</p>
  <table>{stat_rows}</table></div>
</div>
<h2>Kỹ năng</h2>{skills}
<div class="grid">
 <div class="card"><h2 style="margin-top:0">Điểm mạnh</h2>{lst('strengths')}</div>
 <div class="card"><h2 style="margin-top:0">Điểm yếu</h2>{lst('weaknesses')}</div>
 <div class="card"><h2 style="margin-top:0">Cách chơi</h2>{lst('tips')}
  {f'<p class="muted small">Mẹo gốc: {e(t["tips"])}</p>' if t['tips'] else ''}</div>
 <div class="card"><h2 style="margin-top:0">Gặp nó thì làm gì</h2>{lst('counters')}
  {f'<p class="muted small">Gợi ý gốc: {e(against)}</p>' if against else ''}{counter_html}</div>
</div>
<h2>Lịch sử điều chỉnh</h2>{log_html}
<p class="muted small">Chỉ số đọc trực tiếp từ bảng TankUpTemplate cấp 6; máu hiệu dụng = HP × (300 + giáp) / 300,
trung bình giáp vật lý và năng lượng (công thức trong server/combat_math.py). Mã kỹ năng: {e(t['kit_file'] or '')}.
Cập nhật {date.today().isoformat()}.</p>"""
    return page(f"{t['name']} · Cẩm nang tank", body, desc=n.get('summary', ''))


CLASSES = ('Pháp sư', 'Chiến sĩ', 'Sát thủ', 'Xạ thủ', 'Chống chịu', 'Phụ trợ')
FEATURES = ('Bạo phát', 'Khống chế', 'Tiêu hao', 'Sát thương nhóm', 'Chuyển vị trí', 'Linh động', 'Trị liệu',
            'Hồi phục', 'Hút máu', 'Thu hoạch', 'Kết liễu', 'Đánh lui', 'Tịnh hóa', 'Biến thân', 'Ẩn thân',
            'Quấy nhiễu', 'Xuyên thấu', 'Phân thân')
CLASS_COLOR = {'Pháp sư': '#a78bfa', 'Chiến sĩ': '#f59e0b', 'Sát thủ': '#ef4444', 'Xạ thủ': '#22c55e',
               'Chống chịu': '#38bdf8', 'Phụ trợ': '#f472b6'}
ROLE_COLOR = {'Cận chiến': '#f97316', 'Tầm trung': '#eab308', 'Tầm xa': '#06b6d4'}
SCHOOL_COLOR = {'Vật lý': '#fb923c', 'Năng lượng': '#818cf8'}


def tags_of(t):
    text = t['tags'].lower()
    return ([c for c in CLASSES if c.lower() in text],
            [f for f in FEATURES if f.lower() in text or (f == 'Kết liễu' and 'chém' in text and 'liễu' in text)])


def heat(p):
    """Red (bottom of the game) → amber → green (top), by percentile."""
    return f'hsl({round(p * 125)} 70% 48%)'


def bar(p, value=None):
    width = max(4, round(p * 100))
    label = f'<span class="v">{value}</span>' if value is not None else ''
    return (f'<div class="hbar" title="Hơn {round(p * 100)}% số tank">{label}'
            f'<div class="bar"><i style="width:{width}%;background:{heat(p)}"></i></div></div>')


def chip(text, color, cls=''):
    return f'<span class="chip {cls}" style="--c:{color}">{e(text)}</span>'


def render_index(tanks, notes):
    rows, cards = [], []
    count = lambda pred: sum(1 for t in tanks if pred(t))
    for t in sorted(tanks, key=lambda t: t['stat_rank']):
        n = notes.get(t['id']) or {}
        status = (n.get('balance') or {}).get('status', '') or 'none'
        classes, features = tags_of(t)
        s, p = t['stats'], t['pct']
        data = (f'data-name="{e(t["name"].lower())}" data-verdict="{status}" data-role="{e(t["role"])}" '
                f'data-school="{e(s["school"])}" data-tags="{e("|".join(classes + features))}" '
                f'data-rank="{t["stat_rank"]}" data-ehp="{s["ehp"]}" data-aps="{s["atk_per_s"]}" '
                f'data-speed="{s["speed"]}" data-range="{s["range"]}" data-dmg="{t["stars"]["damage"]}" '
                f'data-surv="{t["stars"]["survival"]}" data-diff="{t["difficulty"]}" data-title="{e(t["name"])}"')
        chips = (chip(t['role'], ROLE_COLOR.get(t['role'], '#888')) + chip(s['school'], SCHOOL_COLOR[s['school']])
                 + ''.join(chip(c, CLASS_COLOR[c]) for c in classes))
        img = f'<img class="micro" src="{e(t["micro"])}" alt="" loading="lazy">' if t.get('micro') else ''
        rows.append(
            f'<tr {data}><td class="tank">{img}<a class="tank-link" href="{t["id"]}.html">{e(t["name"])}</a>'
            f'<div class="chips">{chips}</div></td>'
            f'<td>{verdict_badge(n)}</td><td class="num rank" style="--c:{heat(1 - (t["stat_rank"] - 1) / (len(tanks) - 1))}">{t["stat_rank"]}</td>'
            f'<td>{bar(p["ehp"], s["ehp"])}</td><td>{bar(p["atk_per_s"], s["atk_per_s"])}</td>'
            f'<td>{bar(p["speed"], s["speed"])}</td><td>{bar(p["range"], s["range"])}</td>'
            f'<td class="stars">{stars(t["stars"]["damage"])}</td><td class="stars">{stars(t["stars"]["survival"])}</td>'
            f'<td class="muted small sum">{e(n.get("summary", ""))}</td></tr>')
        big = f'<img src="{e(t["avatar"])}" alt="" loading="lazy">' if t.get('avatar') else ''
        cards.append(
            f'<a class="tcard" href="{t["id"]}.html" {data}><div class="tc-top">{big}<div>'
            f'<b>{e(t["name"])}</b><div>{verdict_badge(n)}</div><div class="muted small">#{t["stat_rank"]} chỉ số</div></div></div>'
            f'<div class="chips">{chips}</div>'
            f'<div class="tc-stats"><span>Máu</span>{bar(p["ehp"], s["ehp"])}<span>Công/s</span>{bar(p["atk_per_s"], s["atk_per_s"])}'
            f'<span>Tốc độ</span>{bar(p["speed"], s["speed"])}<span>Tầm</span>{bar(p["range"], s["range"])}</div>'
            f'<div class="muted small sum">{e(n.get("summary", ""))}</div></a>')

    def group(name, label, options):
        btns = ''.join(f'<button type="button" class="chip pick" data-group="{name}" data-value="{e(v)}" '
                       f'style="--c:{c}">{e(text)} <small>{k}</small></button>' for v, text, c, k in options if k)
        return f'<div class="fgroup"><span class="flabel">{label}</span>{btns}</div>'

    verdict_opts = [(k, VERDICT[k][0], VCOLOR[k], count(lambda t, k=k: ((notes.get(t['id']) or {}).get('balance') or {}).get('status') == k))
                    for k in ('strong', 'ok', 'review', 'weak')]
    verdict_opts.append(('none', 'Chưa đánh giá', '#94a3b8', count(lambda t: not ((notes.get(t['id']) or {}).get('balance') or {}).get('status'))))
    role_opts = [(r, r, ROLE_COLOR[r], count(lambda t, r=r: t['role'] == r)) for r in ROLE_COLOR]
    school_opts = [(x, x, SCHOOL_COLOR[x], count(lambda t, x=x: t['stats']['school'] == x)) for x in SCHOOL_COLOR]
    class_opts = [(c, c, CLASS_COLOR[c], count(lambda t, c=c: c in tags_of(t)[0])) for c in CLASSES]
    feat_opts = [(f, f, '#94a3b8', count(lambda t, f=f: f in tags_of(t)[1])) for f in FEATURES]
    body = f"""
<div class="intro"><div><h1>Cẩm nang tank</h1>
<p class="muted">{len(tanks)} tank · chỉ số cấp 6, kỹ năng gốc, đánh giá của nhà làm game, phân tích mã kỹ năng
và lịch sử điều chỉnh cân bằng.</p></div>
<div class="legend small"><span>Thanh màu:</span><i style="background:{heat(0)}"></i>yếu nhất game
<i style="background:{heat(.5)}"></i>trung bình<i style="background:{heat(1)}"></i>mạnh nhất game</div></div>
<div class="filters">
<div class="fgroup"><input id="q" placeholder="Tìm tank…" autocomplete="off">
<label class="flabel">Sắp xếp<select id="sort">
<option value="rank">Hạng chỉ số</option><option value="ehp">Máu hiệu dụng</option><option value="aps">Công / giây</option>
<option value="speed">Tốc độ chạy</option><option value="range">Tầm bắn</option><option value="dmg">Sao sát thương</option>
<option value="surv">Sao sống sót</option><option value="diff">Độ khó</option><option value="title">Tên A→Z</option></select></label>
<span class="seg"><button type="button" data-view="table" aria-pressed="true">Bảng</button><button type="button" data-view="cards">Thẻ</button></span>
<button type="button" id="reset" class="ghost">Xóa lọc</button><span id="shown" class="muted small"></span></div>
{group('verdict', 'Đánh giá', verdict_opts)}{group('role', 'Tầm đánh', role_opts)}{group('school', 'Sát thương', school_opts)}
{group('tags', 'Lớp', class_opts)}{group('tags', 'Sở trường', feat_opts)}
</div>
<div id="tableView" class="wrap"><table><thead><tr><th>Tank</th><th>Đánh giá</th><th>Hạng</th><th>Máu hiệu dụng</th>
<th>Công / giây</th><th>Tốc độ</th><th>Tầm</th><th>Sát thương</th><th>Sống sót</th><th>Tóm tắt</th></tr></thead>
<tbody id="rows">{''.join(rows)}</tbody></table></div>
<div id="cardView" class="cards" hidden>{''.join(cards)}</div>
<p class="muted small">"Hạng" chỉ tính thân tank (40% máu hiệu dụng, 40% công/giây, 10% tốc độ, 10% tầm), chưa tính kỹ năng;
cột "Đánh giá" mới tính cả kỹ năng. Sao là điểm nhà làm game chấm; "—" là bảng gốc không chấm.
Trong một nhóm, chọn nhiều chip là "hoặc"; giữa các nhóm là "và".</p>"""
    return page('Cẩm nang tank · Bang Bang', body, desc='Phân tích 91 tank')


def render_log(log, by_id):
    items = ''.join(
        f'<div class="log"><b>{e(x["date"])}</b> · <a href="{x["tank_id"]}.html">{e(by_id.get(int(x["tank_id"]), {}).get("name", x["tank_id"]))}</a>'
        f' · {e(x["change"])}<div class="muted small">{e(x.get("reason", ""))}</div>'
        f'{f"<div class=\"muted small\">Trước: {e(x["before"])} → Sau: {e(x["after"])}</div>" if x.get("before") or x.get("after") else ""}</div>'
        for x in reversed(log)) or '<p class="muted">Chưa có thay đổi cân bằng nào so với bản gốc.</p>'
    return page('Nhật ký cân bằng · Cẩm nang tank',
                f'<h1>Nhật ký cân bằng</h1><p class="muted">Mọi điều chỉnh chỉ số hay kỹ năng, mới nhất ở trên.</p>{items}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--facts', help='also dump per-tank facts JSON into this folder')
    args = ap.parse_args()
    tanks = collect()
    by_id = {t['id']: t for t in tanks}
    if args.facts:
        Path(args.facts).mkdir(parents=True, exist_ok=True)
        for t in tanks:
            (Path(args.facts) / f"{t['id']}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding='utf-8')
    notes, log = load_notes(), load_log()
    sys.path.insert(0, str(HERE))
    import render
    order = [t['id'] for t in sorted(tanks, key=lambda t: t['stat_rank'])]
    OUT.mkdir(parents=True, exist_ok=True)
    for t in tanks:
        (OUT / f"{t['id']}.html").write_text(render.render_tank(t, notes.get(t['id']), log, by_id, order), encoding='utf-8')
    (OUT / 'index.html').write_text(render.render_index(tanks, notes), encoding='utf-8')
    (OUT / 'balance.html').write_text(render.render_log(log, by_id), encoding='utf-8')
    print(f'wrote {len(tanks) + 2} pages to {OUT.relative_to(ROOT)}; notes {len(notes)}/{len(tanks)}; log {len(log)}')


if __name__ == '__main__':
    main()
