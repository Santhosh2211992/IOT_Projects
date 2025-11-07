import subprocess
import tempfile
import time
import os
import signal
import threading
import queue
import serial


def read_pppd_output(process, output_queue, stop_event):
    """Read pppd output in a background thread"""
    while not stop_event.is_set():
        try:
            line_bytes = process.stdout.readline()
            if not line_bytes:
                break
            
            try:
                line = line_bytes.decode('utf-8', errors='replace').strip()
            except:
                line = line_bytes.decode('latin-1', errors='replace').strip()
            
            if line:
                output_queue.put(line)
        except Exception as e:
            print(f"Error reading output: {e}")
            break


def send_at_command(ser, command, timeout=5):
    """Send AT command and read response"""
    ser.write(f"{command}\r\n".encode())
    time.sleep(0.2)
    
    start_time = time.time()
    response = ""
    
    while time.time() - start_time < timeout:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            response += chunk
            
            # Check if we got OK or ERROR
            if 'OK' in response or 'ERROR' in response:
                break
        time.sleep(0.1)
    
    return response.strip()


def initialize_modem(device="/dev/ttyS0", max_wait=60):
    """Initialize modem and wait for network registration"""
    print("[MODEM] Initializing modem...")
    
    try:
        ser = serial.Serial(device, 9600, timeout=2)
        time.sleep(1)
        
        # Basic initialization
        print("[MODEM] Resetting modem...")
        response = send_at_command(ser, "ATZ")
        print(f"  ATZ: {response}")
        
        print("[MODEM] Disabling echo...")
        response = send_at_command(ser, "ATE0")
        print(f"  ATE0: {response}")
        
        # Check signal quality
        print("[MODEM] Checking signal quality...")
        response = send_at_command(ser, "AT+CSQ")
        print(f"  AT+CSQ: {response}")
        
        # Parse signal quality
        if "+CSQ:" in response:
            try:
                csq = response.split("+CSQ:")[1].split(",")[0].strip()
                rssi = int(csq)
                if rssi == 99:
                    print("  ⚠️  No signal detected!")
                elif rssi < 10:
                    print(f"  ⚠️  Weak signal: {rssi}")
                else:
                    print(f"  ✓ Signal strength: {rssi} (good)")
            except:
                print("  Could not parse signal quality")
        
        # Check network registration
        print("[MODEM] Checking network registration...")
        registered = False
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = send_at_command(ser, "AT+CREG?")
            print(f"  AT+CREG?: {response}")
            
            # +CREG: 0,1 or +CREG: 0,5 means registered
            if "+CREG: 0,1" in response or "+CREG: 0,5" in response:
                print("  ✓ Registered on network!")
                registered = True
                break
            elif "+CREG: 0,2" in response:
                print("  ⏳ Searching for network... (waiting)")
            elif "+CREG: 0,0" in response:
                print("  ✗ Not registered, not searching")
            
            time.sleep(2)
        
        if not registered:
            print("[MODEM] ✗ Failed to register on network within timeout")
            ser.close()
            return False
        
        # Attach to GPRS
        print("[MODEM] Attaching to GPRS...")
        response = send_at_command(ser, "AT+CGATT=1", timeout=30)
        print(f"  AT+CGATT=1: {response}")
        
        # Verify GPRS attachment
        attached = False
        for i in range(10):
            response = send_at_command(ser, "AT+CGATT?")
            print(f"  AT+CGATT?: {response}")
            
            if "+CGATT: 1" in response:
                print("  ✓ Attached to GPRS!")
                attached = True
                break
            
            print(f"  ⏳ Waiting for GPRS attachment... ({i+1}/10)")
            time.sleep(2)
        
        if not attached:
            print("[MODEM] ✗ Failed to attach to GPRS")
            ser.close()
            return False
        
        # Check operator
        print("[MODEM] Checking operator...")
        response = send_at_command(ser, "AT+COPS?")
        print(f"  AT+COPS?: {response}")
        
        ser.close()
        print("[MODEM] ✓ Initialization complete!")
        time.sleep(1)
        return True
        
    except Exception as e:
        print(f"[MODEM] ✗ Initialization failed: {e}")
        return False


def start_ppp(apn: str, device="/dev/ttyS0", baud="9600"):
    print(f"\n[PPP] Starting connection with APN: {apn}")
    
    # Initialize modem first
    if not initialize_modem(device):
        print("[PPP] ✗ Modem initialization failed - cannot continue")
        return None, None, None

    # Create chat script
    chat_script = f"""
TIMEOUT 10
ABORT 'BUSY'
ABORT 'NO CARRIER'
ABORT 'ERROR'
ABORT 'NO DIALTONE'
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
    print(f"[PPP] Chat script created at {tmp_chat_path}")

    # Clean environment
    subprocess.run(["sudo", "pkill", "-f", "pppd"], stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(["sudo", "rm", "-f", f"/var/lock/LCK..{os.path.basename(device)}"], 
                  stderr=subprocess.DEVNULL)

    # Build PPP command
    ppp_cmd = [
        "sudo", "pppd",
        device, baud,
        "connect", f"chat -v -f {tmp_chat_path}",
        "noauth",
        "defaultroute",
        "replacedefaultroute",
        "usepeerdns",
        "persist",
        "maxfail", "3",
        "holdoff", "10",
        "nocrtscts",
        "local",
        "debug",
        "nodetach"
    ]

    print(f"[PPP] Starting pppd...")
    process = subprocess.Popen(ppp_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # Start background thread
    output_queue = queue.Queue()
    stop_event = threading.Event()
    reader_thread = threading.Thread(target=read_pppd_output, args=(process, output_queue, stop_event))
    reader_thread.daemon = True
    reader_thread.start()

    connected = False
    ip_assigned = False
    timeout = time.time() + 90

    # Monitor output
    while time.time() < timeout:
        try:
            line = output_queue.get(timeout=0.5)
            print(line)
            
            if "Connect: ppp0" in line:
                connected = True
                print("[PPP] ✓ Link established, negotiating IP...")
            
            if "local  IP address" in line or "remote IP address" in line:
                ip_assigned = True
                print("[PPP] ✓✓ IP negotiation successful!")
                break
            
            if "LCP: timeout" in line or "LCP terminated" in line:
                print("[PPP] ✗ LCP negotiation failed")
                break
                
            if "Connect script failed" in line:
                print("[PPP] ✗ Connection script failed")
                break
                
        except queue.Empty:
            if process.poll() is not None:
                print("[PPP] Process terminated")
                break
            continue

    if not connected or not ip_assigned:
        print("[PPP] ✗ Connection incomplete")
        stop_event.set()
        cleanup_ppp(process, tmp_chat_path)
        return None, None, None

    # Wait for network
    print("[PPP] Waiting for routes to be configured...")
    time.sleep(8)

    # Diagnostics
    print("\n" + "="*50)
    print("NETWORK DIAGNOSTICS")
    print("="*50)
    
    print("\n[INFO] Interface status:")
    result = subprocess.run(["ifconfig", "ppp0"], capture_output=True, text=True)
    print(result.stdout)
    
    print("\n[INFO] Routing table:")
    result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
    print(result.stdout)
    
    print("\n[INFO] DNS servers:")
    result = subprocess.run(["cat", "/etc/resolv.conf"], capture_output=True, text=True)
    print(result.stdout)

    # Test connectivity
    print("\n" + "="*50)
    print("CONNECTIVITY TESTS")
    print("="*50)
    
    print("\n[TEST 1] Ping 8.8.8.8 via ppp0...")
    ping_result = subprocess.run(["ping", "-I", "ppp0", "-c", "3", "-W", "5", "8.8.8.8"], 
                                capture_output=True, text=True)
    print(ping_result.stdout)

    if "bytes from" in ping_result.stdout or "0% packet loss" in ping_result.stdout:
        print("✅ Internet connectivity WORKING!")
        
        print("\n[TEST 2] DNS resolution test (google.com)...")
        dns_result = subprocess.run(["ping", "-I", "ppp0", "-c", "2", "-W", "5", "google.com"], 
                                   capture_output=True, text=True)
        if "bytes from" in dns_result.stdout:
            print("✅ DNS resolution WORKING!")
        else:
            print("⚠️  DNS not working (but raw IP works)")
    else:
        print("❌ No internet connectivity")

    print("="*50 + "\n")

    return process, tmp_chat_path, stop_event


def cleanup_ppp(process, tmp_chat_path, stop_event=None):
    print("\n[PPP] Shutting down connection...")
    
    if stop_event:
        stop_event.set()
    
    try:
        if process and process.poll() is None:
            process.send_signal(signal.SIGTERM)
            time.sleep(2)
            if process.poll() is None:
                process.kill()
    except Exception as e:
        print(f"Error: {e}")

    subprocess.run(["sudo", "poff", "-a"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-f", "pppd"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "rm", "-f", f"/var/lock/LCK..{os.path.basename('/dev/ttyS0')}"], 
                  stderr=subprocess.DEVNULL)

    if tmp_chat_path and os.path.exists(tmp_chat_path):
        os.remove(tmp_chat_path)

    print("[PPP] Connection closed\n")


if __name__ == "__main__":
    print("="*50)
    print("GPRS/PPP CONNECTION MANAGER")
    print("="*50)
    
    APN = "airtelgprs.com"
    ppp_process, chat_file, stop_evt = start_ppp(APN)

    if ppp_process:
        print("✓ Connection established successfully!")
        print("  Keeping connection alive for 60 seconds...")
        print("  Press Ctrl+C to disconnect early\n")
        
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            print("\n\n[INFO] Interrupted by user")
        finally:
            cleanup_ppp(ppp_process, chat_file, stop_evt)
            print("✓ Disconnected successfully")
    else:
        print("\n❌ Failed to establish connection")
        print("\nTroubleshooting tips:")
        print("  1. Check SIM card has active data plan")
        print("  2. Verify antenna is connected")
        print("  3. Check signal strength in area")
        print("  4. Confirm APN settings with carrier")