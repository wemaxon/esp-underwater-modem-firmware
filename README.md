# esp-underwater-modem-firmware

ESP32-C3 firmware for a TUSS4470-based ultrasonic underwater modem, and a
desktop GUI (`tools/ultrasound-gui`) for measuring the received signal (VOUT
envelope and OUT3 zero crossings) and transmitting tone bursts.

## Architecture

The firmware is a single loop: `app_main` initializes the hardware and then
calls `usb_interface_poll()` forever. There are no application tasks; interrupt
callbacks only buffer RMT and ADC data, which the loop forwards to the host.

| Path | Responsibility |
|---|---|
| `components/tuss4470` | TUSS4470 chip driver: SPI registers, VDRV, tone bursts on IO1/IO2 |
| `components/edge_capture` | Chip-independent, gapless RMT edge recorder for one digital input |
| `components/tinyframe` | Project framing configuration for the vendored `third_party/tinyframe` |
| `main/main.c` | Initialization and the main loop |
| `main/board.*` | Pin assignment and hardware bring-up |
| `main/usb_interface.*` | USB interface to the host: command table, responses, stream and log forwarding |
| `main/tf_protocol.*` | Payload encoding and decoding for the USB interface |
| `main/acquisition.*` | VOUT sampling (ADC, divider-corrected) and OUT3 edges on one time base |
| `main/transmit.*` | Tone burst with VDRV powered only for its duration |
| `main/usb_transport.*`, `main/device_log.*` | USB byte transport; ESP log capture |

A new host command is one handler function plus one row in the command table
in `usb_interface.c`. Payload encoding, SPI frame encoding and RMT decoding have no
ESP-IDF dependencies and are unit tested on the host.

## Development

Firmware (ESP-IDF 6.0.1, ESP32-C3):

```powershell
idf.py build flash
```

`sdkconfig.defaults` keeps the console on UART, because USB Serial/JTAG carries
the TinyFrame interface. An existing `sdkconfig` must also disable the secondary USB console.

Host tests for the firmware (any C11 compiler with CMake; on Windows run from a
Visual Studio developer prompt):

```powershell
cmake -S test/host -B build/host -G Ninja
cmake --build build/host
ctest --test-dir build/host --output-on-failure
```

GUI (Python 3.10+ with Tk):

```powershell
python -m pip install -r tools/ultrasound-gui/requirements.txt
python tools/ultrasound-gui/src/main.py
python -m unittest discover -s tools/ultrasound-gui/tests -t tools/ultrasound-gui/tests
```

The GUI's interoperability test decodes frames produced by the C host test
build in `build/host` and is skipped when that build is missing.

The GUI acquires like an oscilloscope. **Roll** shows the newest window of the
stream continuously. **Single** waits until VOUT rises through the trigger
level (with 50 mV hysteresis), or until *Force trigger* is pressed, then holds
the window around the trigger, including the pre-trigger time, and stops the
stream. Times in a held capture are relative to the trigger.

## USB interface protocol

The development interface between the firmware and the GUI over USB, not the
acoustic modem protocol.

Protocol version: **6**. TinyFrame uses SOF `0x01`, 16-bit frame IDs, 16-bit
payload lengths, 8-bit message types and CRC32. Payload integers are little endian.
Host request IDs use `0x0000` through `0x7FFF`; every response echoes its
request's type and frame ID. Device events use frame IDs `0x8000` through
`0xFFFF`, wrapping within that range, and need no response.

| Message | Type | Request payload | Response or event payload |
|---|---:|---|---|
| GET_DEVICE_INFO | `0x01` | Empty | `uint8 version`, `uint32 vout_rate_hz`, `uint32 edge_clock_hz`, UTF-8 device name (remaining bytes) |
| STREAM_START | `0x02` | Empty | `uint8 result` |
| STREAM_STOP | `0x03` | Empty | `uint8 result` |
| TRANSMIT | `0x04` | `uint32 frequency_hz`, `uint16 cycles` | `uint8 result`, after the burst |
| LOG | `0x05` | Device event | 1–255 bytes of formatted UTF-8 log text |
| VOUT_SAMPLES | `0x06` | Device event | See below |
| OUT3_EDGES | `0x07` | Device event | See below |
| STREAM_END | `0x08` | Device event | `uint8 result`: why the device ended the stream |

While streaming, the device sends VOUT_SAMPLES and OUT3_EDGES as data becomes
available. All stream times are nanoseconds since STREAM_START on the device
clock, so VOUT and OUT3 share one time base. Stream data is never dropped
silently: if the device falls behind, it ends the stream with STREAM_END
(result 3). STREAM_START while streaming and STREAM_STOP while stopped succeed
without effect.

LOG events start after GET_DEVICE_INFO. A log frame need not be a complete
line; logs may be truncated or dropped when buffers are full.

TRANSMIT sends one tone burst: 40000 to 1000000 Hz, 1 to 255 cycles. The
frequency is rounded to the nearest half-period of the 20 MHz burst clock. The
host waits for the response before sending another transmission. Transmitting
does not interrupt streaming.

### VOUT_SAMPLES

| Offset | Field | Type |
|---:|---|---|
| 0 | Time of the first sample, ns | `uint64` |
| 8 | Sample count `n`, at least 1 | `uint16` |
| 10 | VOUT in millivolts | `uint16[n]` |

Samples are consecutive at `vout_rate_hz`.

### OUT3_EDGES

| Offset | Field | Type |
|---:|---|---|
| 0 | Time of the first edge, ns | `uint64` |
| 8 | Level after the first edge: `0` or `1` | `uint8` |
| 9 | Edge count `n`, at least 1 | `uint16` |
| 11 | Intervals between consecutive edges, in ticks of `edge_clock_hz` | `uint16[n - 1]` |

Edges alternate in level. The first edge of each received signal segment is
timestamped by an interrupt (about 1 µs); edges within a segment are exact to
one tick.

### Results

| Value | Meaning |
|---:|---|
| `0` | Success |
| `1` | Invalid request |
| `2` | Operation timed out |
| `3` | Data lost: device buffer overflow |
| `4` | Device error |

## Transducers

### Disc Transducer
[Aliexpress Link](https://de.aliexpress.com/item/1005006299774405.html)

| Specification | Value |
|---|---:|
| Resonant Frequency (kHz) | 40 ± 1 |
| Static Capacitance (pF) | 8,500 ± 10% |
| Resonant Impedance (Ω) | ≤ 20 Ω |
| Dimensions | 50 × 2.6 mm (diameter × height) |
| Power (W) | 35 W |
| Insulation Resistance (at 2500 V DC) | ≥ 100 MΩ |


### TCT40-16T/R watertight transducer
[Aliexpress Link](https://de.aliexpress.com/item/1005007456546786.html)

[CAD](docs/TCT40-16T_R.png)


| Specification | Transmitter (T) | Receiver (R) | Unit |
|---|---:|---:|---|
| Nominal Frequency | 40 | 40 | kHz |
| Frequency Error | ±0.5 | ±1 | kHz |
| Emitted Sound Pressure at 40 kHz (0 dB = 0.02 mPa) | 117 min | — | dB |
| Receive Sensitivity at 40 kHz (0 dB = 1 V/Pa) | — | -65 min | dB |
| Static Capacitance at 1 kHz, <1 V | 2,500 | 2,500 | pF |
| Static Capacitance Error | ±30 | ±30 | % |
| Maximum Driving Voltage | 80 | 80 | V |
| Operating Temperature | -20 to 70 | -20 to 70 | °C |
| Storage Temperature | -40 to 80 | -40 to 80 | °C |
