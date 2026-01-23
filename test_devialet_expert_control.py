#!/usr/bin/env python3
"""
Integration test suite for Devialet Expert Pro amplifier control script.

This script tests the actual functionality of the control script by sending
commands to a real amplifier and verifying that the commands took effect.

IMPORTANT TIMING NOTES:
    - Power on takes ~20 seconds to complete
    - Power off takes ~10 seconds to complete
    - Volume, mute, and channel changes take ~2 seconds to register

Usage:
    python test_devialet_expert_control.py              # Run all tests
    python test_devialet_expert_control.py --quick      # Skip power tests (faster)
    python test_devialet_expert_control.py --ip X.X.X.X # Specify amplifier IP
    python test_devialet_expert_control.py -v           # Verbose output
"""

import argparse
import sys
import time
from typing import Optional

from devialet_expert_control import DevialetExpertController


# Timing constants (seconds)
POWER_ON_DELAY = 25      # Wait after power on (20s + buffer)
POWER_OFF_DELAY = 15     # Wait after power off (10s + buffer)
COMMAND_DELAY = 3        # Wait after volume/mute/channel changes (2s + buffer)
STATUS_POLL_INTERVAL = 2 # Interval between status polls when waiting


class TestResult:
    """Container for test results."""

    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0):
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        msg = f" - {self.message}" if self.message else ""
        return f"[{status}] {self.name}{msg} ({self.duration:.1f}s)"


class DevialetTestSuite:
    """Test suite for Devialet Expert Pro amplifier control."""

    def __init__(self, ip: Optional[str] = None, verbose: bool = False):
        """
        Initialize test suite.

        Args:
            ip: Optional IP address of amplifier (auto-discovers if not specified)
            verbose: Enable verbose output
        """
        self.ip = ip
        self.verbose = verbose
        self.controller: Optional[DevialetExpertController] = None
        self.results: list[TestResult] = []
        self.initial_state: dict = {}

    def log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"  [DEBUG] {message}")

    def setup(self) -> bool:
        """
        Set up test suite by discovering amplifier and saving initial state.

        Returns:
            True if setup succeeded, False otherwise
        """
        print("\n" + "=" * 60)
        print("DEVIALET EXPERT PRO - INTEGRATION TEST SUITE")
        print("=" * 60)

        try:
            print("\nInitializing controller...")
            self.controller = DevialetExpertController(ip=self.ip, timeout=5.0)

            print("Discovering amplifier...")
            status = self.controller.get_status()

            print(f"\nFound: {status['device_name']} at {status['ip']}")
            print(f"Current state:")
            print(f"  Power:   {'ON' if status['power'] else 'STANDBY'}")
            print(f"  Volume:  {status['volume_db']:.1f} dB")
            print(f"  Muted:   {'YES' if status['muted'] else 'NO'}")
            print(f"  Channel: {status['channel']}")

            # Save initial state for restoration
            self.initial_state = {
                'power': status['power'],
                'volume_db': status['volume_db'],
                'muted': status['muted'],
                'channel': status['channel'],
            }

            return True

        except Exception as e:
            print(f"\nERROR: Failed to connect to amplifier: {e}")
            return False

    def teardown(self):
        """Restore amplifier to initial state."""
        if not self.controller or not self.initial_state:
            return

        print("\n" + "-" * 60)
        print("RESTORING INITIAL STATE")
        print("-" * 60)

        try:
            status = self.controller.get_status()

            # Restore mute state
            if status['muted'] != self.initial_state['muted']:
                if self.initial_state['muted']:
                    print("Restoring mute...")
                    self.controller.mute()
                else:
                    print("Restoring unmute...")
                    self.controller.unmute()
                time.sleep(COMMAND_DELAY)

            # Restore volume
            if abs(status['volume_db'] - self.initial_state['volume_db']) > 0.5:
                print(f"Restoring volume to {self.initial_state['volume_db']:.1f} dB...")
                self.controller.set_volume(self.initial_state['volume_db'])
                time.sleep(COMMAND_DELAY)

            # Restore channel
            if status['channel'] != self.initial_state['channel']:
                print(f"Restoring channel to {self.initial_state['channel']}...")
                self.controller.set_channel(self.initial_state['channel'])
                time.sleep(COMMAND_DELAY)

            # Restore power state
            if status['power'] != self.initial_state['power']:
                if self.initial_state['power']:
                    print("Restoring power on...")
                    self.controller.turn_on()
                    time.sleep(POWER_ON_DELAY)
                else:
                    print("Restoring standby...")
                    self.controller.turn_off()
                    time.sleep(POWER_OFF_DELAY)

            print("Initial state restored.")

        except Exception as e:
            print(f"Warning: Failed to restore initial state: {e}")

    def run_test(self, test_func, name: str) -> TestResult:
        """
        Run a single test and record result.

        Args:
            test_func: Test function to run
            name: Human-readable test name

        Returns:
            TestResult object
        """
        print(f"\n  Running: {name}...")
        start_time = time.time()

        try:
            passed, message = test_func()
            duration = time.time() - start_time
            result = TestResult(name, passed, message, duration)
        except Exception as e:
            duration = time.time() - start_time
            result = TestResult(name, False, f"Exception: {e}", duration)

        self.results.append(result)
        print(f"  {result}")
        return result

    def wait_for_status_change(self, field: str, expected_value, timeout: float) -> bool:
        """
        Poll status until field matches expected value or timeout.

        Args:
            field: Status field to check
            expected_value: Expected value of the field
            timeout: Maximum time to wait in seconds

        Returns:
            True if value matched before timeout, False otherwise
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.controller.get_status()
            actual_value = status.get(field)
            self.log(f"Waiting for {field}={expected_value}, currently={actual_value}")
            if actual_value == expected_value:
                return True
            time.sleep(STATUS_POLL_INTERVAL)
        return False

    # =========================================================================
    # STATUS TESTS
    # =========================================================================

    def test_get_status(self) -> tuple[bool, str]:
        """Test that we can retrieve status from the amplifier."""
        status = self.controller.get_status()

        # Verify essential fields are present
        required_fields = ['ip', 'device_name', 'power', 'volume_db', 'muted', 'channel']
        missing_fields = [f for f in required_fields if f not in status]

        if missing_fields:
            return False, f"Missing fields: {missing_fields}"

        return True, f"All fields present"

    def test_status_volume_range(self) -> tuple[bool, str]:
        """Test that reported volume is within valid range."""
        status = self.controller.get_status()
        volume = status['volume_db']

        if volume is None:
            return False, "Volume is None"

        if volume < -97.5 or volume > 0.5:
            return False, f"Volume {volume} dB outside expected range"

        return True, f"Volume {volume:.1f} dB is within valid range"

    def test_status_channels_available(self) -> tuple[bool, str]:
        """Test that channel information is available."""
        status = self.controller.get_status()

        if 'channels' not in status or not status['channels']:
            return False, "No channels reported"

        return True, f"Found {len(status['channels'])} channels"

    # =========================================================================
    # VOLUME TESTS
    # =========================================================================

    def test_set_volume(self) -> tuple[bool, str]:
        """Test setting volume to a specific value."""
        # Get current volume
        initial_status = self.controller.get_status()
        initial_volume = initial_status['volume_db']

        # Choose a target volume different from current (but safe)
        target_volume = -40.0 if initial_volume != -40.0 else -45.0

        self.log(f"Setting volume from {initial_volume:.1f} to {target_volume:.1f} dB")
        self.controller.set_volume(target_volume)
        time.sleep(COMMAND_DELAY)

        # Verify
        new_status = self.controller.get_status()
        new_volume = new_status['volume_db']

        # Allow 0.5 dB tolerance due to quantization
        if abs(new_volume - target_volume) > 0.5:
            return False, f"Expected {target_volume:.1f} dB, got {new_volume:.1f} dB"

        # Restore original volume
        self.controller.set_volume(initial_volume)
        time.sleep(COMMAND_DELAY)

        return True, f"Volume correctly set to {new_volume:.1f} dB"

    def test_volume_minimum(self) -> tuple[bool, str]:
        """Test setting volume to minimum value."""
        initial_status = self.controller.get_status()
        initial_volume = initial_status['volume_db']

        self.log("Setting volume to minimum (-96 dB)")
        self.controller.set_volume(-96.0)
        time.sleep(COMMAND_DELAY)

        new_status = self.controller.get_status()
        new_volume = new_status['volume_db']

        # Restore original volume
        self.controller.set_volume(initial_volume)
        time.sleep(COMMAND_DELAY)

        if new_volume > -95.5:  # Allow some tolerance
            return False, f"Minimum volume test failed, got {new_volume:.1f} dB"

        return True, f"Minimum volume correctly set to {new_volume:.1f} dB"

    def test_volume_increment(self) -> tuple[bool, str]:
        """Test that small volume changes are registered."""
        initial_status = self.controller.get_status()
        initial_volume = initial_status['volume_db']

        # Set to a known value first
        self.controller.set_volume(-50.0)
        time.sleep(COMMAND_DELAY)

        # Increment by 1 dB
        self.controller.set_volume(-49.0)
        time.sleep(COMMAND_DELAY)

        new_status = self.controller.get_status()
        new_volume = new_status['volume_db']

        # Restore original volume
        self.controller.set_volume(initial_volume)
        time.sleep(COMMAND_DELAY)

        if abs(new_volume - (-49.0)) > 0.5:
            return False, f"1 dB increment failed, got {new_volume:.1f} dB instead of -49.0 dB"

        return True, "1 dB volume increment registered correctly"

    # =========================================================================
    # MUTE TESTS
    # =========================================================================

    def test_mute(self) -> tuple[bool, str]:
        """Test muting the amplifier."""
        initial_status = self.controller.get_status()
        initial_muted = initial_status['muted']

        # Ensure we start unmuted
        if initial_muted:
            self.controller.unmute()
            time.sleep(COMMAND_DELAY)

        # Mute
        self.log("Muting amplifier")
        self.controller.mute()
        time.sleep(COMMAND_DELAY)

        new_status = self.controller.get_status()

        # Restore original state
        if not initial_muted:
            self.controller.unmute()
            time.sleep(COMMAND_DELAY)

        if not new_status['muted']:
            return False, "Amplifier not muted after mute command"

        return True, "Mute command successful"

    def test_unmute(self) -> tuple[bool, str]:
        """Test unmuting the amplifier."""
        initial_status = self.controller.get_status()
        initial_muted = initial_status['muted']

        # Ensure we start muted
        if not initial_muted:
            self.controller.mute()
            time.sleep(COMMAND_DELAY)

        # Unmute
        self.log("Unmuting amplifier")
        self.controller.unmute()
        time.sleep(COMMAND_DELAY)

        new_status = self.controller.get_status()

        # Restore original state
        if initial_muted:
            self.controller.mute()
            time.sleep(COMMAND_DELAY)

        if new_status['muted']:
            return False, "Amplifier still muted after unmute command"

        return True, "Unmute command successful"

    def test_toggle_mute(self) -> tuple[bool, str]:
        """Test toggling mute state."""
        initial_status = self.controller.get_status()
        initial_muted = initial_status['muted']

        # Toggle
        self.log(f"Toggling mute from {initial_muted}")
        self.controller.toggle_mute()
        time.sleep(COMMAND_DELAY)

        new_status = self.controller.get_status()

        # Toggle back
        self.controller.toggle_mute()
        time.sleep(COMMAND_DELAY)

        if new_status['muted'] == initial_muted:
            return False, f"Mute state did not toggle (was {initial_muted}, still {new_status['muted']})"

        return True, f"Mute toggled from {initial_muted} to {new_status['muted']}"

    # =========================================================================
    # CHANNEL TESTS
    # =========================================================================

    def test_channel_switch(self) -> tuple[bool, str]:
        """Test switching between channels."""
        initial_status = self.controller.get_status()
        initial_channel = initial_status['channel']
        available_channels = list(initial_status.get('channels', {}).keys())

        # Find channels different from current
        other_channels = [ch for ch in available_channels if ch != initial_channel]

        if not other_channels:
            return True, "No alternative channels to test"

        # Try switching to a different channel
        target_channel = other_channels[0]
        self.log(f"Switching from channel {initial_channel} to {target_channel}")

        self.controller.set_channel(target_channel)
        time.sleep(COMMAND_DELAY)

        new_status = self.controller.get_status()

        # Restore original channel
        self.controller.set_channel(initial_channel)
        time.sleep(COMMAND_DELAY)

        if new_status['channel'] != target_channel:
            return False, f"Channel did not switch to {target_channel}, still on {new_status['channel']}"

        return True, f"Successfully switched to channel {target_channel}"

    def test_all_accessible_channels(self) -> tuple[bool, str]:
        """Test switching to all available channels."""
        initial_status = self.controller.get_status()
        initial_channel = initial_status['channel']
        available_channels = list(initial_status.get('channels', {}).keys())

        if len(available_channels) < 2:
            return True, "Fewer than 2 channels available, skipping"

        failed_channels = []
        for channel in available_channels:
            self.log(f"Testing channel {channel}")
            self.controller.set_channel(channel)
            time.sleep(COMMAND_DELAY)

            status = self.controller.get_status()
            if status['channel'] != channel:
                failed_channels.append(channel)

        # Restore original channel
        self.controller.set_channel(initial_channel)
        time.sleep(COMMAND_DELAY)

        if failed_channels:
            return False, f"Failed to switch to channels: {failed_channels}"

        return True, f"All {len(available_channels)} channels working"

    # =========================================================================
    # POWER TESTS
    # =========================================================================

    def test_power_off(self) -> tuple[bool, str]:
        """Test turning off the amplifier."""
        initial_status = self.controller.get_status()

        if not initial_status['power']:
            # Already off, turn on first
            self.log("Amplifier is off, turning on first")
            self.controller.turn_on()
            if not self.wait_for_status_change('power', True, POWER_ON_DELAY):
                return False, "Could not turn on amplifier to test power off"

        # Turn off
        self.log("Turning off amplifier")
        self.controller.turn_off()

        # Wait for power off
        if not self.wait_for_status_change('power', False, POWER_OFF_DELAY):
            return False, "Amplifier did not turn off within timeout"

        return True, "Power off successful"

    def test_power_on(self) -> tuple[bool, str]:
        """Test turning on the amplifier."""
        initial_status = self.controller.get_status()

        if initial_status['power']:
            # Already on, turn off first
            self.log("Amplifier is on, turning off first")
            self.controller.turn_off()
            if not self.wait_for_status_change('power', False, POWER_OFF_DELAY):
                return False, "Could not turn off amplifier to test power on"

        # Turn on
        self.log("Turning on amplifier")
        self.controller.turn_on()

        # Wait for power on
        if not self.wait_for_status_change('power', True, POWER_ON_DELAY):
            return False, "Amplifier did not turn on within timeout"

        return True, "Power on successful"

    def test_toggle_power(self) -> tuple[bool, str]:
        """Test toggling power state."""
        initial_status = self.controller.get_status()
        initial_power = initial_status['power']

        self.log(f"Toggling power from {'ON' if initial_power else 'STANDBY'}")
        self.controller.toggle_power()

        expected_power = not initial_power
        timeout = POWER_ON_DELAY if expected_power else POWER_OFF_DELAY

        if not self.wait_for_status_change('power', expected_power, timeout):
            return False, f"Power did not toggle to {'ON' if expected_power else 'STANDBY'}"

        # Toggle back
        self.log("Toggling power back")
        self.controller.toggle_power()
        timeout = POWER_ON_DELAY if initial_power else POWER_OFF_DELAY

        if not self.wait_for_status_change('power', initial_power, timeout):
            return False, f"Power did not toggle back to {'ON' if initial_power else 'STANDBY'}"

        return True, "Power toggle successful"

    # =========================================================================
    # TEST RUNNER
    # =========================================================================

    def run_all_tests(self, include_power_tests: bool = True):
        """
        Run all tests.

        Args:
            include_power_tests: Whether to run power on/off tests (slow)
        """
        if not self.setup():
            print("\nTest setup failed. Exiting.")
            return False

        try:
            # Status tests
            print("\n" + "-" * 60)
            print("STATUS TESTS")
            print("-" * 60)
            self.run_test(self.test_get_status, "Get status")
            self.run_test(self.test_status_volume_range, "Volume range validation")
            self.run_test(self.test_status_channels_available, "Channels available")

            # Ensure amplifier is on for other tests
            status = self.controller.get_status()
            if not status['power']:
                print("\n  Amplifier is in standby. Turning on for tests...")
                self.controller.turn_on()
                if not self.wait_for_status_change('power', True, POWER_ON_DELAY):
                    print("  ERROR: Could not turn on amplifier for testing")
                    return False
                print("  Amplifier is now on.")

            # Volume tests
            print("\n" + "-" * 60)
            print("VOLUME TESTS")
            print("-" * 60)
            self.run_test(self.test_set_volume, "Set volume")
            self.run_test(self.test_volume_minimum, "Minimum volume")
            self.run_test(self.test_volume_increment, "Volume increment")

            # Mute tests
            print("\n" + "-" * 60)
            print("MUTE TESTS")
            print("-" * 60)
            self.run_test(self.test_mute, "Mute")
            self.run_test(self.test_unmute, "Unmute")
            self.run_test(self.test_toggle_mute, "Toggle mute")

            # Channel tests
            print("\n" + "-" * 60)
            print("CHANNEL TESTS")
            print("-" * 60)
            self.run_test(self.test_channel_switch, "Channel switch")
            self.run_test(self.test_all_accessible_channels, "All accessible channels")

            # Power tests (slow)
            if include_power_tests:
                print("\n" + "-" * 60)
                print("POWER TESTS (this will take a while)")
                print("-" * 60)
                self.run_test(self.test_power_off, "Power off")
                self.run_test(self.test_power_on, "Power on")
                self.run_test(self.test_toggle_power, "Toggle power")
            else:
                print("\n" + "-" * 60)
                print("POWER TESTS (skipped with --quick)")
                print("-" * 60)

            return True

        finally:
            self.teardown()
            self.print_summary()

    def print_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total_time = sum(r.duration for r in self.results)

        print(f"\nTotal:  {len(self.results)} tests")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Time:   {total_time:.1f} seconds")

        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

        print("\n" + "=" * 60)
        if failed == 0:
            print("ALL TESTS PASSED")
        else:
            print(f"{failed} TEST(S) FAILED")
        print("=" * 60 + "\n")

        return failed == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Integration tests for Devialet Expert Pro control script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run all tests (including power tests)
  %(prog)s --quick            # Skip power tests (faster)
  %(prog)s --ip 192.168.1.10  # Specify amplifier IP
  %(prog)s -v                 # Verbose output
        """
    )

    parser.add_argument('--ip', help='IP address of amplifier (auto-discovers if not specified)')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Skip power tests (much faster)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    suite = DevialetTestSuite(ip=args.ip, verbose=args.verbose)
    success = suite.run_all_tests(include_power_tests=not args.quick)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
