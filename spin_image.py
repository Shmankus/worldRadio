#!/usr/bin/env python3
import time
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FB_WIDTH = 240
FB_HEIGHT = 320
FB_PATH = "/dev/fb1"

DARK_RED = (80, 0, 0)
TEXT_COLOR = (255, 255, 255)

title_text = "Nothing Playing"
title_lock = threading.Lock()
country_text = "No Country"
country_lock = threading.Lock()


is_spinning = threading.Event()   # set() = actively spin the image, clear() = show idle/static frame
_display_thread = None
_display_running = threading.Event()

base_img = None
album_art_path = None
art_lock = threading.Lock()

def set_text(new_title, new_country):
    global title_text
    global country_text
    with title_lock:
        title_text = new_title
    with country_lock:
        country_text = new_country

def set_album_art(image_path):
    """Change which image is displayed/spun."""
    global base_img, album_art_path
    with art_lock:
        album_art_path = image_path
        base_img = Image.open(image_path).convert('RGBA')

def rgb_array_to_565(arr):
    r = arr[:, :, 0].astype(np.uint16)
    g = arr[:, :, 1].astype(np.uint16)
    b = arr[:, :, 2].astype(np.uint16)
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.astype('<u2')

def load_font(size=20):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except IOError:
        return ImageFont.load_default()

def _display_loop(fps=10, degrees_per_frame=6):
    text_zone_height = FB_HEIGHT // 3
    image_zone_height = FB_HEIGHT - text_zone_height
    font = load_font(10)
    angle = 0
    frame_delay = 1.0 / fps

    fb = open(FB_PATH, 'r+b')
    try:
        print("Display loop running.", flush=True)
        while _display_running.is_set():
            start = time.time()

            canvas_img = Image.new('RGB', (FB_WIDTH, FB_HEIGHT), DARK_RED)
            draw = ImageDraw.Draw(canvas_img)

            with title_lock:
                text = title_text
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((FB_WIDTH - text_w) // 2, (text_zone_height - text_h) // 2),
                    text, font=font, fill=TEXT_COLOR)



            with country_lock:
                text = country_text
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((((FB_WIDTH - text_w) // 2), ((text_zone_height - text_h) // 2) + 10),
                    text, font=font, fill=TEXT_COLOR)


            with art_lock:
                img = base_img

            if img is not None:
                size = min(FB_WIDTH, image_zone_height) // 2 
                size = min(size, FB_WIDTH - 20)
                resized = img.resize((size, size))
                paste_x = (FB_WIDTH - size) // 2
                paste_y = text_zone_height + (image_zone_height - size) // 2

                # only rotate if actively spinning; otherwise show it static at angle 0
                draw_angle = angle if is_spinning.is_set() else 0
                rotated = resized.rotate(draw_angle, resample=Image.BICUBIC, expand=False)
                rgb = np.asarray(rotated.convert('RGB'))
                alpha = np.asarray(rotated.split()[-1])

                canvas = np.asarray(canvas_img).copy()
                mask = alpha > 0
                canvas[paste_y:paste_y+size, paste_x:paste_x+size][mask] = rgb[mask]
            else:
                canvas = np.asarray(canvas_img).copy()

            raw = rgb_array_to_565(canvas).tobytes()
            fb.seek(0)
            fb.write(raw)
            fb.flush()

            if is_spinning.is_set():
                angle = (angle + degrees_per_frame) % 360

            elapsed = time.time() - start
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception as e:
        print("Error in display loop:", e, flush=True)
    finally:
        fb.seek(0)
        fb.write(bytes(FB_WIDTH * FB_HEIGHT * 2))
        fb.flush()
        fb.close()
        print("Display loop stopped, screen cleared.", flush=True)

def start_display():
    """Call once, when Flask starts. Runs forever in the background."""
    global _display_thread
    if _display_running.is_set():
        return
    _display_running.set()
    _display_thread = threading.Thread(target=_display_loop, daemon=True)
    _display_thread.start()

def stop_display():
    """Only needed for full shutdown, not for play/pause."""
    _display_running.clear()
    if _display_thread:
        _display_thread.join(timeout=2)

def start_spin():
    """Call when playback starts — screen keeps showing, but image begins rotating."""
    is_spinning.set()

def stop_spin():
    """Call when playback stops — screen keeps showing, image just stops rotating."""
    is_spinning.clear()
