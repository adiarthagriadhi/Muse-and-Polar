"""Local web server: serves the dashboard and a websocket for live data/control."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import webbrowser
from pathlib import Path

from aiohttp import WSMsgType, web

from .hub import Hub

log = logging.getLogger("musepolar")
STATIC = Path(__file__).parent / "static"


class DeviceSlot:
    """Owns the background task that keeps one device connected."""

    def __init__(self, factory):
        self.factory = factory
        self.task: asyncio.Task | None = None
        self.stop: asyncio.Event | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self) -> None:
        if self.running:
            return
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(self.factory().run(self.stop))

    async def halt(self) -> None:
        if not self.running:
            return
        self.stop.set()
        try:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=8)
        except asyncio.TimeoutError:
            self.task.cancel()
        except Exception:  # noqa: BLE001
            log.exception("device task ended with error")


def make_slots(hub: Hub, args) -> dict[str, DeviceSlot]:
    if args.sim:
        from .simulator import SimMuse, SimPolar

        return {"muse": DeviceSlot(lambda: SimMuse(hub)), "polar": DeviceSlot(lambda: SimPolar(hub))}
    from .muse import Muse
    from .polar import PolarH10

    return {
        "muse": DeviceSlot(lambda: Muse(hub, args.muse_name, args.muse_address, ppg=not args.no_ppg)),
        "polar": DeviceSlot(lambda: PolarH10(hub, args.polar_name, args.polar_address, ecg=not args.no_ecg)),
    }


async def handle_command(hub: Hub, slots: dict[str, DeviceSlot], msg: dict) -> None:
    cmd = msg.get("cmd")
    device = msg.get("device")
    if cmd == "connect" and device in slots:
        slots[device].start()
    elif cmd == "disconnect" and device in slots:
        await slots[device].halt()
    elif cmd == "record_start":
        hub.start_recording(str(msg.get("name", "")), str(msg.get("note", "")))
    elif cmd == "record_stop":
        hub.stop_recording()
    elif cmd == "marker":
        hub.marker(str(msg.get("label", "")))
    else:
        log.warning("unknown command: %s", msg)


def build_app(hub: Hub, slots: dict[str, DeviceSlot]) -> web.Application:
    async def index(_request):
        return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    async def ws_handler(request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        hub.clients.add(ws)
        await ws.send_str(json.dumps(hub.hello()))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        await handle_command(hub, slots, json.loads(msg.data))
                    except Exception:  # noqa: BLE001
                        log.exception("command failed")
        finally:
            hub.clients.discard(ws)
        return ws

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC)
    return app


async def serve(args) -> None:
    hub = Hub(Path(args.data_dir))
    slots = make_slots(hub, args)
    app = build_app(hub, slots)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()
    broadcaster = asyncio.create_task(hub.broadcast_loop())
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    log.info("Dashboard: %s  (data folder: %s)%s", url, Path(args.data_dir).resolve(), "  [SIMULATOR]" if args.sim else "")
    if args.autoconnect:
        for slot in slots.values():
            slot.start()
    if not args.no_browser:
        webbrowser.open(url)
    try:
        await asyncio.Event().wait()
    finally:
        hub.stop_recording()
        for slot in slots.values():
            await slot.halt()
        broadcaster.cancel()
        await runner.cleanup()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="musepolar", description="Live dashboard & recorder for Muse 2 + Polar H10")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--data-dir", default="recordings", help="folder for recorded sessions")
    p.add_argument("--sim", action="store_true", help="use simulated devices (no Bluetooth)")
    p.add_argument("--autoconnect", action="store_true", help="connect both devices at startup")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    p.add_argument("--muse-name", default="Muse", help="BLE name prefix of the Muse (default: Muse)")
    p.add_argument("--muse-address", help="exact BLE address/UUID of the Muse (see `python -m musepolar.scan`)")
    p.add_argument("--polar-name", default="Polar H10", help="BLE name prefix of the Polar (default: 'Polar H10')")
    p.add_argument("--polar-address", help="exact BLE address/UUID of the Polar H10")
    p.add_argument("--no-ppg", action="store_true", help="disable Muse PPG (EEG-only preset p21)")
    p.add_argument("--no-ecg", action="store_true", help="disable Polar ECG (HR/RR only)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
