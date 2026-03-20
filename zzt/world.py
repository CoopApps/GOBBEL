"""
ZZT World file parser and serializer.

Binary layout based on ZZT 3.2 (Turbo Pascal 5.5).
Offsets verified against Zookeeper (DrDos0016) and the Reconstruction of ZZT.
"""

import struct
from dataclasses import dataclass, field
from typing import Optional


# ─── Element IDs ────────────────────────────────────────────────────────────

ELEMENT_NAMES = {
    0:  "Empty",
    1:  "BoardEdge",
    2:  "Messenger",
    3:  "Monitor",
    4:  "Player",
    5:  "Ammo",
    6:  "Torch",
    7:  "Gem",
    8:  "Key",
    9:  "Door",
    10: "Scroll",
    11: "Passage",
    12: "Duplicator",
    13: "Bomb",
    14: "Energizer",
    15: "Star",
    16: "CWConveyor",
    17: "CCWConveyor",
    18: "Bullet",
    19: "Water",
    20: "Forest",
    21: "Solid",
    22: "Normal",
    23: "Breakable",
    24: "Boulder",
    25: "SliderNS",
    26: "SliderEW",
    27: "Fake",
    28: "Invisible",
    29: "BlinkWall",
    30: "Transporter",
    31: "Line",
    32: "Ricochet",
    33: "BlinkRayEW",
    34: "Bear",
    35: "Ruffian",
    36: "Object",
    37: "Slime",
    38: "Shark",
    39: "SpinningGun",
    40: "Pusher",
    41: "Lion",
    42: "Tiger",
    43: "BlinkRayNS",
    44: "Head",
    45: "Segment",
    47: "TextBlue",
    48: "TextGreen",
    49: "TextCyan",
    50: "TextRed",
    51: "TextPurple",
    52: "TextYellow",
    53: "TextWhite",
}

ELEMENT_IDS = {v: k for k, v in ELEMENT_NAMES.items()}

# Default display chars for elements (CP437)
ELEMENT_CHARS = {
    0:  32,   # Empty: space
    4:  2,    # Player: ☻
    5:  132,  # Ammo: ä
    6:  157,  # Torch: ¥
    7:  4,    # Gem: ♦
    8:  12,   # Key: ♀
    9:  10,   # Door: ♂
    10: 232,  # Scroll: Σ
    11: 240,  # Passage: ≡
    12: 250,  # Duplicator: ·
    13: 11,   # Bomb: ♂
    14: 127,  # Energizer: ⌂
    20: 176,  # Forest: ░
    21: 219,  # Solid: █
    22: 178,  # Normal: ▓
    23: 177,  # Breakable: ▒
    24: 254,  # Boulder: ■
    25: 18,   # SliderNS: ↕
    26: 29,   # SliderEW: ↔
    27: 178,  # Fake: ▓
    31: 206,  # Line: ╬
    32: 42,   # Ricochet: *
    34: 153,  # Bear: Ö
    35: 5,    # Ruffian: ♣
    36: 2,    # Object: ☻ (overridden by P1 char)
    37: 42,   # Slime: *
    38: 94,   # Shark: ^
    39: 24,   # SpinningGun: ↑
    40: 16,   # Pusher: ►
    41: 234,  # Lion: Ω
    42: 227,  # Tiger: π
    44: 233,  # Head: é
    45: 79,   # Segment: O
}

COLOR_FG = {
    0: "Black", 1: "DarkBlue", 2: "DarkGreen", 3: "DarkCyan",
    4: "DarkRed", 5: "DarkMagenta", 6: "Brown", 7: "Gray",
    8: "DarkGray", 9: "Blue", 10: "Green", 11: "Cyan",
    12: "Red", 13: "Magenta", 14: "Yellow", 15: "White",
}
COLOR_BG = {
    0: "Black", 1: "DarkBlue", 2: "DarkGreen", 3: "DarkCyan",
    4: "DarkRed", 5: "DarkMagenta", 6: "Brown", 7: "Gray",
}


BOARD_WIDTH  = 60
BOARD_HEIGHT = 25
MAX_STAT     = 150
MAX_FLAG     = 10

WORLD_MAGIC_ZZT = -1
HEADER_SIZE = 512  # bytes before first board


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class Tile:
    element: int = 0
    color: int   = 0

    @property
    def element_name(self) -> str:
        return ELEMENT_NAMES.get(self.element, f"Unknown({self.element})")

    @property
    def fg_color(self) -> int:
        return self.color & 0x0F

    @property
    def bg_color(self) -> int:
        return (self.color >> 4) & 0x07

    @property
    def blink(self) -> bool:
        return bool(self.color & 0x80)


@dataclass
class Stat:
    """A status element: player, enemy, object, scroll, etc."""
    x: int           = 0
    y: int           = 0
    step_x: int      = 0
    step_y: int      = 0
    cycle: int       = 1
    p1: int          = 0   # For Object: display char
    p2: int          = 0
    p3: int          = 0
    follower: int    = -1
    leader: int      = -1
    under: Tile      = field(default_factory=Tile)
    data_pos: int    = 0
    data: bytes      = b""   # ZZT-OOP program source

    @property
    def oop_code(self) -> str:
        """Return ZZT-OOP code as text (strips leading @name line if present)."""
        try:
            return self.data.decode("ascii", errors="replace")
        except Exception:
            return ""


@dataclass
class BoardInfo:
    max_shots: int          = 255
    is_dark: bool           = False
    neighbor_north: int     = 0
    neighbor_south: int     = 0
    neighbor_west:  int     = 0
    neighbor_east:  int     = 0
    reenter_on_zap: bool    = False
    message: str            = ""
    player_enter_x: int     = 0
    player_enter_y: int     = 0
    time_limit_sec: int     = 0


@dataclass
class Board:
    name: str  = ""
    tiles: list = field(default_factory=lambda: [
        [Tile() for _ in range(BOARD_HEIGHT + 2)]
        for _ in range(BOARD_WIDTH + 2)
    ])
    stats: list = field(default_factory=list)
    info: BoardInfo = field(default_factory=BoardInfo)

    def get_tile(self, x: int, y: int) -> Tile:
        """x: 1..60, y: 1..25"""
        return self.tiles[x][y]

    def set_tile(self, x: int, y: int, element: int, color: int) -> None:
        """x: 1..60, y: 1..25"""
        self.tiles[x][y] = Tile(element, color)

    def ascii_art(self) -> str:
        """Return an ASCII representation of the board with x/y coordinate rulers."""
        _CHAR_MAP = {
            0: ' ', 20: '░', 21: '█', 22: '▓', 23: '▒',
            4: '@', 36: '☺', 34: 'B', 35: 'R', 41: 'L',
            42: 'T', 44: 'H', 5: 'a', 6: 't', 7: '*',
            8: 'k', 9: 'd', 10: '$', 11: '≡', 13: 'b',
            14: 'E', 19: '~',
        }
        # 3-char row prefix "   " aligns with " y " row labels
        ruler_tens = "   "
        ruler_ones = "   "
        for x in range(1, BOARD_WIDTH + 1):
            ruler_tens += str(x // 10) if x % 10 == 0 else ' '
            ruler_ones += str(x % 10)
        lines = [ruler_tens, ruler_ones]
        for row in range(1, BOARD_HEIGHT + 1):
            line = f"{row:2} "
            for col in range(1, BOARD_WIDTH + 1):
                t = self.tiles[col][row]
                line += _CHAR_MAP.get(t.element, '?')
            lines.append(line)
        return "\n".join(lines)

    def query_region(self, x1: int, y1: int, x2: int, y2: int) -> list:
        """Return tile details for every cell in the bounding box (1-based, inclusive)."""
        from zzt.world import ELEMENT_NAMES
        # Build stat lookup: (x,y) -> stat_index
        stat_at = {(s.x, s.y): i for i, s in enumerate(self.stats)}
        tiles = []
        for row in range(max(1, y1), min(BOARD_HEIGHT, y2) + 1):
            for col in range(max(1, x1), min(BOARD_WIDTH, x2) + 1):
                t = self.tiles[col][row]
                tiles.append({
                    "x": col,
                    "y": row,
                    "element": ELEMENT_NAMES.get(t.element, "Unknown"),
                    "element_id": t.element,
                    "color": f"0x{t.color:02X}",
                    "stat_index": stat_at.get((col, row)),
                })
        return tiles


@dataclass
class WorldInfo:
    ammo: int            = 0
    gems: int            = 0
    keys: list           = field(default_factory=lambda: [False] * 7)
    health: int          = 100
    current_board: int   = 0
    torches: int         = 0
    torch_ticks: int     = 0
    energizer_ticks: int = 0
    score: int           = 0
    name: str            = "UNTITLED"
    flags: list          = field(default_factory=lambda: [""] * MAX_FLAG)
    board_time_sec: int  = 0
    board_time_hsec: int = 0
    is_save: bool        = False


@dataclass
class World:
    info: WorldInfo         = field(default_factory=WorldInfo)
    boards: list            = field(default_factory=list)  # list of Board

    @property
    def board_count(self) -> int:
        return max(0, len(self.boards) - 1)  # title screen excluded from count


# ─── Parsing ─────────────────────────────────────────────────────────────────

def _read_pstring(data: bytes, offset: int, max_len: int) -> tuple[str, int]:
    """Read a Pascal-style length-prefixed string. Returns (string, bytes_consumed)."""
    length = data[offset]
    text   = data[offset + 1 : offset + 1 + min(length, max_len)]
    return text.decode("ascii", errors="replace"), max_len + 1


def _write_pstring(text: str, max_len: int) -> bytes:
    """Encode a Pascal string into (max_len+1) bytes."""
    encoded = text.encode("ascii", errors="replace")[:max_len]
    buf = bytearray(max_len + 1)
    buf[0] = len(encoded)
    buf[1:1 + len(encoded)] = encoded
    return bytes(buf)


def _decode_rle(data: bytes, offset: int) -> tuple[list, int]:
    """
    Decode RLE tile data into a flat list of (element, color) tuples.
    Returns (tiles_flat, new_offset).
    """
    tiles = []
    pos   = offset
    while len(tiles) < BOARD_WIDTH * BOARD_HEIGHT:
        count   = data[pos];     pos += 1
        element = data[pos];     pos += 1
        color   = data[pos];     pos += 1
        if count == 0:
            count = 256
        for _ in range(count):
            tiles.append(Tile(element, color))
            if len(tiles) >= BOARD_WIDTH * BOARD_HEIGHT:
                break
    return tiles, pos


def _encode_rle(board: Board) -> bytes:
    """RLE-encode the board tiles (column-major: left→right, top→bottom)."""
    flat = []
    for row in range(1, BOARD_HEIGHT + 1):
        for col in range(1, BOARD_WIDTH + 1):
            t = board.tiles[col][row]
            flat.append((t.element, t.color))

    out = bytearray()
    i   = 0
    while i < len(flat):
        j = i + 1
        while j < len(flat) and flat[j] == flat[i] and (j - i) < 255:
            j += 1
        count = j - i
        out += bytes([count, flat[i][0], flat[i][1]])
        i = j
    return bytes(out)


def _read_stat(data: bytes, offset: int) -> tuple[Stat, int]:
    """Parse a single TStat record. Returns (stat, bytes_consumed)."""
    s = Stat()
    s.x        = data[offset + 0]
    s.y        = data[offset + 1]
    s.step_x   = struct.unpack_from("<h", data, offset + 2)[0]
    s.step_y   = struct.unpack_from("<h", data, offset + 4)[0]
    s.cycle    = struct.unpack_from("<h", data, offset + 6)[0]
    s.p1       = data[offset + 8]
    s.p2       = data[offset + 9]
    s.p3       = data[offset + 10]
    s.follower = struct.unpack_from("<h", data, offset + 11)[0]
    s.leader   = struct.unpack_from("<h", data, offset + 13)[0]
    under_elem = data[offset + 15]
    under_col  = data[offset + 16]
    s.under    = Tile(under_elem, under_col)
    # offsets 17-20: 4 bytes (two dummy pointers, ignored)
    s.data_pos = struct.unpack_from("<h", data, offset + 21)[0]
    data_len   = struct.unpack_from("<h", data, offset + 23)[0]
    consumed   = 25
    if data_len > 0:
        s.data = data[offset + consumed : offset + consumed + data_len]
        consumed += data_len
    return s, consumed


def _write_stat(stat: Stat) -> bytes:
    """Serialize a TStat record."""
    buf = bytearray(25 + len(stat.data))
    buf[0] = stat.x & 0xFF
    buf[1] = stat.y & 0xFF
    struct.pack_into("<h", buf, 2,  stat.step_x)
    struct.pack_into("<h", buf, 4,  stat.step_y)
    struct.pack_into("<h", buf, 6,  stat.cycle)
    buf[8]  = stat.p1 & 0xFF
    buf[9]  = stat.p2 & 0xFF
    buf[10] = stat.p3 & 0xFF
    struct.pack_into("<h", buf, 11, stat.follower)
    struct.pack_into("<h", buf, 13, stat.leader)
    buf[15] = stat.under.element & 0xFF
    buf[16] = stat.under.color   & 0xFF
    # bytes 17-20: dummy pointers = 0
    struct.pack_into("<h", buf, 21, stat.data_pos)
    struct.pack_into("<h", buf, 23, len(stat.data))
    if stat.data:
        buf[25:25 + len(stat.data)] = stat.data
    return bytes(buf)


def _parse_board(data: bytes, offset: int) -> tuple[Board, int]:
    """Parse one board from the binary stream. Returns (board, bytes_consumed_including_size_word)."""
    board_size = struct.unpack_from("<H", data, offset)[0]
    board_data = data[offset + 2 : offset + 2 + board_size]
    pos = 0

    board      = Board()
    board.name, _ = _read_pstring(board_data, pos, 50)
    pos += 51   # string[50] = 51 bytes

    # RLE tiles
    flat_tiles, pos = _decode_rle(board_data, pos)
    idx = 0
    for row in range(1, BOARD_HEIGHT + 1):
        for col in range(1, BOARD_WIDTH + 1):
            board.tiles[col][row] = flat_tiles[idx]
            idx += 1

    # Board properties
    info = BoardInfo()
    info.max_shots       = board_data[pos];      pos += 1
    info.is_dark         = bool(board_data[pos]); pos += 1
    info.neighbor_north  = board_data[pos];       pos += 1
    info.neighbor_south  = board_data[pos];       pos += 1
    info.neighbor_west   = board_data[pos];       pos += 1
    info.neighbor_east   = board_data[pos];       pos += 1
    info.reenter_on_zap  = bool(board_data[pos]); pos += 1
    info.message, _      = _read_pstring(board_data, pos, 58)
    pos += 59   # string[58] = 59 bytes
    info.player_enter_x  = board_data[pos];       pos += 1
    info.player_enter_y  = board_data[pos];       pos += 1
    info.time_limit_sec  = struct.unpack_from("<h", board_data, pos)[0]; pos += 2
    pos += 16   # 16 unused bytes
    board.info = info

    # Status elements
    stat_count = struct.unpack_from("<h", board_data, pos)[0]; pos += 2
    for _ in range(stat_count + 1):   # +1 includes the player stat
        if pos >= len(board_data):
            break
        stat, consumed = _read_stat(board_data, pos)
        board.stats.append(stat)
        pos += consumed

    return board, 2 + board_size


def _serialize_board(board: Board) -> bytes:
    """Serialize a Board to its on-disk representation (size word + data)."""
    buf = bytearray()

    # Name
    buf += _write_pstring(board.name, 50)

    # RLE tiles
    buf += _encode_rle(board)

    # Board info
    info = board.info
    buf += bytes([info.max_shots & 0xFF])
    buf += bytes([1 if info.is_dark else 0])
    buf += bytes([info.neighbor_north & 0xFF])
    buf += bytes([info.neighbor_south & 0xFF])
    buf += bytes([info.neighbor_west  & 0xFF])
    buf += bytes([info.neighbor_east  & 0xFF])
    buf += bytes([1 if info.reenter_on_zap else 0])
    buf += _write_pstring(info.message, 58)
    buf += bytes([info.player_enter_x & 0xFF])
    buf += bytes([info.player_enter_y & 0xFF])
    struct.pack_into("<h", tmp := bytearray(2), 0, info.time_limit_sec)
    buf += bytes(tmp)
    buf += bytes(16)  # 16 unused bytes

    # Stat count (excluding player stat at index 0)
    stat_count = max(0, len(board.stats) - 1)
    struct.pack_into("<h", tmp := bytearray(2), 0, stat_count)
    buf += bytes(tmp)
    for stat in board.stats:
        buf += _write_stat(stat)

    # Prepend board size
    size_bytes = bytearray(2)
    struct.pack_into("<H", size_bytes, 0, len(buf))
    return bytes(size_bytes) + bytes(buf)


# ─── World-level parse / serialize ───────────────────────────────────────────

def parse_world(data: bytes) -> World:
    """Parse a ZZT world file from raw bytes."""
    magic = struct.unpack_from("<h", data, 0)[0]
    if magic != WORLD_MAGIC_ZZT:
        raise ValueError(f"Not a ZZT world file (magic={magic:#06x}, expected {WORLD_MAGIC_ZZT})")

    num_boards = struct.unpack_from("<h", data, 2)[0]

    info = WorldInfo()
    info.ammo            = struct.unpack_from("<h", data, 4)[0]
    info.gems            = struct.unpack_from("<h", data, 6)[0]
    info.keys            = [bool(data[8 + i]) for i in range(7)]
    info.health          = struct.unpack_from("<h", data, 15)[0]
    info.current_board   = struct.unpack_from("<h", data, 17)[0]
    info.torches         = struct.unpack_from("<h", data, 19)[0]
    info.torch_ticks     = struct.unpack_from("<h", data, 21)[0]
    info.energizer_ticks = struct.unpack_from("<h", data, 23)[0]
    # offset 25-28: two unused int16s
    info.score           = struct.unpack_from("<h", data, 29)[0]
    info.name, _         = _read_pstring(data, 31, 19)
    info.flags           = []
    for i in range(MAX_FLAG):
        flag_text, _ = _read_pstring(data, 51 + i * 20, 19)
        info.flags.append(flag_text)
    info.board_time_sec  = struct.unpack_from("<h", data, 251)[0]
    info.board_time_hsec = struct.unpack_from("<h", data, 253)[0]
    info.is_save         = bool(data[255])

    world = World(info=info)

    # Parse boards (title screen + num_boards)
    offset = HEADER_SIZE
    for _ in range(num_boards + 1):
        if offset >= len(data):
            break
        board, consumed = _parse_board(data, offset)
        world.boards.append(board)
        offset += consumed

    return world


def serialize_world(world: World) -> bytes:
    """Serialize a World to raw bytes suitable for writing as a .ZZT file."""
    buf = bytearray(HEADER_SIZE)

    info = world.info
    struct.pack_into("<h", buf, 0, WORLD_MAGIC_ZZT)
    struct.pack_into("<h", buf, 2, world.board_count)
    struct.pack_into("<h", buf, 4, info.ammo)
    struct.pack_into("<h", buf, 6, info.gems)
    for i, k in enumerate(info.keys[:7]):
        buf[8 + i] = 1 if k else 0
    struct.pack_into("<h", buf, 15, info.health)
    struct.pack_into("<h", buf, 17, info.current_board)
    struct.pack_into("<h", buf, 19, info.torches)
    struct.pack_into("<h", buf, 21, info.torch_ticks)
    struct.pack_into("<h", buf, 23, info.energizer_ticks)
    # offsets 25-28: zeroed unused fields
    struct.pack_into("<h", buf, 29, info.score)
    name_bytes = _write_pstring(info.name[:19], 19)
    buf[31:31 + 20] = name_bytes
    for i, flag in enumerate(info.flags[:MAX_FLAG]):
        flag_bytes = _write_pstring(flag[:19], 19)
        buf[51 + i * 20 : 51 + i * 20 + 20] = flag_bytes
    struct.pack_into("<h", buf, 251, info.board_time_sec)
    struct.pack_into("<h", buf, 253, info.board_time_hsec)
    buf[255] = 1 if info.is_save else 0

    for board in world.boards:
        buf += _serialize_board(board)

    return bytes(buf)


def load_world(path: str) -> World:
    with open(path, "rb") as f:
        return parse_world(f.read())


def save_world(world: World, path: str) -> None:
    with open(path, "wb") as f:
        f.write(serialize_world(world))
