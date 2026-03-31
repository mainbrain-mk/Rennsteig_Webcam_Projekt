import usb.core
import usb.util
import time
import psutil
import pynvml
from PIL import Image, ImageDraw, ImageFont

keep_running = True

last_update_time = "update: --:--"

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
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0) # Erste GPU
    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
    pynvml.nvmlShutdown()
    return temp

def last_update(update="--:--"):
    global last_update_time
    last_update_time = f"upd: {update}"

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
    except:
        pass
    dev.set_configuration()

    print("Starte Live-Uhr auf dem G15 Display... (Strg+C zum Beenden)")

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
            draw.text((3, 20), current_time, font=font_t, fill=0)

            draw.text((80, 0), temp_text_cpu, font=font_d, fill=0)
            draw.text((80, 12), temp_text_gpu, font=font_d, fill=0)
            draw.text((80, 26), last_update_time, font=font_d, fill=0)

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


if __name__ == "__main__":
    # Vorher: sudo killall g15daemon (falls vorhanden)
    g15_live_clock()