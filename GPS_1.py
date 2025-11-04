import serial
import pynmea2
from datetime import datetime, UTC
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import pytz

def get_location(lat, lon):
    geolocator = Nominatim(user_agent="gps_locator")
    try:
        location = geolocator.reverse((lat, lon), language='en', timeout=10)
        if location:
            return location.address
        else:
            return "No location found."
    except GeocoderTimedOut:
        # Retry once after a short delay
        import time
        time.sleep(2)
        try:
            location = geolocator.reverse((lat, lon), language='en', timeout=10)
            return location.address if location else "No location found (after retry)."
        except:
            return "Service still timed out (check internet or API)."

def main():
    # Open GPS serial port
    port = serial.Serial("/dev/serial0", baudrate=9600, timeout=1)
    print("Reading GPS data... (Ctrl+C to stop)\n")

    while True:
        try:
            line = port.readline().decode('ascii', errors='replace').strip()
            if not line:
                continue

            # Print raw line for debugging
            print(f"line: {line}")

            # Match both GN and GP types
            if line.startswith(('$GNGGA', '$GPGGA', '$GNRMC', '$GPRMC')):
                msg = pynmea2.parse(line)

                latitude = getattr(msg, "latitude", None)
                longitude = getattr(msg, "longitude", None)
                altitude = getattr(msg, "altitude", None)
                speed = getattr(msg, "spd_over_grnd", None)

                # Convert knots to km/h if speed available
                speed_kmh = float(speed) * 1.852 if speed else 0.0

                utc_time_now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                india = pytz.timezone("Asia/Kolkata")
                india_time_now = datetime.now(india).strftime("%Y-%m-%d %H:%M:%S")
                print(
                    f"📍 Time: {india_time_now}\n"
                    f"   Lat: {latitude:.6f}, Lon: {longitude:.6f}\n"
                    f"   Altitude: {altitude if altitude else 0} m\n"
                    f"   Speed: {speed_kmh:.2f} km/h\n"
                )
                location = get_location(latitude, longitude)

                if location:
                    print("Address:", location)
                else:
                    print("No location found.")

        except pynmea2.ParseError:
            continue
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"⚠️ Error: {e}")

    port.close()

if __name__ == "__main__":
    main()
