"""Bot chat lines driven by real match events (kills, streaks, low HP, result).

Lines are queued with a human typing delay, rate limited per bot and per
match, and sent as S1597 (speaker id, camp, channel, name, text). The module
only reads public battle facts and uses its own RNG, so combat RNG, AI
decisions and replays are unaffected. State lives in ``arena.pk['bot_chat']``
with string keys so a checkpoint restores it unchanged.
"""
from __future__ import annotations

import random
import struct

CHAT_MSG = 1597
ALL, TEAM = 0, 1
GLOBAL_GAP_MS = 4000
BOT_GAP_MS = 12000
MAX_LINES = 28
STALE_MS = 8000
PRIORITY_EXTRA = 8
LOW_HP = .25

_rng = random.SystemRandom()

# Chance multiplier per event, times the bot's own chattiness.
# Every player is treated alike: a bot victim or killer is named as often as the human.
WEIGHT = dict(start=.35, first_blood=.8, kill=.3, kill_named=.35, streak=.8, multi=.9,
              shutdown=.8, killed=.3, killed_by=.35, ally_down=.15, low_hp=.3,
              grudge=1.0, revenge=1.0, punish=.2, rival_win=1.0, rival_lose=1.0, reply=.8,
              retort=.75, cheer=.35, hunt=.7)
NAMED_SHARE = .5          # share of kill / death lines that address the other player by name
MAX_THREAD = 2            # a taunt can get a retort, and that retort one answer back

LINES = {
    'trash': dict(
        start=['vào đi, đánh nhanh còn đi ngủ', 'team bên kia trông yếu thế', 'ai cản được tôi thì cản'],
        first_blood=['first blood, quá dễ', 'mở hàng rồi nhé', 'xin cái đầu đầu tiên'],
        kill=['ez', 'về nhà tập thêm đi {name}', 'tiếp theo là ai đây'],
        kill_named=['{name} ơi bắn thế thôi à', 'ez {name}', 'gặp tôi là toang {name} ạ'],
        streak=['không ai cản nổi à', '{n} mạng rồi, ai nữa', 'cả team bên kia đâu hết rồi'],
        multi=['ăn {n} một lúc, ngon', 'combo đẹp chưa'],
        shutdown=['hết bá đạo nhé {name}', 'chuỗi của {name} dừng ở đây'],
        killed=['hên thôi', 'lag thế', 'chờ đấy, hồi sinh là xong mày'],
        killed_by=['{name} ăn may thôi', 'đợi đấy {name}', 'lag chứ không phải tôi kém'],
        ally_down=['đánh kiểu gì vậy', 'thôi để tôi gánh'],
        low_hp=['máu thấp nhưng vẫn cân được', 'chưa chết đâu'],
        end_win=['gg ez', 'quá dễ, trận sau đi', 'gg, về tập thêm nhé'],
        end_lose=['team phế quá', 'thua do lag', 'trận sau phục thù'],
        end_draw=['hòa à, chán', 'đánh lại đi']),
    'calm': dict(
        start=['gl hf', 'chúc may mắn', 'bắt đầu thôi'],
        first_blood=['mở được mạng đầu', 'ok, lên đi'],
        kill=['ok', 'xong một'],
        kill_named=['{name} chơi được đấy', 'gg {name}'],
        streak=['giữ nhịp nhé', '{n} mạng, ổn'],
        multi=['được {n}'],
        shutdown=['chặn được {name} rồi'],
        killed=['sơ suất', 'chuẩn đấy'],
        killed_by=['nice shot {name}', '{name} bắn chuẩn'],
        ally_down=['bình tĩnh, đánh chậm lại', 'gom lại đánh cùng nhau'],
        low_hp=['máu thấp, lùi một chút', 'đi hồi máu đây'],
        end_win=['gg wp', 'gg mọi người'],
        end_lose=['gg wp', 'gg, trận sau'],
        end_draw=['gg, hòa']),
    'team': dict(
        start=['bám nhau đánh nhé', 'đi cùng nhau, đừng lẻ', 'tập trung mục tiêu nha'],
        first_blood=['đẹp, cả team lên', 'mở đầu tốt lắm'],
        kill=['dồn tiếp thằng máu thấp', 'xong, tiến lên'],
        kill_named=['hạ được {name} rồi, lên', 'bắt được {name}'],
        streak=['cứ thế giữ đội hình', 'team đang ổn, đừng tham'],
        multi=['dọn được {n}, đẩy lên'],
        shutdown=['chặn được {name} rồi anh em'],
        killed=['sorry, tôi lên sớm quá', 'cẩn thận bên đó'],
        killed_by=['coi chừng {name}, bắn đau lắm', '{name} đang mạnh, đánh hội đồng nó'],
        ally_down=['đợi tôi, đang tới', 'đừng đánh lẻ', 'lùi về gom lại'],
        low_hp=['máu thấp, ai yểm trợ với', 'tôi lùi đây, che giúp'],
        end_win=['gg cả team', 'phối hợp tốt lắm', 'gg, team chơi hay'],
        end_lose=['gg, lần sau bám nhau hơn', 'không sao, trận sau'],
        end_draw=['gg, suýt nữa']),
    'funny': dict(
        start=['ai mang bánh mì không', 'đánh xong đi ăn phở', 'xe tăng của tôi mới rửa đấy'],
        first_blood=['hihi', 'xin lỗi nhé, tay tôi tự bắn'],
        kill=['hihi', 'ối, trúng à', 'xin lỗi nha'],
        kill_named=['{name} ơi xin lỗi nha', 'bắn bừa mà trúng {name}'],
        streak=['tôi cũng không hiểu sao mình mạnh thế', '{n} mạng mà không biết bắn'],
        multi=['{n} mạng, mẹ ơi con giỏi chưa'],
        shutdown=['{name} bị cụt hứng rồi'],
        killed=['toang', 'ơ kìa', 'tôi đi đâu đây'],
        killed_by=['{name} ác thế', 'thôi {name} tha cho tôi'],
        ally_down=['ơ đồng đội đâu rồi', 'một người ngã xuống'],
        low_hp=['máu đỏ lòm rồi', 'cứu với, sắp toang'],
        end_win=['gg, khao trà đá', 'thắng rồi đi ăn thôi'],
        end_lose=['gg, đổ tại xe tăng', 'thua nhưng vui'],
        end_draw=['hòa cả làng']),
    'rookie': dict(
        start=['mới chơi, nhẹ tay nha', 'nút bắn là nút nào nhỉ', 'hello mọi người'],
        first_blood=['ơ tôi giết được à', 'wow'],
        kill=['ơ được rồi', 'may quá'],
        kill_named=['xin lỗi {name}', 'trúng {name} thật à'],
        streak=['tôi đang bá à', '{n} mạng rồi kìa'],
        multi=['ơ {n} mạng luôn'],
        shutdown=['tôi chặn được {name} á'],
        killed=['lại chết', 'khó quá', 'sao chết nhanh vậy'],
        killed_by=['{name} chỉ tôi với', '{name} giỏi quá'],
        ally_down=['phải làm gì giờ', 'ơ'],
        low_hp=['máu thấp phải làm sao', 'sắp chết rồi'],
        end_win=['thắng rồi, gg', 'cảm ơn team gánh'],
        end_lose=['gg, tôi kém quá', 'xin lỗi team'],
        end_draw=['gg']),
}


def _state(arena):
    return arena.pk.setdefault('bot_chat', dict(queue=[], last_at=0, said={}, count=0,
                                                low={}, started=False))


def enabled(arena, *, finished=False):
    from bot_setup import BOT_MAPS
    pk = getattr(arena, 'pk', None)
    return (isinstance(pk, dict) and (finished or not pk.get('finished'))
            and arena.geometry.id in BOT_MAPS and not getattr(arena, 'tank_test', False))


def _speaker(actor):
    from battle_participants import human
    import bot_personality
    return (actor is not None and not human(actor) and not actor.info.get('npc_template')
            and bot_personality.of(actor)['kind'] is not None)


def _name(actor):
    return str(actor.info.get('name') or '')[:16] if actor is not None else ''


def _line(tone, event, **fields):
    extra = EXTRA.get(event, {})
    pool = (LINES.get(tone, {}).get(event) or extra.get(tone) or extra.get('*')
            or LINES['calm'].get(event))
    if not pool:
        return None
    text = _rng.choice(pool)
    try:
        return text.format(**fields)
    except (KeyError, IndexError):
        return None


def _say(arena, actor, event, now, *, channel=ALL, force=False, priority=False, target=None, depth=0, **fields):
    import bot_personality
    if not _speaker(actor):
        return False
    chat = _state(arena)
    if chat['count'] + len(chat['queue']) >= MAX_LINES + (PRIORITY_EXTRA if priority else 0):
        return False
    key = str(actor.id)
    if not priority and now - chat['said'].get(key, -BOT_GAP_MS) < BOT_GAP_MS:
        return False
    if priority:
        chat['queue'] = [item for item in chat['queue'] if item['id'] != actor.id]
    elif any(item['id'] == actor.id for item in chat['queue']):
        return False
    style = bot_personality.of(actor)
    if not force and _rng.random() > style['chat'] * WEIGHT.get(event, .3):
        return False
    text = _line(style['tone'], event, **fields)
    if not text:
        return False
    typing = _rng.randint(700, 1800) + min(2000, 45 * len(text))
    item = dict(id=actor.id, camp=actor.camp, channel=channel,
                name=_name(actor), text=text, due=now + typing, priority=priority)
    if target is not None and fields.get('name') and fields['name'] in text:
        item.update(target=target.id, depth=depth)   # the line addressed this player by name
    chat['queue'].append(item)
    chat['said'][key] = now
    return True


def _packet(item):
    name, text = item['name'].encode('utf-8'), item['text'].encode('utf-8')
    return (CHAT_MSG, struct.pack('<IBB', item['id'], item['camp'], item['channel'])
            + struct.pack('<H', len(name)) + name + struct.pack('<H', len(text)) + text)


def _bots(arena):
    return [a for a in arena.actors.values() if _speaker(a)]


def on_kill(arena, killer, victim, *, multi, streak, first, dead_streak, now):
    """Queue reactions to one kill; returns nothing, lines leave on later ticks."""
    if not enabled(arena) or victim is None or victim.info.get('npc_template'):
        return
    from battle_participants import human
    if killer is not None and (killer.info.get('npc_template') or killer.info.get('map_object')):
        killer = None
    n = max(multi, streak)
    if killer is not None and killer.camp != victim.camp:
        if first:
            _say(arena, killer, 'first_blood', now)
        elif dead_streak >= 3:
            _say(arena, killer, 'shutdown', now, name=_name(victim))
        elif multi >= 2:
            _say(arena, killer, 'multi', now, n=multi)
        elif streak >= 3:
            _say(arena, killer, 'streak', now, n=n)
        elif _rng.random() < NAMED_SHARE:
            _say(arena, killer, 'kill_named', now, target=victim, name=_name(victim))
        else:
            _say(arena, killer, 'kill', now, name=_name(victim))
        if _rng.random() < NAMED_SHARE:
            _say(arena, victim, 'killed_by', now, target=killer, name=_name(killer))
        else:
            _say(arena, victim, 'killed', now, name=_name(killer))
        if multi >= 2 or streak >= 3:
            mates = [a for a in _bots(arena) if a.camp == killer.camp and a is not killer and a.alive]
            if mates:
                _say(arena, _rng.choice(mates), 'cheer', now, channel=TEAM, name=_name(killer))
        if streak == 5:
            hunters = [a for a in _bots(arena) if a.camp == victim.camp and a.alive]
            if hunters:
                _say(arena, _rng.choice(hunters), 'hunt', now, channel=TEAM, priority=True, name=_name(killer))
    allies = [a for a in _bots(arena) if a.camp == victim.camp and a is not victim and a.alive]
    if allies:
        _say(arena, _rng.choice(allies), 'ally_down', now, channel=TEAM)


def tick(arena, now):
    """Greetings, low-HP calls, and due lines (at most one per global gap)."""
    if not enabled(arena):
        return []
    chat = _state(arena)
    # A restored checkpoint runs on a rebased clock; these timestamps are not
    # in battle_persistence.TIMES, so drop any that now lie in the future.
    if chat['last_at'] > now:
        chat['last_at'] = 0
    chat['said'] = {k: v for k, v in chat['said'].items() if v <= now + 6000}
    chat['queue'] = [item for item in chat['queue'] if item['due'] <= now + 10000]
    bots = _bots(arena)
    if not chat['started']:
        chat['started'] = True
        for actor in _rng.sample(bots, min(2, len(bots))):
            _say(arena, actor, 'start', now + _rng.randint(1500, 5000))
    for actor in bots:
        key = str(actor.id)
        if actor.alive and actor.hp / max(1, actor.max_hp) < LOW_HP and chat['low'].get(key) != actor.generation:
            chat['low'][key] = actor.generation
            _say(arena, actor, 'low_hp', now, channel=TEAM)
    chat['queue'] = [item for item in chat['queue']
                     if now - item['due'] < STALE_MS * (2 if item.get('priority') else 1)]
    due = sorted((item for item in chat['queue'] if item['due'] <= now),
                 key=lambda item: (not item.get('priority'), item['due']))
    if not due or now - chat['last_at'] < GLOBAL_GAP_MS:
        return []
    item = due[0]
    chat['queue'].remove(item)
    chat['last_at'] = now
    chat['count'] += 1
    _thread(arena, item, now)
    return [_packet(item)]


def _thread(arena, item, now):
    """A bot that was just addressed by name may answer, and the first speaker answer back."""
    target = arena.actors.get(item.get('target'))
    speaker = arena.actors.get(item['id'])
    depth = item.get('depth', 0) + 1
    if target is None or speaker is None or depth > MAX_THREAD or not _speaker(target):
        return
    _say(arena, target, 'retort', now, target=speaker, depth=depth, name=item['name'])


def finish_lines(arena, winner, now):
    """'gg' style lines sent with the result, one or two per camp."""
    if not enabled(arena, finished=True):
        return []
    lines = []
    for camp in (1, 2):
        event = 'end_draw' if not winner else 'end_win' if winner == camp else 'end_lose'
        members = [a for a in _bots(arena) if a.camp == camp]
        for actor in _rng.sample(members, min(len(members), _rng.randint(1, 2))):
            import bot_personality
            text = _line(bot_personality.of(actor)['tone'], event)
            if text:
                lines.append(_packet(dict(id=actor.id, camp=actor.camp, channel=ALL,
                                          name=_name(actor), text=text, due=now)))
    return lines


# ---------------------------------------------------------------- bot_mind reactions
# Lines for events that come from bot_mind; '*' is used when a tone has none.
EXTRA = {
    'grudge': {'*': ['{name}, nhớ mặt tao đấy', 'lại là {name}, được lắm', 'trận này tao săn {name}'],
               'rookie': ['{name} ơi tha cho em', 'sao {name} cứ nhắm em thế'],
               'funny': ['{name} ơi mình có thù oán gì đâu', 'được rồi {name}, giờ thành kẻ thù nhé']},
    'revenge': {'*': ['trả thù xong, {name}', 'nợ trả rồi nhé {name}', 'một đều {name} ạ'],
                'rookie': ['ơ trả thù được {name} rồi'],
                'calm': ['hòa nhau rồi {name}']},
    'punish': {'*': ['nó vừa dùng chiêu lớn, lên!', 'hết chiêu rồi, đánh nó đi', 'chiêu nó đang hồi, dồn vào']},
    'plan_rush': {'*': ['trận này ép sân từ đầu nhé', 'lên hết, đừng để chúng thở']},
    'plan_hold': {'*': ['giữ đội hình, phòng thủ phản công', 'đừng lao lên, để chúng tự vào']},
    'plan_split': {'*': ['tản ra đánh lẻ, quấy rối khắp nơi', 'mỗi người một hướng nhé']},
    'plan_focus': {'*': ['gọi mục tiêu nào đánh mục tiêu đó', 'dồn từng đứa một nhé']},
    'clutch': {'*': ['sát nút rồi, dồn hết lên!', 'còn kịp, all in!', 'không lùi nữa, đánh tổng lực']},
    'cocky': {'*': ['thắng chắc rồi, chơi thoải mái', 'dễ quá, đi dạo thôi'],
              'calm': ['đang dẫn, đừng chủ quan'], 'team': ['đang dẫn, giữ nhịp nhé']},
    'rival_win': {'*': ['lại gặp {name} à, hôm trước thắng rồi đấy', '{name}, lần trước mày thua tao rồi'],
                  'calm': ['chào {name}, lại gặp nhau'], 'rookie': ['{name} lại đến kìa']},
    'dive': {'*': ['không ai cản nổi tao, lên đây!', 'đang nóng tay, xông vào luôn', 'một mình tao cũng đủ'],
             'calm': ['đang thuận tay, đẩy lên'], 'rookie': ['ơ em đang ăn chuỗi, lao lên nhé'],
             'team': ['tôi mở đường, theo sau nhé']},
    'chase': {'*': ['{name} chạy đâu cho thoát', 'kệ cờ, tao phải hạ {name}', 'đứng lại {name}!'],
              'calm': ['để tôi xử {name}'], 'rookie': ['{name} ơi đứng yên cho em bắn']},
    'retort': {'*': ['{name} nói ít thôi', 'để xem ai cười cuối, {name}', 'ừ, lát gặp lại {name}', '{name} chờ đấy'],
               'trash': ['{name} gà mà nói to', 'im đi {name}', 'lần sau {name} khóc nhé'],
               'calm': ['bình tĩnh {name}, còn dài', 'ok {name}'],
               'team': ['{name} tập trung đánh đi', 'đừng cãi nhau, đánh tiếp'],
               'funny': ['{name} dỗi à', 'hihi {name} cay rồi', '{name} ơi đừng giận'],
               'rookie': ['{name} nhẹ tay thôi mà', 'em mới chơi mà {name}']},
    'cheer': {'*': ['{name} gánh team', 'đỉnh quá {name}', 'cứ thế {name}', '{name} bá đạo'],
              'calm': ['tốt lắm {name}'], 'rookie': ['{name} giỏi quá', 'theo {name} học hỏi'],
              'funny': ['{name} ăn gì mà khỏe thế']},
    'hunt': {'*': ['{name} đang ăn chuỗi, dồn nó!', 'cả team chặn {name}', 'không để {name} ăn thêm'],
             'calm': ['ưu tiên hạ {name}'], 'rookie': ['{name} mạnh quá, ai giúp với']},
    'peak': {'*': ['{name} đang ăn chuỗi, dồn nó lại!', 'cả đội chặn {name} ngay', 'không để {name} ăn tiếp']},
    'rival_lose': {'*':['{name}, lần này không thua nữa đâu', 'phục thù {name} hôm nay'],
                   'rookie': ['{name} nhẹ tay nhé, lần trước đau lắm'], 'funny': ['{name} lại đến bắt nạt à']},
}

REPLIES = (
    (('gg', 'good game'), ['gg', 'gg wp', 'gg nha']),
    (('ez', 'dễ'), ['ez cái gì', 'đợi đấy', 'mới đầu trận thôi']),
    (('noob', 'gà', 'kém', 'phế'), ['nói ít thôi', 'gà mà thắng mày đấy', 'để xem ai gà']),
    (('hi', 'hello', 'chào', 'alo'), ['chào', 'hello', 'hi bạn']),
    (('lag',), ['lag thật', 'mạng tôi cũng lag', 'đổ tại lag hoài']),
    (('haha', 'hihi', 'kk', '=))', ':))'), ['cười gì', 'haha', 'vui ghê']),
    (('sorry', 'xin lỗi', 'sr'), ['không sao', 'ok', 'chuyện nhỏ']),
    (('cứu', 'help', 'giúp'), ['đang tới', 'đợi tí', 'cố lên']),
    (('đẹp', 'hay', 'nice', 'ngon'), ['cảm ơn', 'thường thôi', 'hehe']),
)
DEFAULT_REPLIES = ['ừ', '?', 'tập trung đánh đi', 'ok', 'nói gì vậy']
MAX_HUMAN_TEXT = 80


def _force(arena, actor, event, now, **fields):
    """Speak regardless of chattiness; skips the per-bot gap, has extra cap room."""
    return _say(arena, actor, event, now, force=True, priority=True, **fields)


def react_grudge(arena, bot, other, level, now):
    if enabled(arena):
        _say(arena, bot, 'grudge', now, target=other, name=_name(other))


def react_revenge(arena, bot, other, now):
    if enabled(arena):
        _say(arena, bot, 'revenge', now, target=other, name=_name(other))


def react_punish(arena, caster, now):
    from battle_participants import human
    if not enabled(arena) or not human(caster):
        return
    watchers = [a for a in _bots(arena) if a.camp != caster.camp and a.alive]
    if watchers:
        _say(arena, _rng.choice(watchers), 'punish', now, channel=TEAM)


def react_mistake(arena, bot, target, reason, now):
    """Telegraph a dive or a grudge chase so the player can see and punish it."""
    if enabled(arena):
        _force(arena, bot, reason, now, name=_name(target) if target is not None else '')


def react_peak(arena, player, now):
    if not enabled(arena):
        return
    hunters = [a for a in _bots(arena) if a.camp != player.camp and a.alive]
    if hunters:
        _force(arena, _rng.choice(hunters), 'peak', now, channel=TEAM, name=_name(player))


def react_plan(arena, camp, plan, now):
    if not enabled(arena):
        return
    members = [a for a in _bots(arena) if a.camp == camp]
    if members:
        _force(arena, _rng.choice(members), 'plan_' + plan, now + _rng.randint(2500, 6000), channel=TEAM)


def react_mood(arena, camp, mood, now):
    if not enabled(arena):
        return
    members = [a for a in _bots(arena) if a.camp == camp and a.alive]
    if members:
        _force(arena, _rng.choice(members), mood, now, channel=TEAM if mood == 'clutch' else ALL)


def react_rival_greet(arena, bot, player, rival, now):
    if not enabled(arena):
        return
    won, lost = rival.get('wins', 0), rival.get('losses', 0)
    if won + lost < 2:
        return
    event = 'rival_win' if won > lost else 'rival_lose'
    _force(arena, bot, event, now + _rng.randint(1500, 7000), name=_name(player))


CHAT_INPUT = 598
MAX_CHAT_BYTES = 320


def decode_battle_chat(payload, scene_id):
    """(text, team) from a C598 body (scene u32, channel u8, u16-length UTF-8), or None."""
    if not 7 < len(payload) <= 7 + MAX_CHAT_BYTES:
        return None
    scene, channel, size = struct.unpack_from('<IBH', payload)
    if scene != scene_id or channel not in (0, 1) or len(payload) != 7 + size:
        return None
    try:
        return bytes(payload[7:]).decode('utf-8'), channel == 1
    except UnicodeDecodeError:
        return None


def on_human_chat(arena, speaker, text, team, now):
    """Echo a player's line to the battle and queue one or two bot replies."""
    text = ' '.join(str(text).split())[:MAX_HUMAN_TEXT]
    if not text or not enabled(arena):
        return []
    echo = _packet(dict(id=speaker.id, camp=speaker.camp, channel=TEAM if team else ALL,
                        name=_name(speaker), text=text, due=now))
    lowered = text.lower()
    pool = next((answers for keys, answers in REPLIES if any(k in lowered for k in keys)), DEFAULT_REPLIES)
    listeners = [a for a in _bots(arena) if not team or a.camp == speaker.camp]
    _rng.shuffle(listeners)
    chat = _state(arena)
    replied = 0
    for actor in listeners:
        if replied >= (2 if pool is not DEFAULT_REPLIES else 1):
            break
        import bot_personality
        if _rng.random() > bot_personality.of(actor)['chat'] * WEIGHT['reply']:
            continue
        reply = _rng.choice(pool)
        chat['queue'].append(dict(id=actor.id, camp=actor.camp, channel=TEAM if team else ALL,
                                  name=_name(actor), text=reply,
                                  due=now + _rng.randint(900, 2200) + 40 * len(reply)))
        replied += 1
    return [echo]
