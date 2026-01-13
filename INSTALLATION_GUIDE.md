# Devialet Web Server Installation Guide
## M1 Mac Mini - macOS 12.1

This guide will walk you through installing and configuring the Devialet web server to run automatically on your Mac Mini.

---

## Prerequisites

- M1 Mac Mini running macOS 12.1
- Command Line Developer Tools installed
- Terminal access
- Your Mac Mini and Devialet amp on the same network

---

## Step 1: Verify Python Installation

macOS 12.1 comes with Python 3, but let's verify:

```bash
python3 --version
```

You should see something like `Python 3.8.9` or higher. If not, install Python 3:

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3
brew install python3
```

---

## Step 2: Create Installation Directory

Create a dedicated directory for the Devialet server:

```bash
# Create directory
sudo mkdir -p /usr/local/devialet

# Take ownership of the directory
sudo chown -R $USER:staff /usr/local/devialet

# Navigate to it
cd /usr/local/devialet
```

---

## Step 3: Copy Required Files

Copy the necessary files from your current directory to the installation directory:

```bash
# Assuming you're currently in the directory with the scripts
# Copy the main files
cp ~/claude/devialet_expert_control.py /usr/local/devialet/
cp ~/claude/devialet_web_server.py /usr/local/devialet/
cp ~/claude/devialet_web_interface.html /usr/local/devialet/
cp ~/claude/requirements.txt /usr/local/devialet/

# Optional: Copy documentation
cp ~/claude/DEVIALET_EXPERT_PRO_API.md /usr/local/devialet/
cp ~/claude/README.md /usr/local/devialet/

# Verify files are copied
ls -la /usr/local/devialet/
```

You should see:
- `devialet_expert_control.py`
- `devialet_web_server.py`
- `devialet_web_interface.html`
- `requirements.txt`

---

## Step 4: Install Python Dependencies

Install the required Python packages:

```bash
# Navigate to installation directory
cd /usr/local/devialet

# Install pip if not already installed
python3 -m ensurepip --upgrade

# Install required packages
python3 -m pip install -r requirements.txt
```

This will install:
- Flask (web framework)
- flask-cors (CORS support)

Verify installation:

```bash
python3 -m pip list | grep -i flask
```

You should see:
```
Flask         3.x.x
flask-cors    4.x.x
```

---

## Step 5: Find Your Amp's IP Address (Optional)

You can let the server auto-discover your amp, or specify the IP for faster startup:

```bash
# Test discovery
cd /usr/local/devialet
python3 devialet_expert_control.py status
```

Note the IP address shown (e.g., `10.0.7.28`). You'll use this in the next step.

---

## Step 6: Create launchd Service

Create a launch daemon that will:
- Start the server automatically at boot
- Restart the server if it crashes
- Run in the background

Create the plist file:

```bash
sudo nano /Library/LaunchDaemons/com.devialet.webserver.plist
```

Paste the following content (replace `YOUR_USERNAME` with your actual username and `YOUR_AMP_IP` with your amp's IP, or remove the `--ip` lines for auto-discovery):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.devialet.webserver</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/usr/local/devialet/devialet_web_server.py</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>5000</string>
        <string>--ip</string>
        <string>10.0.7.28</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/usr/local/devialet</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>

    <key>StandardOutPath</key>
    <string>/usr/local/devialet/server.log</string>

    <key>StandardErrorPath</key>
    <string>/usr/local/devialet/server_error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
```

**Key features explained:**
- `RunAtLoad`: Starts automatically at boot
- `KeepAlive`: Restarts if crashes (but not if it exits cleanly)
- `ThrottleInterval`: Waits 10 seconds before restarting (prevents rapid restart loops)
- Logs are written to `/usr/local/devialet/server.log` and `server_error.log`

Save and exit (Ctrl+O, Enter, Ctrl+X).

---

## Step 7: Set Permissions

Set correct permissions for the plist file:

```bash
sudo chown root:wheel /Library/LaunchDaemons/com.devialet.webserver.plist
sudo chmod 644 /Library/LaunchDaemons/com.devialet.webserver.plist
```

---

## Step 8: Load and Start the Service

Load the service into launchd:

```bash
# Load the service
sudo launchctl load /Library/LaunchDaemons/com.devialet.webserver.plist

# Start the service
sudo launchctl start com.devialet.webserver
```

---

## Step 9: Verify Installation

### Check if the service is running:

```bash
# Check service status
sudo launchctl list | grep devialet
```

You should see something like:
```
-    0    com.devialet.webserver
```

The `0` means it's running successfully.

### Check the logs:

```bash
# View server output
tail -f /usr/local/devialet/server.log

# In another terminal, check for errors
tail -f /usr/local/devialet/server_error.log
```

Press Ctrl+C to exit the log view.

### Test the web interface:

1. **From the Mac Mini:**
   ```bash
   open http://localhost:5000
   ```

2. **From your iPhone:**
   - Find your Mac Mini's IP address:
     ```bash
     ifconfig en0 | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}'
     ```
   - Open Safari on iPhone
   - Go to: `http://<mac-mini-ip>:5000`
   - Example: `http://192.168.1.50:5000`

---

## Managing the Service

### Stop the service:
```bash
sudo launchctl stop com.devialet.webserver
```

### Restart the service:
```bash
sudo launchctl stop com.devialet.webserver
sudo launchctl start com.devialet.webserver
```

### Unload the service (disable auto-start):
```bash
sudo launchctl unload /Library/LaunchDaemons/com.devialet.webserver.plist
```

### Reload the service (after editing the plist):
```bash
sudo launchctl unload /Library/LaunchDaemons/com.devialet.webserver.plist
sudo launchctl load /Library/LaunchDaemons/com.devialet.webserver.plist
```

---

## Updating the Server

If you update the Python scripts:

```bash
# Copy new files
cp ~/claude/devialet_web_server.py /usr/local/devialet/
cp ~/claude/devialet_web_interface.html /usr/local/devialet/
cp ~/claude/devialet_expert_control.py /usr/local/devialet/

# Restart the service
sudo launchctl stop com.devialet.webserver
sudo launchctl start com.devialet.webserver
```

---

## Troubleshooting

### Server won't start

1. **Check logs for errors:**
   ```bash
   cat /usr/local/devialet/server_error.log
   ```

2. **Test manual startup:**
   ```bash
   cd /usr/local/devialet
   python3 devialet_web_server.py --ip 10.0.7.28
   ```

   Press Ctrl+C to stop. If this works, the issue is with the launchd configuration.

3. **Check file permissions:**
   ```bash
   ls -la /usr/local/devialet/
   ```

   Files should be readable by your user.

### Port already in use

If port 5000 is in use:

1. Edit the plist to use a different port:
   ```bash
   sudo nano /Library/LaunchDaemons/com.devialet.webserver.plist
   ```

   Change `<string>5000</string>` to `<string>8080</string>` (or another port)

2. Reload the service:
   ```bash
   sudo launchctl unload /Library/LaunchDaemons/com.devialet.webserver.plist
   sudo launchctl load /Library/LaunchDaemons/com.devialet.webserver.plist
   ```

### Can't connect from iPhone

1. **Check firewall settings:**
   ```bash
   # Temporarily disable firewall to test
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
   ```

   Test connection, then re-enable:
   ```bash
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
   ```

2. **Add firewall exception permanently:**
   - System Preferences → Security & Privacy → Firewall → Firewall Options
   - Click "+" and add Python
   - Or add incoming connections on port 5000

3. **Verify Mac Mini IP:**
   ```bash
   ifconfig en0 | grep "inet "
   ```

   Use this IP on your iPhone.

### Service keeps restarting

Check logs to see why:
```bash
tail -50 /usr/local/devialet/server_error.log
```

Common issues:
- Python module not installed
- Amp not reachable on network
- Port already in use

### View real-time service status

```bash
# Watch service status (updates every 2 seconds)
watch -n 2 'sudo launchctl list | grep devialet'

# Monitor logs in real-time
tail -f /usr/local/devialet/server.log
```

---

## Configuration Options

### Change amp IP address

Edit the plist file:
```bash
sudo nano /Library/LaunchDaemons/com.devialet.webserver.plist
```

Find the `--ip` argument and change the IP address, then reload:
```bash
sudo launchctl unload /Library/LaunchDaemons/com.devialet.webserver.plist
sudo launchctl load /Library/LaunchDaemons/com.devialet.webserver.plist
```

### Use auto-discovery instead of fixed IP

Remove the IP arguments from the plist:

Delete these lines:
```xml
        <string>--ip</string>
        <string>10.0.7.28</string>
```

Then reload the service.

### Change server port

Edit the plist file and change:
```xml
        <string>--port</string>
        <string>5000</string>
```

To your desired port, then reload the service.

---

## Security Considerations

### Local network only

The server is configured to listen on `0.0.0.0`, making it accessible from any device on your network. This is safe if:
- Your Mac Mini is on a trusted home network
- Your router is secured with WPA2/WPA3
- The Mac Mini is not exposed to the internet

### Restrict to localhost only

To only allow connections from the Mac Mini itself:

Edit the plist and change:
```xml
        <string>--host</string>
        <string>0.0.0.0</string>
```

To:
```xml
        <string>--host</string>
        <string>127.0.0.1</string>
```

Then reload the service. (You won't be able to access from iPhone with this setting)

---

## Advanced: Using a Custom Domain

If you want to access the server via a custom domain name instead of IP:

1. **Edit your Mac's hosts file:**
   ```bash
   sudo nano /etc/hosts
   ```

   Add:
   ```
   <mac-mini-ip>    devialet.local
   ```

2. **Access from any device on your network:**
   - Visit: `http://devialet.local:5000`

Note: This only works if your router supports mDNS/Bonjour, or you add the same hosts entry on each device.

---

## Uninstallation

To completely remove the Devialet server:

```bash
# Stop and unload the service
sudo launchctl stop com.devialet.webserver
sudo launchctl unload /Library/LaunchDaemons/com.devialet.webserver.plist

# Remove the plist file
sudo rm /Library/LaunchDaemons/com.devialet.webserver.plist

# Remove the installation directory
sudo rm -rf /usr/local/devialet

# Optional: Uninstall Python packages
python3 -m pip uninstall flask flask-cors
```

---

## Summary

After following this guide, you will have:

✅ Python 3 and required packages installed
✅ Devialet server installed in `/usr/local/devialet/`
✅ Server running automatically at boot
✅ Server auto-restarts if it crashes
✅ Logs available for troubleshooting
✅ Web interface accessible from iPhone and other devices

**Quick Reference:**
- **Server files:** `/usr/local/devialet/`
- **Service config:** `/Library/LaunchDaemons/com.devialet.webserver.plist`
- **Logs:** `/usr/local/devialet/server.log` and `server_error.log`
- **Web interface:** `http://<mac-mini-ip>:5000`

---

## Getting Help

If you encounter issues:

1. Check the logs:
   ```bash
   tail -50 /usr/local/devialet/server_error.log
   ```

2. Test manual startup:
   ```bash
   cd /usr/local/devialet
   python3 devialet_web_server.py --ip <your-amp-ip>
   ```

3. Verify amp connectivity:
   ```bash
   python3 devialet_expert_control.py status
   ```

For more details, see:
- `README.md` - Overview and usage
- `DEVIALET_EXPERT_PRO_API.md` - Protocol documentation
- `WEB_SERVER_SETUP.md` - Web server details
