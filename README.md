# Midea Fan (Bluetooth) for Home Assistant

Local Bluetooth control of the Midea **MSFS07RW6GB** Smart Stand Air Circulator.
It needs no Midea account, no cloud token, and no Wi-Fi: the fan never has to
be set up in the SmartHome app.

Other Midea fans (appliance type `0xFA`) that advertise under Bluetooth company
ID `0x06A8` may work, but only this model has been tested. Mode numbers in
particular differ between models.

## What you get

| Entity | Controls |
|---|---|
| `fan` | on/off, 12 speeds, presets Normal / Natural / Sleep / Auto, oscillate |
| `select` Horizontal oscillation | off, 30°, 60°, 120° |
| `select` Vertical oscillation | off, 30°, 60°, 135° |
| `switch` Display, Buzzer | panel display and command beeps |
| `sensor` Temperature | room temperature measured by the fan |

`fan.oscillate` turns on horizontal oscillation at the last-used angle
(120° by default) and turns off both axes.

## Install

With HACS: add this repository as a custom repository (category
Integration), install **Midea Fan (Bluetooth)**, and restart Home Assistant.

Manually: copy `custom_components/midea_fan_ble` into your Home Assistant
`config/custom_components/` directory and restart.

Then:

1. The fan is discovered automatically (Settings → Devices & services). You
   can also add it manually with **Add integration → Midea Fan (Bluetooth)**.
2. Close the SmartHome app first. The fan accepts one Bluetooth connection at a
   time.

The Home Assistant host (or an ESPHome Bluetooth proxy with active connections)
must be within Bluetooth range of the fan.

Setup waits up to two minutes for the advertisement that carries the fan's
serial. If it never arrives, you are asked to type the serial in; get it with
`tools/fanctl.py scan`.

## Security

The handshake key is derived only from data the fan broadcasts publicly (its
serial prefix and Bluetooth address). **Anyone within Bluetooth range running
this code can control the fan.** That is how Midea designed the protocol and
this integration cannot change it. Keep that in mind if the fan is somewhere
that matters.

## Command-line tools

```sh
python -m venv .venv && .venv/bin/pip install bleak cryptography
.venv/bin/python tools/fanctl.py scan
.venv/bin/python tools/fanctl.py --address AA:BB:CC:DD:EE:FF --serial 12345678FA0001 status
.venv/bin/python tools/fanctl.py --address ... --serial ... set --speed 6 --horizontal 120
.venv/bin/python tools/fanctl.py --address ... --serial ... listen 60
.venv/bin/python tools/live_test.py --address ... --serial ...   # exercises everything, then restores
```

## Tests

```sh
.venv/bin/pip install pytest pytest-asyncio ruff
.venv/bin/python -m pytest
.venv/bin/ruff check custom_components tests tools
```

The unit tests use frames captured from a real fan and a simulated fan that
runs the device side of the handshake.

## How it works

See [docs/PROTOCOL.md](docs/PROTOCOL.md).
