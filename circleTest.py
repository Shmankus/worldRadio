#!/usr/bin/env python3
import sys
import time
import signal
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FB_WIDTH = 240
FB_HEIGHT = 320
FB_PATH = "/dev/fb1"

DARK_RED = (80, 0, 0)
TEXT_COLOR = (255, 255, 255)

running = True
current_text = "Loading..."
text_lock = threading.Lock()

def set_text(new_text):
    """Call this from another thread/route to update the displayed title."""
    global current_text
    with text_lock:
        current_text = new_text

def handle_interrupt(sig, frame):
    global running
    running = False

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

def spin_image(image_path, fps=20, degrees_per_frame=6):
    base_img = Image.open(image_path).convert('RGBA')

    text_zone_height = FB_HEIGHT // 3        # top third
    image_zone_height = FB_HEIGHT - text_zone_height  # bottom two-thirds

    size = min(FB_WIDTH, image_zone_height) // 2  # keep it even, sized to fit bottom zone
    size = min(size, FB_WIDTH - 20)  # small margin
    base_img = base_img.resize((size, size))

    paste_x = (FB_WIDTH - size) // 2
    paste_y = text_zone_height + (image_zone_height - size) // 2

    font = load_font(20)

    angle = 0
    frame_delay = 1.0 / fps

    fb = open(FB_PATH, 'r+b')
    try:
        print("Spinning image... Press Ctrl+C to stop.")
        frame_count = 0
        timer_start = time.time()

        while running:
            start = time.time()

            # base canvas: solid dark red
            canvas_img = Image.new('RGB', (FB_WIDTH, FB_HEIGHT), DARK_RED)

            # draw current text, centered in the top third
            draw = ImageDraw.Draw(canvas_img)
            with text_lock:
                text = current_text
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            text_x = (FB_WIDTH - text_w) // 2
            text_y = (text_zone_height - text_h) // 2
            draw.text((text_x, text_y), text, font=font, fill=TEXT_COLOR)

            # rotate and composite the image into the bottom two-thirds
            rotated = base_img.rotate(angle, resample=Image.BICUBIC, expand=False)
            rgb = np.asarray(rotated.convert('RGB'))
            alpha = np.asarray(rotated.split()[-1])

            canvas = np.asarray(canvas_img).copy()
            mask = alpha > 0
            canvas[paste_y:paste_y+size, paste_x:paste_x+size][mask] = rgb[mask]

            raw = rgb_array_to_565(canvas).tobytes()

            fb.seek(0)
            fb.write(raw)
            fb.flush()

            angle = (angle + degrees_per_frame) % 360

            frame_count += 1
            if frame_count % 30 == 0:
                actual_fps = frame_count / (time.time() - timer_start)
                print(f"Actual fps: {actual_fps:.1f}")

            elapsed = time.time() - start
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        fb.seek(0)
        fb.write(bytes(FB_WIDTH * FB_HEIGHT * 2))
        fb.flush()
        fb.close()
        print("\nStopped, screen cleared.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_interrupt)
    if len(sys.argv) < 2:
        print("Usage: python spin_image.py /path/to/image.png")
        sys.exit(1)
    spin_image(sys.argv[1])
