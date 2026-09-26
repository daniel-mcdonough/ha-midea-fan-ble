# Midea fan BLE protocol (MSFS07RW6GB)

Findings from live testing. The crypto and framing are the same as Midea's BLE
air conditioners (reverse engineered by midea-ble / midea-ble-go). The appliance
messages are Midea's standard UART frames, the same ones used over Wi-Fi by
midea-local, except where noted below.

## Advertisement

Company ID `0x06A8`, device name `midea`. The fan alternates two payloads:

| Form | Bytes | Example |
|---|---|---|
| serial | `01` + 14 ASCII characters | `01` `12345678FA0001` |
| address | `01` + 3 opaque bytes + MAC reversed + `00` | `01 12 34 56` `ff ee dd cc bb aa` `00` |

Characters 9–10 of the serial are the appliance type in hex (`FA` = fan).
Depending on the scanner, the serial form can be seen far less often than the
address form.

## GATT

| Service | Characteristics | Use |
|---|---|---|
| `FFA0` | `FFA1` write, `FFA2` indicate | control (this protocol) |
| `FF80` | `FF81` write, `FF82` indicate | unknown |
| `FF90` | `FF91` write, `FF92` indicate | unknown |

## Handshake

1. `root_key = HKDF-SHA256(ikm = type_byte + serial[0:8] + MAC, salt = none, info = "midea_bleapp", 16 bytes)`.
   The type byte is `0xFA` for this fan; the AC implementation's hard-coded
   `0xAC` is rejected with a security error (`ff04`).
2. C1/C2/C3 exchange encrypted with the root key (AES-128-CCM, 8-byte nonce
   and tag). C2 carries the fan's P-256 public key.
3. `session_key = SHA256(ECDH shared X)[0:16]`. C3 proves the key by
   encrypting the advertisement data with it.
4. Afterwards, business frames (type `0x20`) carry raw appliance frames,
   encrypted with the session key.

No cloud token or pairing is involved.

## Appliance frames

```
AA LEN FA 00 00 00 00 00 PROTO MSGTYPE BODY... CHECKSUM
```

`PROTO` is `02` for this fan. Message types: `02` set, `03` query, `04` notify.
The checksum is the two's complement of the sum of bytes 1..n-1. Query is
`aa0afa00000000000203f7`; every set gets a full status reply.

### Status body (byte 0 is the body type)

| Byte | Meaning |
|---|---|
| 1 | error code |
| 2 | buzzer: `04` on, `08` off |
| 4 | bit 0 power; bits 1–5 mode |
| 5 | speed 1–12 |
| 8 | bit 0 oscillating; bits 1–3 axis group (1 horizontal, 2 vertical, 6 both) |
| 13 | temperature + 41 (°C) |
| 19 | bits 6–7: `01` display on |
| 23 | fan protocol (`05`) |
| 25 | vertical angle / 5 |
| 51 | horizontal angle / 5 |

Not understood yet: byte 22 (`15`), 24 (`40`), 30 (repeats the speed), and
38 (`1a` at speed 1, `1e` at speed 2).

### Set body

Status byte n+1 corresponds to set byte n. Unset fields are 0, except bytes 3
and 7, where `80` means "no change".

| Byte | Meaning |
|---|---|
| 1 | buzzer `04` on / `08` off |
| 3 | `0`/`1` power, or `1 \| mode << 1` (mode also powers on) |
| 4 | speed 1–12 (13+ is clamped to 12) |
| 7 | `group << 1 \| on`: `03`/`02` horizontal on/off, `05`/`04` vertical, `0d`/`0c` both |
| 18 | display `40` on / `80` off |
| 24 | vertical angle / 5 (30, 60, 135°) |
| 50 | horizontal angle / 5 (30, 60, 120°); the body is extended to 51 bytes |

Oscillation "on" is ignored unless a valid angle for that axis is included.
Axes are independent. midea-local's encoding (angle bits inside byte 7) does
not work on this model.

### Modes

The fan accepts 20, 2, 18 and 22 and maps other values onto the nearest of
those. In midea-local's protocol-5 table, 20 is "self_selection", 2 "natural"
and 18 "sleeping_wind".

| Value | Name here | Evidence |
|---|---|---|
| 20 | normal | the fan's own starting mode |
| 2 | natural | matches midea-local |
| 18 | sleep | midea-local "sleeping_wind" |
| 22 | auto | picks its own speed (12 at 27 °C) and enables both oscillation axes; not yet confirmed on the panel |

Child lock (midea-local's set byte 2) had no effect.
