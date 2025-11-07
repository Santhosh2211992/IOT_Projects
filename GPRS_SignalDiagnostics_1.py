import serial
import time

def diagnose_sim800l(device="/dev/ttyS0"):
    print("="*60)
    print("SIM800L SIGNAL DIAGNOSTICS")
    print("="*60)
    
    try:
        ser = serial.Serial(device, 9600, timeout=3)
        time.sleep(2)
        
        def send_cmd(cmd, delay=1):
            ser.write(f"{cmd}\r\n".encode())
            time.sleep(delay)
            response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            return response
        
        # 1. Basic check
        print("\n[1] Module Response Test")
        response = send_cmd("AT")
        print(f"    AT: {response.strip()}")
        if "OK" not in response:
            print("    ❌ Module not responding!")
            return
        print("    ✓ Module responding")
        
        # 2. Signal Quality (multiple readings)
        print("\n[2] Signal Quality Test (5 readings)")
        signals = []
        for i in range(5):
            response = send_cmd("AT+CSQ", 0.5)
            print(f"    Reading {i+1}: {response.strip()}")
            try:
                if "+CSQ:" in response:
                    rssi = int(response.split("+CSQ:")[1].split(",")[0].strip())
                    signals.append(rssi)
            except:
                pass
            time.sleep(1)
        
        if signals:
            avg_signal = sum(signals) / len(signals)
            print(f"\n    Average RSSI: {avg_signal:.1f}")
            if avg_signal == 99:
                print("    ❌ NO SIGNAL - Check antenna and power!")
            elif avg_signal < 10:
                print("    ⚠️  WEAK SIGNAL - Improve antenna/power")
            elif avg_signal < 15:
                print("    ⚙️  MARGINAL - May work but unstable")
            elif avg_signal < 20:
                print("    ✓ GOOD SIGNAL")
            else:
                print("    ✓✓ EXCELLENT SIGNAL")
        
        # 3. Network Registration
        print("\n[3] Network Registration")
        response = send_cmd("AT+CREG?", 1)
        print(f"    AT+CREG?: {response.strip()}")
        if "+CREG: 0,1" in response or "+CREG: 0,5" in response:
            print("    ✓ Registered on network")
        elif "+CREG: 0,2" in response:
            print("    ⏳ Searching for network...")
        else:
            print("    ❌ Not registered")
        
        # 4. Operator Info
        print("\n[4] Network Operator")
        response = send_cmd("AT+COPS?", 2)
        print(f"    AT+COPS?: {response.strip()}")
        
        # 5. GPRS Attachment
        print("\n[5] GPRS Attachment")
        response = send_cmd("AT+CGATT?", 1)
        print(f"    AT+CGATT?: {response.strip()}")
        if "+CGATT: 1" in response:
            print("    ✓ Attached to GPRS")
        else:
            print("    ❌ Not attached to GPRS")
        
        # 6. SIM Card
        print("\n[6] SIM Card Status")
        response = send_cmd("AT+CPIN?", 1)
        print(f"    AT+CPIN?: {response.strip()}")
        if "+CPIN: READY" in response:
            print("    ✓ SIM card ready")
        else:
            print("    ❌ SIM card issue")
        
        # 7. Power supply voltage (if supported)
        print("\n[7] Battery/Power Status")
        response = send_cmd("AT+CBC", 1)
        print(f"    AT+CBC: {response.strip()}")
        
        ser.close()
        
        # Recommendations
        print("\n" + "="*60)
        print("RECOMMENDATIONS:")
        print("="*60)
        
        if not signals or sum(signals) / len(signals) < 10:
            print("⚠️  CRITICAL: Signal too weak!")
            print("   → Use 18650 battery (3.7V) or proper 5V→3.7V buck converter")
            print("   → Add 100µF capacitor across VCC/GND")
            print("   → Check antenna is properly connected")
            print("   → Move closer to window")
        elif sum(signals) / len(signals) < 15:
            print("⚠️  Signal marginal - may be unstable")
            print("   → Improve power supply (add capacitors)")
            print("   → Reposition antenna vertically")
        else:
            print("✓ Signal looks good!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    diagnose_sim800l()

## 📋 Quick Checklist:

# Power:
# [ ] Using 3.7V-4.2V power (battery or buck converter)
# [ ] 100µF capacitor added near module
# [ ] Wires are thick and short

# Antenna:
# [ ] External antenna connected (not using PCB antenna)
# [ ] Connector clicked in properly
# [ ] Antenna is GSM 900/1800 MHz compatible
# [ ] Positioned vertically, away from metal

# Environment:
# [ ] Near window or outside
# [ ] Not in metal enclosure
# [ ] Away from interference sources

# Module:
# [ ] SIM card inserted correctly
# [ ] SIM has active data plan
# [ ] Module not overheating