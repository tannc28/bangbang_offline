"""HTML rendering for the tank guide, built on vendored Tabler + List.js + Chart.js.

Everything loads from www/tank-guide/vendor/ (pinned, MIT), so the guide works
offline like the game itself. build.py collects the data; this file only draws.
"""
from __future__ import annotations

import html
import json
from datetime import date

TABLER = 'vendor/tabler-1.7.3/tabler.min.css'
LISTJS = 'vendor/listjs-2.3.1/list.min.js'
CHARTJS = 'vendor/chartjs-4.6.1/chart.umd.min.js'

VERDICT = {'strong': ('Mạnh', 'red'), 'ok': ('Cân bằng', 'green'), 'review': ('Cần theo dõi', 'blue'),
           'weak': ('Yếu', 'yellow'), 'none': ('Chưa đánh giá', 'secondary')}
ROLE_COLOR = {'Cận chiến': 'orange', 'Tầm trung': 'yellow', 'Tầm xa': 'cyan'}
SCHOOL_COLOR = {'Vật lý': 'orange', 'Năng lượng': 'purple'}
CLASSES = {'Pháp sư': 'purple', 'Chiến sĩ': 'orange', 'Sát thủ': 'red', 'Xạ thủ': 'green',
           'Chống chịu': 'azure', 'Phụ trợ': 'pink'}
FEATURES = ('Bạo phát', 'Khống chế', 'Tiêu hao', 'Sát thương nhóm', 'Chuyển vị trí', 'Linh động', 'Trị liệu',
            'Hồi phục', 'Hút máu', 'Thu hoạch', 'Kết liễu', 'Đánh lui', 'Tịnh hóa', 'Biến thân', 'Ẩn thân',
            'Quấy nhiễu', 'Xuyên thấu', 'Phân thân')
CHART_ROLE = {'Cận chiến': '#f76707', 'Tầm trung': '#f59f00', 'Tầm xa': '#17a2b8'}
STATS = (('ehp', 'Máu hiệu dụng'), ('atk_per_s', 'Công / giây'), ('speed', 'Tốc độ'), ('range', 'Tầm bắn'))

CSS = """
.avatar-tank{background-size:contain;background-repeat:no-repeat;background-color:var(--tblr-bg-surface-secondary)}
.stars{color:var(--tblr-yellow);letter-spacing:1px;white-space:nowrap}
.skill-desc{white-space:pre-line;color:var(--tblr-secondary);font-size:.8125rem}
.pill-group .form-selectgroup-label{padding:.2rem .65rem;font-size:.75rem}
.pill-group .form-selectgroup-item{margin:0 .25rem .35rem 0}
.filter-label{width:92px;flex:none;font-size:.75rem;font-weight:600;color:var(--tblr-secondary);padding-top:.25rem}
.stat-cell{min-width:130px}.stat-cell .progress{height:.4rem}
.table-tank td{vertical-align:middle}.summary{max-width:420px;white-space:normal}
.tank-card .progress{height:.35rem}.note-list li{margin-bottom:.4rem}
.dot-list{list-style:none;padding-left:0}.dot-list li{position:relative;padding-left:1.1rem;margin-bottom:.45rem}
.dot-list li::before{content:"";position:absolute;left:0;top:.55em;width:.5rem;height:.5rem;border-radius:50%;background:var(--dot)}
#scatter{height:340px}#radar{max-height:300px}
"""


def e(text):
    return html.escape(str(text or ''))


def heat(p):
    """Tabler color by percentile among all tanks (low → high)."""
    return 'red' if p < .2 else 'orange' if p < .4 else 'yellow' if p < .6 else 'lime' if p < .8 else 'green'


def stars(n):
    # 0 means the native table has no rating for this tank, not a zero score.
    return f'<span class="stars">{"★" * n}{"☆" * (5 - n)}</span>' if n else '<span class="text-secondary">—</span>'


def status_of(note):
    status = ((note or {}).get('balance') or {}).get('status')
    return status if status in VERDICT else 'none'


def verdict_badge(note):
    label, color = VERDICT[status_of(note)]
    return f'<span class="badge bg-{color}-lt">{label}</span>'


def tags_of(t):
    text = t['tags'].lower()
    return ([c for c in CLASSES if c.lower() in text],
            [f for f in FEATURES if f.lower() in text or (f == 'Kết liễu' and 'liễu' in text)])


def chips(t):
    classes, _ = tags_of(t)
    out = [f'<span class="badge bg-{ROLE_COLOR.get(t["role"], "secondary")}-lt">{e(t["role"])}</span>',
           f'<span class="badge bg-{SCHOOL_COLOR[t["stats"]["school"]]}-lt">{e(t["stats"]["school"])}</span>']
    out += [f'<span class="badge bg-{CLASSES[c]}-lt">{e(c)}</span>' for c in classes]
    return ' '.join(out)


def progress(p, value=None, label=''):
    color = heat(p)
    top = (f'<div class="d-flex mb-1"><span class="small text-secondary">{label}</span>'
           f'<span class="ms-auto small fw-bold">{value}</span></div>') if label else (
           f'<div class="small fw-bold mb-1">{value}</div>' if value is not None else '')
    return (f'{top}<div class="progress progress-sm" title="Hơn {round(p * 100)}% số tank">'
            f'<div class="progress-bar bg-{color}" style="width:{max(4, round(p * 100))}%"></div></div>')


def avatar(url, size='', extra=''):
    style = f' style="background-image:url({e(url)})"' if url else ''
    return f'<span class="avatar avatar-tank {size} {extra}"{style}></span>'


THEME_JS = """
(()=>{const k='tank-guide-theme',r=document.documentElement;
try{const t=localStorage.getItem(k);if(t)r.dataset.bsTheme=t}catch(e){}
document.querySelectorAll('[data-theme-toggle]').forEach(b=>b.onclick=()=>{
const t=r.dataset.bsTheme==='dark'?'light':'dark';r.dataset.bsTheme=t;try{localStorage.setItem(k,t)}catch(e){}})})();
"""


def page(title, body, *, header='', scripts='', desc=''):
    return f"""<!doctype html><html lang="vi" data-bs-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<link rel="stylesheet" href="/tank-guide/{TABLER}"><style>{CSS}</style></head><body>
<div class="page">
<header class="navbar navbar-expand-md d-print-none"><div class="container-fluid">
<a class="navbar-brand fw-bold" href="/tank-guide/">🛡️ Cẩm nang tank</a>
<div class="navbar-nav flex-row gap-1">
<a class="nav-link" href="/html5/">Vào game</a><a class="nav-link" href="/bots.html">Thiết lập trận bot</a>
<a class="nav-link" href="/tank-guide/balance.html">Nhật ký cân bằng</a>
<button class="btn btn-ghost-secondary btn-sm ms-2" data-theme-toggle type="button" title="Đổi giao diện sáng/tối">Sáng / Tối</button>
</div></div></header>
<div class="page-wrapper">
<div class="page-header d-print-none"><div class="container-fluid">{header}</div></div>
<div class="page-body"><div class="container-fluid">{body}</div></div>
<footer class="footer footer-transparent d-print-none"><div class="container-fluid text-secondary small">
Dữ liệu đọc trực tiếp từ bảng của game. Cập nhật {date.today().isoformat()}.
Giao diện: Tabler, List.js, Chart.js (MIT).</div></footer>
</div></div><script>{THEME_JS}</script>{scripts}</body></html>"""


# ---------------------------------------------------------------- index
def render_index(tanks, notes):
    n_all = len(tanks)
    counts = {k: sum(1 for t in tanks if status_of(notes.get(t['id'])) == k) for k in VERDICT}
    rows, cards, points = [], [], []
    for t in sorted(tanks, key=lambda t: t['stat_rank']):
        n = notes.get(t['id']) or {}
        s, p = t['stats'], t['pct']
        classes, features = tags_of(t)
        data = (f'data-verdict="{status_of(n)}" data-role="{e(t["role"])}" data-school="{e(s["school"])}" '
                f'data-tags="{e("|".join(classes + features))}" data-rank="{t["stat_rank"]:03d}" '
                f'data-ehp="{s["ehp"]:05d}" data-aps="{s["atk_per_s"]:04d}" data-speed="{s["speed"]:03d}" '
                f'data-range="{s["range"]:04d}" data-dmg="{t["stars"]["damage"]}" data-surv="{t["stars"]["survival"]}"')
        href = f'{t["id"]}.html'
        rows.append(f"""<tr>
<td><div class="d-flex align-items-center">{avatar(t.get('avatar'), 'me-2')}<div>
<a class="name fw-bold" href="{href}">{e(t['name'])}</a><div class="mt-1">{chips(t)}</div></div></div></td>
<td>{verdict_badge(n)}</td><td class="text-{heat(1 - (t['stat_rank'] - 1) / (n_all - 1))} fw-bold">#{t['stat_rank']}</td>
<td class="stat-cell">{progress(p['ehp'], s['ehp'])}</td><td class="stat-cell">{progress(p['atk_per_s'], s['atk_per_s'])}</td>
<td class="stat-cell">{progress(p['speed'], s['speed'])}</td><td class="stat-cell">{progress(p['range'], s['range'])}</td>
<td>{stars(t['stars']['damage'])}</td><td>{stars(t['stars']['survival'])}</td>
<td class="summary small text-secondary">{e(n.get('summary', ''))}
<span class="d-none meta" {data}></span></td></tr>""")
        cards.append(f"""<div class="col-sm-6 col-lg-4 col-xxl-3"><a class="card card-link card-link-pop tank-card h-100" href="{href}">
<div class="card-status-top bg-{VERDICT[status_of(n)][1]}"></div><div class="card-body">
<div class="d-flex align-items-center mb-3">{avatar(t.get('avatar'), 'avatar-lg', 'me-3')}<div>
<div class="name h3 m-0">{e(t['name'])}</div><div class="mt-1">{verdict_badge(n)}
<span class="badge bg-{heat(1 - (t['stat_rank'] - 1) / (n_all - 1))}-lt">#{t['stat_rank']} chỉ số</span></div></div></div>
<div class="mb-2">{chips(t)}</div>
<div class="row g-2 mb-2">{''.join(f'<div class="col-6">{progress(p[k], s[k], label)}</div>' for k, label in STATS)}</div>
<div class="small text-secondary">{e(n.get('summary', ''))}</div>
<span class="d-none meta" {data}></span></div></a></div>""")
        points.append(dict(x=s['ehp'], y=s['atk_per_s'], name=t['name'], id=t['id'], role=t['role']))

    def pills(group, options):
        return ''.join(
            f'<label class="form-selectgroup-item"><input type="checkbox" class="form-selectgroup-input" '
            f'data-group="{group}" value="{e(v)}"><span class="form-selectgroup-label">'
            f'<span class="badge bg-{color} badge-blink me-1 p-1"></span>{e(text)} '
            f'<span class="text-secondary ms-1">{k}</span></span></label>'
            for v, text, color, k in options if k)

    count = lambda pred: sum(1 for t in tanks if pred(t))
    groups = [
        ('Đánh giá', 'verdict', [(k, VERDICT[k][0], VERDICT[k][1], counts[k]) for k in VERDICT]),
        ('Tầm đánh', 'role', [(r, r, c, count(lambda t, r=r: t['role'] == r)) for r, c in ROLE_COLOR.items()]),
        ('Sát thương', 'school', [(x, x, c, count(lambda t, x=x: t['stats']['school'] == x)) for x, c in SCHOOL_COLOR.items()]),
        ('Lớp', 'tags', [(c, c, col, count(lambda t, c=c: c in tags_of(t)[0])) for c, col in CLASSES.items()]),
        ('Sở trường', 'tags', [(f, f, 'secondary', count(lambda t, f=f: f in tags_of(t)[1])) for f in FEATURES]),
    ]
    filters = ''.join(f'<div class="d-flex"><div class="filter-label">{label}</div>'
                      f'<div class="form-selectgroup form-selectgroup-pills pill-group">{pills(g, opts)}</div></div>'
                      for label, g, opts in groups)
    kpis = ''.join(f"""<div class="col-6 col-lg"><div class="card card-sm"><div class="card-body d-flex align-items-center">
<span class="bg-{VERDICT[k][1]} text-white avatar me-3">{counts[k]}</span><div><div class="fw-bold">{VERDICT[k][0]}</div>
<div class="text-secondary small">{round(100 * counts[k] / n_all)}% số tank</div></div></div></div></div>"""
                   for k in ('strong', 'ok', 'review', 'weak') )
    header = f"""<div class="row align-items-center"><div class="col"><div class="page-pretitle">Bang Bang offline</div>
<h2 class="page-title">Cẩm nang {n_all} tank</h2>
<div class="text-secondary mt-1">Chỉ số cấp 6, kỹ năng gốc, điểm của nhà làm game, phân tích mã kỹ năng và lịch sử cân bằng.</div></div></div>"""
    body = f"""
<div class="row row-deck row-cards mb-3">{kpis}</div>
<div class="row row-cards mb-3">
<div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Trâu hay đau?</h3>
<div class="card-actions small text-secondary">Mỗi chấm là một tank · bấm để mở</div></div>
<div class="card-body"><canvas id="scatter"></canvas></div></div></div>
<div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">Đọc biểu đồ</h3></div>
<div class="card-body small text-secondary">
<p><b>Ngang</b> là máu hiệu dụng (HP tính cả giáp), <b>dọc</b> là công mỗi giây. Góc trên phải vừa trâu vừa đau; góc dưới trái mỏng và yếu, sống nhờ kỹ năng.</p>
<p>Màu theo tầm đánh: <span class="badge bg-orange-lt">Cận chiến</span> <span class="badge bg-yellow-lt">Tầm trung</span> <span class="badge bg-cyan-lt">Tầm xa</span>.</p>
<p class="mb-0">"Hạng chỉ số" chỉ tính thân tank (40% máu hiệu dụng, 40% công/giây, 10% tốc độ, 10% tầm). Cột "Đánh giá" mới tính cả kỹ năng.</p>
</div></div></div></div>
<div class="card mb-3"><div class="card-body">
<div class="d-flex flex-wrap gap-2 mb-3 align-items-center">
<div class="input-icon flex-grow-1" style="max-width:340px"><input class="form-control search" id="q" placeholder="Tìm tank…" autocomplete="off"></div>
<select class="form-select w-auto" id="sort"><option value="rank:asc">Hạng chỉ số</option><option value="ehp:desc">Máu hiệu dụng</option>
<option value="aps:desc">Công / giây</option><option value="speed:desc">Tốc độ</option><option value="range:desc">Tầm bắn</option>
<option value="dmg:desc">Sao sát thương</option><option value="surv:desc">Sao sống sót</option><option value="name:asc">Tên A→Z</option></select>
<div class="btn-group" role="group"><button type="button" class="btn" data-view="table">Bảng</button>
<button type="button" class="btn" data-view="cards">Thẻ</button></div>
<button type="button" class="btn btn-ghost-secondary" id="reset">Xóa lọc</button>
<span class="ms-auto text-secondary" id="shown"></span></div>
{filters}
<div class="small text-secondary mt-1">Trong một nhóm chọn nhiều là "hoặc", giữa các nhóm là "và".</div>
</div></div>
<div id="tableView" class="card"><div class="table-responsive"><table class="table table-vcenter card-table table-tank">
<thead><tr><th>Tank</th><th>Đánh giá</th><th>Hạng</th><th>Máu hiệu dụng</th><th>Công / giây</th><th>Tốc độ</th><th>Tầm</th>
<th>Sát thương</th><th>Sống sót</th><th>Tóm tắt</th></tr></thead><tbody class="list">{''.join(rows)}</tbody></table></div></div>
<div id="cardView" class="d-none"><div class="row row-cards list">{''.join(cards)}</div></div>"""
    scripts = f"""<script src="/tank-guide/{LISTJS}"></script><script src="/tank-guide/{CHARTJS}"></script><script>
const POINTS={json.dumps(points, ensure_ascii=False)},ROLE={json.dumps(CHART_ROLE, ensure_ascii=False)};
(()=>{{const css=getComputedStyle(document.body),ink=()=>css.getPropertyValue('--tblr-secondary').trim()||'#888';
const ch=new Chart(document.getElementById('scatter'),{{type:'scatter',
 data:{{datasets:Object.keys(ROLE).map(r=>({{label:r,data:POINTS.filter(p=>p.role===r),backgroundColor:ROLE[r]+'cc',
  borderColor:ROLE[r],pointRadius:5,pointHoverRadius:8}}))}},
 options:{{maintainAspectRatio:false,plugins:{{legend:{{labels:{{color:ink()}}}},
  tooltip:{{callbacks:{{label:c=>`${{c.raw.name}}: máu ${{c.raw.x}}, công/giây ${{c.raw.y}}`}}}}}},
  scales:{{x:{{title:{{display:true,text:'Máu hiệu dụng',color:ink()}},ticks:{{color:ink()}},grid:{{color:'#8882'}}}},
   y:{{title:{{display:true,text:'Công / giây',color:ink()}},ticks:{{color:ink()}},grid:{{color:'#8882'}}}}}},
  onClick:(ev,els)=>{{if(els.length){{const p=ch.data.datasets[els[0].datasetIndex].data[els[0].index];location.href=p.id+'.html'}}}}}}}});
}})();
(()=>{{const KEY='tank-guide-filters-v2',$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const opts={{valueNames:['name',{{name:'meta',attr:'data-rank'}}]}};
const mk=id=>new List(id,{{listClass:'list',searchClass:'__none'}});
const lists=[mk('tableView'),mk('cardView')];let view='table';
const meta=item=>item.elm.querySelector('.meta').dataset;
function picked(){{const g={{}};$$('[data-group]:checked').forEach(i=>(g[i.dataset.group]||=[]).push(i.value));return g}}
function apply(){{const q=$('#q').value.trim().toLowerCase(),g=picked();
 for(const l of lists)l.filter(it=>{{const d=meta(it);if(q&&!it.elm.querySelector('.name').textContent.toLowerCase().includes(q))return false;
  for(const[k,vals]of Object.entries(g)){{const have=k==='tags'?d.tags.split('|'):[d[k]];if(!vals.some(v=>have.includes(v)))return false}}return true}});
 $('#shown').textContent=`Đang hiện ${{lists[0].matchingItems.length}}/${{lists[0].items.length}} tank`;
 $$('[data-view]').forEach(b=>b.classList.toggle('btn-primary',b.dataset.view===view));
 $('#tableView').classList.toggle('d-none',view!=='table');$('#cardView').classList.toggle('d-none',view!=='cards');
 try{{localStorage.setItem(KEY,JSON.stringify({{g,view,sort:$('#sort').value,q:$('#q').value}}))}}catch(e){{}}}}
function sort(){{const[k,order]=$('#sort').value.split(':');for(const l of lists){{
 l.sort('x',{{sortFunction:(a,b)=>k==='name'?a.elm.querySelector('.name').textContent.localeCompare(b.elm.querySelector('.name').textContent,'vi')
  :(parseFloat(meta(a)[k])-parseFloat(meta(b)[k]))||(meta(a).rank-meta(b).rank),order}})}}apply()}}
try{{const s=JSON.parse(localStorage.getItem(KEY)||'{{}}');view=s.view||'table';if(s.sort)$('#sort').value=s.sort;$('#q').value=s.q||'';
 for(const[k,vals]of Object.entries(s.g||{{}}))vals.forEach(v=>{{const i=$(`[data-group="${{k}}"][value="${{CSS.escape(v)}}"]`);if(i)i.checked=true}})}}catch(e){{}}
$$('[data-group]').forEach(i=>i.onchange=apply);$('#q').oninput=apply;$('#sort').onchange=sort;
$$('[data-view]').forEach(b=>b.onclick=()=>{{view=b.dataset.view;apply()}});
$('#reset').onclick=()=>{{$$('[data-group]').forEach(i=>i.checked=false);$('#q').value='';apply()}};
sort();}})();
</script>"""
    return page(f'Cẩm nang tank · Bang Bang', body, header=header, scripts=scripts, desc=f'Phân tích {n_all} tank')


# ---------------------------------------------------------------- tank page
def render_tank(t, note, log, by_id, order):
    n = note or {}
    s, p = t['stats'], t['pct']
    bal = n.get('balance') or {}
    status = status_of(n)
    idx = order.index(t['id'])
    prev_t, next_t = by_id[order[idx - 1]], by_id[order[(idx + 1) % len(order)]]

    def items(key, color):
        values = n.get(key) or []
        if not values:
            return '<div class="text-secondary">Chưa có.</div>'
        return f'<ul class="dot-list" style="--dot:var(--tblr-{color})">' + ''.join(f'<li>{e(x)}</li>' for x in values) + '</ul>'

    skills = ''.join(f"""<div class="list-group-item"><div class="row align-items-start g-3">
<div class="col-auto">{f'<span class="avatar avatar-md" style="background-image:url({e(k["icon"])})"></span>' if k.get('icon') else '<span class="avatar avatar-md"></span>'}</div>
<div class="col"><div class="d-flex flex-wrap align-items-center gap-2 mb-1"><kbd>{e(k['slot'])}</kbd><span class="fw-bold">{e(k['name'])}</span>
{f'<span class="badge bg-azure-lt">hồi {k["cooldown_s"]:g}s</span>' if k.get('cooldown_s') else ''}
{f'<span class="badge bg-teal-lt">tầm {k["range"]}</span>' if k.get('range') else ''}
{f'<span class="badge bg-purple-lt">{k["charges"]} lần tích</span>' if k.get('charges') else ''}</div>
<div class="skill-desc">{e(k['desc'])}</div></div></div></div>""" for k in t['skills'])

    counter = t.get('counter')
    against = n.get('against') or t.get('against')
    changes = [x for x in log if int(x.get('tank_id', 0)) == t['id']]
    history = ''.join(f"""<div class="list-group-item"><div class="d-flex gap-2"><span class="badge bg-blue-lt">{e(x['date'])}</span>
<div><div class="fw-bold">{e(x['change'])}</div><div class="small text-secondary">{e(x.get('reason', ''))}</div>
{f'<div class="small text-secondary">Trước: {e(x.get("before"))} → Sau: {e(x.get("after"))}</div>' if x.get('before') or x.get('after') else ''}</div></div></div>"""
                      for x in reversed(changes)) or '<div class="list-group-item text-secondary">Chưa có thay đổi nào so với bản gốc.</div>'
    datagrid = ''.join(f'<div class="datagrid-item"><div class="datagrid-title">{label}</div><div class="datagrid-content">{value}</div></div>'
                       for label, value in (
                           ('Máu (HP)', s['hp']), ('Giáp vật lý / năng lượng', f"{s['armor']} / {s['egarmor']}"),
                           ('Công', f"{s['atk']} {s['school'].lower()}"), ('Xuyên giáp', s['pen']),
                           ('Tốc bắn', f"{s['fire_ms']} ms/phát"), ('Hạng chỉ số', f"#{t['stat_rank']}/{len(by_id)}")))
    header = f"""<div class="row align-items-center g-3">
<div class="col-auto">{avatar(t.get('avatar'), 'avatar-xl rounded')}</div>
<div class="col"><div class="page-pretitle"><a href="/tank-guide/">Cẩm nang tank</a> · {e(t['title'])}</div>
<h2 class="page-title">{e(t['name'])}</h2>
<div class="mt-2 d-flex flex-wrap gap-1">{verdict_badge(n)} {chips(t)}</div>
<div class="text-secondary mt-2">{e(t['tags'])}</div></div>
<div class="col-auto d-flex gap-2"><a class="btn" href="{prev_t['id']}.html">← {e(prev_t['name'])}</a>
<a class="btn" href="{next_t['id']}.html">{e(next_t['name'])} →</a></div></div>"""
    body = f"""
<div class="alert alert-{VERDICT[status][1] if status != 'none' else 'secondary'} bg-{VERDICT[status][1]}-lt mb-3"><b>{e(n.get('summary', ''))}</b></div>
<div class="row row-cards mb-3">
<div class="col-lg-4"><div class="card h-100"><div class="card-status-top bg-{VERDICT[status][1]}"></div>
<div class="card-header"><h3 class="card-title">Đánh giá cân bằng</h3><div class="card-actions">{verdict_badge(n)}</div></div>
<div class="card-body"><p>{e(bal.get('reason', ''))}</p>
{f'<div class="alert alert-info mb-0"><div class="fw-bold mb-1">Đề xuất</div>{e(bal["suggestion"])}</div>' if bal.get('suggestion') else ''}</div></div></div>
<div class="col-lg-4"><div class="card h-100"><div class="card-header"><h3 class="card-title">Hồ sơ chỉ số</h3>
<div class="card-actions small text-secondary">so với cả game</div></div><div class="card-body"><canvas id="radar"></canvas></div></div></div>
<div class="col-lg-4"><div class="card h-100"><div class="card-header"><h3 class="card-title">Nhà làm game chấm</h3></div>
<div class="card-body"><div class="row g-2 mb-3">
<div class="col-6"><div class="small text-secondary">Sát thương</div>{stars(t['stars']['damage'])}</div>
<div class="col-6"><div class="small text-secondary">Sống sót</div>{stars(t['stars']['survival'])}</div>
<div class="col-6"><div class="small text-secondary">Hỗ trợ</div>{stars(t['stars']['support'])}</div>
<div class="col-6"><div class="small text-secondary">Độ khó</div>{stars(t['difficulty'])}</div></div>
<div class="datagrid">{datagrid}</div></div></div></div></div>
<div class="row row-cards mb-3">{''.join(f'<div class="col-sm-6 col-lg-3">{progress(p[k], s[k], label)}</div>' for k, label in STATS)}</div>
<div class="card mb-3"><div class="card-header"><h3 class="card-title">Kỹ năng</h3></div><div class="list-group list-group-flush">{skills}</div></div>
<div class="row row-cards mb-3">
<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-status-start bg-green"></div><div class="card-header"><h3 class="card-title text-green">Điểm mạnh</h3></div><div class="card-body">{items('strengths', 'green')}</div></div></div>
<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-status-start bg-red"></div><div class="card-header"><h3 class="card-title text-red">Điểm yếu</h3></div><div class="card-body">{items('weaknesses', 'red')}</div></div></div>
<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-status-start bg-blue"></div><div class="card-header"><h3 class="card-title text-blue">Cách chơi</h3></div><div class="card-body">{items('tips', 'blue')}
{f'<div class="small text-secondary">Mẹo gốc: {e(t["tips"])}</div>' if t.get('tips') else ''}</div></div></div>
<div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-status-start bg-orange"></div><div class="card-header"><h3 class="card-title text-orange">Gặp nó thì làm gì</h3></div><div class="card-body">{items('counters', 'orange')}
{f'<div class="small text-secondary mb-2">Gợi ý gốc: {e(against)}</div>' if against else ''}
{f'<div class="small"><b>Khắc chế theo game gốc:</b> <a href="{counter["id"]}.html">{e(counter["name"])}</a>. {e(n.get("counter_why") or counter["why"])}</div>' if counter else ''}</div></div></div></div>
<div class="row row-cards">
<div class="col-lg-6"><div class="card"><div class="card-header"><h3 class="card-title">Lịch sử điều chỉnh</h3></div><div class="list-group list-group-flush">{history}</div></div></div>
<div class="col-lg-6"><div class="card"><div class="card-header"><h3 class="card-title">Căn cứ</h3><div class="card-actions small text-secondary">{e(t.get('kit_file') or '')}</div></div>
<div class="card-body small text-secondary"><ul class="mb-2">{''.join(f'<li>{e(x)}</li>' for x in n.get('evidence', []))}</ul>
Máu hiệu dụng = HP × (300 + giáp) / 300, trung bình giáp vật lý và năng lượng (server/combat_math.py).</div></div></div></div>"""
    radar = dict(labels=[label for _, label in STATS] + ['Máu gốc'],
                 tank=[round(p[k] * 100) for k, _ in STATS] + [round(p['hp'] * 100)])
    scripts = f"""<script src="/tank-guide/{CHARTJS}"></script><script>
(()=>{{const R={json.dumps(radar, ensure_ascii=False)},css=getComputedStyle(document.body),ink=css.getPropertyValue('--tblr-secondary').trim()||'#888';
new Chart(document.getElementById('radar'),{{type:'radar',data:{{labels:R.labels,datasets:[
{{label:{json.dumps(t['name'], ensure_ascii=False)},data:R.tank,fill:true,backgroundColor:'rgba(247,103,7,.25)',borderColor:'#f76707',pointBackgroundColor:'#f76707'}},
{{label:'Trung bình game',data:R.labels.map(()=>50),fill:false,borderColor:'rgba(150,150,150,.8)',borderDash:[4,4],pointRadius:0}}]}},
options:{{plugins:{{legend:{{labels:{{color:ink}}}},tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: hơn ${{c.raw}}% số tank`}}}}}},
scales:{{r:{{min:0,max:100,ticks:{{display:false,stepSize:25}},grid:{{color:'#8884'}},angleLines:{{color:'#8884'}},pointLabels:{{color:ink,font:{{size:12}}}}}}}}}}}});}})();
</script>"""
    return page(f"{t['name']} · Cẩm nang tank", body, header=header, scripts=scripts, desc=n.get('summary', ''))


# ---------------------------------------------------------------- balance log
def render_log(log, by_id):
    rows = ''.join(f"""<tr><td class="text-nowrap">{e(x['date'])}</td>
<td><a href="{x['tank_id']}.html" class="d-flex align-items-center gap-2">{avatar(by_id.get(int(x['tank_id']), {}).get('avatar'), 'avatar-sm')}
{e(by_id.get(int(x['tank_id']), {}).get('name', x['tank_id']))}</a></td>
<td>{e(x['change'])}<div class="small text-secondary">{e(x.get('reason', ''))}</div></td>
<td class="small">{e(x.get('before', ''))}</td><td class="small">{e(x.get('after', ''))}</td></tr>""" for x in reversed(log))
    body = (f'<div class="card"><div class="table-responsive"><table class="table card-table table-vcenter">'
            f'<thead><tr><th>Ngày</th><th>Tank</th><th>Thay đổi</th><th>Trước</th><th>Sau</th></tr></thead><tbody>{rows}</tbody></table></div></div>'
            if log else '<div class="empty"><p class="empty-title">Chưa có điều chỉnh nào</p>'
                        '<p class="empty-subtitle text-secondary">Mọi thay đổi chỉ số hay kỹ năng so với bản gốc sẽ hiện ở đây, mới nhất ở trên.</p></div>')
    header = '<div class="page-pretitle">Cẩm nang tank</div><h2 class="page-title">Nhật ký cân bằng</h2>'
    return page('Nhật ký cân bằng · Cẩm nang tank', body, header=header)
