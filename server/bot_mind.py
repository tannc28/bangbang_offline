"""Match-level bot "mind": grudges, rivalry memory, seen cooldowns, team plans,
end-of-match mood and between-match difficulty.

Everything here biases choices the AI already makes (target score, the
personality multipliers); nothing grants information a player could not have:
a cooldown is remembered only after an enemy bot saw the cast, a grudge only
after real kills, and rivalry history only from finished matches.
State lives in ``arena.pk['bot_mind']`` with string keys; times that look wrong
after a checkpoint restore are dropped instead of trusted.
"""
from __future__ import annotations

import json
import math
import random

_rng = random.SystemRandom()

MAJOR_COOLDOWN_MS = 8000
SIGHT = 960
GRUDGE_STEPS = (2, 4)          # deaths to one human that raise grudge to 1, then 2
GRUDGE_BIAS = 150              # target-score points per grudge level
PUNISH_BIAS = 90               # target with a major skill on cooldown
PK_TARGET = 25
FLAG_TARGET = 1000
FLAG_MAPS = frozenset((7, 9, 10, 37, 170))
PK_MAPS = frozenset((1, 4, 17, 18, 19, 20, 21, 34, 35, 36))

PLANS = {
    'rush':  dict(label='Ép sân', caution=.8, reaction=.95, team=1.15),
    'hold':  dict(label='Thủ chắc', caution=1.25, team=1.1),
    'split': dict(label='Đánh lẻ', team=.8, dodge=1.15),
    'focus': dict(label='Dồn mục tiêu', team=1.5),
}
MOODS = {
    'clutch': dict(caution=.7, team=1.3, reaction=.92),
    'cocky':  dict(team=.75, aim=1.1),
}
RIVAL_PREFIX = 'rank_bot_rivalry:'

# In-match pacing (casual rooms with one human only), after Valve's AI Director:
# build up -> peak -> relax. Only the enemies of the player change behaviour,
# and only through the same multipliers and target scores; HP, damage and
# perception are never touched.
RELAX_AFTER_DEATHS = 2         # player deaths in a row without a kill
RELAX_MS = 15000               # counted from the death, so it covers the respawn walk
PEAK_STREAK = 3                # player kills in a row without dying
PEAK_MS = 12000
POST_PEAK_RELAX_MS = 8000
RELAX_BIAS = -220              # the player is a less attractive target while relaxing
PEAK_BIAS = 80
PACE = {
    'relax': dict(caution=1.35, reaction=1.15, team=.8),
    'peak':  dict(team=1.3, reaction=.95),
}

# Readable mistakes: a bot on a streak dives alone, a bot with a strong grudge
# leaves the objective to chase. Both are announced in chat and can be punished.
DIVE_STREAK = 3
DIVE_MIN_HP = .3
CHASE_GRUDGE = 2
CHASE_MIN_HP = .2


# ---------------------------------------------------------------- state

def _mind(arena):
    pk = getattr(arena, 'pk', None)
    if not isinstance(pk, dict):
        return None
    return pk.setdefault('bot_mind', dict(plans={}, grudge={}, deaths={}, cd={'1': {}, '2': {}},
                                          mood={}, mood_at=-1, announced={}))


def active(arena):
    from bot_setup import BOT_MAPS
    pk = getattr(arena, 'pk', None)
    return (isinstance(pk, dict) and arena.geometry.id in BOT_MAPS
            and not getattr(arena, 'tank_test', False))


def _is_bot(actor):
    from battle_participants import human
    return actor is not None and not human(actor) and not actor.info.get('npc_template')


# ---------------------------------------------------------------- multipliers

def _progress(arena, camp, now):
    """('clutch'|'cocky'|None) for one camp from score and clock."""
    pk = arena.pk
    scores = pk.get('scores') or {}
    mine, theirs = scores.get(camp, 0), scores.get(3 - camp, 0)
    if not isinstance(mine, (int, float)) or not isinstance(theirs, (int, float)):
        return None
    target = PK_TARGET if arena.geometry.id in PK_MAPS else FLAG_TARGET if arena.geometry.id in FLAG_MAPS else None
    begin, end = pk.get('begin'), pk.get('end')
    clock = (now - begin) / (end - begin) if isinstance(begin, (int, float)) and isinstance(end, (int, float)) and end > begin else 0
    if target:
        late = max(mine, theirs) >= .75 * target or clock >= .75
        if late and theirs > mine and theirs - mine <= .2 * target:
            return 'clutch'
        if mine - theirs >= .3 * target:
            return 'cocky'
    elif clock >= .8:
        return 'clutch'
    return None


def modifier(actor, key):
    """Extra multiplier from the camp's plan and current mood (1.0 if none)."""
    arena = getattr(actor, 'arena', None)
    if arena is None or not _is_bot(actor) or not active(arena):
        return 1.0
    mind = _mind(arena)
    camp = str(actor.camp)
    value = PLANS.get(mind['plans'].get(camp), {}).get(key, 1.0)
    value *= MOODS.get(mind['mood'].get(camp), {}).get(key, 1.0)
    player = _paced_player(arena)
    if player is not None and actor.camp != player.camp:
        value *= PACE.get(phase(arena, arena.clock()), {}).get(key, 1.0)
    return value


# ---------------------------------------------------------------- pacing

def _paced_player(arena):
    """The single human of a casual room, or None when pacing does not apply."""
    from battle_participants import human
    if not active(arena) or ((getattr(arena, 'state', None) or {}).get('room') or {}).get('ranked'):
        return None
    humans = [a for a in arena.actors.values() if human(a)]
    return humans[0] if len(humans) == 1 else None


def _pace(arena):
    return _mind(arena).setdefault('pace', dict(phase='build', until=0, deaths_row=0, kills_row=0,
                                                 relax=0, peak=0))


def phase(arena, now):
    """'build', 'peak' or 'relax' for the enemies of the paced player."""
    if _paced_player(arena) is None:
        return 'build'
    pace = _pace(arena)
    if pace['until'] - now > PEAK_MS + RELAX_MS:      # clock moved back after a restore
        pace.update(phase='build', until=0)
    if pace['phase'] != 'build' and now >= pace['until']:
        if pace['phase'] == 'peak':
            pace.update(phase='relax', until=now + POST_PEAK_RELAX_MS)
            pace['relax'] += 1
        else:
            pace.update(phase='build', until=0)
    return pace['phase']


def _pace_kill(arena, killer, victim, now):
    from battle_participants import human
    player = _paced_player(arena)
    if player is None:
        return
    pace = _pace(arena)
    phase(arena, now)
    if victim is player:
        pace['deaths_row'] += 1
        pace['kills_row'] = 0
        if pace['deaths_row'] >= RELAX_AFTER_DEATHS and pace['phase'] != 'relax':
            pace.update(phase='relax', until=now + RELAX_MS)
            pace['relax'] += 1
    elif killer is player and human(killer):
        pace['kills_row'] += 1
        pace['deaths_row'] = 0
        if pace['kills_row'] >= PEAK_STREAK and pace['phase'] == 'build':
            pace.update(phase='peak', until=now + PEAK_MS)
            pace['peak'] += 1
            import bot_chat
            bot_chat.react_peak(arena, player, now)


# ---------------------------------------------------------------- readable mistakes

def steer(arena, actor, brain, target, retreat, recovering, now):
    """Turn a grudge or a streak into a visible, punishable mistake.

    Returns the retreat flag to use. The goal is set before the kit executor
    runs, so tank-specific steering and dodging still apply on top.
    """
    if (target is None or recovering or not active(arena) or not _is_bot(actor)
            or arena.pk.get('finished') or target.get('objective', target.get('robo'))):
        return retreat
    mind = _mind(arena)
    key = str(actor.id)
    ratio = actor.hp / max(1, actor.max_hp)
    grudge = mind['grudge'].get(key) or {}
    reason = None
    if grudge.get('level', 0) >= CHASE_GRUDGE and grudge.get('target') == target['id'] and ratio >= CHASE_MIN_HP:
        reason = 'chase'
    elif (arena.pk.get('streaks') or {}).get(actor.id, 0) >= DIVE_STREAK and ratio >= DIVE_MIN_HP:
        reason = 'dive'
    if reason is None:
        return retreat
    player = _paced_player(arena)
    if player is not None and target['id'] == player.id and phase(arena, now) == 'relax':
        return retreat
    brain['goal'] = tuple(target['pos'])
    told = mind.setdefault('told', {})
    if told.get(key) != reason:
        told[key] = reason
        import bot_chat
        bot_chat.react_mistake(arena, actor, arena.actors.get(target['id']), reason, now)
    return False


def _refresh_mood(arena, now):
    mind = _mind(arena)
    if now - mind['mood_at'] < 1000 and mind['mood_at'] <= now:
        return []
    mind['mood_at'] = now
    events = []
    for camp in (1, 2):
        mood = _progress(arena, camp, now)
        key = str(camp)
        if mood and mind['mood'].get(key) != mood and mind['announced'].get(key + mood) is None:
            mind['announced'][key + mood] = now
            events.append((camp, mood))
        mind['mood'][key] = mood
    return events


# ---------------------------------------------------------------- target bias

def target_bias(arena, actor, target_id, now):
    """Points to subtract from a target's score (lower score = preferred)."""
    if arena is None or not active(arena) or not _is_bot(actor):
        return 0
    mind = _mind(arena)
    bias = 0
    grudge = mind['grudge'].get(str(actor.id))
    if grudge and grudge.get('target') == target_id:
        bias += GRUDGE_BIAS * grudge.get('level', 1)
    ready = mind['cd'].get(str(actor.camp), {}).get(str(target_id))
    if ready and ready > now:
        bias += PUNISH_BIAS
    player = _paced_player(arena)
    if player is not None and target_id == player.id and actor.camp != player.camp:
        bias += {'relax': RELAX_BIAS, 'peak': PEAK_BIAS}.get(phase(arena, now), 0)
    return bias


# ---------------------------------------------------------------- cooldown memory

def saw_cooldown(caster, duration, slot):
    """Record a major cooldown if an enemy bot had sight of the caster."""
    arena = getattr(caster, 'arena', None)
    if (arena is None or not active(arena) or not slot or caster.info.get('npc_template')
            or not isinstance(duration, (int, float)) or duration < MAJOR_COOLDOWN_MS):
        return
    now = arena.clock()
    pos = caster.position_at(now)
    seen = False
    for other in arena.actors.values():
        if other.camp == caster.camp or not other.alive or not _is_bot(other):
            continue
        spot = other.position_at(now)
        if math.dist(pos, spot) <= SIGHT and arena.geometry.wall_contact(spot, pos) is None:
            seen = True
            break
    if not seen:
        return
    mind = _mind(arena)
    observers = mind['cd'].setdefault(str(3 - caster.camp), {})
    ready = now + int(duration)
    key = str(caster.id)
    if ready > observers.get(key, 0):
        observers[key] = ready
        import bot_chat
        bot_chat.react_punish(arena, caster, now)


# ---------------------------------------------------------------- grudges

def on_kill(arena, killer, victim, now):
    """Grudges form when a bot keeps dying to the same human; revenge eases them."""
    from battle_participants import human
    if not active(arena) or killer is None or victim is None:
        return
    mind = _mind(arena)
    _pace_kill(arena, killer, victim, now)
    mind.get('told', {}).pop(str(victim.id), None)
    import bot_chat
    if _is_bot(victim) and human(killer):
        key = f'{victim.id}:{killer.id}'
        count = mind['deaths'][key] = mind['deaths'].get(key, 0) + 1
        grudge = mind['grudge'].setdefault(str(victim.id), dict(target=killer.id, level=0))
        if grudge['target'] != killer.id and count < GRUDGE_STEPS[0]:
            return
        level = sum(count >= step for step in GRUDGE_STEPS)
        if level > grudge['level'] or grudge['target'] != killer.id:
            grudge.update(target=killer.id, level=max(level, 1))
            bot_chat.react_grudge(arena, victim, killer, grudge['level'], now)
    elif _is_bot(killer) and human(victim):
        grudge = mind['grudge'].get(str(killer.id))
        if grudge and grudge.get('target') == victim.id and grudge.get('level', 0) > 0:
            grudge['level'] -= 1
            bot_chat.react_revenge(arena, killer, victim, now)


# ---------------------------------------------------------------- per tick

def tick(arena, now):
    """Pick team plans once, keep moods current, heal times after restore."""
    if not active(arena) or arena.pk.get('finished'):
        return
    mind = _mind(arena)
    for camp, ready in list(mind['cd'].items()):
        mind['cd'][camp] = {k: v for k, v in ready.items() if v <= now + 120000}
    if mind['mood_at'] > now:
        mind['mood_at'] = -1
    import bot_chat
    for camp in (1, 2):
        key = str(camp)
        if key not in mind['plans']:
            members = [a for a in arena.actors.values() if a.camp == camp and _is_bot(a)]
            if not members:
                mind['plans'][key] = None
                continue
            plan = mind['plans'][key] = _rng.choice(sorted(PLANS))
            bot_chat.react_plan(arena, camp, plan, now)
            _seed_rival_grudges(arena, members)
    for camp, mood in _refresh_mood(arena, now):
        bot_chat.react_mood(arena, camp, mood, now)


# ---------------------------------------------------------------- ranked rivalry

def _seed_rival_grudges(arena, members):
    """A ranked bot that died a lot to this player before starts the match hunting."""
    from battle_participants import human
    humans = [a for a in arena.actors.values() if human(a)]
    if len(humans) != 1:
        return
    player = humans[0]
    mind = _mind(arena)
    import bot_chat
    for actor in members:
        rival = actor.info.get('rivalry')
        if not isinstance(rival, dict) or actor.camp == player.camp:
            continue
        if rival.get('deaths_to_player', 0) >= 6:
            mind['grudge'][str(actor.id)] = dict(target=player.id, level=1)
        bot_chat.react_rival_greet(arena, actor, player, rival, arena.clock())


def load_rivalry(db, owner):
    row = db.execute('SELECT value FROM settings WHERE name=?', (RIVAL_PREFIX + str(int(owner)),)).fetchone()
    try:
        value = json.loads(row[0]) if row else {}
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def record_rivalry(db, state, arena):
    """After a ranked match: per rank identity, kills on / deaths to the player and results."""
    from battle_participants import human
    pk = arena.pk or {}
    room = state.get('room') or {}
    if not room.get('ranked'):
        return
    humans = [a for a in arena.actors.values() if human(a)]
    if len(humans) != 1:
        return
    player = humans[0]
    owner = state['char_id']
    value = load_rivalry(db, owner)
    pairs = (pk.get('bot_mind') or {}).get('pairs', {})
    winner = pk.get('winner')
    for actor in arena.actors.values():
        ident = actor.info.get('rank_bot_id')
        if not _is_bot(actor) or ident is None or actor.camp == player.camp:
            continue
        rec = value.setdefault(str(ident), dict(kills_on_player=0, deaths_to_player=0, wins=0, losses=0))
        rec['kills_on_player'] += pairs.get(f'{actor.id}>{player.id}', 0)
        rec['deaths_to_player'] += pairs.get(f'{player.id}>{actor.id}', 0)
        if winner:
            rec['wins' if winner == actor.camp else 'losses'] += 1
    db.execute('INSERT INTO settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
               (RIVAL_PREFIX + str(int(owner)), json.dumps(value, separators=(',', ':'))))


def count_pair(arena, killer, victim):
    if not active(arena) or killer is None or victim is None:
        return
    pairs = _mind(arena).setdefault('pairs', {})
    key = f'{killer.id}>{victim.id}'
    pairs[key] = pairs.get(key, 0) + 1


# ---------------------------------------------------------------- casual difficulty

def casual_level(db, profile_id, limit=5):
    """-1..+1 from the last casual results: +1 = the player keeps winning."""
    rows = db.execute('SELECT summary FROM match_history WHERE profile_id=? AND ranked=0 '
                      'ORDER BY ended_ms DESC LIMIT ?', (profile_id, limit)).fetchall()
    score = 0
    for (summary,) in rows:
        try:
            outcome = json.loads(summary).get('outcome')
        except (TypeError, ValueError):
            continue
        score += {'win': 1, 'loss': -1}.get(outcome, 0)
    return max(-1.0, min(1.0, score / limit)) if rows else 0.0


def apply_casual_level(bots, level):
    """Sharper bots after a win streak, gentler after losses (at most ~15%)."""
    if not level:
        return
    for bot in bots:
        style = bot.get('personality')
        if not isinstance(style, dict) or bot.get('side') != 'enemies':
            continue
        style['aim'] = round(style['aim'] * (1 - .15 * level), 3)
        style['reaction'] = round(style['reaction'] * (1 - .1 * level), 3)
        style['dda'] = round(level, 2)
