#!/usr/bin/env python3
"""
ZZT Live Renderer Server
========================
Watches a .ZZT file for changes and hot-reloads the browser view.

Usage:
    python3 renderer/server.py path/to/world.zzt [--port 8080]

Open http://localhost:8080 in your browser.
Every time Claude (or you) edits the .ZZT file, the browser updates automatically.

Dependencies:
    pip install aiohttp watchdog
Optionally for Zeta WASM rendering:
    python3 renderer/get_zeta.py
"""

import argparse
import asyncio
import json
import mimetypes
import os
import sys
from pathlib import Path

# Allow importing the zzt library from the parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiohttp import web, WSMsgType
import watchdog.events
import watchdog.observers

from zzt.world import (
    load_world, ELEMENT_NAMES, BOARD_WIDTH, BOARD_HEIGHT,
)

# ── Global state ──────────────────────────────────────────────────────────────

_clients: set = set()
_loop: asyncio.AbstractEventLoop = None


# ── File watcher ──────────────────────────────────────────────────────────────

class ZZTFileHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, zzt_path: str):
        self._zzt_path = os.path.abspath(zzt_path)

    def on_modified(self, event):
        if not event.is_directory and os.path.abspath(event.src_path) == self._zzt_path:
            asyncio.run_coroutine_threadsafe(_broadcast_reload(), _loop)

    on_created = on_modified


async def _broadcast_reload():
    msg = json.dumps({"type": "reload"})
    dead = set()
    for ws in _clients:
        try:
            await ws.send_str(msg)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


# ── HTTP handlers ─────────────────────────────────────────────────────────────

async def handle_index(request):
    path = Path(__file__).parent / "index.html"
    with open(path) as f:
        html = f.read()
    return web.Response(text=html, content_type="text/html")


async def handle_world_zzt(request):
    """Serve the raw .ZZT file with CORS and no-cache headers."""
    zzt_path = request.app["zzt_path"]
    try:
        with open(zzt_path, "rb") as f:
            data = f.read()
        return web.Response(
            body=data,
            content_type="application/octet-stream",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Disposition": "inline; filename=world.zzt",
            },
        )
    except FileNotFoundError:
        return web.Response(status=404, text="World file not found")


async def handle_board_api(request):
    """Return board info as JSON — used by the ASCII fallback renderer."""
    zzt_path = request.app["zzt_path"]
    board_index = int(request.match_info.get("index", "1"))
    try:
        world = load_world(zzt_path)
        if board_index >= len(world.boards):
            return web.json_response({"error": f"Board {board_index} not found"}, status=404)
        board = world.boards[board_index]
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
                "has_oop": len(stat.data) > 0,
            })
        return web.json_response(
            {
                "board_index": board_index,
                "name": board.name,
                "ascii_art": board.ascii_art(),
                "stats": stats_info,
                "north": board.info.neighbor_north,
                "south": board.info.neighbor_south,
                "east":  board.info.neighbor_east,
                "west":  board.info.neighbor_west,
                "world_name": world.info.name,
                "board_count": len(world.boards),
                "boards": [{"index": i, "name": b.name} for i, b in enumerate(world.boards)],
            },
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"},
        )
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ws(request):
    """WebSocket endpoint — clients subscribe here for hot-reload notifications."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _clients.add(ws)
    try:
        async for msg in ws:
            if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    finally:
        _clients.discard(ws)
    return ws


async def handle_static(request):
    """Serve zeta-web/ static assets (Zeta WASM build)."""
    base = Path(__file__).parent
    filename = request.match_info.get("filename", "")
    # Normalise and restrict to renderer dir
    target = (base / "zeta-web" / filename).resolve()
    if not str(target).startswith(str(base)):
        return web.Response(status=403, text="Forbidden")
    if not target.exists() or not target.is_file():
        return web.Response(status=404, text=f"Not found: zeta-web/{filename}")
    mime, _ = mimetypes.guess_type(str(target))
    with open(target, "rb") as f:
        return web.Response(
            body=f.read(),
            content_type=mime or "application/octet-stream",
            headers={"Access-Control-Allow-Origin": "*"},
        )


# ── App factory ───────────────────────────────────────────────────────────────

def build_app(zzt_path: str) -> web.Application:
    app = web.Application()
    app["zzt_path"] = os.path.abspath(zzt_path)
    app.router.add_get("/",                    handle_index)
    app.router.add_get("/world.zzt",           handle_world_zzt)
    app.router.add_get("/api/board/{index}",   handle_board_api)
    app.router.add_get("/ws",                  handle_ws)
    app.router.add_get("/zeta-web/{filename:.*}", handle_static)
    return app


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _loop

    parser = argparse.ArgumentParser(description="ZZT Live Renderer Server")
    parser.add_argument("zzt_file", help="Path to .ZZT file to watch and serve")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default 8080)")
    args = parser.parse_args()

    zzt_path = os.path.abspath(args.zzt_file)
    if not os.path.exists(zzt_path):
        print(f"Error: {zzt_path!r} not found", file=sys.stderr)
        sys.exit(1)

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    # Start file watcher in background thread
    observer = watchdog.observers.Observer()
    handler = ZZTFileHandler(zzt_path)
    observer.schedule(handler, path=os.path.dirname(zzt_path) or ".", recursive=False)
    observer.start()

    app = build_app(zzt_path)

    print(f"ZZT Live Renderer  →  http://localhost:{args.port}")
    print(f"Watching           →  {zzt_path}")
    print("Press Ctrl+C to stop.")

    try:
        web.run_app(app, port=args.port, loop=_loop, print=lambda *a, **kw: None)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
