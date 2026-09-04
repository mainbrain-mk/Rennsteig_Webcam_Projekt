import asyncio
import logging

import usb.core
import usb.util
import time
import psutil
import pynvml
from PIL import Image, ImageDraw, ImageFont

from config import URL_WEATHER_2
from weather import WeatherService

# Logger für dieses Modul konfigurieren
logger = logging.getLogger(__name__)

keep_running = True

last_update_time = "update: --:--"
last_secondary_weather = "---"

try:
    pynvml.nvmlInit()
    nvml_available = True
except Exception:
    nvml_available = False

def get_cpu_temp():
    temps = psutil.sensors_temperatures()
    if 'coretemp' in temps:
        # Meistens ist der erste Eintrag der "Package"-Wert (Gesamttemperatur)
        return temps['coretemp'][0].current
    elif 'cpu_thermal' in temps:
        # Alternative für manche AMD oder ARM Systeme
        return temps['cpu_thermal'][0].current
    return 0.0

def get_gpu_temp_nvidia():
    if not nvml_available:
        return 0.0
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        return pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
    except Exception:
        return 0.0
def shut_down():
    # Nur aufrufen, wenn nvmlInit() beim Start auch erfolgreich war (z.B. keine
    # NVIDIA-GPU vorhanden) - sonst wirft nvmlShutdown() eine Exception, die den
    # finally-Block in main.py mitten in der Cleanup-Sequenz abbricht.
    if nvml_available:
        pynvml.nvmlShutdown()

def last_update(update="--:--"):
    global last_update_time
    last_update_time = f"upd: {update}"

def set_secondary_weather(temp, pressure):
    """Aktualisiert die Temperatur/Luftdruck-Zeile des zweiten Standorts (URL_WEATHER_2)."""
    global last_secondary_weather
    if temp is not None and pressure is not None:
        last_secondary_weather = f"{temp:.0f}°C {pressure:.0f}hPa"
    else:
        last_secondary_weather = "---"

async def update_secondary_weather_loop():
    """Holt periodisch Wetterdaten für den zweiten Standort (nur für die G15-Zeile
    unter der Uhr, kein DB-Speichern/Overlay/Chart wie beim Rennsteigbahn-Standort)."""
    logger.info("Sekundärer Wetter-Loop (G15) gestartet.")
    service = WeatherService(url=URL_WEATHER_2)

    while True:
        try:
            success = await service.update()
            if success:
                cw = service.raw_data.get("current", {})
                set_secondary_weather(cw.get("temperature_2m"), cw.get("pressure_msl"))
                wait_time = service.compute_next_wait_seconds()
            else:
                wait_time = 60.0
        except Exception as e:
            logger.error(f"Fehler im sekundären Wetter-Loop (G15): {e}")
            wait_time = 60.0

        await asyncio.sleep(wait_time)

def g15_live_clock():
    global keep_running

    # 1. USB Setup
    dev = usb.core.find(idVendor=0x046d, idProduct=0xc222)
    if dev is None:
        print("G15 nicht gefunden!")
        return

    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass
    dev.set_configuration()

    logger.info("Starte Live-Uhr auf dem G15 Display...")

    try:
        font_t = ImageFont.truetype("/usr/share/fonts/truetype/terminus/TerminusTTF-4.46.0.ttf", 16)
        font_d = ImageFont.truetype("/usr/share/fonts/truetype/terminus/TerminusTTF-4.46.0.ttf", 12)

        while keep_running:
            # 2. Bild in Pillow erstellen (160x43)
            # Hintergrund Weiß (1) = Transparent auf LCD
            img = Image.new("1", (160, 43), 1)
            draw = ImageDraw.Draw(img)

            # Aktuelle Zeit formatieren
            current_time = time.strftime("%H:%M:%S")
            datum = time.strftime("%d.%m.%Y")
            temp_text_cpu = f"CPU: {get_cpu_temp():2.0f}°C"
            temp_text_gpu = f"GPU: {get_gpu_temp_nvidia():2.0f}°C"

            # Text zeichnen (Schwarz/0 = Sichtbar auf LCD)
            # Nutzt Standardschrift, falls keine .ttf geladen wird
            draw.text((5, 0), datum, font=font_d, fill=0)
            draw.text((3, 11), current_time, font=font_t, fill=0)
            # Zweiter Standort (Temperatur + Luftdruck) in der Zeile, die durch
            # das Verschieben der Uhr frei geworden ist. x=1 statt 3, damit auch
            # der Extremfall "-15°C 1035hPa" (78px) nicht in die rechte Spalte
            # bei x=80 hineinragt.
            draw.text((1, 30), last_secondary_weather, font=font_d, fill=0)

            draw.text((90, 0), temp_text_cpu, font=font_d, fill=0)
            draw.text((90, 12), temp_text_gpu, font=font_d, fill=0)
            draw.text((90, 26), last_update_time, font=font_d, fill=0)

            # Rahmen zur Kontrolle, ob das Alignment noch stimmt
            #draw.rectangle([0, 0, 159, 42], outline=0)

            # 3. Das verifizierte G15 V1 Mapping
            buffer = bytearray(992)
            buffer[0] = 0x03  # Dein Header
            offset = 32  # Dein entdeckter Offset

            pixels = img.load()
            for x in range(160):
                for y in range(43):
                    if pixels[x, y] == 0:  # Pixel soll schwarz sein
                        # Formel: Offset + Spalte + (Etage * Breite)
                        byte_idx = offset + x + (y // 8) * 160
                        bit_idx = y % 8
                        if byte_idx < 992:
                            buffer[byte_idx] |= (1 << bit_idx)

            # 4. Daten an die Hardware senden
            dev.write(0x02, bytes(buffer), 1000)

            # Kurze Pause, um die CPU zu schonen (0.1s für flüssige Reaktion)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nTest beendet. Display wird geleert...")
        # Optional: Display beim Beenden leeren
        dev.write(0x02, b'\x03' + b'\x00' * 991, 1000)


async def run_g15(loop):
    """Async-Wrapper um g15_live_clock(), damit der supervisor() in main.py
    den Thread bei einem Absturz (z.B. USB-Gerät abgezogen) automatisch neu starten kann."""
    await loop.run_in_executor(None, g15_live_clock)


if __name__ == "__main__":
    # Vorher: sudo killall g15daemon (falls vorhanden)
    g15_live_clock()