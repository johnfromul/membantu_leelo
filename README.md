# Membantu LeeLo — Home Assistant Integration

<p align="center">
  <img src="https://raw.githubusercontent.com/johnfromul/membantu_leelo/main/custom_components/membantu_leelo/brand/logo.png"
     alt="Membantu LeeLo" width="420">
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/johnfromul/membantu_leelo.svg)](https://github.com/johnfromul/membantu_leelo/releases)
![HA](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-green)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom Home Assistant integration for the **Membantu LeeLo01 / LeeLo02** baby swing, controlled locally over Bluetooth Low Energy (BLE).

> The BLE protocol was fully reverse-engineered from the official Membantu app using Frida instrumentation and JADX static analysis. The integration talks directly to the swing's ESP32 — **no cloud, no account, no internet required.**

---

## Features

- **On / Off control** — start and stop the swing
- **Speed control** — 10 levels, adjustable live while swinging
- **Timer intervals** — 15 / 30 / 45 / 60 minutes or Unlimited, changeable on the fly
- **Remaining time** — live countdown sensor showing time left before auto-stop
- **Persistent settings** — speed and timer survive Home Assistant restarts
- **Auto-reconnect** — reconnects automatically when the swing is back in range, with a periodic connection check
- **Local push** — direct BLE, no external dependencies

---

## Supported devices

| Device | Status |
|--------|--------|
| Membantu LeeLo01 | Tested and working |
| Membantu LeeLo02 | Untested (expected to work — same protocol) |

---

## Requirements

- Home Assistant 2024.1 or newer
- The built-in **Bluetooth** integration enabled (Settings → Devices & Services → Add Integration → Bluetooth)
- A Bluetooth adapter reachable by Home Assistant (built-in, USB dongle, or an ESPHome Bluetooth proxy)
- A Membantu LeeLo01 or LeeLo02 baby swing, powered on and in range

---

## Installation

### HACS (recommended)

1. In HACS, open **Integrations**
2. Click the three-dot menu in the top right → **Custom repositories**
3. Add the repository URL `https://github.com/johnfromul/membantu_leelo` and select category **Integration**
4. Find **Membantu LeeLo** in the list and click **Download**
5. Restart Home Assistant

### Manual

1. Download the latest release from the [Releases](https://github.com/johnfromul/membantu_leelo/releases) page
2. Copy the `custom_components/membantu_leelo/` folder into your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

---

## Configuration

First find your swing's BLE MAC address: go to **Settings → Devices & Services → Bluetooth**. The swing appears as `Leelo01` (or `Leelo02`) along with its address.

Then add the following to your `configuration.yaml`:

```yaml
membantu_leelo:
  - address: "B0:B2:1C:35:1F:B2"   # your swing's BLE MAC address
    name: "LeeLo"                    # friendly name (optional, default: LeeLo)
```

Restart Home Assistant after saving.

Multiple swings can be configured by adding more list entries.

---

## Entities

The integration creates four entities per swing:

| Entity | Type | Icon | Description |
|--------|------|------|-------------|
| `switch.leelo` | Switch | `mdi:cradle` | Start / stop the swing |
| `number.leelo_speed` | Number | `mdi:speedometer` | Speed level 1–10 (slider) |
| `select.leelo_timer` | Select | `mdi:timer` | Timer interval selection |
| `sensor.leelo_remaining` | Sensor | `mdi:timer-sand` | Remaining time until auto-stop |

### How they work together

- **`switch.leelo`** starts the swing using the currently selected speed and timer. Turning it off stops the swing immediately.
- **`number.leelo_speed`** sets the swing speed. Changing it while running applies the new speed live.
- **`select.leelo_timer`** chooses the auto-off interval. Changing it while running restarts the countdown with the new interval.
- **`sensor.leelo_remaining`** shows `MM:SS` remaining, `Unlimited` when no timer is set, or `—` when the swing is stopped. When the timer expires, the swing stops and the switch updates to off automatically.

### Timer options

| Option | Behavior |
|--------|----------|
| 15 min | Auto-stop after 15 minutes |
| 30 min | Auto-stop after 30 minutes |
| 45 min | Auto-stop after 45 minutes |
| 60 min | Auto-stop after 60 minutes |
| Unlimited | Runs until manually stopped |

---

## Automation example

```yaml
automation:
  - alias: "Soothe baby at bedtime"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.leelo_timer
        data:
          option: "30 min"
      - service: number.set_value
        target:
          entity_id: number.leelo_speed
        data:
          value: 4
      - service: switch.turn_on
        target:
          entity_id: switch.leelo
```

---

## BLE Protocol

Reverse-engineered from the official Membantu Android app.

**GATT service:** `0000a002-0000-1000-8000-00805f9b34fb`

| Characteristic | UUID | Direction | Property |
|----------------|------|-----------|----------|
| Write | `0000c304-0000-1000-8000-00805f9b34fb` | App → Device | WRITE |
| Indicate | `0000c306-0000-1000-8000-00805f9b34fb` | Device → App | INDICATE |

**Packet format:** `0xAA [CMD] [LEN] [DATA...] 0xDD 0x0D 0x0A`

| CMD | Function | Values |
|-----|----------|--------|
| `0x01` | Handshake | `0x01` on connect |
| `0x02` | Speed | `0x00`–`0x0A` (0–10) |
| `0x03` | Timer interval | `0x00`=15min, `0x01`=30min, `0x02`=45min, `0x03`=60min, `0x04`=Unlimited |
| `0x04` | On / Off | `0x00`=start, `0x01`=stop |
| `0x07` | Sync / status | 5-byte device state report |
| `0x0A` | Acknowledge | `0x00` |

**To start swinging:** send interval (`0x03`), then speed (`0x02`), then start (`0x04 00`).
**To stop swinging:** send stop (`0x04 01`).

> Note: the device echoes every command back on the indicate characteristic, and the timer interval can be changed live while running.

---

## Troubleshooting

**Entity shows unavailable after a restart**

The integration automatically disconnects and clears the BlueZ cache before each connection attempt, and retries periodically. If it stays unavailable, make sure the swing is powered on and in range. As a last resort, from an SSH session:

```bash
bluetoothctl -- disconnect B0:B2:1C:35:1F:B2
bluetoothctl -- remove B0:B2:1C:35:1F:B2
```

**`Characteristic 0000c304 was not found`**

This means a connection completed without full GATT service discovery (sometimes happens after another app held the connection). The integration detects this and forces a clean reconnect on the next attempt. Toggling the switch again usually resolves it.

**Swing doesn't respond**

Only one BLE connection is possible at a time. Make sure the official Membantu app is fully closed on all phones.

---

## Contributing

Issues and pull requests are welcome. For significant changes, please open an issue first to discuss the approach.

---

## License

Released under the [MIT License](LICENSE).

---

## Credits

- BLE protocol reverse-engineered with [Frida](https://frida.re/) and [JADX](https://github.com/skylot/jadx)
- Built on [bleak](https://github.com/hbldh/bleak) and [bleak-retry-connector](https://github.com/Bluetooth-Devices/bleak-retry-connector)
