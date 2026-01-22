#!/usr/bin/env python3
"""
Control script for Devialet Expert Pro amplifier using UDP protocol.

Based on the protocol reverse-engineered by gnulabis/devimote:
https://github.com/gnulabis/devimote

IMPORTANT NOTE:
    The Expert Pro sends 598-byte UDP status packets (not 512 bytes like Phantom).
    Volume is encoded in byte 565 of the packet.
    Formula: dB = (byte_565 / 2.0) - 97.5

IP ADDRESS CACHING:
    The script caches the discovered IP address in ~/.devialet_expert_ip
    This makes subsequent commands much faster (no discovery wait).
    If your amp's IP changes, the script will auto-discover and update the cache.
    Use --no-cache to disable caching.

Usage (auto-discovers amplifier):
    python devialet_expert_control.py --status
    python devialet_expert_control.py --on
    python devialet_expert_control.py --off
    python devialet_expert_control.py --volume -20
    python devialet_expert_control.py --mute
    python devialet_expert_control.py --unmute

Or specify IP address:
    python devialet_expert_control.py --ip 192.168.1.10 --on
"""

import socket
import struct
import argparse
import sys
import time
import math as m
import os
from pathlib import Path


def crc16(data: bytearray) -> int:
    """Calculate CRC-16/CCITT-FALSE checksum."""
    if data is None:
        return 0
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if (crc & 0x8000) > 0:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
    return crc & 0xFFFF


class DevialetExpertController:
    """Controller for Devialet Expert Pro amplifier via UDP."""

    UDP_PORT_STATUS = 45454
    UDP_PORT_CMD = 45455
    VOLUME_MIN = -96.0  # dB
    VOLUME_MAX = 0.0  # dB (recommended maximum; amps capable of going louder)
    CACHE_FILE = Path.home() / ".devialet_expert_ip"

    def __init__(self, ip: str = None, timeout: float = 2.0, use_cache: bool = True):
        """
        Initialize controller.

        Args:
            ip: IP address of amplifier (if None, will auto-discover)
            timeout: Timeout for status updates in seconds
            use_cache: Whether to use cached IP address
        """
        self.ip = ip
        self.timeout = timeout
        self.packet_cnt = 0
        self.status = {}
        self.use_cache = use_cache and (ip is None)  # Only use cache if IP not explicitly specified

    def _read_cached_ip(self) -> str:
        """Read cached IP address from file."""
        try:
            if self.CACHE_FILE.exists():
                return self.CACHE_FILE.read_text().strip()
        except:
            pass
        return None

    def _write_cached_ip(self, ip: str):
        """Write IP address to cache file."""
        try:
            self.CACHE_FILE.write_text(ip + '\n')
        except:
            pass  # Silently ignore cache write failures

    def discover(self) -> dict:
        """
        Listen for status broadcast to discover amplifier on network.

        Returns:
            Status dictionary with amplifier info
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(('', self.UDP_PORT_STATUS))
        sock.settimeout(self.timeout)

        try:
            # Increased buffer to 2048 to capture full 598-byte packet
            data, addr = sock.recvfrom(2048)
            self.ip = addr[0]

            # Cache the discovered IP
            if self.use_cache:
                self._write_cached_ip(addr[0])

            return self._decode_status(data, addr[0])
        except socket.timeout:
            raise Exception(f"No Devialet Expert amplifier found on network after {self.timeout}s")
        finally:
            sock.close()

    def get_status(self) -> dict:
        """
        Get current amplifier status.

        Returns:
            Dictionary with status information
        """
        # If no IP set, try cache first, then discover
        if not self.ip:
            if self.use_cache:
                cached_ip = self._read_cached_ip()
                if cached_ip:
                    self.ip = cached_ip
                    try:
                        return self._get_status_from_broadcast()
                    except:
                        # Cached IP failed, fall back to discovery
                        self.ip = None

            # No cache or cache failed - do discovery
            return self.discover()

        # IP is set (either from cache, explicit, or previous discovery)
        return self._get_status_from_broadcast()

    def _get_status_from_broadcast(self) -> dict:
        """Internal method to get status from UDP broadcast."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(('', self.UDP_PORT_STATUS))
        sock.settimeout(self.timeout)

        try:
            # Increased buffer to 2048 to capture full 598-byte packet
            data, addr = sock.recvfrom(2048)
            return self._decode_status(data, addr[0])
        except socket.timeout:
            raise Exception(f"Timeout waiting for status from {self.ip if self.ip else 'amplifier'}")
        finally:
            sock.close()

    def _decode_status(self, data: bytes, ip: str) -> dict:
        """Decode status packet from amplifier."""
        status = {}
        status['ip'] = ip
        status['device_name'] = data[19:50].decode('UTF-8').strip('\x00')

        # Decode available channels
        status['channels'] = {}
        for i in range(15):
            enabled = int(chr(data[52 + i * 17]))
            if enabled:
                status['channels'][i] = data[53 + i * 17:52 + (i + 1) * 17].decode('UTF-8').strip('\x00')

        # Decode current state
        # Power status is in byte 562, bit 7 (discovered through packet analysis)
        # Note: Original documentation incorrectly stated byte 307
        if len(data) >= 563:
            status['power'] = (data[562] & 0x80) != 0
        else:
            status['power'] = None

        # Channel and mute are both in byte 563 (in the extended part of the packet)
        if len(data) >= 564:
            # Byte 563 encoding:
            #   Bit 1 (0x02): Mute status
            #   Bits 2-7 (0xfc): Channel number (shifted right by 2)
            status['muted'] = (data[563] & 0x02) != 0
            status['channel'] = (data[563] & 0xfc) >> 2
        else:
            status['muted'] = None
            status['channel'] = None

        # Volume is in byte 565 (in the extended part of the packet beyond 512 bytes)
        # Formula discovered through packet analysis: dB = (byte_565 / 2.0) - 97.5
        if len(data) >= 566:
            status['volume_raw'] = data[565]
            status['volume_db'] = (data[565] / 2.0) - 97.5
        else:
            # Packet truncated (shouldn't happen with 2048 byte buffer)
            status['volume_db'] = None

        # Verify CRC
        crc_received = struct.unpack('>H', data[-2:])[0]
        crc_calculated = crc16(bytearray(data[:-2]))
        status['crc_ok'] = (crc_received == crc_calculated)

        return status

    def _send_command(self, data: bytearray):
        """Send command packet to amplifier."""
        if not self.ip:
            raise Exception("No IP address set. Run get_status() first to discover amplifier.")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Set packet header
            data[0] = 0x44
            data[1] = 0x72

            # Send command 4 times (as per original implementation)
            for _ in range(4):
                data[3] = self.packet_cnt
                data[5] = self.packet_cnt >> 1
                self.packet_cnt += 1

                # Calculate and append CRC
                crc = crc16(data[0:12])
                data[12] = (crc & 0xff00) >> 8
                data[13] = (crc & 0x00ff)

                sock.sendto(data, (self.ip, self.UDP_PORT_CMD))
        finally:
            sock.close()

    def turn_on(self):
        """Turn on the amplifier (exit standby)."""
        data = bytearray(142)
        data[6] = 0x01  # Power on
        data[7] = 0x01  # Power command
        self._send_command(data)

    def turn_off(self):
        """Turn off the amplifier (enter standby)."""
        data = bytearray(142)
        data[6] = 0x00  # Power off
        data[7] = 0x01  # Power command
        self._send_command(data)

    def toggle_power(self):
        """Toggle power state."""
        status = self.get_status()
        if status['power']:
            self.turn_off()
        else:
            self.turn_on()

    def mute(self):
        """Mute the amplifier."""
        data = bytearray(142)
        data[6] = 0x01  # Mute on
        data[7] = 0x07  # Mute command
        self._send_command(data)

    def unmute(self):
        """Unmute the amplifier."""
        data = bytearray(142)
        data[6] = 0x00  # Mute off
        data[7] = 0x07  # Mute command
        self._send_command(data)

    def toggle_mute(self):
        """Toggle mute state."""
        status = self.get_status()
        if status['muted']:
            self.unmute()
        else:
            self.mute()

    def set_volume(self, db_value: float):
        """
        Set volume level.

        Args:
            db_value: Volume in dB (range: -96.0 to 0.0)
                     Normal listening level: -20.0 dB
                     Recommended maximum: 0.0 dB
        """
        # Safety limits
        if db_value > self.VOLUME_MAX:
            print(f"Warning: Limiting volume to {self.VOLUME_MAX}dB (recommended maximum)")
            db_value = self.VOLUME_MAX
        if db_value < self.VOLUME_MIN:
            db_value = self.VOLUME_MIN

        def db_convert(db_val):
            """Convert dB to 16-bit representation used by amplifier."""
            db_abs = m.fabs(db_val)
            if db_abs == 0:
                return 0
            elif db_abs == 0.5:
                return 0x3f00
            else:
                return (256 >> m.ceil(1 + m.log(db_abs, 2))) + db_convert(db_abs - 0.5)

        volume = db_convert(db_value)

        if db_value < 0:
            volume |= 0x8000

        data = bytearray(142)
        data[6] = 0x00
        data[7] = 0x04  # Volume command
        data[8] = (volume & 0xff00) >> 8
        data[9] = (volume & 0x00ff)
        self._send_command(data)

    # Mapping from status channel number to command value
    # Discovered through automated testing - Expert Pro has non-linear channel encoding
    # Note: Phono uses hardcoded bytes discovered via Wireshark packet analysis
    CHANNEL_COMMAND_MAP = {
        0: -1,   # Optical 1 (commands -10 to -1 all work)
        1: 'hardcoded',  # Phono - uses hardcoded bytes 0x3F 0x80 (Wireshark analysis)
        2: 0,    # UPnP (commands 0-1 work)
        3: 3,    # Roon Ready
        4: 4,    # AirPlay
        5: 5,    # Spotify
        14: 14,  # Air (commands 9-20 work)
    }

    def set_channel(self, channel: int):
        """
        Set input channel.

        Args:
            channel: Status channel number (0-14) as shown in get_status()

        Note: Phono (channel 1) uses hardcoded bytes discovered via Wireshark
              packet analysis of the official Devialet app.
        """
        # Check if this channel has a known command mapping
        if channel not in self.CHANNEL_COMMAND_MAP:
            raise Exception(f"Channel {channel} is not accessible via network commands. "
                          f"Accessible channels: {sorted(self.CHANNEL_COMMAND_MAP.keys())}")

        # Special handling for Phono - uses hardcoded bytes from Wireshark analysis
        # The standard formula doesn't work for Phono; the official app sends 0x3F 0x80
        # Reference: https://github.com/gnulabis/devimote/issues/2
        if channel == 1:  # Phono
            data = bytearray(142)
            data[6] = 0x00
            data[7] = 0x05  # Channel command
            data[8] = 0x3F  # Hardcoded byte 8 for Phono
            data[9] = 0x80  # Hardcoded byte 9 for Phono
            self._send_command(data)
            return

        # Standard channel selection for other inputs
        cmd_value = self.CHANNEL_COMMAND_MAP[channel]
        out_val = 0x4000 | (cmd_value << 5)

        data = bytearray(142)
        data[6] = 0x00
        data[7] = 0x05  # Channel command
        data[8] = (out_val & 0xff00) >> 8
        if cmd_value > 7:
            data[9] = (out_val & 0x00ff) >> 1
        else:
            data[9] = (out_val & 0x00ff)
        self._send_command(data)


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description='Control Devialet Expert Pro amplifier via UDP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                    # Auto-discover and show status
  %(prog)s on                        # Auto-discover and turn on
  %(prog)s volume -20                # Auto-discover and set volume to normal listening level
  %(prog)s mute                      # Auto-discover and mute
  %(prog)s channel 5                 # Auto-discover and switch to channel 5

  %(prog)s status --ip 192.168.1.10  # Specify IP (faster, skips discovery)
  %(prog)s volume -20 --ip 10.0.7.28 # Set volume with specific IP
        """
    )

    # Global options available to all commands
    parser.add_argument('--ip', help='IP address of amplifier (optional, will auto-discover)')
    parser.add_argument('--timeout', type=float, default=2.0, help='Discovery timeout (default: 2s)')
    parser.add_argument('--no-cache', action='store_true', help='Disable IP address caching')

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', required=True, help='Command to execute')

    # status command
    subparsers.add_parser('status', help='Show current status')

    # discover command
    subparsers.add_parser('discover', help='Discover amplifier on network')

    # on command
    subparsers.add_parser('on', help='Turn on (exit standby)')

    # off command
    subparsers.add_parser('off', help='Turn off (enter standby)')

    # toggle-power command
    subparsers.add_parser('toggle-power', help='Toggle power state')

    # volume command
    volume_parser = subparsers.add_parser('volume', help='Set volume in dB (-96 to 0; normal: -20)')
    volume_parser.add_argument('db', type=float, help='Volume in dB (-96 to 0; normal: -20, max recommended: 0)')

    # mute command
    subparsers.add_parser('mute', help='Mute the amplifier')

    # unmute command
    subparsers.add_parser('unmute', help='Unmute the amplifier')

    # toggle-mute command
    subparsers.add_parser('toggle-mute', help='Toggle mute state')

    # channel command
    channel_parser = subparsers.add_parser('channel', help='Set input channel')
    channel_parser.add_argument('number', type=int, help='Channel number (see status for available channels)')

    args = parser.parse_args()

    try:
        controller = DevialetExpertController(ip=args.ip, timeout=args.timeout, use_cache=not args.no_cache)

        # Auto-discover if no IP specified (unless already doing status/discover)
        if not args.ip and args.command not in ['status', 'discover']:
            # Try to use cached IP first
            cached_ip = controller._read_cached_ip()
            if cached_ip:
                try:
                    status = controller.get_status()
                    # Cache worked, no need to print anything
                except:
                    # Cache failed, will auto-discover
                    print("Cached IP failed, discovering...")
                    status = controller.get_status()
                    print(f"Found {status['device_name']} at {status['ip']}\n")
            else:
                # No cache, auto-discover
                print("Auto-discovering...")
                status = controller.get_status()
                print(f"Found {status['device_name']} at {status['ip']}\n")

        if args.command in ['status', 'discover']:
            status = controller.get_status()
            print(f"\nDevice: {status['device_name']}")
            print(f"IP: {status['ip']}")
            print(f"Power: {'ON' if status['power'] else 'STANDBY'}")
            if status['volume_db'] is not None:
                print(f"Volume: {status['volume_db']:.1f} dB")
            else:
                print(f"Volume: Unknown (packet too short)")
            print(f"Muted: {'YES' if status['muted'] else 'NO'}")
            if status['channels']:
                current_channel = status['channels'].get(status['channel'], 'Unknown')
                print(f"Channel: {current_channel}")
                print(f"Available channels:")
                for ch_num, ch_name in sorted(status['channels'].items()):
                    current_marker = " *" if ch_num == status['channel'] else ""
                    accessible_marker = "" if ch_num in DevialetExpertController.CHANNEL_COMMAND_MAP else " (not network accessible)"
                    print(f"  {ch_num}: {ch_name}{current_marker}{accessible_marker}")
            print(f"CRC: {'OK' if status['crc_ok'] else 'ERROR'}")

        elif args.command == 'on':
            controller.turn_on()
            print("Turning on...")

        elif args.command == 'off':
            controller.turn_off()
            print("Turning off...")

        elif args.command == 'toggle-power':
            controller.toggle_power()
            print("Toggling power...")

        elif args.command == 'volume':
            controller.set_volume(args.db)
            print(f"Volume set to {args.db} dB")

        elif args.command == 'mute':
            controller.mute()
            print("Muting...")

        elif args.command == 'unmute':
            controller.unmute()
            print("Unmuting...")

        elif args.command == 'toggle-mute':
            controller.toggle_mute()
            print("Toggling mute...")

        elif args.command == 'channel':
            controller.set_channel(args.number)
            print(f"Switching to channel {args.number}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
