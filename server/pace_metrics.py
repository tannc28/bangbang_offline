"""Per-match pacing numbers for the human player, to see where a match feels flat.

Sampled once per second while the match runs and stored in ``arena.pk['pace_metrics']``
(string keys, plain numbers, so checkpoints keep it). At settlement the summary is
added to the match_history row as ``pacing``; ``python3 server/pace_metrics.py``
prints the recent matches.

contact: the player is alive and an enemy tank is alive within CONTACT_RANGE.
idle: the player is alive and not in contact.
"""
from __future__ import annotations

import json
import math

CONTACT_RANGE = 700
SAMPLE_MS = 1000


def _player(arena):
    from battle_participants import human
    humans = [a for a in arena.actors.values() if human(a)]
    return humans[0] if len(humans) == 1 else None


def _state(arena):
    return arena.pk.setdefault('pace_metrics', dict(at=-1, first_contact=None, idle_run=0, longest_idle=0,
                                                    idle=0, contact=0, dead=0, deaths_row=0, worst_deaths_row=0))


def tick(arena, now):
    import bot_mind
    if not bot_mind.active(arena) or arena.pk.get('finished'):
        return
    player = _player(arena)
    if player is None:
        return
    m = _state(arena)
    if m['at'] > now:                       # clock moved back after a restore
        m['at'] = -1
    if m['at'] >= 0 and now - m['at'] < SAMPLE_MS:
        return
    m['at'] = now
    if not player.alive:
        m['dead'] += 1
        m['idle_run'] = 0
        return
    pos = player.position_at(now)
    contact = any(a.alive and a.camp != player.camp and not a.info.get('npc_template')
                  and not a.info.get('map_object') and not a.info.get('robo')
                  and math.dist(pos, a.position_at(now)) <= CONTACT_RANGE
                  for a in arena.actors.values())
    if contact:
        m['contact'] += 1
        m['idle_run'] = 0
        if m['first_contact'] is None:
            begin = arena.pk.get('begin')
            m['first_contact'] = int((now - begin) / 1000) if isinstance(begin, (int, float)) else None
    else:
        m['idle'] += 1
        m['idle_run'] += 1
        m['longest_idle'] = max(m['longest_idle'], m['idle_run'])


def on_kill(arena, killer, victim):
    import bot_mind
    if not bot_mind.active(arena):
        return
    player = _player(arena)
    if player is None:
        return
    m = _state(arena)
    if victim is player:
        m['deaths_row'] += 1
        m['worst_deaths_row'] = max(m['worst_deaths_row'], m['deaths_row'])
    elif killer is player:
        m['deaths_row'] = 0


def summary(arena):
    """Numbers for match_history, or None when this match was not measured."""
    pk = getattr(arena, 'pk', None) or {}
    m = pk.get('pace_metrics')
    if not m:
        return None
    pace = (pk.get('bot_mind') or {}).get('pace') or {}
    alive = m['idle'] + m['contact']
    return dict(first_contact_s=m['first_contact'], longest_idle_s=m['longest_idle'],
                idle_share=round(m['idle'] / alive, 2) if alive else None,
                dead_s=m['dead'], worst_deaths_row=m['worst_deaths_row'],
                relax=pace.get('relax', 0), peak=pace.get('peak', 0))


def report(db_path, limit=20):
    import sqlite3
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    rows = db.execute('SELECT profile_id,ended_ms,ranked,summary FROM match_history '
                      'ORDER BY ended_ms DESC LIMIT ?', (limit,)).fetchall()
    head = ('profile', 'map', 'rank', 'result', 'len_s', 'first_contact_s', 'longest_idle_s',
            'idle_share', 'dead_s', 'worst_deaths_row', 'relax', 'peak')
    print('\t'.join(head))
    for profile, _, ranked, raw in rows:
        s = json.loads(raw)
        p = s.get('pacing')
        if not p:
            continue
        print('\t'.join(str(v) for v in (profile, s.get('map_id'), 'R' if ranked else 'C', s.get('outcome'),
                                          s.get('duration'), p['first_contact_s'], p['longest_idle_s'],
                                          p['idle_share'], p['dead_s'], p['worst_deaths_row'],
                                          p['relax'], p['peak'])))


if __name__ == '__main__':
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    report(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, '..', 'data', 'bangbang.sqlite3'))
