# Devialet Expert Pro Network Control API

**Complete Protocol Documentation for Network Control of Devialet Expert Pro Amplifiers**

Version: 1.0
Date: January 2026
Protocol: UDP-based proprietary protocol

---

## Table of Contents

1. [Overview](#overview)
2. [Network Discovery](#network-discovery)
3. [Status Packets](#status-packets)
4. [Command Packets](#command-packets)
5. [Commands Reference](#commands-reference)
6. [Channel Mapping](#channel-mapping)
7. [Implementation Examples](#implementation-examples)
8. [Known Issues & Limitations](#known-issues--limitations)
9. [Protocol Differences: Expert Pro vs Phantom](#protocol-differences-expert-pro-vs-phantom)

---

## Overview

### Protocol Summary

The Devialet Expert Pro uses a **UDP-based binary protocol** for network control, distinctly different from the HTTP REST API used by Phantom speakers.

**Key Characteristics:**
- **Transport:** UDP (not TCP)
- **Status Port:** 45454 (UDP broadcast from amp to network)
- **Command Port:** 45455 (UDP unicast to amp)
- **Packet Format:** Binary with CRC-16/CCITT-FALSE checksums
- **Status Packet Size:** 598 bytes (NOT 512 bytes like Phantom)
- **Command Packet Size:** 142 bytes
- **Discovery:** Passive listening to broadcast status packets

### Note on Devialet Phantom API

⚠️ **IMPORTANT:** The Expert Pro uses an entirely different API than Devialet Phantom speakers. The Phantom API uses HTTP REST, while Expert Pro uses UDP binary protocol. Do NOT use Phantom protocol documentation as a model for controlling Expert Pro amplifiers.

---

## Network Discovery

### Automatic Discovery

The Expert Pro broadcasts status packets on **UDP port 45454** approximately once per second. Any device on the network can listen for these broadcasts to discover the amplifier.

**Discovery Algorithm:**

```
1. Create UDP socket
2. Bind to port 45454 (any interface: 0.0.0.0)
3. Set SO_REUSEADDR to allow multiple listeners
4. Listen for incoming packets (timeout: 2-5 seconds recommended)
5. Extract IP address from packet source
6. Decode device name from bytes 19-50
```

**Python Example:**

```python
import socket

UDP_PORT_STATUS = 45454

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('', UDP_PORT_STATUS))
sock.settimeout(5.0)

data, addr = sock.recvfrom(2048)  # Must be >= 598 bytes
amplifier_ip = addr[0]
device_name = data[19:50].decode('UTF-8').strip('\x00')

print(f"Found: {device_name} at {amplifier_ip}")
sock.close()
```

**Swift/iOS Example:**

```swift
import Network

let connection = NWConnection(
    host: NWEndpoint.Host("0.0.0.0"),
    port: NWEndpoint.Port(rawValue: 45454)!,
    using: .udp
)

connection.receiveMessage { (data, context, isComplete, error) in
    guard let data = data, data.count >= 598 else { return }

    let ipAddress = context?.protocolMetadata.first as? NWProtocolIP.Metadata
    let deviceName = String(data: data[19..<50], encoding: .utf8)?
        .trimmingCharacters(in: .controlCharacters)

    print("Found: \(deviceName) at \(ipAddress?.remoteAddress)")
}
```

### IP Address Caching

For production apps, cache the discovered IP address to avoid 2-5 second discovery delays on every command:

- Store IP in user defaults / local storage
- On app launch, try cached IP first
- If cached IP fails (timeout), fall back to discovery
- Update cache when IP changes

---

## Status Packets

### Packet Structure

Status packets are **598 bytes** broadcast on UDP port 45454.

**Buffer Size Warning:** You MUST allocate at least 598 bytes (recommended: 2048 bytes) to receive the full packet. Truncating at 512 bytes will lose critical data (volume, mute, channel information).

### Byte Map

| Byte Range | Description | Data Type | Notes |
|------------|-------------|-----------|-------|
| 0-1 | Header | uint16 | Always `0x4472` |
| 2 | Packet counter LSB | uint8 | Increments with each broadcast |
| 3 | Packet counter MSB | uint8 | Changes between different states |
| 19-50 | Device Name | ASCII string | Null-terminated UTF-8 |
| 52-306 | Channel Definitions | 15 × 17-byte blocks | See [Channel Definitions](#channel-definitions) |
| 307 | **UNUSED** | - | Previously documented as power, incorrect |
| 308 | **UNUSED on Expert Pro** | - | Used on Phantom, ignore on Expert |
| 562 | **Power State** | bitfield | **Bit 7: power (1=on, 0=standby)** |
| 563 | **Mute + Channel** | bitfield | **CRITICAL BYTE** |
| 565 | **Volume** | uint8 | **CRITICAL BYTE** |
| 596-597 | CRC-16 | uint16 (BE) | CRC-16/CCITT-FALSE of bytes 0-595 |

### Channel Definitions (Bytes 52-306)

The packet contains space for up to 15 input channels, each occupying 17 bytes:

**Structure for channel `i` (i = 0 to 14):**

| Offset | Size | Description |
|--------|------|-------------|
| 52 + i×17 | 1 byte | Enabled flag (ASCII '0' or '1') |
| 53 + i×17 | 16 bytes | Channel name (null-terminated UTF-8) |

**Example:**

```python
channels = {}
for i in range(15):
    enabled = int(chr(data[52 + i * 17]))
    if enabled:
        name_bytes = data[53 + i * 17 : 52 + (i + 1) * 17]
        channels[i] = name_bytes.decode('UTF-8').strip('\x00')

# Result: {0: 'Optical 1', 1: 'Phono', 2: 'UPnP', ...}
```

### Decoding Critical Bytes

#### Byte 562: Power State

```python
power_on = (data[562] & 0x80) != 0
# True = amplifier is on
# False = amplifier in standby
```

**Note:** Earlier documentation incorrectly stated byte 307. The correct power status is in byte 562, bit 7, discovered through systematic packet analysis.

#### Byte 563: Mute + Channel (CRITICAL)

This byte encodes TWO pieces of information:

```python
# Bit 1: Mute status
muted = (data[563] & 0x02) != 0

# Bits 2-7: Channel number
channel_number = (data[563] & 0xfc) >> 2
```

**Byte 563 Bit Layout:**

```
Bit:     7  6  5  4  3  2  1  0
        [  Channel Number  ][M][?]
                             |
                             Mute flag (1=muted)
```

**Example Values:**

| Byte 563 Value | Binary | Channel | Muted |
|----------------|--------|---------|-------|
| 0x00 | 00000000 | 0 (Optical) | No |
| 0x02 | 00000010 | 0 (Optical) | Yes |
| 0x04 | 00000100 | 1 (Phono) | No |
| 0x06 | 00000110 | 1 (Phono) | Yes |
| 0x14 | 00010100 | 5 (Spotify) | No |
| 0x16 | 00010110 | 5 (Spotify) | Yes |

#### Byte 565: Volume (CRITICAL)

Volume is encoded as a single byte with a linear formula:

```python
volume_raw = data[565]
volume_db = (volume_raw / 2.0) - 97.5
```

**Formula:** `dB = (byte_565 / 2.0) - 97.5`

**Example Values:**

| Byte 565 | Volume (dB) | Notes |
|----------|-------------|-------|
| 3 | -96.0 | Minimum volume |
| 155 | -20.0 | Normal listening level |
| 175 | -10.0 | Moderate volume |
| 195 | 0.0 | Recommended maximum |
| >195 | >0.0 | Amplifier capable but not recommended |

**Reverse Formula (dB to byte):**

```python
byte_565 = int((db_value + 97.5) * 2.0)
```

### CRC Validation

Status packets include a CRC-16/CCITT-FALSE checksum in the last 2 bytes (big-endian).

**Algorithm:**

```python
def crc16(data: bytes) -> int:
    """Calculate CRC-16/CCITT-FALSE checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if (crc & 0x8000) > 0:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
    return crc & 0xFFFF

# Validate packet
crc_received = (data[596] << 8) | data[597]  # Big-endian
crc_calculated = crc16(data[0:596])
crc_ok = (crc_received == crc_calculated)
```

---

## Command Packets

### Packet Structure

Commands are sent as **142-byte UDP packets** to the amplifier's IP on **port 45455**.

**Base Packet Structure:**

| Byte | Description | Value |
|------|-------------|-------|
| 0 | Header byte 1 | 0x44 |
| 1 | Header byte 2 | 0x72 |
| 2 | Reserved | 0x00 |
| 3 | Packet counter | Incrementing |
| 4 | Reserved | 0x00 |
| 5 | Packet counter / 2 | counter >> 1 |
| 6 | Command value byte 1 | Varies by command |
| 7 | Command type | See [Command Types](#command-types) |
| 8 | Command value byte 2 | Varies by command |
| 9 | Command value byte 3 | Varies by command |
| 10-11 | Reserved | 0x00 |
| 12 | CRC high byte | (CRC >> 8) & 0xFF |
| 13 | CRC low byte | CRC & 0xFF |
| 14-141 | Padding | 0x00 |

### Packet Counter

Maintain a packet counter that increments with each command:

```python
packet_counter = 0  # Initialize once per session

# For each command:
data[3] = packet_counter & 0xFF
data[5] = packet_counter >> 1
packet_counter += 1
```

### Command Reliability

**CRITICAL:** Commands must be sent **4 times** with incrementing packet counters to ensure reliable delivery.

```python
def send_command(ip, data):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    for i in range(4):
        data[3] = packet_counter
        data[5] = packet_counter >> 1

        # Calculate CRC on bytes 0-11
        crc = crc16(data[0:12])
        data[12] = (crc & 0xff00) >> 8
        data[13] = (crc & 0x00ff)

        sock.sendto(data, (ip, 45455))
        packet_counter += 1

    sock.close()
```

### Command Types

| Byte 7 Value | Command Type |
|--------------|--------------|
| 0x01 | Power (on/standby) |
| 0x04 | Volume |
| 0x05 | Channel/Input |
| 0x07 | Mute |

---

## Commands Reference

### Power Control

#### Turn On (Exit Standby)

```python
data = bytearray(142)
data[0] = 0x44
data[1] = 0x72
data[6] = 0x01  # Power on
data[7] = 0x01  # Power command type
# Send 4 times with incrementing counters
```

#### Turn Off (Enter Standby)

```python
data = bytearray(142)
data[0] = 0x44
data[1] = 0x72
data[6] = 0x00  # Power off
data[7] = 0x01  # Power command type
# Send 4 times with incrementing counters
```

### Volume Control

Volume uses a complex encoding based on binary decomposition.

#### Volume Encoding Algorithm

```python
import math

def db_convert(db_val):
    """Convert dB value to amplifier's 16-bit representation."""
    db_abs = abs(db_val)

    if db_abs == 0:
        return 0
    elif db_abs == 0.5:
        return 0x3f00
    else:
        return (256 >> math.ceil(1 + math.log(db_abs, 2))) + db_convert(db_abs - 0.5)

def set_volume(db_value):
    """
    Set volume in dB.
    Range: -96.0 to 0.0 dB
    Normal listening level: -20.0 dB
    Recommended maximum: 0.0 dB
    """
    # Convert dB to volume value
    volume = db_convert(db_value)

    # Set sign bit for negative values
    if db_value < 0:
        volume |= 0x8000

    # Build command packet
    data = bytearray(142)
    data[0] = 0x44
    data[1] = 0x72
    data[6] = 0x00
    data[7] = 0x04  # Volume command type
    data[8] = (volume & 0xff00) >> 8
    data[9] = (volume & 0x00ff)

    # Send 4 times with incrementing counters
    return data
```

**Safety Limits:**

- **Minimum:** -96.0 dB (effectively silent)
- **Normal listening level:** -20.0 dB (typical comfortable volume)
- **Recommended maximum:** 0.0 dB (amplifiers capable of going louder but not recommended)

### Mute Control

#### Mute

```python
data = bytearray(142)
data[0] = 0x44
data[1] = 0x72
data[6] = 0x01  # Mute on
data[7] = 0x07  # Mute command type
# Send 4 times with incrementing counters
```

#### Unmute

```python
data = bytearray(142)
data[0] = 0x44
data[1] = 0x72
data[6] = 0x00  # Mute off
data[7] = 0x07  # Mute command type
# Send 4 times with incrementing counters
```

### Channel Control

Channel switching on Expert Pro uses **non-linear encoding**. You must use the mapping table below.

#### Channel Command Encoding

```python
# Status channel number -> Command value mapping
CHANNEL_MAP = {
    0: -1,   # Optical 1
    1: 'hardcoded',  # Phono (uses hardcoded bytes 0x3F 0x80)
    2: 0,    # UPnP
    3: 3,    # Roon Ready
    4: 4,    # AirPlay
    5: 5,    # Spotify
    14: 14,  # Air
}

def set_channel(status_channel_number):
    """
    Switch to input channel.

    Args:
        status_channel_number: Channel number from status packet byte 563

    Raises:
        Exception if channel not accessible via network
    """
    if status_channel_number not in CHANNEL_MAP:
        raise Exception(f"Channel {status_channel_number} not accessible")

    # Special handling for Phono - uses hardcoded bytes from Wireshark analysis
    # The standard formula doesn't work for Phono; the official app sends 0x3F 0x80
    # Reference: https://github.com/gnulabis/devimote/issues/2
    if status_channel_number == 1:  # Phono
        data = bytearray(142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x00
        data[7] = 0x05  # Channel command type
        data[8] = 0x3F  # Hardcoded byte 8 for Phono
        data[9] = 0x80  # Hardcoded byte 9 for Phono
        # Send 4 times with incrementing counters
        return data

    # Standard channel selection for other inputs
    cmd_value = CHANNEL_MAP[status_channel_number]
    out_val = 0x4000 | (cmd_value << 5)

    data = bytearray(142)
    data[0] = 0x44
    data[1] = 0x72
    data[6] = 0x00
    data[7] = 0x05  # Channel command type
    data[8] = (out_val & 0xff00) >> 8

    if cmd_value > 7:
        data[9] = (out_val & 0x00ff) >> 1
    else:
        data[9] = (out_val & 0x00ff)

    # Send 4 times with incrementing counters
    return data
```

---

## Channel Mapping

### Discovered Mapping Table

Through extensive testing, the following channel mappings were discovered:

| Status Ch# | Command Value | Channel Name (Example) | Network Accessible |
|------------|---------------|------------------------|-------------------|
| 0 | -1 | Optical 1 | ✅ Yes |
| 1 | 0x3F80 (hardcoded) | Phono | ✅ Yes* |
| 2 | 0 | UPnP | ✅ Yes |
| 3 | 3 | Roon Ready | ✅ Yes |
| 4 | 4 | AirPlay | ✅ Yes |
| 5 | 5 | Spotify | ✅ Yes |
| 6-13 | Not used | - | - |
| 14 | 14 | Air (Bluetooth) | ✅ Yes |

\*Phono uses hardcoded bytes discovered via Wireshark packet analysis of the official Devialet app.

### Channel Encoding Notes

1. **Non-linear mapping:** There is NO mathematical formula to convert status channel numbers to command values. You must use a lookup table.

2. **Phono requires hardcoded bytes:** The Phono input (channel 1) doesn't follow the standard encoding formula. Through Wireshark packet analysis of the official Devialet app, it was discovered that Phono requires hardcoded bytes `0x3F 0x80` in positions 8-9 of the command packet. Reference: [gnulabis/devimote Issue #2](https://github.com/gnulabis/devimote/issues/2)

3. **Alternative command values:** Some channels accept multiple command values:
   - Optical 1: Commands -10 through -1 all work
   - UPnP: Commands 0-1 work
   - Air: Commands 9-20 work

   The mapping table shows the recommended values.

4. **User-defined channel names:** Channel names (Optical 1, Phono, etc.) are user-configurable in the Devialet app. Your app should read channel names from status packets (bytes 52-306) rather than hard-coding them.

---

## Implementation Examples

### Complete Python Example

```python
#!/usr/bin/env python3
import socket
import struct
import math

UDP_PORT_STATUS = 45454
UDP_PORT_CMD = 45455

class DevialetExpertPro:
    def __init__(self):
        self.ip = None
        self.packet_counter = 0

    def discover(self, timeout=5.0):
        """Discover amplifier on network."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', UDP_PORT_STATUS))
        sock.settimeout(timeout)

        try:
            data, addr = sock.recvfrom(2048)
            self.ip = addr[0]
            return self._decode_status(data)
        finally:
            sock.close()

    def get_status(self):
        """Get current status (requires IP to be set)."""
        if not self.ip:
            return self.discover()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', UDP_PORT_STATUS))
        sock.settimeout(2.0)

        try:
            data, _ = sock.recvfrom(2048)
            return self._decode_status(data)
        finally:
            sock.close()

    def _decode_status(self, data):
        """Decode status packet."""
        status = {
            'device_name': data[19:50].decode('UTF-8').strip('\x00'),
            'power': (data[307] & 0x80) != 0,
            'muted': (data[563] & 0x02) != 0,
            'channel': (data[563] & 0xfc) >> 2,
            'volume_db': (data[565] / 2.0) - 97.5,
        }

        # Decode channels
        status['channels'] = {}
        for i in range(15):
            if int(chr(data[52 + i * 17])):
                name = data[53 + i*17:52 + (i+1)*17].decode('UTF-8').strip('\x00')
                status['channels'][i] = name

        return status

    def _send_command(self, data):
        """Send command packet 4 times."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        for _ in range(4):
            data[3] = self.packet_counter & 0xff
            data[5] = (self.packet_counter >> 1) & 0xff
            self.packet_counter += 1

            # Calculate CRC
            crc = self._crc16(data[0:12])
            data[12] = (crc & 0xff00) >> 8
            data[13] = (crc & 0x00ff)

            sock.sendto(data, (self.ip, UDP_PORT_CMD))

        sock.close()

    def _crc16(self, data):
        """Calculate CRC-16/CCITT-FALSE."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if (crc & 0x8000) > 0:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
        return crc & 0xFFFF

    def turn_on(self):
        """Turn on amplifier."""
        data = bytearray(142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x01
        data[7] = 0x01
        self._send_command(data)

    def turn_off(self):
        """Turn off amplifier."""
        data = bytearray(142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x00
        data[7] = 0x01
        self._send_command(data)

    def set_volume(self, db):
        """Set volume in dB (-96 to 0; normal: -20, recommended max: 0)."""
        def db_convert(val):
            val = abs(val)
            if val == 0:
                return 0
            elif val == 0.5:
                return 0x3f00
            else:
                return (256 >> math.ceil(1 + math.log(val, 2))) + db_convert(val - 0.5)

        volume = db_convert(db)
        if db < 0:
            volume |= 0x8000

        data = bytearray(142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x00
        data[7] = 0x04
        data[8] = (volume & 0xff00) >> 8
        data[9] = (volume & 0x00ff)
        self._send_command(data)

    def mute(self):
        """Mute amplifier."""
        data = bytearray(142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x01
        data[7] = 0x07
        self._send_command(data)

    def unmute(self):
        """Unmute amplifier."""
        data = bytearray(142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x00
        data[7] = 0x07
        self._send_command(data)

# Usage
amp = DevialetExpertPro()
status = amp.discover()
print(f"Found: {status['device_name']}")
print(f"Volume: {status['volume_db']:.1f} dB")

amp.turn_on()
amp.set_volume(-20)
amp.unmute()
```

### Swift/iOS Pseudo-Implementation

```swift
import Foundation
import Network

class DevialetExpertPro {
    private var ipAddress: String?
    private var packetCounter: UInt8 = 0

    // MARK: - Discovery

    func discover(timeout: TimeInterval = 5.0, completion: @escaping (Result<Status, Error>) -> Void) {
        let listener = try? NWListener(using: .udp, on: 45454)

        listener?.newConnectionHandler = { connection in
            connection.start(queue: .main)
            connection.receiveMessage { data, context, isComplete, error in
                guard let data = data, data.count >= 598 else { return }

                if let ip = self.extractIP(from: context) {
                    self.ipAddress = ip
                }

                let status = self.decodeStatus(data)
                completion(.success(status))
                listener?.cancel()
            }
        }

        listener?.start(queue: .main)

        // Timeout handler
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
            listener?.cancel()
            completion(.failure(NSError(domain: "Discovery timeout", code: -1)))
        }
    }

    // MARK: - Status Decoding

    func decodeStatus(_ data: Data) -> Status {
        let deviceName = String(data: data[19..<50], encoding: .utf8)?
            .trimmingCharacters(in: .controlCharacters) ?? "Unknown"

        let power = (data[307] & 0x80) != 0
        let muted = (data[563] & 0x02) != 0
        let channel = (data[563] & 0xfc) >> 2
        let volumeDB = (Double(data[565]) / 2.0) - 97.5

        // Decode channels
        var channels: [Int: String] = [:]
        for i in 0..<15 {
            let offset = 52 + i * 17
            if data[offset] == 0x31 { // ASCII '1'
                let nameData = data[(offset+1)..<(offset+17)]
                if let name = String(data: nameData, encoding: .utf8)?
                    .trimmingCharacters(in: .controlCharacters) {
                    channels[i] = name
                }
            }
        }

        return Status(
            deviceName: deviceName,
            power: power,
            muted: muted,
            channel: Int(channel),
            volumeDB: volumeDB,
            channels: channels
        )
    }

    // MARK: - Commands

    func turnOn() {
        var data = Data(count: 142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x01
        data[7] = 0x01
        sendCommand(data)
    }

    func setVolume(_ db: Double) {
        // Normal listening: -20 dB, Recommended max: 0 dB
        let volume = encodeVolume(db)

        var data = Data(count: 142)
        data[0] = 0x44
        data[1] = 0x72
        data[6] = 0x00
        data[7] = 0x04
        data[8] = UInt8((volume & 0xff00) >> 8)
        data[9] = UInt8(volume & 0x00ff)
        sendCommand(data)
    }

    private func sendCommand(_ data: Data) {
        guard let ip = ipAddress else { return }

        let connection = NWConnection(
            host: NWEndpoint.Host(ip),
            port: 45455,
            using: .udp
        )

        connection.start(queue: .global())

        // Send 4 times with incrementing counters
        for _ in 0..<4 {
            var packet = data
            packet[3] = packetCounter
            packet[5] = packetCounter >> 1
            packetCounter += 1

            let crc = calculateCRC16(packet[0..<12])
            packet[12] = UInt8((crc & 0xff00) >> 8)
            packet[13] = UInt8(crc & 0x00ff)

            connection.send(content: packet, completion: .idempotent)
        }

        connection.cancel()
    }

    private func calculateCRC16(_ data: Data) -> UInt16 {
        var crc: UInt16 = 0xFFFF
        for byte in data {
            crc ^= UInt16(byte) << 8
            for _ in 0..<8 {
                if (crc & 0x8000) > 0 {
                    crc = (crc << 1) ^ 0x1021
                } else {
                    crc = crc << 1
                }
            }
        }
        return crc & 0xFFFF
    }
}

struct Status {
    let deviceName: String
    let power: Bool
    let muted: Bool
    let channel: Int
    let volumeDB: Double
    let channels: [Int: String]
}
```

---

## Known Issues & Limitations

### 1. Phono Input Requires Special Handling

**Issue:** The Phono input (status channel 1) doesn't follow the standard channel encoding formula used by other inputs.

**Solution:** Through Wireshark packet analysis of the official Devialet app, it was discovered that Phono requires hardcoded bytes `0x3F 0x80` in positions 8-9 of the command packet. The reference implementation includes this special handling.

**Implementation:** When switching to channel 1 (Phono), use:
```python
data[8] = 0x3F  # Hardcoded byte 8 for Phono
data[9] = 0x80  # Hardcoded byte 9 for Phono
```

**Reference:** [gnulabis/devimote Issue #2](https://github.com/gnulabis/devimote/issues/2)

### 2. No Real-Time Status Push

**Issue:** The amplifier broadcasts status packets approximately once per second, but there's no way to request an immediate status update.

**Implications:**
- After sending a command, you must wait up to 1 second to receive confirmation
- Can't determine if a command succeeded immediately
- Status updates have ~1 second latency

**Workaround:** Cache last known status and update optimistically after sending commands.

### 3. No Authentication

**Issue:** No authentication or encryption. Any device on the network can control the amplifier.

**Security Implications:**
- Anyone with network access can control volume, power, etc.
- No way to prevent unauthorized access
- Malicious actors could damage speakers with maximum volume

**Mitigations:**
- Isolate amplifier on secure network
- Use firewall rules to restrict access to port 45454/45455
- Implement volume safety limits in your app (-10 dB maximum recommended)

### 4. Channel Encoding is Non-Linear

**Issue:** There is no mathematical formula to convert status channel numbers to command values.

**Impact:** You must maintain a hardcoded mapping table that may differ between amplifier models or firmware versions.

**Workaround:** Build the mapping dynamically by:
1. Reading available channels from status packet
2. Testing command values to see which channel they select
3. Building a runtime mapping table

### 5. Packet Truncation Risk

**Issue:** Many UDP implementations default to 512-byte buffers, which truncates Expert Pro packets at exactly the wrong place (cutting off volume, mute, and channel data).

**Critical Fix:** ALWAYS allocate at least 598 bytes (recommend 2048) for receive buffers.

```python
# WRONG - truncates critical data
data, addr = sock.recvfrom(512)

# CORRECT
data, addr = sock.recvfrom(2048)
```

### 6. Command Reliability

**Issue:** UDP is unreliable (packets can be lost).

**Solution:** The protocol requires sending each command **4 times** with incrementing packet counters. Always follow this pattern.

### 7. Volume Encoding Complexity

**Issue:** The volume encoding algorithm uses recursive binary decomposition, which is computationally expensive and non-obvious.

**Impact:** Difficult to implement from scratch in languages without good math libraries.

**Solution:** Use the provided `db_convert()` function or pre-compute a lookup table:

```python
# Pre-compute volume lookup table
VOLUME_TABLE = {}
for db_int in range(-960, -99):  # -96.0 to -10.0 in 0.1 dB steps
    db = db_int / 10.0
    VOLUME_TABLE[db] = encode_volume(db)

# Fast lookup
volume_value = VOLUME_TABLE[round(db * 10) / 10]
```

---

## Note on Devialet Phantom Compatibility

**The Devialet Expert Pro uses an entirely different API than Devialet Phantom speakers.**

- **Phantom speakers:** HTTP REST API
- **Expert Pro amplifiers:** UDP Binary Protocol

Do NOT attempt to use Phantom API code or documentation for Expert Pro. The protocols are fundamentally incompatible.

**Original Protocol Source:** The UDP protocol was reverse-engineered from Phantom speakers by the [devimote project](https://github.com/gnulabis/devimote), but Expert Pro uses a significantly different packet structure.

---

## Appendix A: Byte-by-Byte Packet Examples

### Status Packet Example (598 bytes)

```
Device: "My Devialet-ETH"
IP: 10.0.7.28
Power: ON
Volume: -20.0 dB
Muted: NO
Channel: 5 (Spotify)

Hex dump (key bytes):
0000: 44 72 32 47 00 00 ...              # Header
0013: 4D 79 20 44 65 76 69 61 6C 65 74  # "My Devialet"
      2D 45 54 48 00 00 00 ...          # "-ETH"
0034: 31 4F 70 74 69 63 61 6C 20 31 00  # Channel 0: "Optical 1"
0045: 31 50 68 6F 6E 6F 00 00 00 ...    # Channel 1: "Phono"
0056: 31 55 50 6E 50 00 00 00 00 ...    # Channel 2: "UPnP"
...
0133: 81                                 # Byte 307: Power ON (bit 7 set)
0234: 14                                 # Byte 563: Channel 5, not muted
0235: 00                                 # Byte 564
0236: 9B                                 # Byte 565: Volume (155 = -20.0 dB)
...
0254: A3 2F                              # Bytes 596-597: CRC-16
```

### Power On Command (142 bytes)

```
Hex dump:
00: 44 72 00 05 00 02 01 01 00 00 00 00 8B 9E  # Header + power on + CRC
0E: 00 00 00 00 00 00 00 00 00 00 00 00 00 00  # Padding
...
8C: 00 00                                       # End padding

Breakdown:
Bytes 0-1:  0x44 0x72  - Header
Byte 3:     0x05       - Packet counter
Byte 5:     0x02       - Packet counter >> 1
Byte 6:     0x01       - Power ON
Byte 7:     0x01       - Power command type
Bytes 12-13: 0x8B 0x9E - CRC-16
```

### Volume -20 dB Command (142 bytes)

```
Hex dump:
00: 44 72 00 09 00 04 00 04 83 FF 00 00 38 86  # Header + volume + CRC

Breakdown:
Bytes 0-1:  0x44 0x72  - Header
Byte 3:     0x09       - Packet counter
Byte 5:     0x04       - Packet counter >> 1
Byte 6:     0x00       - Reserved
Byte 7:     0x04       - Volume command type
Bytes 8-9:  0x83 0xFF  - Encoded -20.0 dB (0x83FF)
Bytes 12-13: 0x38 0x86 - CRC-16
```

---

## Appendix B: Testing Tools

### Packet Capture

To capture packets for analysis:

```bash
# Capture status broadcasts
tcpdump -i any -n udp port 45454 -w devialet_status.pcap

# Capture commands to amp
tcpdump -i any -n udp port 45455 -w devialet_commands.pcap

# Capture both
tcpdump -i any -n 'udp port 45454 or udp port 45455' -w devialet_all.pcap
```

### Manual Packet Analysis

```python
#!/usr/bin/env python3
"""Dump and analyze a single status packet."""

import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('', 45454))
sock.settimeout(5.0)

data, addr = sock.recvfrom(2048)
sock.close()

print(f"Received {len(data)} bytes from {addr[0]}")
print("\nHex dump:")

for i in range(0, len(data), 16):
    hex_str = ' '.join(f'{data[j]:02x}' for j in range(i, min(i+16, len(data))))
    ascii_str = ''.join(chr(data[j]) if 32 <= data[j] < 127 else '.'
                       for j in range(i, min(i+16, len(data))))
    print(f"{i:04x}: {hex_str:<48}  {ascii_str}")

print(f"\nKey values:")
print(f"  Device name: {data[19:50].decode('UTF-8').strip()}")
print(f"  Power: {'ON' if data[307] & 0x80 else 'STANDBY'}")
print(f"  Muted: {'YES' if data[563] & 0x02 else 'NO'}")
print(f"  Channel: {(data[563] & 0xfc) >> 2}")
print(f"  Volume: {(data[565] / 2.0) - 97.5:.1f} dB (normal: -20, recommended max: 0)")
```

---

## Appendix C: Reference Implementation

The reference Python implementation is available in `devialet_expert_control.py` and includes:

- ✅ Auto-discovery with IP caching
- ✅ Complete status decoding (all bytes)
- ✅ Power control (on/off/toggle)
- ✅ Volume control with safety limits
- ✅ Mute control
- ✅ Channel switching (including Phono with hardcoded bytes)
- ✅ CRC validation
- ✅ Command-line interface
- ✅ Error handling

**Usage:**
```bash
python3 devialet_expert_control.py status
python3 devialet_expert_control.py on
python3 devialet_expert_control.py volume -20
python3 devialet_expert_control.py mute
python3 devialet_expert_control.py channel 1  # Switch to Phono
python3 devialet_expert_control.py channel 5  # Switch to Spotify
```

---

## Credits & References

- **Protocol reverse-engineering:** Based on [gnulabis/devimote](https://github.com/gnulabis/devimote) for Phantom speakers
- **Expert Pro packet analysis:** Discovered through systematic testing and packet capture (January 2026)
- **Phono channel encoding:** Wireshark packet analysis documented in [gnulabis/devimote Issue #2](https://github.com/gnulabis/devimote/issues/2)
- **Key discoveries:**
  - 598-byte packet size (not 512)
  - Byte 562, bit 7: Power status (corrected from byte 307)
  - Byte 565 volume encoding
  - Byte 563 dual-purpose (mute + channel)
  - Non-linear channel mapping
  - Phono hardcoded bytes (0x3F 0x80)

---

## Version History

**v1.0 (January 2026)**
- Initial documentation
- Complete protocol specification
- Python and Swift/iOS examples
- Channel mapping table
- Known issues and limitations

---

## License

This documentation is provided as-is for educational and development purposes. Devialet is a trademark of Devialet SAS. This documentation is not affiliated with or endorsed by Devialet.

The protocol information was derived through legal reverse-engineering and packet analysis of devices owned by the author.
