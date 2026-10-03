# Midea Fan (Bluetooth)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Home Assistant integration for Midea fans over Bluetooth Low Energy. Control is
fully local: no Midea account, no cloud token, no Wi-Fi. The fan doesn't need
to be set up in the SmartHome app.

## Supported devices

| Model | Name | Status |
|---|---|---|
| MSFS07RW6GB | Smart Stand Air Circulator | Tested |

Other Midea fans (appliance type `0xFA`) that advertise under Bluetooth company
ID `0x06A8` may work, but haven't been tested. Mode numbers in particular
differ between models, so presets may be wrong on other fans.

## Entities

| Platform | Entity | Description |
|---|---|---|
| `fan` | Fan | On/off, 12 speeds, presets Normal / Natural / Sleep / Auto, oscillate |
| `select` | Horizontal oscillation | Off, 30°, 60°, 120° |
| `select` | Vertical oscillation | Off, 30°, 60°, 135° |
| `switch` | Display | Panel display on/off |
| `switch` | Buzzer | Beep on commands |
| `sensor` | Temperature | Room temperature measured by the fan |

Turning `oscillate` on enables horizontal oscillation at the last-used angle
(120° by default). Turning it off disables both axes.

## Requirements

- Home Assistant 2026.8.0 or newer
- The [Bluetooth](https://www.home-assistant.io/integrations/bluetooth/)
  integration, using either a local adapter or an
  [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
  with active connections enabled
- The adapter or proxy has to be in range of the fan

## Installation

### HACS

1. In HACS, open the menu and choose **Custom repositories**.
2. Add this repository's URL with category **Integration**.
3. Search for **Midea Fan (Bluetooth)** and download it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/midea_fan_ble` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

Configuration is done in the UI.

1. Close the SmartHome app on any phone near the fan. The fan only accepts one
   Bluetooth connection at a time.
2. The fan should show up as discovered under **Settings → Devices &
   services**. If it doesn't, click **Add integration** and search for
   **Midea Fan (Bluetooth)**.
3. Confirm the device.

Setup needs the fan's serial number, which the fan broadcasts in only one of the
two advertisements it alternates between. Setup waits up to two minutes for it.
If it doesn't arrive, you are asked to enter the serial manually. You can read
it with `tools/fanctl.py scan` (see [Command-line tools](#command-line-tools)).

## How it works

- State is polled every 60 seconds. Every command returns a full status, so
  changes made from Home Assistant show up right away.
- The Bluetooth connection is closed after 15 seconds of inactivity, so the
  phone app can still connect between polls.
- The protocol is the same encrypted BLE transport Midea uses for its Bluetooth
  air conditioners, carrying the standard Midea appliance frames. See
  [docs/PROTOCOL.md](docs/PROTOCOL.md) for the details.

## Security

The encryption key is derived only from data the fan broadcasts publicly (its
serial prefix and Bluetooth address). **Anyone in Bluetooth range running this
code can control the fan.** That's how Midea designed the protocol, and this
integration can't change it.

## Known limitations

- Only the MSFS07RW6GB has been tested.
- Auto preset: the fan picks its own speed and enables both oscillation axes.
  It hasn't been confirmed that this matches "Auto" on the fan's panel.
- Child lock is not supported. The command had no effect on the tested fan.
- Changes made with the fan's remote or panel show up at the next poll, up to
  60 seconds later.

## Troubleshooting

**The fan isn't discovered, or the connection fails.**
The SmartHome app is most likely holding the connection. Close it. Otherwise,
check that your adapter or proxy is in range and that proxies have active
connections enabled.

**Setup times out waiting for the serial.**
Enter it manually. Run `tools/fanctl.py scan` and copy the 14-character serial.

### Debug logging

Add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.midea_fan_ble: debug
```

Or enable debug logging from the integration's page under **Devices &
services**.

## Removal

1. Go to **Settings → Devices & services**, select **Midea Fan (Bluetooth)**,
   and delete the entry.
2. If you installed it with HACS, remove it there. If you installed it
   manually, delete `config/custom_components/midea_fan_ble`.
3. Restart Home Assistant.

## Command-line tools

The `tools/` directory has standalone scripts for testing the fan without Home
Assistant.

```sh
python -m venv .venv && .venv/bin/pip install bleak cryptography
.venv/bin/python tools/fanctl.py scan
.venv/bin/python tools/fanctl.py --address AA:BB:CC:DD:EE:FF --serial 12345678FA0001 status
.venv/bin/python tools/fanctl.py --address ... --serial ... set --speed 6 --horizontal 120
.venv/bin/python tools/fanctl.py --address ... --serial ... listen 60
.venv/bin/python tools/live_test.py --address ... --serial ...   # exercises everything, then restores
```

## Development

```sh
.venv/bin/pip install pytest pytest-asyncio ruff
.venv/bin/python -m pytest
.venv/bin/ruff check custom_components tests tools
```

The unit tests use frames captured from a real fan, plus a simulated fan that
runs the device side of the handshake.

## License

MIT. See [LICENSE](LICENSE).
