"""End-of-match story: a few lines that retell what happened in this match.

Moments are collected from real kills and score changes while the match runs
(first blood, streaks, multi-kills, shutdowns, comebacks, a bot hunting the
player, the player's revenge). At the end the best few become S1596:
u16 count, then each line as u16-length UTF-8. Only public match facts are used.
State lives in ``arena.pk['story']`` with string keys.
"""
from __future__ import annotations

import struct

STORY_MSG = 1596
MAX_LINES = 6
PK_MAPS = frozenset((1, 4, 17, 18, 19, 20, 21, 34, 35, 36))
FLAG_MAPS = frozenset((7, 9, 10, 37, 170))


def _story(arena):
    pk = getattr(arena, 'pk', None)
    if not isinstance(pk, dict):
        return None
    return pk.setdefault('story', dict(first=None, best_streak={}, best_multi={}, shutdowns=[],
                                       deficit={'1': 0, '2': 0}, lead={'1': 0, '2': 0},
                                       last_killer={}, revenges=[], kills={}, deaths={}))


def _name(actor):
    return str(actor.info.get('name') or '').strip()[:16] if actor is not None else ''


def _clock(arena, now):
    begin = (arena.pk or {}).get('begin')
    seconds = max(0, int((now - begin) / 1000)) if isinstance(begin, (int, float)) else 0
    return f'{seconds // 60}:{seconds % 60:02d}'


def active(arena):
    from bot_setup import BOT_MAPS
    pk = getattr(arena, 'pk', None)
    return (isinstance(pk, dict) and arena.geometry.id in BOT_MAPS
            and not getattr(arena, 'tank_test', False))


def sample_score(arena):
    """Remember the largest deficit and lead each camp ever had."""
    if not active(arena):
        return
    story = _story(arena)
    scores = arena.pk.get('scores') or {}
    for camp in (1, 2):
        mine, theirs = scores.get(camp, 0), scores.get(3 - camp, 0)
        if isinstance(mine, (int, float)) and isinstance(theirs, (int, float)):
            key = str(camp)
            story['deficit'][key] = max(story['deficit'][key], theirs - mine)
            story['lead'][key] = max(story['lead'][key], mine - theirs)


def on_kill(arena, killer, victim, *, multi, streak, first, dead_streak, now):
    from battle_participants import human
    if not active(arena) or victim is None or victim.info.get('npc_template'):
        return
    story = _story(arena)
    vkey = str(victim.id)
    story['deaths'][vkey] = story['deaths'].get(vkey, 0) + 1
    if killer is None or killer.camp == victim.camp or killer.info.get('map_object'):
        sample_score(arena)
        return
    kkey = str(killer.id)
    story['kills'][kkey] = story['kills'].get(kkey, 0) + 1
    if first and story['first'] is None:
        story['first'] = dict(killer=_name(killer), victim=_name(victim), at=_clock(arena, now))
    if streak > story['best_streak'].get('n', 0):
        story['best_streak'] = dict(n=streak, name=_name(killer), human=human(killer))
    if multi > story['best_multi'].get('n', 1):
        story['best_multi'] = dict(n=multi, name=_name(killer), human=human(killer))
    if dead_streak >= 3:
        story['shutdowns'].append(dict(killer=_name(killer), victim=_name(victim), n=dead_streak,
                                       human=human(killer) or human(victim)))
    if human(killer) and story['last_killer'].get(kkey) == victim.id:
        story['revenges'].append(_name(victim))
        story['last_killer'].pop(kkey, None)
    if human(victim):
        story['last_killer'][vkey] = killer.id
    sample_score(arena)


def _lines(arena):
    from battle_participants import human
    story = _story(arena)
    pk = arena.pk
    winner = pk.get('winner')
    humans = [a for a in arena.actors.values() if human(a)]
    player = humans[0] if len(humans) == 1 else None
    scores = pk.get('scores') or {}
    candidates = []   # (priority, text) — higher priority first

    # Comeback / collapse, from the player's side when there is one.
    big = 5 if arena.geometry.id in PK_MAPS else 250 if arena.geometry.id in FLAG_MAPS else None
    if big and winner:
        loser = 3 - winner
        if story['deficit'][str(winner)] >= big:
            side = ('Đội bạn' if player and player.camp == winner else 'Đội đối thủ')
            candidates.append((9, f'Lật kèo! {side} từng bị dẫn {story["deficit"][str(winner)]} điểm mà vẫn thắng.'))
        elif story['lead'][str(loser)] >= big:
            side = ('Đội bạn' if player and player.camp == loser else 'Đội đối thủ')
            candidates.append((8, f'{side} từng dẫn {story["lead"][str(loser)]} điểm nhưng để thua ngược.'))
        elif abs(scores.get(1, 0) - scores.get(2, 0)) <= max(1, big // 5):
            candidates.append((6, f'Nghẹt thở đến phút chót: {scores.get(1, 0)}–{scores.get(2, 0)}.'))

    if player is not None:
        pairs = (pk.get('bot_mind') or {}).get('pairs', {})
        hunters = [(n, arena.actors.get(int(key.split('>')[0])))
                   for key, n in pairs.items() if key.endswith(f'>{player.id}') and n >= 3]
        hunters = [(n, a) for n, a in hunters if a is not None and a.camp != player.camp]
        if hunters:
            n, bot = max(hunters, key=lambda item: item[0])
            candidates.append((8, f'{_name(bot)} săn bạn cả trận: hạ bạn {n} lần.'))
        if story['revenges']:
            names = ', '.join(dict.fromkeys(story['revenges']))
            candidates.append((7, f'Bạn đã trả thù được {names}.'))
        mine_k = story['kills'].get(str(player.id), 0)
        mine_d = story['deaths'].get(str(player.id), 0)
        if mine_k or mine_d:
            candidates.append((3, f'Bạn: {mine_k} lần hạ địch, {mine_d} lần ngã.'))

    streak = story['best_streak']
    if streak.get('n', 0) >= 4:
        who = 'Bạn' if streak.get('human') else streak['name']
        candidates.append((7 if streak.get('human') else 5, f'Chuỗi dài nhất: {who} hạ liền {streak["n"]} mạng không chết.'))
    multi = story['best_multi']
    if multi.get('n', 0) >= 3:
        who = 'Bạn' if multi.get('human') else multi['name']
        candidates.append((6, f'{who} ăn {multi["n"]} mạng trong một pha.'))
    for row in story['shutdowns'][-2:]:
        candidates.append((6 if row.get('human') else 4,
                           f'{row["killer"]} chặn đứng chuỗi {row["n"]} mạng của {row["victim"]}.'))
    if story['first']:
        f = story['first']
        candidates.append((2, f'First blood {f["at"]}: {f["killer"]} hạ {f["victim"]}.'))
    if story['kills']:
        key, n = max(story['kills'].items(), key=lambda item: item[1])
        top = arena.actors.get(int(key))
        if top is not None and n >= 5:
            who = 'Bạn' if player is not None and top is player else _name(top)
            candidates.append((4, f'Bá chủ trận đấu: {who} với {n} lần hạ địch.'))
    candidates.sort(key=lambda item: -item[0])
    seen, lines = set(), []
    for _, line in candidates:
        if line not in seen:
            seen.add(line)
            lines.append(line)
        if len(lines) >= MAX_LINES:
            break
    return lines


def packet(arena):
    """S1596 with the story lines, or [] when this match has none."""
    if not active(arena):
        return []
    sample_score(arena)
    lines = _lines(arena)
    if not lines:
        return []
    body = struct.pack('<H', len(lines))
    for line in lines:
        raw = line.encode('utf-8')
        body += struct.pack('<H', len(raw)) + raw
    return [(STORY_MSG, body)]


def live_summary(arena, speaker=None):
    """One compact mid-match commentary string from public battle facts."""
    pk = getattr(arena, 'pk', None)
    if not isinstance(pk, dict):
        return 'Trận đấu đang diễn ra.'
    scores = pk.get('scores') or {}
    camp = getattr(speaker, 'camp', 1) if speaker is not None else 1
    mine, theirs = scores.get(camp, 0), scores.get(3 - camp, 0)
    parts = [f'Tỷ số {mine}:{theirs}']
    streaks = pk.get('streaks') or {}
    hot = [(n, arena.actors.get(ident)) for ident, n in streaks.items() if n >= 3]
    hot = [(n, a) for n, a in hot if a is not None and not a.info.get('npc_template')]
    if hot:
        n, actor = max(hot, key=lambda item: item[0])
        side = 'phe ta' if actor.camp == camp else 'địch'
        parts.append(f'🔥 {_name(actor)} ({side}) chuỗi {n} mạng')
    stats = pk.get('stats') or {}
    if stats:
        top_id = max(stats, key=lambda i: (stats[i][6], stats[i][1], -i), default=None)
        top_actor = arena.actors.get(top_id) if top_id is not None else None
        if top_actor is not None and stats[top_id][6] > 0:
            parts.append(f'Top ST: {_name(top_actor)} ({stats[top_id][6]})')
    return ' · '.join(parts)
