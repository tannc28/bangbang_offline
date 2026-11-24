"""Per-bot playstyle: multipliers over the existing AI constants.

A personality never adds information or resources. It only scales values the
AI already uses (decision interval, aim spread, retreat thresholds, focus
weight, dodge window) and reuses the same RNG draws, so legacy/PRO perception
rules and the 180 ms minimum reaction stay intact.

Every match rolls a fresh archetype with some jitter, ranked and casual alike,
so the same name can play recklessly one match and carefully the next. Within
one ranked room the roll is fixed (seeded by the room), so a lobby refresh does
not reshuffle it.
"""
from __future__ import annotations

import hashlib
import random

MIN_REACTION_MS = 180

# reaction: decision-interval factor (<1 faster); aim: spread factor (<1 tighter)
# caution: retreat-threshold factor (>1 retreats earlier); team: focus-fire factor
# dodge: projectile-awareness factor; chat: chance to speak; tone: line set.
ARCHETYPES = {
    'reckless':      dict(label='Liều mạng', reaction=.85, aim=1.25, caution=.55, team=.6,  dodge=.8,  chat=.75, tone='trash'),
    'sharpshooter':  dict(label='Xạ thủ',    reaction=1.1, aim=.7,   caution=1.35, team=.9, dodge=1.0, chat=.35, tone='calm'),
    'team_player':   dict(label='Đồng đội',  reaction=1.0, aim=1.0,  caution=1.1, team=1.6,  dodge=1.0, chat=.6,  tone='team'),
    'slippery':      dict(label='Lươn lẹo',  reaction=.95, aim=1.05, caution=1.2, team=.85,  dodge=1.5, chat=.45, tone='funny'),
    'rookie':        dict(label='Tân binh',  reaction=1.3, aim=1.5,  caution=.8,  team=.8,   dodge=.65, chat=.55, tone='rookie'),
    'veteran':       dict(label='Cao thủ',   reaction=.9,  aim=.8,   caution=1.0, team=1.2,  dodge=1.25, chat=.3, tone='calm'),
    'clown':         dict(label='Lầy',       reaction=1.05, aim=1.15, caution=.9, team=.9,   dodge=.95, chat=.9,  tone='funny'),
    'berserker':     dict(label='Cuồng chiến', reaction=.82, aim=1.3, caution=.45, team=.55, dodge=.75, chat=.8,  tone='trash'),
    'guardian':      dict(label='Hộ vệ',     reaction=1.05, aim=.95,  caution=1.4, team=1.8,  dodge=1.1, chat=.4,  tone='team'),
    'trickster':     dict(label='Láu cá',    reaction=.92, aim=1.1,  caution=1.1, team=.7,   dodge=1.6, chat=.7,  tone='funny'),
    'ice':           dict(label='Lạnh lùng', reaction=.88, aim=.85,  caution=1.15, team=1.0, dodge=1.2, chat=.15, tone='calm'),
}
# Rare archetypes appear less often so a lobby of five still feels plausible.
WEIGHTS = {'reckless': 3, 'sharpshooter': 2, 'team_player': 3, 'slippery': 2,
           'rookie': 3, 'veteran': 1, 'clown': 2, 'berserker': 2, 'guardian': 2,
           'trickster': 2, 'ice': 1}
NUMERIC = ('reaction', 'aim', 'caution', 'team', 'dodge', 'chat')
NEUTRAL = dict(reaction=1.0, aim=1.0, caution=1.0, team=1.0, dodge=1.0, chat=0.0, tone='calm', kind=None)


def _pick(rng):
    kinds = sorted(WEIGHTS)
    return rng.choices(kinds, weights=[WEIGHTS[k] for k in kinds])[0]


def _profile(kind, jitter, rng):
    base = ARCHETYPES[kind]
    out = dict(kind=kind, tone=base['tone'])
    for key in NUMERIC:
        value = base[key] * (rng.uniform(1 - jitter, 1 + jitter) if jitter else 1)
        out[key] = round(value, 3)
    out['chat'] = min(1.0, out['chat'])
    return out


def roll_casual(rng):
    """A fresh playstyle for one casual match."""
    return _profile(_pick(rng), .12, rng)


def ranked(owner, rank_bot_id, room_seed):
    """A new style per ranked room; the same room always yields the same roll."""
    seed = hashlib.sha256(f'rank-personality:{int(owner)}:{int(rank_bot_id)}:{int(room_seed)}'.encode()).digest()
    rng = random.Random(int.from_bytes(seed[:8], 'big'))
    return _profile(_pick(rng), .12, rng)


def of(actor):
    value = actor.info.get('personality') if hasattr(actor, 'info') else None
    if not isinstance(value, dict) or value.get('kind') not in ARCHETYPES:
        return NEUTRAL
    return value


def factor(actor, key):
    import bot_mind
    return float(of(actor).get(key, 1.0)) * bot_mind.modifier(actor, key)


def reaction_delay(actor, drawn_ms):
    """Scale an already drawn interval; never below the fixed reaction floor."""
    return max(MIN_REACTION_MS, int(round(drawn_ms * factor(actor, 'reaction'))))


def threshold(actor, value, cap=.9):
    """Retreat threshold scaled by caution, kept inside a sane HP band."""
    return max(.05, min(cap, value * factor(actor, 'caution')))
