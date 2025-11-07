#!/usr/bin/env python3

import subprocess
import tempfile
import time
import os
import serial
import sys
import signal
from datetime import datetime
import re

ppp_process = None
tmp_chat_path = None
last_signal_info = (None, "Unknown", "?")  # Cache signal info from initialization

def signal_handler(sig, frame):
    print("\n[SIGNAL] Shutting down...")
    cleanup_connection()
    sys.exit(0)

def send_at_command(ser, command, timeout=5):
    ser.write(f"{command}\r\n".encode())
    time.sleep(0.2)
    
    start_time = time.time()
    response = ""
    
    while time.time() - start_time < timeout:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            response += chunk
            if 'OK' in response or 'ERROR' in response:
                break
        time.sleep(0.1)
    
    return response.strip()

def get_signal_strength_at_init(device="/dev/ttyS0"):
    """Get signal strength during initialization (before PPP starts)"""
    try:
        ser = serial.Serial(device, 9600, timeout=1)
        response = send_at_command(ser, "AT+CSQ")
        ser.close()
        
        if "+CSQ:" in response:
            rssi = int(response.split("+CSQ:")[1].split(",")[0].strip())
            if rssi == 99:
                return 99, "No Signal", "❌"
            elif rssi < 10:
                return rssi, "Poor", "⚠️"
            elif rssi < 15:
                return rssi, "Fair", "⚙️"
            elif rssi < 20:
                return rssi, "Good", "✓"
            else:
                return rssi, "Excellent", "✓✓"
        return None, "Unknown", "?"
    except Exception as e:
        return None, f"Error: {e}", "?"

def get_ppp_stats_from_log():
    """Parse pppd log for connection stats"""
    try:
        with open("/var/log/pppd.log", "r") as f:
            lines = f.readlines()
            
        # Look for recent connection info
        for line in reversed(lines[-50:]):  # Check last 50 lines
            if "local  IP address" in line:
                # Extract IP from log
                pass
            if "remote IP address" in line:
                pass
        
        return {}
    except:
        return {}

def get_connection_stats():
    """Get PPP connection statistics from ifconfig"""
    try:
        result = subprocess.run(["ifconfig", "ppp0"], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            output = result.stdout
            
            # Extract IP address
            ip_addr = "Unknown"
            if "inet " in output:
                ip_line = [line for line in output.split('\n') if 'inet ' in line][0]
                ip_addr = ip_line.split()[1]
            
            # Extract RX/TX bytes
            rx_bytes = 0
            tx_bytes = 0
            
            # Parse RX/TX - handle different ifconfig formats
            for line in output.split('\n'):
                if "RX packets" in line or "RX:" in line:
                    # Format: RX packets 123  bytes 456 (1.2 MB)
                    match = re.search(r'bytes[:\s]+(\d+)', line)
                    if match:
                        rx_bytes = int(match.group(1))
                
                if "TX packets" in line or "TX:" in line:
                    # Format: TX packets 123  bytes 456 (1.2 KB)
                    match = re.search(r'bytes[:\s]+(\d+)', line)
                    if match:
                        tx_bytes = int(match.group(1))
            
            return True, ip_addr, rx_bytes, tx_bytes
        else:
            return False, None, 0, 0
            
    except Exception as e:
        return False, None, 0, 0

def get_uptime():
    """Get PPP connection uptime"""
    try:
        result = subprocess.run(["ps", "-eo", "pid,etime,cmd"], 
                              capture_output=True, text=True)
        
        for line in result.stdout.split('\n'):
            if 'pppd' in line and '/dev/ttyS0' in line:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]  # Return elapsed time
        
        return "Unknown"
    except:
        return "Unknown"

def format_bytes(bytes_val):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def print_status_header():
    """Print status table header"""
    print("\n" + "="*120)
    print(f"{'Time':<10} | {'Uptime':<12} | {'Signal (Init)':<20} | {'IP Address':<16} | {'RX Data':<15} | {'TX Data':<15} | {'Ping':<6}")
    print("="*120)

def print_status_line(timestamp, uptime, signal_info, ip_addr, rx_bytes, tx_bytes, ping_ok, ping_ms):
    """Print a single status line"""
    rssi, quality, icon = signal_info
    
    signal_str = f"{icon} {rssi if rssi is not None else '?'} ({quality})"
    
    ping_str = f"{'🟢' if ping_ok else '🔴'} {ping_ms if ping_ms else 'N/A'}"
    
    print(f"{timestamp:<10} | {uptime:<12} | {signal_str:<20} | {ip_addr:<16} | {format_bytes(rx_bytes):<15} | {format_bytes(tx_bytes):<15} | {ping_str:<6}")

def test_ping_with_latency():
    """Test ping and return latency"""
    try:
        result = subprocess.run(["ping", "-I", "ppp0", "-c", "1", "-W", "3", "8.8.8.8"],
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            # Extract latency from output
            # Example: "time=45.2 ms"
            match = re.search(r'time=([\d.]+)\s*ms', result.stdout)
            if match:
                latency = f"{float(match.group(1)):.1f}ms"
                return True, latency
            return True, "?"
        else:
            return False, None
    except:
        return False, None

def initialize_modem(device="/dev/ttyS0", max_wait=60):
    global last_signal_info
    
    print("[MODEM] Initializing...")
    
    try:
        ser = serial.Serial(device, 9600, timeout=2)
        time.sleep(1)
        
        send_at_command(ser, "ATZ")
        send_at_command(ser, "ATE0")
        
        # Get initial signal strength
        print("[MODEM] Checking signal strength...")
        last_signal_info = get_signal_strength_at_init(device)
        rssi, quality, icon = last_signal_info
        print(f"[MODEM] Signal: {icon} {rssi} ({quality})")
        
        print("[MODEM] Waiting for network registration...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = send_at_command(ser, "AT+CREG?")
            
            if "+CREG: 0,1" in response or "+CREG: 0,5" in response:
                print("[MODEM] ✓ Registered on network")
                break
            
            print(f"[MODEM] Searching for network...")
            time.sleep(5)
        else:
            print("[MODEM] ✗ Network registration timeout")
            ser.close()
            return False
        
        # Get operator info
        response = send_at_command(ser, "AT+COPS?")
        if "+COPS:" in response:
            try:
                parts = response.split('"')
                if len(parts) >= 2:
                    print(f"[MODEM] Operator: {parts[1]}")
            except:
                pass
        
        print("[MODEM] Attaching to GPRS...")
        send_at_command(ser, "AT+CGATT=1", timeout=30)
        
        for i in range(10):
            response = send_at_command(ser, "AT+CGATT?")
            if "+CGATT: 1" in response:
                print("[MODEM] ✓ Attached to GPRS")
                ser.close()
                return True
            time.sleep(2)
        
        print("[MODEM] ✗ GPRS attachment failed")
        ser.close()
        return False
        
    except Exception as e:
        print(f"[MODEM] ✗ Error: {e}")
        return False

def start_persistent_connection(apn="airtelgprs.com", device="/dev/ttyS0"):
    global ppp_process, tmp_chat_path
    
    print(f"[PPP] Starting persistent connection with APN: {apn}")
    
    if not initialize_modem(device):
        return False
    
    chat_script = f"""
TIMEOUT 10
ABORT 'BUSY'
ABORT 'NO CARRIER'
ABORT 'ERROR'
'' AT
OK ATZ
OK ATE0
OK 'AT+CGDCONT=1,"IP","{apn}"'
OK ATD*99#
TIMEOUT 30
CONNECT ''
"""
    
    tmp_chat = tempfile.NamedTemporaryFile(mode="w", delete=False)
    tmp_chat.write(chat_script)
    tmp_chat.close()
    tmp_chat_path = tmp_chat.name
    
    subprocess.run(["sudo", "pkill", "-f", "pppd"], stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(["sudo", "rm", "-f", f"/var/lock/LCK..{os.path.basename(device)}"], 
                  stderr=subprocess.DEVNULL)
    
    ppp_cmd = [
        "sudo", "pppd",
        device, "9600",
        "connect", f"chat -v -f {tmp_chat_path}",
        "noauth",
        "defaultroute",
        "replacedefaultroute",
        "usepeerdns",
        "persist",
        "maxfail", "0",
        "holdoff", "30",
        "nocrtscts",
        "local",
        "logfile", "/var/log/pppd.log"
    ]
    
    print("[PPP] Starting pppd daemon...")
    process = subprocess.Popen(ppp_cmd, 
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    
    ppp_process = process
    
    print("[PPP] Waiting for connection to establish...")
    for i in range(30):
        time.sleep(2)
        
        result = subprocess.run(["ifconfig", "ppp0"], 
                              capture_output=True, text=True)
        
        if result.returncode == 0 and "inet " in result.stdout:
            print("[PPP] ✓ Connection established!")
            
            ping_ok, latency = test_ping_with_latency()
            if ping_ok:
                print(f"[PPP] ✓ Internet connectivity verified! (latency: {latency})")
            else:
                print("[PPP] ⚠️  Connection up but verifying internet...")
            
            return True
        
        print(f"[PPP] Waiting... ({i+1}/30)")
    
    print("[PPP] ✗ Connection timeout")
    return False

def cleanup_connection():
    global tmp_chat_path
    
    print("\n[PPP] Cleaning up...")
    subprocess.run(["sudo", "poff", "-a"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-f", "pppd"], stderr=subprocess.DEVNULL)
    
    if tmp_chat_path and os.path.exists(tmp_chat_path):
        os.remove(tmp_chat_path)
    
    print("[PPP] Cleanup complete")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    APN = "airtelgprs.com"
    DEVICE = "/dev/ttyS0"
    
    if start_persistent_connection(APN, DEVICE):
        print("\n" + "="*120)
        print("✓ GPRS CONNECTION ACTIVE - MONITORING MODE")
        print("="*120)
        print("  - Connection will auto-reconnect if dropped")
        print("  - Status updates every 30 seconds")
        print("  - Signal strength shown from initialization (cannot query during PPP)")
        print("  - Logs: /var/log/pppd.log")
        print("  - Press Ctrl+C to stop")
        print("="*120)
        
        print_status_header()
        
        try:
            update_interval = 30  # Update every 30 seconds
            line_counter = 0
            
            while True:
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                # Get connection uptime
                uptime = get_uptime()
                
                # Get connection stats
                ppp_up, ip_addr, rx_bytes, tx_bytes = get_connection_stats()
                
                if not ppp_up:
                    ip_addr = "Disconnected"
                
                # Test connectivity with latency
                ping_ok, ping_ms = test_ping_with_latency()
                
                # Print status line (using cached signal info from init)
                print_status_line(
                    timestamp,
                    uptime,
                    last_signal_info,  # Cached from initialization
                    ip_addr if ip_addr else "N/A",
                    rx_bytes,
                    tx_bytes,
                    ping_ok,
                    ping_ms
                )
                
                # Re-print header every 20 lines for readability
                line_counter += 1
                if line_counter >= 20:
                    print_status_header()
                    line_counter = 0
                
                time.sleep(update_interval)
        
        except KeyboardInterrupt:
            print("\n[INFO] Shutting down...")
            cleanup_connection()
    else:
        print("\n[FAILED] Could not establish connection")
        cleanup_connection()
        sys.exit(1)
# ```

# ## Key Changes:

# 1. **Signal strength captured at initialization** - Stored before PPP starts
# 2. **No AT commands during PPP** - Avoids "device busy" error
# 3. **Added connection uptime** - Shows how long pppd has been running
# 4. **Added ping latency** - Shows response time in milliseconds
# 5. **Cleaner output** - More readable table format

# ## Sample Output:
# ```
# ========================================================================================================================
# Time       | Uptime       | Signal (Init)        | IP Address       | RX Data         | TX Data         | Ping  
# ========================================================================================================================
# 15:45:23   | 00:03:45     | ✓ 18 (Good)         | 100.91.2.107     | 5.74 KB         | 5.82 KB         | 🟢 45.2ms
# 15:45:53   | 00:04:15     | ✓ 18 (Good)         | 100.91.2.107     | 8.92 KB         | 9.15 KB         | 🟢 42.8ms
# 15:46:23   | 00:04:45     | ✓ 18 (Good)         | 100.91.2.107     | 12.45 KB        | 13.02 KB        | 🟢 48.1ms

#=======================
#  System Service Setup
#=======================
# Make it executable:
# bashchmod +x /home/santhosh-rpi1/gprs_connection.py
# Create systemd service:
# bashsudo nano /etc/systemd/system/gprs-connection.service
# ini[Unit]
# Description=GPRS/PPP Internet Connection
# After=network.target
# Wants=network.target

# [Service]
# Type=simple
# User=root
# ExecStart=/usr/bin/python3 /home/santhosh-rpi1/gprs_connection.py
# Restart=always
# RestartSec=30
# StandardOutput=journal
# StandardError=journal

# [Install]
# WantedBy=multi-user.target
# Enable and start:
# bash# Reload systemd
# sudo systemctl daemon-reload

# # Enable on boot
# sudo systemctl enable gprs-connection.service

# # Start now
# sudo systemctl start gprs-connection.service

# # Check status
# sudo systemctl status gprs-connection.service

# # View logs
# sudo journalctl -u gprs-connection.service -f