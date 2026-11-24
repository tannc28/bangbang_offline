"""Coarse PRO movement around an already published, visible warning.

This is a sensor/planner, not a combat or collision implementation. Its only
authored template is Chu Du's stationary S1556 warning388311. Other objects
can be hidden traps or invisible logic markers even when arena.objects holds
them. No caster, enemy intent, cooldown, queue or exact detonation is read.
"""
from __future__ import annotations

import math
import struct


MIN_AGE = 180
MAX_AGE = 1000
SENSOR_RADIUS = 600
OBJECT = struct.Struct('<IIhhiBiIiH')
# Verified enemy-visible SceneItems (non-empty szCoverEnemySwf in SceneItem_Templet)
# mapped to their native nCampRadius / authored blast radius. Concealed traps stay excluded.
PUBLIC_WARNINGS = {
    388311: 120,  # Chu Du Space warning
    358305: 120, 358301: 96, 358303: 96, 358601: 196, 358602: 196, 358901: 300,  # Gia Cat Luong
    303301: 300, 303402: 72,   # Spider-Man
    306301: 264, 306311: 264,  # Teddy Bear
    308521: 168,               # Hulk
    311301: 240,               # Ho Lo
    312411: 192,               # Ghost Rider
    313302: 192,               # Thor
    315303: 144, 315304: 144, 315403: 144,  # Legolas
    318304: 144,               # Naruto
    324301: 168,               # Transformer
    326309: 168, 326313: 168,  # Son Tinh
    327201: 96,                # Pumpkin
    328311: 120,               # Superman landing warning
    334306: 288,               # Phuong Hoang Lua
    335301: 264, 335304: 264,  # Minion
    340201: 108,               # Tien Ca
    349311: 192,               # Lu Bo
    353301: 192,               # Thuy Tinh
    354401: 72,                # Doraemon
    356314: 216,               # Na Tra
    357301: 144, 357304: 144, 357305: 144,  # Doctor Strange
    362201: 144,               # Gilgamesh
    363204: 144,               # Iron Man
    368321: 196,               # Sasuke
    372201: 108, 372403: 168,  # Magneto
    373201: 144, 373202: 144,  # Tu Ma Yi
    374402: 120,               # Hoa Moc Lan
    376401: 96,                # Sniper
    379401: 196, 379402: 196,  # Falcon
    380221: 192,               # Hoa Than
    381301: 216, 381302: 216, 381401: 144, 381403: 144,  # Elsa
    382201: 144, 382301: 196, 382401: 144, 382402: 144,  # Hikari
    384213: 144,               # Thach Than
    8190411: 192, 8190412: 192,  # Optimus Prime
}
BULLET_CLEARANCE = 76
DIRECTIONS = ((-1,-1), (0,-1), (1,-1), (1,0),
              (1,1), (0,1), (-1,1), (-1,0))


def _enabled(arena, actor, brain):
    from bot_policy import ELITE, policy_for
    return (actor.alive and brain.get('generation') == actor.generation
            and not actor.info.get('npc_template')
            and policy_for(arena, actor) == ELITE)


def _parse(ident, body):
    """A body excludes the packet's sceneId; HP0 is normal for scene items."""
    try:
        raw = bytes.fromhex(body)
        if len(raw) < OBJECT.size:
            return None
        key, template, x, y, hp, camp, level, owner, maximum, count = OBJECT.unpack_from(raw)
        if (key != ident or key >> 26 != 4 or template not in PUBLIC_WARNINGS
                or camp not in (1, 2) or len(raw) != OBJECT.size + 13 * count):
            return None
        return dict(id=key, template=template, pos=(x, y), camp=camp, body=body)
    except (TypeError, ValueError, struct.error):
        return None


def _observe_skillshots(arena, actor, pos, now):
    """Sample already-launched public enemy skillshot rays within sight."""
    rays = []
    for _, _, callback, args in getattr(arena, 'pending', ()):
        if getattr(callback, '__name__', '') != '_event' or len(args) < 2 or args[0] != 'flight':
            continue
        caster = getattr(callback, '__self__', None)
        flight = args[1][0] if args[1] and isinstance(args[1][0], dict) else None
        if (caster is None or flight is None or caster.camp == actor.camp
                or flight.get('kind') != 'bullet' or flight.get('basic')
                or flight.get('target') is not None):
            continue
        if flight.get('finish', 0) <= now or now < flight.get('begin', now):
            continue
        bpos = flight.get('pos') or flight.get('start')
        end = flight.get('end')
        if not bpos or not end or math.dist(pos, bpos) > SENSOR_RADIUS:
            continue
        if not flight.get('through_walls') and arena.geometry.wall_contact(pos, bpos) is not None:
            continue
        rays.append(dict(id=flight['id'], kind='ray', start=tuple(bpos), end=tuple(end),
                         camp=caster.camp, generation=actor.generation,
                         observed_at=flight.get('begin', now)))
        if len(rays) >= 8:
            break
    return rays


def observe(arena, actor, brain, now):
    """Called only at the ordinary end-of-notice observation point."""
    objects = getattr(arena, 'objects', {})
    old = brain.get('elite_hazards', ())
    if not _enabled(arena, actor, brain):
        return
    previous = {sample['id']: sample for sample in old
                if sample.get('generation') == actor.generation and sample.get('kind') != 'ray'}
    rows = []
    found = set()
    pos = actor.position_at(now)
    for ident, body in objects.items():
        sample = _parse(ident, body)
        if (sample is None or sample['camp'] == actor.camp
                or math.dist(pos, sample['pos']) > SENSOR_RADIUS
                or arena.geometry.wall_contact(pos, sample['pos']) is not None):
            continue
        prior = previous.get(ident)
        if prior is not None and prior.get('body') == body:
            sample = prior
        else:
            sample.update(generation=actor.generation, observed_at=now)
        rows.append(sample)
        found.add(ident)
    for ident, sample in previous.items():
        if ident not in found and 0 <= now-sample.get('observed_at', now) <= MAX_AGE:
            rows.append(sample)
    rows.extend(_observe_skillshots(arena, actor, pos, now))
    if rows:
        brain['elite_hazards'] = rows
    else:
        brain.pop('elite_hazards', None)


def mature(brain, actor, now):
    out = []
    for sample in brain.get('elite_hazards', ()):
        if sample.get('generation') != actor.generation or sample.get('camp') == actor.camp:
            continue
        age = now - sample.get('observed_at', now)
        if sample.get('kind') == 'ray':
            if MIN_AGE <= age <= 850:
                out.append(sample)
        elif sample.get('template') in PUBLIC_WARNINGS and sample.get('camp') in (1, 2) and MIN_AGE <= age <= MAX_AGE:
            out.append(sample)
    return out


def _segment_distance(start, end, point):
    dx, dy = end[0]-start[0], end[1]-start[1]
    length2 = dx*dx+dy*dy
    fraction = (max(0.0, min(1.0, ((point[0]-start[0])*dx+(point[1]-start[1])*dy)/length2))
                if length2 else 0.0)
    return math.dist((start[0]+dx*fraction, start[1]+dy*fraction), point)


def _risk(point, hazards):
    total = 0.0
    for h in hazards:
        if h.get('kind') == 'ray':
            total += max(0.0, BULLET_CLEARANCE - _segment_distance(h['start'], h['end'], point)) * 1.4
        else:
            total += max(0.0, PUBLIC_WARNINGS[h['template']]+24-math.dist(point,h['pos']))
    return total


def _crosses(start, end, hazards):
    for h in hazards:
        if h.get('kind') == 'ray':
            if _segment_distance(h['start'], h['end'], end) < BULLET_CLEARANCE:
                return True
        elif _segment_distance(start, end, h['pos']) < PUBLIC_WARNINGS[h['template']]+24:
            return True
    return False


def evade(arena, actor, brain, now):
    """Override only an ordinary walk goal using previous mature samples.

    The discrete destinations are requested through the existing native
    navigator/walker. They are neither teleports nor a guarantee of dodging.
    No RNG is consumed; no current enemy or warning-removal state is read.
    """
    if not brain.get('elite_hazards'):
        return False
    if not _enabled(arena, actor, brain):
        return False
    motion = getattr(actor, 'motion', None)
    if (actor.blocked('move', now) or getattr(actor, 'channel', None)
            or getattr(actor, 'ready', None) or brain.get('elite_native_goal')
            or brain.get('repair_goal') or brain.get('repair_box')
            or (motion and motion[3] > now and getattr(actor, 'motion_kind', 0) != 0)
            or arena.pk.get('finished') or arena.pk.get('round_phase', 'playing') != 'playing'
            or now < arena.pk.get('intro_until', 0)):
        return False
    hazards = mature(brain, actor, now)
    if not hazards:
        brain.pop('elite_hazard_goal', None)
        return False
    pos = actor.position_at(now)
    if actor._speed(now) <= 0:
        return False
    goal = brain.get('goal') or pos
    distance = math.dist(pos, goal)
    lookahead = (tuple(pos[i]+(goal[i]-pos[i])*min(1.0,240/distance) for i in range(2))
                 if distance else pos)
    stay_risk = _risk(pos, hazards)
    if not stay_risk and not _crosses(pos, lookahead, hazards):
        brain.pop('elite_hazard_goal', None)
        return False
    water = arena.water_rects(now)
    friends = [ally.position_at(now) for ally in arena.actors.values()
               if ally is not actor and ally.camp == actor.camp and ally.alive
               and not any(ally.info.get(k) for k in
                           ('map_object','cow_object','bomb_cart','totem'))]
    safe_center = None
    if arena.geometry.id in (30, 40) and arena.pk.get('collapse_warned'):
        from death_mode import RADIUS, center
        safe_center, safe_radius = center(arena), RADIUS
    hold_center = brain.get('elite_hold_center')
    hold_radius = brain.get('elite_hold_radius', 0)

    def legal(point):
        if arena.geometry.walk_end(pos, point, water) != point:
            return False
        # Match ordinary walking's64px ally clearance, including friendly
        # summons. If already crowded, allow only non-worsening separation.
        if any(_segment_distance(pos, point, p)+.01 < min(64,math.dist(pos,p))
               for p in friends):
            return False
        if safe_center is not None:
            old, new = math.dist(pos, safe_center), math.dist(point, safe_center)
            if new > safe_radius and (old <= safe_radius or new >= old):
                return False
        if brain.get('elite_final_push') and hold_center is not None and hold_radius:
            old, new = math.dist(pos, hold_center), math.dist(point, hold_center)
            if new > hold_radius and (old <= hold_radius or new >= old):
                return False
        # Once outside all observed warning circles, do not cross one to get
        # to another safe endpoint. If initially inside, an exit is necessary.
        if not stay_risk and _crosses(pos, point, hazards):
            return False
        return True

    previous = brain.get('elite_hazard_goal')
    candidates = []
    # Keep a still-valid escape rather than reversing sides each reaction.
    if (previous is not None and legal(tuple(previous))
            and _risk(previous, hazards) <= max(0,stay_risk-24)):
        chosen = tuple(previous)
    else:
        points = [pos] if not stay_risk else []
        for radius in (96, 168, 240):
            for dx, dy in DIRECTIONS:
                length = math.hypot(dx, dy)
                points.append((round(pos[0]+dx*radius/length),
                               round(pos[1]+dy*radius/length)))
        for point in points:
            risk = _risk(point, hazards)
            if not legal(point) or (stay_risk and risk > max(0,stay_risk-24)):
                continue
            penalty = math.dist(point, goal)*.025
            if hold_center is not None and hold_radius:
                penalty += max(0,math.dist(point,hold_center)-hold_radius)*.35
            # Leaving every sampled circle is the first priority. Within that
            # group, prefer short walks and the current objective direction.
            candidates.append((risk, math.dist(pos,point)*.05+penalty, point))
        if not candidates:
            return False
        chosen = min(candidates)[2]
    if tuple(brain.get('goal') or pos) != chosen:
        brain['repath_at'] = 0
    brain['goal'] = chosen
    brain['elite_hazard_goal'] = chosen
    return True
