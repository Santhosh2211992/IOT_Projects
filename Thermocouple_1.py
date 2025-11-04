import time
import spidev

spi = spidev.SpiDev()
spi.open(0, 0)  # Bus 0, CE0
spi.max_speed_hz = 500000

def read_max6675():
    raw = spi.xfer2([0x00, 0x00])
    value = ((raw[0] << 8) | raw[1]) >> 3
    if value & 0x1000:
        return None  # No thermocouple connected
    return value * 0.25  # Each bit = 0.25 °C

while True:
    temp = read_max6675()
    if temp is not None:
        print(f"Temperature: {temp:.2f} °C")
    else:
        print("Thermocouple not connected")
    time.sleep(1)