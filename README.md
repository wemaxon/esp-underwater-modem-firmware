# esp-underwater-modem-firmware

## Protocol

Protocol version: **5**. TinyFrame uses SOF `0x01`, 16-bit frame IDs, 16-bit
payload lengths, 8-bit message types and CRC32. Payload integers are little endian.
Host request IDs use `0x0000` through `0x7FFF`. Every response echoes its request's type
and frame ID.

| Message | Type | Request payload | Response payload |
|---|---:|---|---|
| GET_DEVICE_INFO | `0x01` | Empty | `uint8 version`, `uint32 tick_hz`, `uint16 max_edges`, UTF-8 device name (remaining bytes, no terminator) |
| CAPTURE | `0x02` | Empty | Complete OUT3 capture below, or one `uint8 result` on failure |
| STOP | `0x03` | Empty | `uint8 result` |
| TRANSMIT | `0x04` | `uint32 frequency_hz`, `uint16 cycles` | `uint8 result`, returned after completion or failure |
| LOG | `0x05` | None (device event) | 1–255 bytes of formatted UTF-8 log text, no terminator |

GET_DEVICE_INFO is read-only. CAPTURE returns one independent trace. Only one
capture may be pending. STOP cancels a pending capture, returning its cancelled
CAPTURE response before the STOP response. There are no separate ACK, DATA or
completion messages.

TRANSMIT sends one finite tone burst: 40000 to 1000000 Hz, 1 to 255 cycles.
Frequency is rounded to the nearest supported half-period on the device clock.
The host waits for the TRANSMIT response before sending another transmission.
Capture and transmission may run concurrently. STOP applies only to capture.

LOG events begin after GET_DEVICE_INFO. They use device-generated frame IDs
`0x8000` through `0xFFFF`, wrapping within that range, and require no response.
Text includes the device's log formatting and line breaks; a frame need not be
a complete line. Logs may be truncated or dropped when buffers are full.

### CAPTURE response

| Offset | Field | Type |
|---:|---|---|
| 0 | Result: `0` | `uint8` |
| 1 | Initial OUT3 level: `0` or `1` | `uint8` |
| 2 | Capture duration, ticks | `uint32` |
| 6 | Edge count | `uint16` |
| 8 | Edge offsets from capture start, ticks | `uint32[edge_count]` |

Each edge toggles the level. Offsets are strictly increasing, greater than zero
and less than the duration. A trace with zero edges has a constant level.
Time in seconds is ticks divided by `tick_hz`. Captures have independent time
origins; they do not form a continuous stream.

### Results

| Value | Meaning |
|---:|---|
| `0` | Success |
| `1` | Invalid request |
| `2` | Device busy |
| `3` | Operation timed out |
| `4` | Capture cancelled |
| `5` | Capture buffer overflow |
| `6` | Device error |

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
