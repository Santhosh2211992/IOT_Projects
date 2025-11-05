import RPi.GPIO as GPIO
import time

# GPIO setup
SENSOR_PIN = 22  # Connect sensor output here (after voltage divider)

GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN)

print("Proximity sensor test started (Press Ctrl+C to exit)...")

try:
    while True:
        state = GPIO.input(SENSOR_PIN)
        if state == GPIO.HIGH:
            print("Metal detected! ⚙️")
        else:
            print("No metal detected.")
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nExiting program.")
finally:
    GPIO.cleanup()
