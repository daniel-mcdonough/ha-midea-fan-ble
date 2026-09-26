#!/usr/bin/env python3
"""Exercise every control on a real fan and restore its original state.

    live_test.py --address AA:BB:.. --serial 12345678FA0001
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bleak import BleakClient, BleakScanner  # noqa: E402

from custom_components.midea_fan_ble.client import MideaFanClient  # noqa: E402
from custom_components.midea_fan_ble.protocol.advertisement import build_advertis_data  # noqa: E402
from custom_components.midea_fan_ble.protocol.fa import MSFS07_MODES, FanStatus  # noqa: E402

results: list[tuple[str, bool, str]] = []


def summary(s: FanStatus) -> str:
    return (f"power={s.power} speed={s.speed} mode={s.mode}({s.mode_name}) "
            f"h={s.horizontal_angle} v={s.vertical_angle} display={s.display} buzzer={s.buzzer}")


async def check(client, label, fields, expect, pause=1.5):
    reply = await client.set(**fields)
    await asyncio.sleep(pause)
    after = await client.query()
    ok = all(getattr(after, k) == v for k, v in expect.items())
    results.append((label, ok, summary(after)))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: reply[{summary(reply)}] query[{summary(after)}]")
    return after


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--modes", default="2,18,22,20", help="mode numbers to try")
    ap.add_argument("--max-speed", type=int, default=12)
    args = ap.parse_args()

    async def connector(cb):
        dev = await BleakScanner.find_device_by_address(args.address, timeout=20)
        c = BleakClient(dev, disconnected_callback=cb, timeout=20)
        await c.connect()
        return c

    client = MideaFanClient(build_advertis_data(args.address, args.serial), connector, idle_timeout=120)
    orig = await client.query()
    print("original:", summary(orig))
    try:
        await check(client, "buzzer off", {"buzzer": False}, {"buzzer": False})
        for a in (30, 60, 120):
            await check(client, f"horizontal {a}", {"horizontal_angle": a}, {"horizontal_angle": a})
        for a in (30, 60, 135):
            await check(client, f"vertical {a}", {"vertical_angle": a}, {"vertical_angle": a})
        await check(client, "vertical off", {"vertical_angle": 0}, {"vertical_angle": 0, "horizontal_angle": 120})
        await check(client, "horizontal off", {"horizontal_angle": 0}, {"horizontal_angle": 0})
        await check(client, "display off", {"display": False}, {"display": False})
        await check(client, "display on", {"display": True}, {"display": True})
        await check(client, f"speed {args.max_speed}", {"speed": args.max_speed}, {"speed": args.max_speed})
        s = await client.set(speed=args.max_speed + 1)
        print(f"[INFO] speed {args.max_speed + 1} request -> fan reports speed {s.speed}")
        await check(client, "speed 1", {"speed": 1}, {"speed": 1})
        for m in [int(x) for x in args.modes.split(",")]:
            await check(client, f"mode {m} ({MSFS07_MODES[m]})", {"mode": m}, {"mode": m}, pause=2.5)
        await check(client, "power off", {"power": False}, {"power": False})
        await check(client, "power on", {"power": True}, {"power": True})
    finally:
        print("restoring...")
        await client.set(mode=orig.mode) if orig.mode in MSFS07_MODES else None
        await client.set(speed=orig.speed or 1, display=orig.display)
        await client.set(horizontal_angle=orig.horizontal_angle)
        await client.set(vertical_angle=orig.vertical_angle)
        if not orig.power:
            await client.set(power=False)
        await client.set(buzzer=orig.buzzer)
        final = await client.query()
        print("final:   ", summary(final))
        print("restored:", summary(final) == summary(orig))
        await client.disconnect()
    print(f"\n{sum(ok for _, ok, _ in results)}/{len(results)} passed")


asyncio.run(main())
