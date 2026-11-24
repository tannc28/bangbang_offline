"""Background ranked ladder for one owner's 100 bot identities.

Nothing runs on a timer. When the owner's ranked data is read, the ladder
catches up on the virtual matches that "happened" since the last read: one 5v5
every ROUND_MS, ten bots with neighbouring ratings, teams split at random. The
winner is drawn from each bot's hidden skill (fixed per identity) plus a daily
form, so strong bots climb, weak ones stall, and streaks happen. Results go
into the same rank rows as real matches (rating, wins, losses), with the same
POINTS, so the leaderboard simply shows them.

Cost: a few microseconds per virtual match; a full catch-up is capped at
MAX_ROUNDS, so a long break never turns into a long pause.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

ROUND_MS = 20 * 60 * 1000      # one virtual match every 20 minutes: ~7 games per bot per day
MAX_ROUNDS = 216               # catch up at most 3 days at a time
TEAM = 5
SKILL_SCALE = .45              # team skill gap that makes the stronger team win ~73%
FORM_SPREAD = .35              # day-to-day form on top of the fixed skill
STATE_PREFIX = 'rank_bot_ladder:'


def _unit(*parts):
    digest = hashlib.sha256(':'.join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], 'big'))


def _skill(owner, ident, day):
    return _unit('skill', owner, ident).gauss(0, 1) + _unit('form', owner, ident, day).gauss(0, FORM_SPREAD)


def catch_up(db, owner, season, now):
    """Play the virtual matches due since the last call; return how many were played."""
    import ranked_matches as rm
    owner = int(owner)
    now_ms = int(now * 1000)
    row = db.execute('SELECT value FROM settings WHERE name=?', (STATE_PREFIX + str(owner),)).fetchone()
    saved = db.execute('SELECT value FROM settings WHERE name=?', (rm._profile_key(owner),)).fetchone()
    if saved is None:
        return 0
    profiles = json.loads(saved[0])
    if profiles.get('version') != rm.BOT_PROFILE_VERSION:
        return 0   # The pool grows to its full size at the owner's next ranked room.
    state = json.loads(row[0]) if row else {}
    if state.get('season') != season or not isinstance(state.get('last_ms'), int) or state['last_ms'] > now_ms:
        _save(db, owner, season, now_ms)   # A new season (or a moved clock) starts counting from now.
        return 0
    rounds = (now_ms - state['last_ms']) // ROUND_MS
    if rounds <= 0:
        return 0
    rounds_played = min(rounds, MAX_ROUNDS)
    bots = {b['rank_bot_id']: b for b in profiles['bots']}
    ratings = {}
    for ident, bot in bots.items():
        entry = rm._entry(db, season, owner, ident)
        if entry is None:
            data = dict(char_oid=bot['acct_id'], char_uuid=bot['char_uuid'], char_name=bot['name'],
                        char_level=36, char_avatar=bot.get('avatar', 0), char_decorate=bot.get('decorate_id', 0),
                        char_maintank=bot['tank_id'], char_maintank_l=bot['tank_level'],
                        char_maintank_e=bot.get('tank_ext', 0), halo_id=bot.get('halo_id', 0))
            db.execute('INSERT INTO rank_entries (season_id,entry_key,profile_id,owner_id,is_bot,object_id,'
                       'rating,updated_ms,data) VALUES(?,?,?,?,1,?,?,?,?)',
                       (season, rm._key(owner, ident), bot['acct_id'], owner, ident, rm.INITIAL_RATING,
                        now_ms, rm._json(data)))
            entry = rm._entry(db, season, owner, ident)
        ratings[ident] = dict(rating=int(entry['rating']), wins=0, losses=0)
    rng = _unit('ladder', owner, season, state['last_ms'])
    first = state['last_ms'] + (rounds - rounds_played) * ROUND_MS
    for index in range(rounds_played):
        day = (first + (index + 1) * ROUND_MS) // 86_400_000
        ladder = sorted(ratings, key=lambda i: (ratings[i]['rating'], rng.random()))
        start = rng.randrange(len(ladder) - 2 * TEAM + 1)
        players = ladder[start:start + 2 * TEAM]
        rng.shuffle(players)
        a, b = players[:TEAM], players[TEAM:]
        gap = (sum(_skill(owner, i, day) for i in a) - sum(_skill(owner, i, day) for i in b)) / TEAM
        winners, losers = (a, b) if rng.random() < 1 / (1 + math.exp(-gap / SKILL_SCALE)) else (b, a)
        for ident in winners:
            ratings[ident]['rating'] = min(rm.MAX_RATING, ratings[ident]['rating'] + rm.POINTS['win'])
            ratings[ident]['wins'] += 1
        for ident in losers:
            ratings[ident]['rating'] = max(rm.INITIAL_RATING, ratings[ident]['rating'] + rm.POINTS['loss'])
            ratings[ident]['losses'] += 1
    db.executemany('UPDATE rank_entries SET rating=?,played=played+?,wins=wins+?,losses=losses+?,updated_ms=? '
                   'WHERE season_id=? AND entry_key=?',
                   [(r['rating'], r['wins'] + r['losses'], r['wins'], r['losses'], now_ms, season, rm._key(owner, i))
                    for i, r in ratings.items() if r['wins'] or r['losses']])
    _save(db, owner, season, state['last_ms'] + rounds * ROUND_MS)
    return rounds_played


def _save(db, owner, season, last_ms):
    db.execute('INSERT INTO settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
               (STATE_PREFIX + str(owner), json.dumps(dict(season=season, last_ms=last_ms))))
