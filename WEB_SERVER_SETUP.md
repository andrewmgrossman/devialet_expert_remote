# Devialet Expert Pro Web Server Setup

This guide will help you set up the web server to control your Devialet Expert Pro from your phone.

## Quick Start

### 1. Install Dependencies

```bash
# Install Flask and flask-cors
pip3 install -r requirements.txt
```

### 2. Start the Server

```bash
# Basic usage (auto-discover amp)
python3 devialet_web_server.py

# Or specify amp IP for faster startup
python3 devialet_web_server.py --ip 192.168.1.100
```

The server will start on `http://<server-ip-address>:5000` (accessible from any device on your network).

### 3. Access from Phone

1. Make sure your phone is on the same network as your server
2. Find your server's IP address:
   ```bash
   # On server, run:
   ifconfig | grep "inet " | grep -v 127.0.0.1
   ```
3. Open the browser on your phone
4. Go to: `http://<server-ip-address>:5000`
   - Example: `http://192.168.1.50:5000`

### 4. Add to iPhone Home Screen (Optional)

For a native app-like experience:

1. Open the web interface in Safari
2. Tap the Share button (square with arrow)
3. Scroll down and tap "Add to Home Screen"
4. Name it "Devialet" and tap "Add"

Now you have a dedicated icon on your home screen!

## Server Options

```bash
# Listen on all network interfaces (default)
python3 devialet_web_server.py --host 0.0.0.0

# Listen only on localhost (not accessible from other devices)
python3 devialet_web_server.py --host 127.0.0.1

# Use a different port
python3 devialet_web_server.py --port 8080

# Specify amp IP (skips auto-discovery)
python3 devialet_web_server.py --ip 192.168.1.100

# Enable debug mode (verbose logging)
python3 devialet_web_server.py --debug
```

## Running the Server on Startup (macOS)

To have the server start automatically when your Mac boots:

### Option 1: Using launchd (Recommended)

Create a launch agent file:

```bash
nano ~/Library/LaunchAgents/com.devialet.webserver.plist
```

Paste the following (adjust paths as needed):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.devialet.webserver</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/YOUR_USERNAME/claude/devialet_web_server.py</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>5000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/claude/devialet_server.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/claude/devialet_server_error.log</string>
</dict>
</plist>
```

Load the launch agent:

```bash
launchctl load ~/Library/LaunchAgents/com.devialet.webserver.plist
```

To stop the service:

```bash
launchctl unload ~/Library/LaunchAgents/com.devialet.webserver.plist
```

To restart the service:

```bash
launchctl unload ~/Library/LaunchAgents/com.devialet.webserver.plist
launchctl load ~/Library/LaunchAgents/com.devialet.webserver.plist
```

### Option 2: Using screen (Quick and simple)

Start the server in a detached screen session:

```bash
screen -dmS devialet python3 devialet_web_server.py
```

To reattach and view the server:

```bash
screen -r devialet
```

To detach: Press `Ctrl+A` then `D`

To stop the server:

```bash
screen -X -S devialet quit
```

## API Endpoints

The server provides a REST API that you can use for automation or scripting:

### Status

```bash
# Get current status
curl http://localhost:5000/api/status
```

Response:
```json
{
  "success": true,
  "data": {
    "device_name": "My Devialet",
    "ip": "192.168.1.100",
    "power": true,
    "volume_db": -20.0,
    "muted": false,
    "channel": 1,
    "channels": {
      "0": {"name": "Optical 1", "accessible": true},
      "1": {"name": "Phono", "accessible": true},
      ...
    }
  }
}
```

### Power Control

```bash
# Turn on
curl -X POST http://localhost:5000/api/power/on

# Turn off
curl -X POST http://localhost:5000/api/power/off

# Toggle
curl -X POST http://localhost:5000/api/power/toggle
```

### Volume Control

```bash
# Set volume to -20 dB
curl -X POST http://localhost:5000/api/volume \
  -H "Content-Type: application/json" \
  -d '{"db": -20.0}'
```

### Mute Control

```bash
# Mute
curl -X POST http://localhost:5000/api/mute

# Unmute
curl -X POST http://localhost:5000/api/unmute

# Toggle mute
curl -X POST http://localhost:5000/api/mute/toggle
```

### Channel Selection

```bash
# Switch to channel 1 (Phono)
curl -X POST http://localhost:5000/api/channel \
  -H "Content-Type: application/json" \
  -d '{"channel": 1}'
```

## Integration Examples

### Home Automation (curl)

Create shell scripts for common tasks:

```bash
#!/bin/bash
# turn_on_vinyl.sh
curl -X POST http://192.168.1.50:5000/api/power/on
sleep 2
curl -X POST http://192.168.1.50:5000/api/channel -H "Content-Type: application/json" -d '{"channel": 1}'
curl -X POST http://192.168.1.50:5000/api/volume -H "Content-Type: application/json" -d '{"db": -25}'
```

### iOS Shortcuts

1. Open the Shortcuts app on iPhone
2. Create a new shortcut
3. Add "Get Contents of URL" action
4. Configure:
   - URL: `http://<server-ip-address>:5000/api/power/on`
   - Method: POST
5. Name it "Turn On Amp" and add to home screen

### HomeKit (via Homebridge)

If you use Homebridge, you can create HTTP switch accessories:

```json
{
  "accessory": "HTTP-SWITCH",
  "name": "Devialet Power",
  "onUrl": "http://192.168.1.50:5000/api/power/on",
  "offUrl": "http://192.168.1.50:5000/api/power/off",
  "statusUrl": "http://192.168.1.50:5000/api/status"
}
```

## Troubleshooting

### Can't connect from iPhone

1. **Check firewall:**
   ```bash
   # Temporarily disable macOS firewall to test
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
   ```

2. **Verify server is listening on all interfaces:**
   - Make sure you're using `--host 0.0.0.0` (default)

3. **Check network connectivity:**
   ```bash
   # On iPhone, ping your server
   ping <server-ip-address>
   ```

4. **Verify port is accessible:**
   ```bash
   # On another device on network
   telnet <server-ip-address> 5000
   ```

### Server crashes or won't start

1. **Check Python version:**
   ```bash
   python3 --version  # Should be 3.7 or higher
   ```

2. **Verify dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Check logs:**
   ```bash
   python3 devialet_web_server.py --debug
   ```

### Amp not discovered

1. **Specify IP manually:**
   ```bash
   python3 devialet_web_server.py --ip 192.168.1.100
   ```

2. **Check network:**
   - Amp and server must be on same network
   - Check amp is powered on and connected to network

3. **Test with control script:**
   ```bash
   python3 devialet_expert_control.py status
   ```

### Slow response times

- Use `--ip` flag to skip auto-discovery
- The amp broadcasts status ~1x per second, so some delay is normal
- Web interface auto-refreshes every 2 seconds

## Security Notes

No authentication has been implemented. Use at your own risk.

## Files Reference

- `devialet_web_server.py` - Flask server backend
- `devialet_web_interface.html` - Mobile-friendly web UI
- `devialet_expert_control.py` - Core amp control library
- `requirements.txt` - Python dependencies

## Support

For issues or questions:
- Check the main documentation: `DEVIALET_EXPERT_PRO_API.md`
- Review the control script documentation: `devialet_expert_control.py --help`
- Test direct control: `python3 devialet_expert_control.py status`
