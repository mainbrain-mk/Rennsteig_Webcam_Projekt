import logging
from datetime import timedelta

from PIL import ImageDraw, ImageFont, Image

# Logger für dieses Modul konfigurieren
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)

def load_font(size, bold=False):
    try:
        # Pfad für Kubuntu
        font_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{font_name}", size)
    except:
        return ImageFont.load_default()

def draw_gradient_rounded_rect(draw, img, coords, radius, color_top, color_bottom):
    """Zeichnet ein abgerundetes Rechteck mit vertikalem Farbverlauf."""
    x1, y1, x2, y2 = coords
    width = x2 - x1
    height = y2 - y1

    # 1. Erstelle ein temporäres Bild für den Verlauf
    gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)

    # 2. Zeichne den Verlauf Zeile für Zeile
    for y in range(height):
        # Berechne die Farbe für die aktuelle Zeile
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * (y / height))
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * (y / height))
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * (y / height))
        g_draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # 3. Erstelle eine Maske für die abgerundeten Ecken
    mask = Image.new('L', (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=255)

    # 4. Blende den Verlauf mit der Maske auf das Hauptbild ein
    img.paste(gradient, (x1, y1), mask)

def lerp_color(c1, c2, t):
    """Interpoliert linear zwischen zwei RGB-Farben basierend auf Faktor t (0.0-1.0)."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

def get_dynamic_color(w: dict):
    """Berechnet einen fließenden Farbübergang basierend auf dem vollen Sonnenzyklus."""
    now = w.get('now')
    dawn = w.get('dawn')
    sunrise = w.get('sunrise')
    noon = w.get('noon')
    sunset = w.get('sunset')
    dusk = w.get('dusk')
    midnight = w.get('midnight')
    next_midnight = w.get('next_midnight')

    logger.debug(f"now: {now}, dawn: {dawn}, sunrise: {sunrise}, noon: {noon}, "
                f"sunset: {sunset}, dusk: {dusk}, midnight: {midnight}, next_midnight: {next_midnight}")

    # Basis-Check (ohne Mitternacht, falls die mal fehlt)
    if not all([now, dawn, sunrise, noon, sunset, dusk]):
        return (0, 175, 255)

    # Definierte Farbpunkte
    color_midnight = (5, 5, 20)      # Tiefste Nacht (fast Schwarz-Blau)
    color_dawn     = (100, 50, 100)  # Dämmerung (Violett/Rosa)
    color_sunrise  = (0, 200, 200)   # Sonnenaufgang (Türkis/Cyan)
    color_noon     = (0, 175, 255)   # Mittags (Helles Blau)
    color_sunset   = (255, 100, 0)   # Sonnenuntergang (Warmes Orange/Gold)
    color_dusk     = (60, 0, 90)     # Späte Dämmerung (Dunkelviolett)

    def get_t(start, end, current):
        total = (end - start).total_seconds()
        if total <= 0: return 0.0
        elapsed = (current - start).total_seconds()
        return max(0.0, min(1.0, elapsed / total))

    # --- Die vollständige Zyklus-Logik ---

    # 1. Von Mitternacht (heute Morgen) bis zum Morgengrauen (Dawn)
    if midnight and now <= dawn:
        # Wir blenden von der tiefsten Nacht langsam zum Dämmerungsviolett auf
        t = get_t(midnight, dawn, now)
        return lerp_color(color_midnight, color_dawn, t)

    # 2. Dämmerung (Dawn) bis Sonnenaufgang (Sunrise)
    elif dawn < now <= sunrise:
        t = get_t(dawn, sunrise, now)
        return lerp_color(color_dawn, color_sunrise, t)

    # 3. Vormittag (Sunrise bis Noon)
    elif sunrise < now <= noon:
        t = get_t(sunrise, noon, now)
        return lerp_color(color_sunrise, color_noon, t)

    # 4. Nachmittag (Noon bis Sunset)
    elif noon < now <= sunset:
        t = get_t(noon, sunset, now)
        return lerp_color(color_noon, color_sunset, t)

    # 5. Abenddämmerung (Sunset bis Dusk)
    elif sunset < now <= dusk:
        t = get_t(sunset, dusk, now)
        return lerp_color(color_sunset, color_dusk, t)

    # 6. Von Dusk bis zur nächsten Mitternacht (morgen früh)
    else:
        # Wenn next_midnight fehlt, nehmen wir einen 2h-Fallback
        target = next_midnight if next_midnight else (dusk + timedelta(hours=2))
        t = get_t(dusk, target, now)
        return lerp_color(color_dusk, color_midnight, t)

def draw_overlay(img, weather_info: dict):
    draw = ImageDraw.Draw(img)
    w = weather_info or {}

    # Box-Parameter
    OX, OY = 20, 80
    OW, OH = 720, 320  # Etwas breiter gemacht
    CORNER_RADIUS = 20

    #draw.rounded_rectangle([OX, OY, OX + OW, OY + OH], radius=CORNER_RADIUS, fill=(120, 170, 255))

    # Hintergrund mit Verlauf zeichnen (Hellblau zu Dunkelblau)
    color_start = get_dynamic_color(w)
    color_end = (40, 0, 50)
    draw_gradient_rounded_rect(draw, img, [OX, OY, OX + OW, OY + OH], CORNER_RADIUS, color_start, color_end)

    f_header = load_font(34, bold=True)
    f_temp = load_font(65, bold=True)
    f_details = load_font(22)
    f_small = load_font(18)

    # --- Linke Sektion ---

    # --- Linke Sektion (Icon & Beschreibung) ---
    icon_text = w.get("icon", "❓")
    icon_size = 109
    icon_x = OX + 30
    icon_y = OY + 15

    # 1. Font laden
    try:
        f_emoji = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", icon_size)
    except Exception as e:
        logger.warning(f"Konnte NotoColorEmoji nicht laden: {e}")
        f_emoji = load_font(100)


    # 2. Realbreite des Icons über textbbox ermitteln
    # bbox liefert (left, top, right, bottom)
    i_bbox = draw.textbbox((icon_x, icon_y), icon_text, font=f_emoji, embedded_color=True)
    icon_real_width = i_bbox[2] - i_bbox[0]
    icon_real_height = i_bbox[3] - i_bbox[1]  # Realhöhe des Emojis

    # Der exakte Mittelpunkt des gerenderten Icons
    icon_center_x = icon_x + (icon_real_width // 2)
    icon_center_y = icon_y + (icon_real_height // 2)

    # 3. Icon zeichnen
    draw.text((icon_x, icon_y), icon_text, font=f_emoji, embedded_color=True)

    # Wetter-Beschreibung (z.B. "Schneeschauer") zentriert unter dem Icon
    desc_text = w.get("text", "Lade...")
    desc_y = OY + 150  # Position unter dem Icon

    # Text am Leerzeichen splitten für automatischen Umbruch
    lines = desc_text.split(' ')
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f_details)
        line_width = bbox[2] - bbox[0]
        # X so berechnen, dass die Mitte der Zeile auf der Mitte des Icons liegt
        draw.text((icon_center_x - (line_width // 2), desc_y), line, fill="white", font=f_details)
        desc_y += 30  # Zeilenabstand für das nächste Wort

    # --- Mittlere Sektion (Temperatur & Gefühlt) ---
    temp_val = str(w.get("temp", "--.-"))
    if "°C" not in temp_val: temp_val += " °C"

    # 2. Temperatur vertikal mittig zum Icon ausrichten
    # Wir messen die Höhe des Temperatur-Texts
    temp_x = OX + 200
    t_bbox = draw.textbbox((0, 0), temp_val, font=f_temp)
    temp_width = t_bbox[2] - t_bbox[0]
    temp_height = t_bbox[3] - t_bbox[1]

    # Y-Position: Icon-Mitte minus halbe Texthöhe
    temp_y_centered = icon_center_y - (temp_height // 2)

    draw.text((temp_x, temp_y_centered), temp_val, fill="white", font=f_temp)

    feels_val = str(w.get("feels", "--"))
    # Fix: Nur "Gefühlt" voranstellen, wenn es nicht schon aus weather.py kommt
    if "Gefühlt" not in feels_val:
        feels_val = f"Gefühlt {feels_val}"

    # X-Mitte der Temperatur berechnen
    temp_center_x = temp_x + (temp_width // 2)

    # Breite des "Gefühlt"-Texts ermitteln
    f_bbox = draw.textbbox((0, 0), feels_val, font=f_details)
    feels_width = f_bbox[2] - f_bbox[0]

    # Auf die gleiche Höhe wie die Beschreibung setzen (OY + 150)
    # Falls der Wettertext zwei Zeilen hat, nutzt dieser desc_y.
    # Wir nehmen hier den festen Startwert OY + 150 für eine saubere Linie.
    draw.text((temp_center_x - (feels_width // 2), OY + 150), feels_val, fill="white", font=f_details)

    # --- Rechte Sektion (Fix für doppelte Labels wie "Wind Wind") ---
    col_x = OX + 480
    line_height = 40
    start_y = OY + 30

    # Liste der anzuzeigenden Daten (Keys aus deinem weather.py Dictionary)
    # Da deine weather.py schon "Wind 10 km/h" liefert, nutzen wir die Werte direkt
    details = [
        w.get("wind", "Wind --"),
        w.get("gusts", "Böen --"),
        w.get("humidity", "Feuchte --"),
        w.get("pressure", "Druck --")
    ]

    for i, detail_text in enumerate(details):
        draw.text((col_x, start_y + (i * line_height)), str(detail_text), fill="white", font=f_details)

    # --- Untere Sektion ---
    line_y = OY + 210
    draw.line([OX + 30, line_y, OX + OW - 30, line_y], fill=(255, 255, 255, 180), width=2)

    # --- Höhe links unten im Overlay ---
    elevation_text = w.get("elevation", "-- m ü. NHN")

    # Sonnenaufgang
    sunrise_dt = w.get("sunrise")
    sunrise_str = sunrise_dt.strftime('%H:%M') if sunrise_dt else "--:--"

    # Sonnenuntergang
    sunset_dt = w.get("sunset")
    sunset_str = sunset_dt.strftime('%H:%M') if sunset_dt else "--:--"

    # Kombinierter String mit Emojis
    sun_info = f"  ▲ {sunrise_str}   ▼ {sunset_str}"



    # 1. Emoji-Font laden (für farbige Darstellung)
    try:
        f_emoji_small = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 22)
    except:
        f_emoji_small = f_details

    # Position: OX + kleiner Puffer, OY + Boxhöhe - kleiner Puffer
    # Wir setzen es etwa 20 Pixel vom linken und unteren Rand der Box entfernt
    elev_x = OX + 25
    elev_y = OY + OH - 55

    station_text = "Bahnhof Rennsteig"
    bbox = draw.textbbox((0, 0), station_text, font=f_header)
    draw.text((OX + OW - (bbox[2] - bbox[0]) - 30, elev_y), station_text, fill="white", font=f_header)
    draw.text((OX + OW - (bbox[2] - bbox[0]) - 30, elev_y - bbox[1] - 18), elevation_text, fill="white", font=f_small)
    draw.text((OX + OW - (bbox[2] - bbox[0]) + 160, elev_y - bbox[1] - 18), sun_info, font=f_small, embedded_color=True)

    dt = w.get("datetime")
    time_str = dt.strftime('%H:%M') if dt else "--:--"
    draw.text((OX + 30, elev_y), time_str, fill="white", font=f_header)
    draw.text((OX + 30, elev_y - bbox[1] - 18), "letztes Wetter Update:", fill="white", font=f_small)
    return img