"""Kit-aware tactical geometry for displacement, Insec flanking, tosses and ranged kiting.

All helpers strictly consume communicated friendly state, public map geometry,
and delayed enemy sightings (``target`` / ``seen``). No live enemy actor, hidden
bush/stealth state, or enemy cooldown is ever inspected.
"""
from __future__ import annotations

import math

from combat_geometry import circle_contact, point_at
from melee_common import aimed


def _ratio(actor) -> float:
    return float(actor.hp / actor.max_hp) if actor.max_hp else 0.0


def _unit(start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 1.0, 0.0
    return dx / length, dy / length


def _friendly_fighters(arena, actor):
    return [
        a for a in arena.actors.values()
        if a.alive and a.camp == actor.camp and a.id != actor.id
        and not a.info.get('npc_template')
    ]


def ally_pull_anchor(actor, now):
    """Return ``(anchor_pos, has_real_ally_or_turret)`` where we want enemies pushed/tossed.

    Prefers nearby allied turrets/base and healthy allied teammates so displacement
    kits (Deadpool, Superman, Lạc Long Quân, Saitama, etc.) launch enemies INTO our
    team's kill zone rather than knocking them away to safety.
    """
    arena = actor.arena
    pos = actor.position_at(now)
    weighted_x = 0.0
    weighted_y = 0.0
    total_w = 0.0

    for struct in arena.actors.values():
        if not struct.alive or struct.camp != actor.camp:
            continue
        if not (struct.info.get('map_turret') or struct.info.get('base')):
            continue
        spos = struct.position_at(now)
        dist = math.dist(pos, spos)
        if dist <= 820:
            w = 2.2 * max(0.25, 1.0 - dist / 950.0)
            weighted_x += spos[0] * w
            weighted_y += spos[1] * w
            total_w += w

    for ally in _friendly_fighters(arena, actor):
        hp = _ratio(ally)
        if hp < 0.32:
            continue
        apos = ally.position_at(now)
        dist = math.dist(pos, apos)
        if dist <= 780:
            w = (0.55 + 0.75 * hp) * max(0.2, 1.0 - dist / 900.0)
            weighted_x += apos[0] * w
            weighted_y += apos[1] * w
            total_w += w

    if total_w > 0.05:
        return (weighted_x / total_w, weighted_y / total_w), True
    return arena.geometry.spawn(actor.camp, 0), False


def push_is_favorable(actor, target, seen, now, *, push_dist=480, lethal_hp=0.22,
                      retreat=False, origin=None) -> bool:
    """Decide whether knocking ``target`` away from ``origin`` helps our team.

    Approves the push when:
    1. Target is in lethal burst range (``hp <= lethal_hp``).
    2. Critical self-peel (``hp < 0.22`` and not under Deadpool R rescue) or saving a
       critically wounded nearby teammate (``ally_hp < 0.42`` within 230px).
    3. Insec push: sends ``target`` back toward allied teammates / allied turret!
    4. Wall-slam / multi-enemy bowling that does NOT shove the enemy straight away
       from nearby teammates toward enemy escape.
    """
    if target.get('objective') or target.get('structure') or target.get('barrier'):
        return False
    if target.get('hp', 1.0) <= lethal_hp:
        return True

    arena = actor.arena
    pos = actor.position_at(now) if origin is None else origin
    tpos = target['pos']
    hp = _ratio(actor)
    tank = actor.info['tank_id']

    # Critical emergency self-peel only when truly near death (and not protected by Deadpool R).
    if retreat and hp < 0.22 and not (tank == 10000070 and actor.has_buff(344101, now)):
        return True

    push_dx, push_dy = _unit(pos, tpos)
    push_end = (tpos[0] + push_dx * push_dist, tpos[1] + push_dy * push_dist)

    anchor, has_allies = ally_pull_anchor(actor, now)
    to_anchor_dx, to_anchor_dy = _unit(tpos, anchor)
    alignment = push_dx * to_anchor_dx + push_dy * to_anchor_dy

    # Peel check: push target away from a critically wounded nearby teammate.
    for ally in _friendly_fighters(arena, actor):
        if _ratio(ally) < 0.42:
            apos = ally.position_at(now)
            before = math.dist(apos, tpos)
            if before <= 230 and math.dist(apos, push_end) > before + 110:
                return True

    # Insec check: pushes enemy toward teammates / allied turret / allied side!
    if has_allies and alignment >= 0.25 and math.dist(tpos, anchor) >= 120:
        return True
    if not has_allies and alignment >= 0.40:
        return True

    # Bowling check: push ray intersects another visible enemy tank laterally or toward allies.
    if alignment >= -0.25:
        for other in seen:
            if (other.get('id') == target.get('id')
                    or other.get('objective') or other.get('structure') or other.get('barrier')):
                continue
            if circle_contact(tpos, push_end, other['pos'], other['pos'], 72) is not None:
                return True

    # Wall-slam check: solid wall within 65% of push distance pins & stuns enemy,
    # only if we are NOT shoving them away from our team!
    wall_hit = arena.geometry.wall_contact(tpos, push_end, 36)
    if wall_hit is not None and wall_hit * push_dist <= min(300, push_dist * 0.65):
        if alignment >= 0.0 or not has_allies:
            return True

    return False


def best_push_victim(actor, candidates, seen, now, *, cast_range=168, push_dist=480,
                     lethal_hp=0.24, retreat=False):
    """Pick the best visible enemy within ``cast_range`` for a directional push skill."""
    pos = actor.position_at(now)
    anchor, _ = ally_pull_anchor(actor, now)
    scored = []
    for sample in candidates:
        if sample.get('objective') or sample.get('structure') or sample.get('barrier'):
            continue
        if math.dist(pos, sample['pos']) > cast_range:
            continue
        if not push_is_favorable(actor, sample, seen, now, push_dist=push_dist,
                                 lethal_hp=lethal_hp, retreat=retreat, origin=pos):
            continue
        tpos = sample['pos']
        pdx, pdy = _unit(pos, tpos)
        adx, ady = _unit(tpos, anchor)
        insec_score = pdx * adx + pdy * ady
        scored.append((insec_score + (0.6 if sample.get('hp', 1.0) <= lethal_hp else 0.0),
                       -sample.get('hp', 1.0), sample))
    return max(scored, key=lambda item: item[:2])[2] if scored else None


def insec_goal(arena, actor, target, seen, now, *, behind_dist=116):
    """Compute a walkable position BEHIND ``target`` so knockbacks push into allies/walls.

    When currently standing on the allied front side of ``target``, guides the bot
    along a smooth 125px side-arc tangent around ``target`` so it wraps cleanly behind
    the enemy and kicks them straight back into teammates!
    """
    if target is None or target.get('objective') or target.get('structure') or target.get('barrier'):
        return None
    tank = actor.info['tank_id']
    hp = _ratio(actor)
    if tank == 10000070:
        if (actor.skill_sealed(2, now)
                or actor.cooldowns.get(2, now + 9999) > now + 1800
                or (hp < 0.35 and not actor.has_buff(344101, now))):
            return None
    elif tank == 10000094:
        if (getattr(actor, 'form', None) or actor.skill_sealed(1, now)
                or (now >= getattr(actor, 'e_second_until', 0)
                    and actor.cooldowns.get(1, now + 9999) > now + 900)
                or hp < 0.42):
            return None
    else:
        return None

    pos = actor.position_at(now)
    tpos = target['pos']
    if math.dist(pos, tpos) > 580:
        return None

    anchor, _ = ally_pull_anchor(actor, now)
    away_dx, away_dy = _unit(anchor, tpos)
    behind_angle = math.atan2(away_dy, away_dx)
    cur_angle = math.atan2(pos[1] - tpos[1], pos[0] - tpos[0])
    diff = (behind_angle - cur_angle + math.pi) % math.tau - math.pi

    # If we are >95 deg away from the behind-spot and close to target, step via side arc
    # so we circle around target's body instead of body-blocking on target's front!
    if abs(diff) > 1.65 and math.dist(pos, tpos) < 220:
        step_dir = 1.0 if diff >= 0 else -1.0
        mid_angle = cur_angle + step_dir * 1.35
        arc_pt = arena.geometry.clamp_tank_position((
            round(tpos[0] + math.cos(mid_angle) * 132),
            round(tpos[1] + math.sin(mid_angle) * 132),
        ))
        if arena.geometry.can_walk_to(arc_pt):
            return arc_pt

    friends = len([a for a in _friendly_fighters(arena, actor)
                   if math.dist(tpos, a.position_at(now)) <= 640])

    best = None
    best_cost = 1e9
    for offset in (0.0, 0.34, -0.34, 0.68, -0.68):
        ang = behind_angle + offset
        cand = arena.geometry.clamp_tank_position((
            round(tpos[0] + math.cos(ang) * behind_dist),
            round(tpos[1] + math.sin(ang) * behind_dist),
        ))
        if not arena.geometry.can_walk_to(cand):
            continue
        if arena.geometry.wall_contact(cand, tpos) is not None:
            continue
        threats = sum(math.dist(cand, s['pos']) <= 300 for s in seen
                      if not s.get('barrier') and not s.get('structure'))
        if threats > friends + 2 and not (tank == 10000070 and actor.has_buff(344101, now)):
            continue
        cost = math.dist(pos, cand) + abs(offset) * 95.0 + threats * 35.0
        if cost < best_cost:
            best_cost = cost
            best = cand
    return best


def superman_toss_point(actor, victim_sample, seen, now):
    """Choose a 528px throw destination for Superman's Space (328301).

    Throws the grabbed enemy straight into allied teammates / allied turret first,
    or onto a multi-enemy cluster for AoE stun, or backward toward allied spawn.
    Never drops the enemy 0px in place on top of Superman when a better throw exists.
    """
    pos = actor.position_at(now)
    anchor, has_allies = ally_pull_anchor(actor, now)
    if has_allies and math.dist(pos, anchor) >= 96:
        dx, dy = _unit(pos, anchor)
        dist = min(528.0, math.dist(pos, anchor))
        return actor.arena.geometry.clamp_tank_position((
            round(pos[0] + dx * dist),
            round(pos[1] + dy * dist),
        ))

    # Secondary: slam into a >= 2 enemy cluster within 528px for AoE landing stun.
    clusters = [
        s for s in seen
        if s.get('id') != victim_sample.get('id')
        and not s.get('barrier') and not s.get('structure')
        and 96 <= math.dist(pos, s['pos']) <= 528
    ]
    if clusters:
        best_cluster = max(
            clusters,
            key=lambda s: (
                sum(math.dist(s['pos'], o['pos']) <= 130 for o in seen if not o.get('barrier')),
                -math.dist(pos, s['pos']),
            ),
        )
        return tuple(round(v) for v in best_cluster['pos'])

    # Fallback: throw full 528px back toward allied spawn.
    dx, dy = _unit(pos, anchor)
    return actor.arena.geometry.clamp_tank_position((
        round(pos[0] + dx * 480),
        round(pos[1] + dy * 480),
    ))


def ranged_kite_point(actor, brain, target, seen, dest, retreat, now, length, *,
                      desired=350, fixed=False, blink=False):
    """Smart dash/blink positioning for ranged Mages & Marksmen.

    Unlike frontline ``mobility()`` (which demands landing within <=200px melee!),
    ranged carries use mobility to:
    1. Kite backward / diagonally away when an enemy closes inside ``< 260px`` or retreating.
    2. Step onto an open lateral firing angle at ``[desired-65, desired+45]`` when chasing
       from afar — NEVER dashing face-first into enemy melee unless executing a solo <20% foe.
    """
    from bot_ai04 import mobility_goal_ok

    arena = actor.arena
    pos = actor.position_at(now)
    tpos = target['pos']
    distance = math.dist(pos, tpos)
    hp = _ratio(actor)
    threats = [s for s in seen if not s.get('barrier') and not s.get('structure')]
    closest_threat = min(threats, key=lambda s: math.dist(pos, s['pos'])) if threats else target
    closest_dist = math.dist(pos, closest_threat['pos'])
    anchor, _ = ally_pull_anchor(actor, now)

    need_kite = retreat or closest_dist < min(260, desired - 55) or (hp < 0.55 and closest_dist < 330)
    resolver = actor.blink_destination if blink else actor.move_destination

    if need_kite:
        away_angle = math.atan2(pos[1] - closest_threat['pos'][1], pos[0] - closest_threat['pos'][0])
        options = []
        for offset in (0.0, 0.45, -0.45, 0.90, -0.90, 1.30, -1.30):
            ang = away_angle + offset
            raw_dir = arena.geometry.clamp_tank_position((
                round(pos[0] + math.cos(ang) * length),
                round(pos[1] + math.sin(ang) * length),
            ))
            if math.dist(pos, raw_dir) < 1:
                continue
            requested = aimed(pos, raw_dir, length, fixed=fixed)
            end = resolver(pos, requested)
            if math.dist(pos, end) < 84 or not arena.geometry.can_walk_to(end):
                continue
            if not mobility_goal_ok(brain, pos, end):
                continue
            new_closest = min((math.dist(end, s['pos']) for s in threats), default=math.dist(end, tpos))
            if new_closest < closest_dist + 64:
                continue
            # Prefer kiting toward allies while keeping firing LOS when healthy.
            ally_bonus = -math.dist(end, anchor) * 0.18
            los_bonus = 55.0 if (not retreat and math.dist(end, tpos) <= desired + 130
                                 and arena.geometry.wall_contact(end, tpos) is None) else 0.0
            crowd_pen = sum(max(0.0, 320.0 - math.dist(end, s['pos'])) for s in threats) * 0.9
            score = new_closest + ally_bonus + los_bonus - crowd_pen
            choice_pt = raw_dir if fixed else tuple(round(v) for v in requested)
            options.append((score, choice_pt))
        return max(options, key=lambda item: item[0])[1] if options else None

    # Offensive reposition: only when out of comfortable range, landing at safe kiting band!
    solo_execute = target.get('hp', 1.0) <= 0.20 and len(threats) <= 1 and hp >= 0.50
    if distance <= desired + 55 and not solo_execute:
        return None

    to_target = math.atan2(tpos[1] - pos[1], tpos[0] - pos[0])
    min_safe = 155 if solo_execute else max(255, desired - 75)
    max_safe = 260 if solo_execute else desired + 55
    friends_near = len([a for a in _friendly_fighters(arena, actor)
                        if math.dist(tpos, a.position_at(now)) <= 560])
    options = []
    for offset in (0.35, -0.35, 0.65, -0.65, 0.0, 0.95, -0.95):
        ang = to_target + offset
        step = min(length, max(96.0, distance - desired + 40.0))
        raw_dir = arena.geometry.clamp_tank_position((
            round(pos[0] + math.cos(ang) * step),
            round(pos[1] + math.sin(ang) * step),
        ))
        if math.dist(pos, raw_dir) < 1:
            continue
        requested = aimed(pos, raw_dir, length if fixed else step, fixed=fixed)
        end = resolver(pos, requested)
        if math.dist(pos, end) < 84 or not arena.geometry.can_walk_to(end):
            continue
        if not mobility_goal_ok(brain, pos, end):
            continue
        after = math.dist(end, tpos)
        if not (min_safe <= after <= max_safe):
            continue
        if any(math.dist(end, s['pos']) < 230 for s in threats if s.get('id') != target.get('id')):
            continue
        local_enemies = sum(math.dist(end, s['pos']) <= 360 for s in threats)
        if hp < 0.50 or local_enemies > friends_near + 1:
            continue
        if arena.geometry.wall_contact(end, tpos) is not None:
            continue
        score = -abs(after - desired) - local_enemies * 45.0 + abs(offset) * 20.0
        choice_pt = raw_dir if fixed else tuple(round(v) for v in requested)
        options.append((score, choice_pt))
    return max(options, key=lambda item: item[0])[1] if options else None
