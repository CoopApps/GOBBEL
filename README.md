# GOBBEL — ZZT × Claude Code Integration

Bring ZZT into the 21st century: ask Claude Code to design levels, write
ZZT-OOP scripts, place enemies, connect boards — and have it write the changes
**directly into a `.ZZT` file** that ZZT or the Zeta emulator can open.

---

## What is ZZT?

ZZT (1991, Tim Sweeney / Epic MegaGames) is a tile-based game creation system
with an ASCII character display and a simple scripting language called **ZZT-OOP**.
The source was reconstructed in 2020 and released under the MIT licence:
[asiekierka/reconstruction-of-zzt](https://github.com/asiekierka/reconstruction-of-zzt).

---

## Architecture

```
┌─────────────────────────┐       MCP (stdio)      ┌──────────────────────┐
│  Claude Code (you chat  │ ◄──────────────────────► │  zzt_mcp_server.py   │
│  here, Claude edits)    │                          │  (Python MCP server) │
└─────────────────────────┘                          └──────────┬───────────┘
                                                                │ reads/writes
                                                     ┌──────────▼───────────┐
                                                     │   zzt/world.py       │
                                                     │  (binary parser)     │
                                                     └──────────┬───────────┘
                                                                │
                                                     ┌──────────▼───────────┐
                                                     │   YOUR_WORLD.ZZT     │
                                                     │  (open in ZZT/Zeta)  │
                                                     └──────────────────────┘
```

Claude Code connects to `zzt_mcp_server.py` via the `.mcp.json` config.
The server exposes **12 tools** for reading and editing `.ZZT` world files.
Every change is written back to disk immediately — reload in ZZT to see them.

---

## Quick Start

### 1. Requirements

- Python 3.11+
- ZZT or the [Zeta emulator](https://github.com/asiekierka/zeta) (Linux/Win/HTML5)

```bash
python3 --version   # must be ≥ 3.11
```

### 2. Run the demo world generator

```bash
python3 examples/generate_demo_world.py
# Writes examples/DEMO.ZZT
```

Open `DEMO.ZZT` in Zeta to play a three-board dungeon that was generated
entirely in Python.

### 3. Enable the MCP server in Claude Code

The `.mcp.json` at the repo root is already configured:

```json
{
  "mcpServers": {
    "zzt": {
      "type": "stdio",
      "command": "python3",
      "args": ["zzt_mcp_server.py"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Start Claude Code in this directory:

```bash
cd /path/to/GOBBEL
claude
```

Claude will automatically detect `.mcp.json` and connect the `zzt` server.
You will see the ZZT tools listed when you run `/mcp`.

### 4. Ask Claude to build things

Examples of what you can say:

```
Create a new ZZT world at /tmp/castle.zzt called "CASTLE"

Add a second board named "Guard Room" to /tmp/castle.zzt

Fill a rectangle from (2,2) to (59,24) with Normal walls on board 1

Add a bear enemy at (30,12) on board 1 with code that makes it wander randomly

Place a locked blue door at (60,13) on board 1

Add a scroll object at (5,5) that says "Beware! A dragon lurks ahead."

Connect board 1 east exit to board 2 and board 2 west to board 1

Show me the ASCII art of board 1

Set the world health to 50 and starting ammo to 10
```

---

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `zzt_create_world` | Create a new `.ZZT` file with title + play board |
| `zzt_read_world` | Parse a world and return metadata as JSON |
| `zzt_list_boards` | List all board names and indices |
| `zzt_get_board` | Get ASCII art + stat list for a board |
| `zzt_set_tile` | Place a single tile (element + color) |
| `zzt_fill_rect` | Flood a rectangle with one tile type |
| `zzt_add_object` | Place a ZZT Object with ZZT-OOP code |
| `zzt_get_oop_code` | Read ZZT-OOP from a stat element |
| `zzt_set_oop_code` | Overwrite ZZT-OOP on a stat element |
| `zzt_add_board` | Append a new board to a world |
| `zzt_connect_boards` | Set N/S/E/W exits between boards |
| `zzt_set_world_info` | Edit health, ammo, name, start board, etc. |

---

## ZZT-OOP Primer

ZZT-OOP is the scripting language used by Object elements. Claude can generate
this for you, but here is a quick reference:

```
@object_name        First line — sets the object's name (optional)

'This is a comment

/n /s /e /w         Walk one step in a direction each cycle
?n ?s ?e ?w         Try to walk; skip if blocked
/i                  Idle for one cycle

#shoot n            Fire a bullet north
#give ammo 5        Give the player 5 ammo
#give gems 1        Give the player a gem (+10 score)
#take health 10     Remove 10 health
#die                Remove this object from the board
#become solid       Replace self with a Solid wall
#become empty       Remove self, leave empty tile

$Centered heading   Display text in a scroll
Regular text line   Normal scroll body text

:label              Define a jump label
#send label         Jump to :label in this object
#send name:label    Send a message to another object named @name
#zap label          Delete a :label (makes #send skip it)

#if flag name       Conditional branch
#set myflag         Set a world flag
#clear myflag       Clear a world flag

#end                Stop executing until next touch/shot
#restart            Jump back to the start of the program
```

---

## File Structure

```
GOBBEL/
├── .mcp.json                  Claude Code MCP server config
├── zzt_mcp_server.py          MCP server (12 ZZT tools)
├── zzt/
│   ├── __init__.py
│   └── world.py               ZZT binary parser + serializer
└── examples/
    ├── generate_demo_world.py  Three-board demo dungeon generator
    └── DEMO.ZZT               (generated — open in ZZT/Zeta)
```

---

## 21st-Century ZZT Ideas

This repo is a foundation. Future directions:

- **Web player** — embed Zeta (WASM) in a browser, live-reload on file save
- **ZZT-OOP language server** — syntax highlighting, diagnostics in VS Code
- **World diff / version control** — human-readable JSON export for git diffs
- **Multiplayer via sockets** — patch libzoo for networked ZZT
- **AI-generated worlds** — Claude designs full games from a single prompt
- **ZZT → web export** — compile ZZT-OOP to JavaScript for browser play

---

## References

- [Reconstruction of ZZT](https://github.com/asiekierka/reconstruction-of-zzt) — MIT-licenced Pascal source
- [Zeta emulator](https://github.com/asiekierka/zeta) — Play ZZT on Linux/Win/HTML5
- [Wiki of ZZT — File Format](https://wiki.zzt.org/wiki/ZZT_file_format)
- [ZZT-OOP Introduction](https://en.wikibooks.org/wiki/ZZT-OOP/Introduction)
- [Zookeeper](https://github.com/DrDos0016/zookeeper) — Python ZZT library (inspiration)
- [Museum of ZZT](https://museumofzzt.com) — Archive of ZZT worlds
