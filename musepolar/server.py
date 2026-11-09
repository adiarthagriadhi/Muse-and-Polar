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
from cass_polar.live_routes import add_routes
from corva import protocol as corva_protocol
from corva.routes import add_routes as add_corva_routes

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
        "polar": DeviceSlot(lambda: PolarH10(
            hub, args.polar_name, args.polar_address, ecg=not args.no_ecg, acc=not args.no_polar_acc
        )),
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
    elif cmd == "sync":
        hub.start_sync(float(msg.get("duration", 10)))
    elif cmd == "marker":
        hub.marker(str(msg.get("label", "")))
    else:
        log.warning("unknown command: %s", msg)


def build_app(hub: Hub, slots: dict[str, DeviceSlot], corva_norms: dict | None = None) -> web.Application:
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
    add_routes(app, hub.data_dir)

    async def corva_protocol_json(_request):
        return web.json_response(corva_protocol.as_json())

    app.router.add_get("/api/corva/protocol", corva_protocol_json)
    add_corva_routes(app, hub.data_dir, norms=corva_norms)
    app.router.add_static("/static", STATIC)
    return app


async def serve(args) -> None:
    demo = []
    if args.demo:
        from .demo import ensure_demo_sessions

        demo = ensure_demo_sessions(Path(args.data_dir))
    hub = Hub(Path(args.data_dir))
    hub.mode = "demo" if args.demo else "sim" if args.sim else "live"
    if demo:
        # CASS and CorVa buttons work right away on the CorVa protocol demo (falls back to the first one)
        last = next((d for d in demo if d.name.endswith("DEMO_P04")), demo[0])
        meta = json.loads((last / "session.json").read_text(encoding="utf-8"))
        hub.last_recording = {"active": False, "name": meta["name"], "dir": str(last),
                              "elapsed": meta["duration_sec"], "counts": meta["samples"]}
    slots = make_slots(hub, args)
    norms = None
    if getattr(args, "corva_norms", None):
        from corva.norms import load as load_norms

        norms = load_norms(args.corva_norms)
        log.info("CorVa norms: %s (N = %s)", args.corva_norms, norms["n_participants"])
    app = build_app(hub, slots, corva_norms=norms)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()
    broadcaster = asyncio.create_task(hub.broadcast_loop())
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    log.info("Dashboard: %s  (data folder: %s)%s", url, Path(args.data_dir).resolve(), "  [DEMO]" if args.demo else "  [SIMULATOR]" if args.sim else "")
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
    p.add_argument("--data-dir", help="folder for recorded sessions (default recordings/, demo_recordings/ with --demo)")
    p.add_argument("--demo", action="store_true",
                   help="try everything without devices: simulator, auto-connect, and five ready-made "
                        "synthetic sessions for the CASS explorer and CorVa Space, all in demo_recordings/")
    p.add_argument("--sim", action="store_true", help="use simulated devices (no Bluetooth)")
    p.add_argument("--autoconnect", action="store_true", help="connect both devices at startup")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    p.add_argument("--muse-name", default="Muse", help="BLE name prefix of the Muse (default: Muse)")
    p.add_argument("--muse-address", help="exact BLE address/UUID of the Muse (see `python -m musepolar.scan`)")
    p.add_argument("--polar-name", default="Polar H10", help="BLE name prefix of the Polar (default: 'Polar H10')")
    p.add_argument("--polar-address", help="exact BLE address/UUID of the Polar H10")
    p.add_argument("--no-ppg", action="store_true", help="disable Muse PPG (EEG-only preset p21)")
    p.add_argument("--no-ecg", action="store_true", help="disable Polar ECG")
    p.add_argument("--no-polar-acc", action="store_true", help="disable Polar accelerometer (needed for sync)")
    p.add_argument("--corva-norms", help="reference-group norms for CorVa Space (JSON from `python -m corva.validate "
                                         "--norms-out`, kept in the private research repository)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    if args.demo:
        args.sim = args.autoconnect = True
    if args.data_dir is None:
        args.data_dir = "demo_recordings" if args.demo else "recordings"
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
