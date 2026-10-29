# sk700v-linux

Linux support for the LCD on the **Sudokoo SK700V** CPU cooler (USB `381c:0003`).

The cooler's display shows CPU frequency, load, package power and temperature, but it stays blank
unless the host keeps sending it data. The vendor app (MasterCraft) is Windows-only. This repo
provides a small Python daemon that feeds it live stats on Linux, plus the reverse-engineered protocol.

- No dependencies beyond Python 3 (standard library only)
- Runs as a systemd service and survives unplug, replug and suspend
- Tested on CachyOS (kernel 6.18) with a Ryzen 7 9800X3D

## Install

```sh
git clone https://github.com/canoptic-vis/sk700v-linux.git
cd sk700v-linux
sudo ./install.sh
```

Uninstall with `sudo ./install.sh --uninstall`.

The service runs as root because the kernel only lets root read the CPU package power counter
(RAPL `energy_uj`). It is sandboxed with `ProtectSystem=strict`, `ProtectHome`, and `NoNewPrivileges`.
If you run `sk700v-display.py` as a normal user instead, everything works except power, which reads 0.

## Data sources

| Display field | Source |
|---|---|
| FREQ (GHz) | Highest current core clock, `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` |
| LOAD (%) | Overall CPU utilisation from `/proc/stat` |
| POWER (W) | Package power from RAPL, `/sys/class/powercap/intel-rapl:0/energy_uj` (also works on AMD) |
| Power bar | Power as a share of the CPU's package power limit (see below) |
| CPU TEMP (°C) | `k10temp` Tctl (AMD) |

Intel CPUs would need the temperature source changed to `coretemp`. Pull requests are welcome.

The bar under the wattage shows power as a percentage of the CPU's power limit. Intel CPUs report
that limit through RAPL and it is read automatically. AMD CPUs don't, so it defaults to 162 W (the
stock limit of a Ryzen 7 9800X3D). For another CPU, set `SK700V_MAX_WATTS`:

```sh
sudo systemctl edit sk700v-display     # add these two lines:
#   [Service]
#   Environment=SK700V_MAX_WATTS=230
```

## Protocol

The cooler is a vendor-defined HID device (usage page `0xFF00`). Everything goes through 64-byte
writes of output report `0x10` on the hidraw node:

```
10 | 68 01 09 | LEN | PAYLOAD (LEN bytes) | SUM | 16 | zero padding to 64 bytes
```

- `68` / `16` are start and end markers
- `LEN` is the payload length
- `SUM` is the low byte of the sum of every byte from `68` through the end of the payload

### Commands

| Payload | Meaning |
|---|---|
| `03 01` | Screen on / keep-alive. The vendor app sends it before every data frame. |
| `01 02 …` (13 bytes) | Sensor data, see below |
| `01 01 xx …` | Segment test: any non-zero `xx` lights every segment. Send `01 01` + 12 zero bytes to clear it. |
| `01 03 …` | Blanks the screen (send `03 01` + a data frame to recover) |

### Data frame (`01 02`), all multi-byte fields big-endian

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | `01` |
| 1 | 1 | `02` |
| 2 | 2 | Power, W (uint16) |
| 4 | 1 | Power bar fill, % (uint8, 0-100). The vendor app sends `0a` (10 %). |
| 5 | 1 | Temperature unit: `00` = °C, `01` = °F. The firmware doesn't convert, so the temperature must be sent in the chosen unit. |
| 6 | 4 | CPU temperature, °C (float32) |
| 10 | 1 | Load, % (uint8) |
| 11 | 2 | Frequency, MHz (uint16), shown as GHz with two decimals |

Example: 137 W, 46 °C, 39 %, 5.28 GHz

```
10 68 01 09 0d 01 02 00 89 0a 00 42 38 00 00 27 14 a0 6a 16
```

The meaning of the power bar and unit bytes comes from
[Birchwood-Grey/sk700v-linux](https://github.com/Birchwood-Grey/sk700v-linux) (see Related projects).

The vendor app sends `03 01` followed by a data frame about once a second. The device never
sends anything back on its own.

### Probe tool

`sk700v-probe.py` sends hand-built frames for experimenting. To use it as a normal user, install
the udev rule (`install.sh` does this).

```sh
./sk700v-probe.py on data:137,39,5280,46     # power, load, freq MHz, temp °C
./sk700v-probe.py test1                      # all segments on
./sk700v-probe.py test0 on data:0,0,0,0
./sk700v-probe.py raw:0301                   # arbitrary payload
```

## How it works, in plain English

The screen on the cooler is "dumb": it can't measure anything itself. It just shows whatever numbers
the computer sends it over USB. On Windows, the MasterCraft app reads your CPU's sensors and sends the
cooler a small message about once a second saying, in effect, "show 5.28 GHz, 39 %, 137 W, 46 °C".
If nothing sends those messages, the screen stays blank, which is what happens on Linux out of the box.

This project is a small program that does that same job on Linux. Once a second it:

1. Reads the CPU temperature, power, load and clock speed that Linux already exposes
2. Packs them into a message in the exact format the cooler expects
3. Sends the message to the cooler over USB

It runs in the background as a system service, so it starts automatically when the computer boots.

## How this was figured out

Sudokoo doesn't publish how the cooler's messages are laid out, so it had to be worked out by watching
the official software talk to the cooler. Think of it like learning a language by listening in on a
conversation.

1. **Looking inside the official app.** MasterCraft is built from web technology (Electron), so its
   files could be unpacked. The part that talks to the cooler is stored in a compiled form that can't
   be read directly. The text labels left inside it (things like `screen-data` and `cpuMessage`) still
   gave clues: the app sends the cooler CPU readings over and over.

2. **Running the Windows app on Linux.** Wine is a tool that lets many Windows programs run on Linux.
   The real MasterCraft app was run through Wine and allowed to talk to the cooler, and it worked: it
   found the cooler and lit up the screen.

3. **Listening in on the USB cable.** Linux has a built-in USB "wiretap" called `usbmon` that records
   every message sent to a device. Recording MasterCraft's messages showed their basic shape: a fixed
   start marker, a length, the data, a checksum and an end marker. It also showed that the app sends
   a "screen on" message followed by a data message about once a second.

4. **Trial and error with a webcam.** Hand-made messages were sent to the cooler with deliberately
   odd numbers in different positions, and a webcam pointed at the cooler showed which number appeared
   in which spot. For example, putting `03 04` in one position made the POWER readout show 772,
   because `0x0304` is 772. That mapped out power, load and clock speed.

5. **Planting fake readings to find the temperature.** The temperature wasn't where anyone expected.
   Under Wine, MasterCraft couldn't read the real CPU temperature (it needs a Windows-only driver), so
   the app was tweaked to receive made-up readings: 46 °C, 137 W, 39 %, 5.28 GHz. Capturing what it
   then sent to the cooler gave the answer. The temperature is stored as a "floating point" number
   (the bytes `42 38 00 00` mean 46.0), which is why the earlier single-number guesses showed 0.

6. **Writing the Linux version.** With the format known, the Linux program builds exactly the same
   messages as MasterCraft (checked byte for byte against the captured ones) and fills them with real
   readings from Linux's own sensors.

The official software was only run and observed. Nothing in this repo is copied from it.

This project was built with the help of Claude, an AI assistant from Anthropic, working hands-on in
the terminal: unpacking the app, capturing the USB traffic, testing messages, and writing the code.

## Related projects

Others reverse-engineered this cooler independently, before this repo:

- [Birchwood-Grey/sk700v-linux](https://github.com/Birchwood-Grey/sk700v-linux): Python package
  with a CLI, Celsius/Fahrenheit toggle and power bar, plus its own protocol notes. It runs without
  root by making the RAPL power counters readable by all users, which is the trade-off this repo
  avoids by running a sandboxed root service.
- [gdedrouas/SK700V-display](https://github.com/gdedrouas/SK700V-display): earlier SK700V work
  credited by the project above.

## Disclaimer

Not affiliated with or endorsed by Sudokoo. The protocol was worked out by observing traffic from the
vendor's software. Use at your own risk. The commands above are the only ones that have been tested.

## License

MIT, see [LICENSE](LICENSE).
