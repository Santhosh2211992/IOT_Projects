import serial
import time

# Open serial port (default UART on Pi)
ser = serial.Serial(
    port="/dev/serial0",  # or "/dev/ttyAMA0"
    baudrate=9600,
    timeout=1
)

def send_at(cmd, delay=1):
    """Send AT command and print response"""
    ser.write((cmd + "\r\n").encode())
    time.sleep(delay)
    while ser.in_waiting:
        print(ser.readline().decode(errors="ignore").strip())

try:
    print("Initializing SIM800L...")
    time.sleep(2)

    # Basic AT test
    print("\n--- AT Check ---")
    send_at("AT")

    # Check SIM card presence
    print("\n--- SIM Status ---")
    send_at("AT+CPIN?")

    # Check network registration
    print("\n--- Network Registration ---")
    send_at("AT+CREG?")

    # Check signal strength
    print("\n--- Signal Strength ---")
    send_at("AT+CSQ")

    # Read operator name (SIM/network info)
    print("\n--- Operator ---")
    send_at("AT+COPS?")

    # Get module info
    print("\n--- Device Info ---")
    send_at("ATI")
    time.sleep(3)

    # Optional: send SMS (uncomment and edit below)
    
    print("\n--- Sending SMS ---")
    send_at("AT+CMGF=1")  # Text mode
    send_at('AT+CMGS="+917760883563"')  # Replace with your number
    ser.write(b"Hello Again!\x1A")  # Ctrl+Z = 0x1A
    time.sleep(3)
    while ser.in_waiting:
        print(ser.readline().decode(errors="ignore").strip())
    

except KeyboardInterrupt:
    print("Exiting...")

finally:
    ser.close()
