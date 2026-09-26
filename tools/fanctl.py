#!/usr/bin/env python3
"""Control a Midea BLE fan from the command line.

fanctl.py scan
fanctl.py --address AA:BB:.. --serial 12345678FA0001 status
fanctl.py --address .. --serial .. set --speed 3 --oscillate on
fanctl.py --address .. --serial .. listen 60
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bleak import BleakClient, BleakScanner

from custom_components.midea_fan_ble.client import MideaFanClient
from custom_components.midea_fan_ble.protocol.advertisement import (
    build_advertis_data,
    parse_serial_payload,
)
from custom_components.midea_fan_ble.protocol.constants import MIDEA_MANUFACTURER_ID
from custom_components.midea_fan_ble.protocol.exceptions import (
    MideaBleAdvertisementError,
)
from custom_components.midea_fan_ble.protocol.fa import MSFS07_MODES, FanStatus


def on_off(value: str) -> bool:
    if value.lower() in ("on", "1", "true", "yes"):
        return True
    if value.lower() in ("off", "0", "false", "no"):
        return False
    raise argparse.ArgumentTypeError("expected on/off")


def show(status: FanStatus) -> None:
    print(
        f"power={'on' if status.power else 'off'} speed={status.speed} "
        f"mode={status.mode}({status.mode_name}) horizontal={status.horizontal_angle} "
        f"vertical={status.vertical_angle} display={status.display} buzzer={status.buzzer} "
        f"temp={status.temperature}C error={status.error_code} proto={status.fa_protocol}"
    )
    print(f"  raw {status.raw.hex()}")


async def scan(seconds: float) -> None:
    found: dict[str, str] = {}

    def cb(device, adv):
        payload = adv.manufacturer_data.get(MIDEA_MANUFACTURER_ID)
        if payload is None:
            return
        try:
            parsed = parse_serial_payload(payload, device.address)
        except MideaBleAdvertisementError:
            found.setdefault(device.address, "")
            return
        found[device.address] = f"serial={parsed.serial} type=0x{parsed.device_type:02X}"

    async with BleakScanner(cb, scanning_mode="active"):
        await asyncio.sleep(seconds)
    for addr, info in found.items():
        print(addr, info or "(serial advertisement not seen yet)")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--address")
    ap.add_argument("--serial")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").add_argument("seconds", nargs="?", type=float, default=15)
    sub.add_parser("status")
    listen = sub.add_parser("listen", help="stay connected and print pushed status")
    listen.add_argument("seconds", type=float)
    s = sub.add_parser("set")
    s.add_argument("--power", type=on_off)
    s.add_argument("--speed", type=int)
    s.add_argument("--mode", help="number or name: " + ", ".join(MSFS07_MODES.values()))
    s.add_argument("--horizontal", type=int, help="angle 30/60/120, 0 = off")
    s.add_argument("--vertical", type=int, help="angle 30/60/135, 0 = off")
    s.add_argument("--display", type=on_off)
    s.add_argument("--buzzer", type=on_off)
    args = ap.parse_args()

    if args.verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)
    if args.cmd == "scan":
        await scan(args.seconds)
        return
    if not (args.address and args.serial):
        ap.error("--address and --serial are required")

    async def connector(disconnected_callback):
        device = await BleakScanner.find_device_by_address(args.address, timeout=20)
        if device is None:
            raise SystemExit("fan not found")
        client = BleakClient(device, disconnected_callback=disconnected_callback, timeout=20)
        await client.connect()
        return client

    def pushed(status: FanStatus) -> None:
        if args.cmd == "listen":
            print("push:", end=" ")
            show(status)

    client = MideaFanClient(
        build_advertis_data(args.address, args.serial), connector, on_status=pushed
    )
    try:
        if args.cmd == "status":
            show(await client.query())
        elif args.cmd == "listen":
            show(await client.query())
            client._idle_timeout = args.seconds + 5
            await asyncio.sleep(args.seconds)
        else:
            mode = args.mode
            if mode is not None and not mode.isdigit():
                mode = {v: k for k, v in MSFS07_MODES.items()}[mode]
            if (
                args.horizontal is not None
                and args.vertical is not None
                and bool(args.horizontal) != bool(args.vertical)
            ):
                ap.error("--horizontal and --vertical must both be on or both off in one command")
            fields = dict(
                power=args.power,
                speed=args.speed,
                mode=int(mode) if mode else None,
                horizontal_angle=args.horizontal,
                vertical_angle=args.vertical,
                display=args.display,
                buzzer=args.buzzer,
            )
            show(await client.set(**{k: v for k, v in fields.items() if v is not None}))
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
