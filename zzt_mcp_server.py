#!/usr/bin/env python3
"""
ZZT MCP Server
==============
An MCP (Model Context Protocol) server that lets Claude Code directly
read, create, and modify ZZT world files (.ZZT).

Usage (stdio transport, for Claude Code .mcp.json):
    python3 zzt_mcp_server.py

Available tools:
  zzt_read_world      – Parse a .ZZT file and return its structure as JSON
  zzt_list_boards     – List all boards in a world
  zzt_get_board       – Get a board's tiles as ASCII art + stat list
  zzt_set_tile        – Set a tile at (x, y) on a board
  zzt_add_object      – Add a ZZT Object with ZZT-OOP code
  zzt_add_board       – Add a new board to a world
  zzt_create_world    – Create a brand-new empty world file
  zzt_set_world_info  – Update world metadata (name, health, ammo, etc.)
  zzt_get_oop_code    – Get ZZT-OOP code from a stat element
  zzt_set_oop_code    – Set ZZT-OOP code on a stat element
  zzt_fill_rect       – Fill a rectangle of tiles with a single element
  zzt_connect_boards  – Set north/south/east/west exits between boards
"""

import json
import sys
import os
import traceback
from typing import Any

# Ensure local zzt package is importable
sys.path.insert(0, os.path.dirname(__file__))

from zzt.world import (
    World, WorldInfo, Board, BoardInfo, Tile, Stat,
    load_world, save_world, parse_world, serialize_world,
    ELEMENT_NAMES, ELEMENT_IDS, BOARD_WIDTH, BOARD_HEIGHT,
)


# ─── MCP protocol helpers ────────────────────────────────────────────────────

def _send(msg: dict) -> None:
    line = json.dumps(msg) + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


def _error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _ok(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _text(content: str) -> dict:
    return {"type": "text", "text": content}


# ─── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "zzt_create_world",
        "description": (
            "Create a new, empty ZZT world file. "
            "The world will have a title board (board 0) and one blank play board."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write the .ZZT file"},
                "name": {"type": "string", "description": "World name (max 19 chars)"},
                "title_board_name": {"type": "string", "description": "Title of the opening board"},
            },
            "required": ["path", "name"],
        },
    },
    {
        "name": "zzt_read_world",
        "description": "Parse a .ZZT file and return its metadata and board list as JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the .ZZT file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "zzt_list_boards",
        "description": "List all boards in a ZZT world with their indices and names.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "zzt_get_board",
        "description": (
            "Get a board's layout as ASCII art and a list of all stat elements "
            "(objects, enemies, scrolls). "
            "Coordinates are 1-based: x=1..60, y=1..25."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "board_index": {"type": "integer", "description": "0 = title board, 1+ = play boards"},
            },
            "required": ["path", "board_index"],
        },
    },
    {
        "name": "zzt_set_tile",
        "description": (
            "Set a single tile on a board. "
            "Element names: Empty, Solid, Normal, Breakable, Water, Forest, "
            "Fake, Invisible, Door, Boulder, SliderNS, SliderEW, Gem, Key, "
            "Ammo, Torch, Energizer, Bomb, Line, Ricochet, BlinkWall, Transporter. "
            "Color byte: bg(0-7)<<4 | fg(0-15). Common: 0x0F=white, 0x1F=white-on-blue, "
            "0x0E=yellow, 0x0A=green, 0x0C=red, 0x0B=cyan, 0x0D=magenta."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "board_index": {"type": "integer"},
                "x":           {"type": "integer", "description": "1..60"},
                "y":           {"type": "integer", "description": "1..25"},
                "element":     {"type": "string",  "description": "Element name or integer ID"},
                "color":       {"type": "integer", "description": "Color byte (bg<<4|fg)"},
            },
            "required": ["path", "board_index", "x", "y", "element", "color"],
        },
    },
    {
        "name": "zzt_fill_rect",
        "description": "Fill a rectangular region of a board with one element/color.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "board_index": {"type": "integer"},
                "x1":          {"type": "integer", "description": "Left edge (1..60)"},
                "y1":          {"type": "integer", "description": "Top edge (1..25)"},
                "x2":          {"type": "integer", "description": "Right edge (1..60)"},
                "y2":          {"type": "integer", "description": "Bottom edge (1..25)"},
                "element":     {"type": "string"},
                "color":       {"type": "integer"},
            },
            "required": ["path", "board_index", "x1", "y1", "x2", "y2", "element", "color"],
        },
    },
    {
        "name": "zzt_add_object",
        "description": (
            "Place a ZZT Object element on a board with ZZT-OOP code. "
            "ZZT-OOP examples:\n"
            "  #end  (do nothing)\n"
            "  #shoot n  (shoot north)\n"
            "  /n  (walk north each cycle)\n"
            "  ?n  (try to walk north, skip if blocked)\n"
            "  #give ammo 5  (give player 5 ammo)\n"
            "  @name  (first line sets object name)\n"
            "  :label  (defines a label to jump to)\n"
            "  #send label  (send message to self)\n"
            "  #send name:label  (send message to other object)\n"
            "  /i  (idle/pause one cycle)\n"
            "  #become solid  (replace self with solid wall)\n"
            "  'This is a comment\n"
            "  #die  (remove this object)\n"
            "Cycle: how often the object runs (1=fast, 3=normal, 8=slow)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "board_index": {"type": "integer"},
                "x":           {"type": "integer"},
                "y":           {"type": "integer"},
                "oop_code":    {"type": "string", "description": "ZZT-OOP source code"},
                "char":        {"type": "integer", "description": "Display character (0-255, default 2=☻)"},
                "color":       {"type": "integer", "description": "Color byte"},
                "cycle":       {"type": "integer", "description": "Execution cycle (default 3)"},
            },
            "required": ["path", "board_index", "x", "y", "oop_code"],
        },
    },
    {
        "name": "zzt_get_oop_code",
        "description": "Get the ZZT-OOP code from a stat element by its stat index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "board_index": {"type": "integer"},
                "stat_index":  {"type": "integer", "description": "0=player, 1+ = other stats"},
            },
            "required": ["path", "board_index", "stat_index"],
        },
    },
    {
        "name": "zzt_set_oop_code",
        "description": "Replace the ZZT-OOP code on an existing stat element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "board_index": {"type": "integer"},
                "stat_index":  {"type": "integer"},
                "oop_code":    {"type": "string"},
            },
            "required": ["path", "board_index", "stat_index", "oop_code"],
        },
    },
    {
        "name": "zzt_add_board",
        "description": "Add a new empty board to an existing world.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string"},
                "name":  {"type": "string", "description": "Board name (max 50 chars)"},
            },
            "required": ["path", "name"],
        },
    },
    {
        "name": "zzt_connect_boards",
        "description": "Set the exit links between two boards (north/south/east/west).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":           {"type": "string"},
                "board_index":    {"type": "integer", "description": "Board to configure"},
                "north":          {"type": "integer", "description": "Board index to the north (0 = none)"},
                "south":          {"type": "integer", "description": "Board index to the south (0 = none)"},
                "east":           {"type": "integer", "description": "Board index to the east (0 = none)"},
                "west":           {"type": "integer", "description": "Board index to the west (0 = none)"},
            },
            "required": ["path", "board_index"],
        },
    },
    {
        "name": "zzt_set_world_info",
        "description": "Update world metadata: name, health, ammo, gems, torches, score, starting board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string"},
                "name":          {"type": "string"},
                "health":        {"type": "integer"},
                "ammo":          {"type": "integer"},
                "gems":          {"type": "integer"},
                "torches":       {"type": "integer"},
                "score":         {"type": "integer"},
                "start_board":   {"type": "integer", "description": "Which board the player starts on"},
            },
            "required": ["path"],
        },
    },
]


# ─── Tool implementations ─────────────────────────────────────────────────────

def _resolve_element(value: str | int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        if v.isdigit():
            return int(v)
        # Case-insensitive lookup
        for name, eid in ELEMENT_IDS.items():
            if name.lower() == v.lower():
                return eid
        raise ValueError(f"Unknown element name: {v!r}")
    raise TypeError(f"Element must be str or int, got {type(value)}")


def _make_default_world(name: str, title_board_name: str = "Title Screen") -> World:
    """Build a minimal valid ZZT world."""
    info = WorldInfo()
    info.name          = name[:19]
    info.health        = 100
    info.current_board = 1

    # Title board (board 0)
    title = Board()
    title.name = title_board_name[:50]
    _border_board(title)
    # Player stat on title board
    player_stat = Stat()
    player_stat.x = 30
    player_stat.y = 12
    title.stats.append(player_stat)

    # First play board (board 1)
    play = Board()
    play.name = "Level 1"
    _border_board(play)
    player_stat2 = Stat()
    player_stat2.x = 30
    player_stat2.y = 12
    play.stats.append(player_stat2)

    return World(info=info, boards=[title, play])


def _border_board(board: Board) -> None:
    """Draw a solid border around the play area."""
    for x in range(1, BOARD_WIDTH + 1):
        board.set_tile(x, 1,           21, 0x0F)  # top
        board.set_tile(x, BOARD_HEIGHT, 21, 0x0F)  # bottom
    for y in range(1, BOARD_HEIGHT + 1):
        board.set_tile(1,           y, 21, 0x0F)   # left
        board.set_tile(BOARD_WIDTH, y, 21, 0x0F)   # right


def tool_create_world(args: dict) -> str:
    path  = args["path"]
    name  = args.get("name", "MY WORLD")
    title = args.get("title_board_name", "Title Screen")
    world = _make_default_world(name, title)
    save_world(world, path)
    return f"Created ZZT world '{name}' at {path!r} with {len(world.boards)} boards."


def tool_read_world(args: dict) -> dict:
    world = load_world(args["path"])
    boards = [
        {"index": i, "name": b.name,
         "stats": len(b.stats),
         "north": b.info.neighbor_north,
         "south": b.info.neighbor_south,
         "east":  b.info.neighbor_east,
         "west":  b.info.neighbor_west}
        for i, b in enumerate(world.boards)
    ]
    return {
        "world_name":    world.info.name,
        "health":        world.info.health,
        "ammo":          world.info.ammo,
        "gems":          world.info.gems,
        "torches":       world.info.torches,
        "score":         world.info.score,
        "keys":          world.info.keys,
        "current_board": world.info.current_board,
        "flags":         [f for f in world.info.flags if f],
        "board_count":   len(world.boards),
        "boards":        boards,
    }


def tool_list_boards(args: dict) -> list:
    world = load_world(args["path"])
    return [
        {"index": i, "name": b.name, "stat_count": len(b.stats)}
        for i, b in enumerate(world.boards)
    ]


def tool_get_board(args: dict) -> dict:
    world = load_world(args["path"])
    idx   = args["board_index"]
    board = world.boards[idx]
    stats_info = []
    for si, stat in enumerate(board.stats):
        elem_id = board.tiles[stat.x][stat.y].element if (
            1 <= stat.x <= BOARD_WIDTH and 1 <= stat.y <= BOARD_HEIGHT
        ) else 0
        stats_info.append({
            "index":   si,
            "x":       stat.x,
            "y":       stat.y,
            "element": ELEMENT_NAMES.get(elem_id, "Unknown"),
            "cycle":   stat.cycle,
            "p1":      stat.p1,
            "has_oop": len(stat.data) > 0,
            "oop_preview": stat.oop_code[:80] if stat.data else "",
        })
    return {
        "name":       board.name,
        "is_dark":    board.info.is_dark,
        "max_shots":  board.info.max_shots,
        "north":      board.info.neighbor_north,
        "south":      board.info.neighbor_south,
        "east":       board.info.neighbor_east,
        "west":       board.info.neighbor_west,
        "ascii_art":  board.ascii_art(),
        "stats":      stats_info,
    }


def tool_set_tile(args: dict) -> str:
    path = args["path"]
    world = load_world(path)
    board = world.boards[args["board_index"]]
    x     = args["x"]
    y     = args["y"]
    elem  = _resolve_element(args["element"])
    color = args["color"]
    if not (1 <= x <= BOARD_WIDTH and 1 <= y <= BOARD_HEIGHT):
        raise ValueError(f"Coordinates ({x},{y}) out of range (1..{BOARD_WIDTH}, 1..{BOARD_HEIGHT})")
    board.set_tile(x, y, elem, color)
    save_world(world, path)
    return f"Set tile at ({x},{y}) on board {args['board_index']} to {ELEMENT_NAMES.get(elem, elem)} color=0x{color:02X}"


def tool_fill_rect(args: dict) -> str:
    path  = args["path"]
    world = load_world(path)
    board = world.boards[args["board_index"]]
    elem  = _resolve_element(args["element"])
    color = args["color"]
    x1, y1 = max(1, args["x1"]), max(1, args["y1"])
    x2, y2 = min(BOARD_WIDTH, args["x2"]), min(BOARD_HEIGHT, args["y2"])
    count = 0
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            board.set_tile(x, y, elem, color)
            count += 1
    save_world(world, path)
    return f"Filled {count} tiles in rect ({x1},{y1})-({x2},{y2}) with {ELEMENT_NAMES.get(elem, elem)}"


def tool_add_object(args: dict) -> str:
    path  = args["path"]
    world = load_world(path)
    board = world.boards[args["board_index"]]
    x     = args["x"]
    y     = args["y"]
    code  = args.get("oop_code", "#end")
    char  = args.get("char", 2)
    color = args.get("color", 0x0E)
    cycle = args.get("cycle", 3)

    if not (1 <= x <= BOARD_WIDTH and 1 <= y <= BOARD_HEIGHT):
        raise ValueError(f"Coordinates ({x},{y}) out of range")

    stat = Stat()
    stat.x     = x
    stat.y     = y
    stat.cycle = cycle
    stat.p1    = char  # display char for Object
    stat.data  = code.encode("ascii", errors="replace")

    # The tile itself must be element 36 (Object)
    board.set_tile(x, y, 36, color)
    board.stats.append(stat)
    save_world(world, path)
    return (
        f"Added Object at ({x},{y}) on board {args['board_index']}, "
        f"char={char}, cycle={cycle}, code length={len(stat.data)}"
    )


def tool_get_oop_code(args: dict) -> str:
    world = load_world(args["path"])
    board = world.boards[args["board_index"]]
    stat  = board.stats[args["stat_index"]]
    return stat.oop_code or "(no ZZT-OOP code)"


def tool_set_oop_code(args: dict) -> str:
    path  = args["path"]
    world = load_world(path)
    board = world.boards[args["board_index"]]
    stat  = board.stats[args["stat_index"]]
    stat.data = args["oop_code"].encode("ascii", errors="replace")
    save_world(world, path)
    return f"Updated ZZT-OOP code on stat {args['stat_index']} ({len(stat.data)} bytes)"


def tool_add_board(args: dict) -> str:
    path  = args["path"]
    world = load_world(path)
    board = Board()
    board.name = args.get("name", "New Board")[:50]
    _border_board(board)
    # Place player stat
    ps = Stat()
    ps.x = 30
    ps.y = 12
    board.stats.append(ps)
    world.boards.append(board)
    save_world(world, path)
    return f"Added board '{board.name}' as index {len(world.boards) - 1}"


def tool_connect_boards(args: dict) -> str:
    path  = args["path"]
    world = load_world(path)
    board = world.boards[args["board_index"]]
    if "north" in args: board.info.neighbor_north = args["north"]
    if "south" in args: board.info.neighbor_south = args["south"]
    if "east"  in args: board.info.neighbor_east  = args["east"]
    if "west"  in args: board.info.neighbor_west  = args["west"]
    save_world(world, path)
    return (
        f"Board {args['board_index']} exits: "
        f"N={board.info.neighbor_north} S={board.info.neighbor_south} "
        f"E={board.info.neighbor_east} W={board.info.neighbor_west}"
    )


def tool_set_world_info(args: dict) -> str:
    path  = args["path"]
    world = load_world(path)
    info  = world.info
    if "name"        in args: info.name          = args["name"][:19]
    if "health"      in args: info.health        = args["health"]
    if "ammo"        in args: info.ammo          = args["ammo"]
    if "gems"        in args: info.gems          = args["gems"]
    if "torches"     in args: info.torches       = args["torches"]
    if "score"       in args: info.score         = args["score"]
    if "start_board" in args: info.current_board = args["start_board"]
    save_world(world, path)
    return f"Updated world info for '{info.name}'"


TOOL_HANDLERS = {
    "zzt_create_world":  tool_create_world,
    "zzt_read_world":    tool_read_world,
    "zzt_list_boards":   tool_list_boards,
    "zzt_get_board":     tool_get_board,
    "zzt_set_tile":      tool_set_tile,
    "zzt_fill_rect":     tool_fill_rect,
    "zzt_add_object":    tool_add_object,
    "zzt_get_oop_code":  tool_get_oop_code,
    "zzt_set_oop_code":  tool_set_oop_code,
    "zzt_add_board":     tool_add_board,
    "zzt_connect_boards": tool_connect_boards,
    "zzt_set_world_info": tool_set_world_info,
}


# ─── MCP message dispatch ─────────────────────────────────────────────────────

def handle_message(msg: dict) -> dict | None:
    method = msg.get("method", "")
    id_    = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return _ok(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "zzt-mcp-server", "version": "1.0.0"},
        })

    if method == "notifications/initialized":
        return None  # no response needed

    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return _error(id_, -32601, f"Unknown tool: {name!r}")
        try:
            result = handler(args)
            if isinstance(result, dict):
                text = json.dumps(result, indent=2)
            elif isinstance(result, list):
                text = json.dumps(result, indent=2)
            else:
                text = str(result)
            return _ok(id_, {"content": [_text(text)]})
        except Exception as e:
            tb = traceback.format_exc()
            return _ok(id_, {
                "content": [_text(f"Error: {e}\n\n{tb}")],
                "isError": True,
            })

    if method == "ping":
        return _ok(id_, {})

    return _error(id_, -32601, f"Method not found: {method!r}")


def main() -> None:
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError as e:
            _send(_error(None, -32700, f"Parse error: {e}"))
            continue

        response = handle_message(msg)
        if response is not None:
            _send(response)


if __name__ == "__main__":
    main()
