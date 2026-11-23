"""Player-like nicknames for bots, in the style of a Vietnamese game lobby.

Ranked identities get one stable name (seeded by owner + rank identity);
casual rooms draw fresh names per match. Names stay short for the native UI.
"""
from __future__ import annotations

import hashlib
import random

MAX_LEN = 16

_GIVEN = ('Hùng', 'Tuấn', 'Nam', 'Long', 'Minh', 'Huy', 'Khoa', 'Đạt', 'Phúc', 'Quân',
          'Trang', 'Linh', 'Ngọc', 'Vy', 'Thảo', 'My', 'Hiếu', 'Sơn', 'Bảo', 'Tùng')
_ASCII = ('hung', 'tuan', 'nam', 'long', 'minh', 'huy', 'khoa', 'dat', 'phuc', 'quan',
          'trang', 'linh', 'ngoc', 'vy', 'thao', 'my', 'hieu', 'son', 'bao', 'tung')
_NICK = ('Sói Đơn Độc', 'Gà Mờ', 'Thánh Bắn Lén', 'Vua Né', 'Kẻ Hủy Diệt', 'Mèo Lười',
         'Bé Bánh Bao', 'Tay To', 'Chiến Thần', 'Lính Mới', 'Bá Đạo', 'Hổ Báo',
         'Trùm Phố Cổ', 'Cáo Già', 'Xe Tăng Sữa', 'Pháo Thủ', 'Bố Đời', 'Rùa Thần')
_TAG = ('Pro', 'VN', 'Tank', 'Boy', 'Girl', 'Kute', 'Vip', 'Gaming', 'TV', 'xD')
_YEAR = ('97', '98', '99', '2k1', '2k3', '2k5', '2k7', '88', '123', '69', '102')


def _one(rng):
    shape = rng.randrange(7)
    if shape == 0:
        name = rng.choice(_NICK)
    elif shape == 1:
        name = f'{rng.choice(_NICK)} {rng.choice(_YEAR)}'
    elif shape == 2:
        name = f'{rng.choice(_ASCII)}{rng.choice(_YEAR)}'
    elif shape == 3:
        name = f'{rng.choice(_TAG)}{rng.choice(_ASCII).capitalize()}'
    elif shape == 4:
        name = f'{rng.choice(_GIVEN)} {rng.choice(_TAG)}'
    elif shape == 5:
        name = f'xX{rng.choice(_ASCII).capitalize()}Xx'
    else:
        name = f'{rng.choice(_ASCII)}_{rng.choice(_TAG).lower()}{rng.randrange(1, 100)}'
    return name[:MAX_LEN].strip()


def draw(rng, taken=()):
    """One nickname not already used in this room."""
    taken = set(taken)
    for _ in range(50):
        name = _one(rng)
        if name and name not in taken:
            return name
    return f'{rng.choice(_ASCII)}{rng.randrange(1000, 9999)}'


def ranked(owner, rank_bot_id, taken=()):
    seed = hashlib.sha256(f'rank-name:{int(owner)}:{int(rank_bot_id)}'.encode()).digest()
    return draw(random.Random(int.from_bytes(seed[:8], 'big')), taken)


def is_placeholder(name):
    """The historical '<Tank> <n>' label generated before nicknames existed."""
    from bot_setup import AI_TANKS
    if not isinstance(name, str) or ' ' not in name:
        return False
    prefix, _, number = name.rpartition(' ')
    return number.isdigit() and prefix in set(AI_TANKS.values())
