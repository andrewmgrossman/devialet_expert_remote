#!/usr/bin/env python3
"""
Flask web server for controlling Devialet Expert Pro amplifier.

Provides:
- REST API for programmatic control
- Mobile-friendly web interface for iPhone/browser control

Usage:
    python3 devialet_web_server.py [--host HOST] [--port PORT] [--ip AMP_IP]

Examples:
    python3 devialet_web_server.py
    python3 devialet_web_server.py --port 8080
    python3 devialet_web_server.py --host 0.0.0.0 --port 5000
    python3 devialet_web_server.py --ip 192.168.1.100
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import argparse
import logging
import sys
from pathlib import Path
from devialet_expert_control import DevialetExpertController

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global controller instance
controller = None
amp_ip = None


def get_controller():
    """Get or create controller instance."""
    global controller
    if controller is None:
        controller = DevialetExpertController(ip=amp_ip)
    return controller


def controller_response(func):
    """Decorator to handle controller errors consistently."""
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    wrapper.__name__ = func.__name__
    return wrapper


# API Routes

@app.route('/api/status', methods=['GET'])
@controller_response
def get_status():
    """Get current amplifier status."""
    ctrl = get_controller()
    status = ctrl.get_status()

    # Add channel info (all channels are now accessible with dynamic mapping)
    for ch_num in status['channels'].keys():
        status['channels'][ch_num] = {
            'name': status['channels'][ch_num],
            'accessible': True
        }

    return status


@app.route('/api/power/on', methods=['POST'])
@controller_response
def power_on():
    """Turn amplifier on."""
    ctrl = get_controller()
    ctrl.turn_on()
    return {"message": "Power on command sent"}


@app.route('/api/power/off', methods=['POST'])
@controller_response
def power_off():
    """Turn amplifier off."""
    ctrl = get_controller()
    ctrl.turn_off()
    return {"message": "Power off command sent"}


@app.route('/api/power/toggle', methods=['POST'])
@controller_response
def power_toggle():
    """Toggle power state."""
    ctrl = get_controller()
    ctrl.toggle_power()
    return {"message": "Power toggle command sent"}


@app.route('/api/volume', methods=['POST'])
@controller_response
def set_volume():
    """
    Set volume level.

    Expects JSON body: {"db": -20.0}
    """
    data = request.get_json()
    if not data or 'db' not in data:
        return jsonify({"success": False, "error": "Missing 'db' parameter"}), 400

    db_value = float(data['db'])

    # Safety check
    if db_value < -96 or db_value > 0:
        return jsonify({"success": False, "error": "Volume must be between -96 and 0 dB"}), 400

    ctrl = get_controller()
    ctrl.set_volume(db_value)
    return {"message": f"Volume set to {db_value} dB"}


@app.route('/api/mute', methods=['POST'])
@controller_response
def mute():
    """Mute amplifier."""
    ctrl = get_controller()
    ctrl.mute()
    return {"message": "Mute command sent"}


@app.route('/api/unmute', methods=['POST'])
@controller_response
def unmute():
    """Unmute amplifier."""
    ctrl = get_controller()
    ctrl.unmute()
    return {"message": "Unmute command sent"}


@app.route('/api/mute/toggle', methods=['POST'])
@controller_response
def mute_toggle():
    """Toggle mute state."""
    ctrl = get_controller()
    ctrl.toggle_mute()
    return {"message": "Mute toggle command sent"}


@app.route('/api/channel', methods=['POST'])
@controller_response
def set_channel():
    """
    Set input channel.

    Expects JSON body: {"channel": 1}
    """
    data = request.get_json()
    if not data or 'channel' not in data:
        return jsonify({"success": False, "error": "Missing 'channel' parameter"}), 400

    channel = int(data['channel'])

    ctrl = get_controller()
    ctrl.set_channel(channel)
    return {"message": f"Channel set to {channel}"}


# Static file serving

@app.route('/')
def index():
    """Serve the main HTML interface."""
    return send_from_directory('.', 'devialet_web_interface.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files."""
    return send_from_directory('.', path)


# Health check

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "devialet-web-server"})


def main():
    """Main entry point."""
    global amp_ip

    parser = argparse.ArgumentParser(
        description='Web server for Devialet Expert Pro control',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Run on localhost:5000, auto-discover amp
  %(prog)s --host 0.0.0.0               # Listen on all interfaces
  %(prog)s --port 8080                  # Run on port 8080
  %(prog)s --ip 192.168.1.100           # Connect to specific amp IP

After starting, open http://localhost:5000 (or your Mac Mini's IP) on your iPhone.
        """
    )

    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind to (default: 0.0.0.0 for all interfaces)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to listen on (default: 5000)')
    parser.add_argument('--ip', help='IP address of amplifier (optional, will auto-discover)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')

    args = parser.parse_args()
    amp_ip = args.ip

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print(f"\n{'='*70}")
    print("Devialet Expert Pro Web Server")
    print(f"{'='*70}\n")
    print(f"Starting server on http://{args.host}:{args.port}")
    print(f"Amplifier IP: {amp_ip if amp_ip else 'Auto-discover'}")
    print("\nTo access from your iPhone:")
    print(f"  1. Make sure your iPhone is on the same network")
    print(f"  2. Open Safari and go to: http://<your-mac-mini-ip>:{args.port}")
    print(f"\nAPI Documentation:")
    print(f"  GET  /api/status          - Get current status")
    print(f"  POST /api/power/on        - Turn on")
    print(f"  POST /api/power/off       - Turn off")
    print(f"  POST /api/power/toggle    - Toggle power")
    print(f"  POST /api/volume          - Set volume (JSON: {{'db': -20}})")
    print(f"  POST /api/mute            - Mute")
    print(f"  POST /api/unmute          - Unmute")
    print(f"  POST /api/mute/toggle     - Toggle mute")
    print(f"  POST /api/channel         - Set channel (JSON: {{'channel': 1}})")
    print(f"\nPress Ctrl+C to stop\n")
    print(f"{'='*70}\n")

    try:
        app.run(host=args.host, port=args.port, debug=args.debug)
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"\nERROR: Port {args.port} is already in use.")
            print(f"Either stop the existing server or use a different port with --port")
            sys.exit(1)
        else:
            raise


if __name__ == '__main__':
    main()
