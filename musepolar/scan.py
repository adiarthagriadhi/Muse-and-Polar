"""List nearby BLE devices so you can find your Muse / Polar H10 name or address.

Usage: python -m musepolar.scan [seconds]
"""

from __future__ import annotations

import asyncio
import sys


async def scan(seconds: float) -> None:
    from bleak import BleakScanner

    print(f"Scanning {seconds:.0f} s ...")
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    rows = sorted(found.values(), key=lambda da: -(da[1].rssi or -999))
    for device, adv in rows:
        name = adv.local_name or device.name or "?"
        mark = "  <--" if name.lower().startswith(("muse", "polar")) else ""
        print(f"{adv.rssi:>5} dBm  {device.address}  {name}{mark}")


if __name__ == "__main__":
    asyncio.run(scan(float(sys.argv[1]) if len(sys.argv) > 1 else 8))
