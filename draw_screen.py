#!/usr/bin/env python3
import time
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta

# Display Configurations
FB_WIDTH = 240
FB_HEIGHT = 320
FB_PATH = "/dev/fb1"

# Upgraded Color Palette (Deep Cyberpunk / Synthwave Vibe)
BG_COLOR = (50, 25, 30)        # Deep cherry
ACCENT_COLOR = (255, 45, 85)   # Neon pink/red line accent
TEXT_MAIN = (240, 240, 255)    # Crisp off-white
TEXT_MUTED = (130, 120, 150)   # Muted lavender/grey for labels

GIF_SIZE = 380
GIF_PASTE_X = (FB_WIDTH - GIF_SIZE) // 2
GIF_PASTE_Y = 130

# Threading & Shared State
is_spinning = threading.Event()
_display_running = threading.Event()
_display_thread = None
_state_lock = threading.Lock()

# App State
title_text = "Nothing Playing"
country_text = "No Country"
time_offset_str = "0"
song_name = "Unknown"
artist_name = "Unknown"


def load_font(size=12):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except IOError:
        return ImageFont.load_default()

font_large = load_font(15)
font_small = load_font(11)

# Module level
_last_est_str = ""
_last_dest_str = ""


def set_text(new_title, new_country, new_timeOffset, new_song_name, new_artist_name):
    global title_text, country_text, time_offset_str, song_name, artist_name, _text_overlay_bytes, _last_est_str, _last_dest_str
    with _state_lock:
        title_text = " ".join(new_title.strip().split()) if new_title else "Nothing Playing"
        country_text = " ".join(new_country.strip().split()) if new_country else "No Country"
        time_offset_str = str(new_timeOffset)
        song_name = " ".join(new_song_name.strip().split()) if new_song_name else "Unknown"
        artist_name = " ".join(new_artist_name.strip().split()) if new_artist_name else "Unknown"

        # Always recompute clock so it's never blank
        now_utc = datetime.now(timezone.utc)
        try:
            target_time = now_utc + timedelta(minutes=int(time_offset_str))
        except (ValueError, TypeError):
            target_time = now_utc
        now_est = datetime.now(ZoneInfo("America/New_York"))
        _last_est_str = now_est.strftime('%I:%M %p')
        _last_dest_str = target_time.strftime('%I:%M %p')

        _text_overlay_bytes = _render_text_overlay(
            title_text, country_text, song_name, artist_name,
            _last_est_str, _last_dest_str
        )


# Add this global
_text_overlay_bytes = None  # RGB565 bytes of just the text strip

def _render_text_overlay(title, country, song, artist, est_str="", dest_str=""):
    TEXT_STRIP_H = 150
    canvas = Image.new('RGB', (FB_WIDTH, TEXT_STRIP_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, FB_WIDTH, 4], fill=ACCENT_COLOR)

    bbox_t = draw.textbbox((0, 0), title, font=font_large)
    draw.text(((FB_WIDTH - (bbox_t[2] - bbox_t[0])) // 2, 12), title, font=font_large, fill=TEXT_MAIN)

    bbox_c = draw.textbbox((0, 0), country, font=font_small)
    draw.text(((FB_WIDTH - (bbox_c[2] - bbox_c[0])) // 2, 34), country, font=font_small, fill=TEXT_MUTED)

    # Clock at y=61
    if est_str:
        draw.text((20, 66), "LOCAL", font=font_small, fill=TEXT_MUTED)
        draw.text((20, 80), est_str, font=font_large, fill=TEXT_MAIN)
    if dest_str:
        bbox_dl = draw.textbbox((0, 0), "DEST", font=font_small)
        draw.text((FB_WIDTH - 20 - (bbox_dl[2]-bbox_dl[0]), 66), "DEST", font=font_small, fill=TEXT_MUTED)
        bbox_d = draw.textbbox((0, 0), dest_str, font=font_large)
        draw.text((FB_WIDTH - 20 - (bbox_d[2]-bbox_d[0]), 80), dest_str, font=font_large, fill=ACCENT_COLOR)

    draw.line([(20, 56), (FB_WIDTH - 20, 56)], fill=(40, 35, 60), width=1)
    draw.line([(20, 110), (FB_WIDTH - 20, 110)], fill=(40, 35, 60), width=1)

    if len(song) > 24: song = song[:21] + "..."
    bbox_song = draw.textbbox((0, 0), song, font=font_large)
    draw.text(((FB_WIDTH - (bbox_song[2] - bbox_song[0])) // 2, 116), song, font=font_large, fill=TEXT_MAIN)

    if len(artist) > 26: artist = artist[:23] + "..."
    bbox_artist = draw.textbbox((0, 0), artist, font=font_small)
    draw.text(((FB_WIDTH - (bbox_artist[2] - bbox_artist[0])) // 2, 132), artist, font=font_small, fill=TEXT_MUTED)

    return bytearray(_rgb_to_rgb565(np.asarray(canvas)))



_base_gif_frames = []  # list of bytearray, only the GIF portion (y=150 to y=320)

GIF_REGION_Y = 150
GIF_REGION_BYTES = (FB_HEIGHT - GIF_REGION_Y) * FB_WIDTH * 2

def _preload_gif(gif_path="uploads/vinyl2.gif"):
    global _base_gif_frames
    staging = []

    # Background canvas for gif region only
    canvas_base = Image.new('RGB', (FB_WIDTH, FB_HEIGHT - GIF_REGION_Y), BG_COLOR)

    try:
        img = Image.open(gif_path)
        for f in ImageSequence.Iterator(img):
            rgba_f = f.convert('RGBA').resize((GIF_SIZE, GIF_SIZE))
            rgb_f = rgba_f.convert('RGB')
            frame_canvas = canvas_base.copy()
            # Adjust paste Y relative to the gif region
            paste_y = GIF_PASTE_Y - GIF_REGION_Y
            frame_canvas.paste(rgb_f, (GIF_PASTE_X, paste_y), rgba_f)
            staging.append(bytearray(_rgb_to_rgb565(np.asarray(frame_canvas))))
            time.sleep(0.005)
    except Exception as e:
        print(f"GIF preload failed: {e}")
        staging.append(bytearray(_rgb_to_rgb565(np.asarray(canvas_base))))

    _base_gif_frames = staging
    print(f"GIF preloaded: {len(staging)} frames", flush=True)

def _rgb_to_rgb565(rgb_array):
    """Vectorized conversion of RGB arrays into raw RGB565 bytes."""
    r = rgb_array[:, :, 0].astype(np.uint16)
    g = rgb_array[:, :, 1].astype(np.uint16)
    b = rgb_array[:, :, 2].astype(np.uint16)
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.astype('<u2').tobytes()



TEXT_STRIP_H = 150
TEXT_STRIP_BYTES = TEXT_STRIP_H * FB_WIDTH * 2

def _display_loop(fps=5):
    frame_delay = 1.0 / fps
    last_minute = -1
    frame_idx = 0

    global _text_overlay_bytes

    try:
        fb = open(FB_PATH, 'r+b')
        print("Hardware display loop loaded.", flush=True)

        while _display_running.is_set():
            start_time = time.time()

            # 1. Clock tick - regenerate overlay once per minute
            now_utc = datetime.now(timezone.utc)
            if now_utc.minute != last_minute:
                last_minute = now_utc.minute
                with _state_lock:
                    offset_str = time_offset_str
                try:
                    total_minutes = int(offset_str)
                    target_time = now_utc + timedelta(minutes=total_minutes)
                except (ValueError, TypeError):
                    target_time = now_utc

                now_est = datetime.now(ZoneInfo("America/New_York"))
                est_time_str = now_est.strftime('%I:%M %p')
                dest_time_str = target_time.strftime('%I:%M %p')

                with _state_lock:
                    _last_est_str = est_time_str
                    _last_dest_str = dest_time_str
                    _text_overlay_bytes = _render_text_overlay(
                        title_text, country_text, song_name, artist_name,
                        est_time_str, dest_time_str
                    )



            # 2. Blit
            n = len(_base_gif_frames)
            if n > 0:
                idx = frame_idx % n

                with _state_lock:
                    overlay = _text_overlay_bytes

                fb.seek(0)
                if overlay:
                    fb.write(overlay)
                else:
                    fb.write(bytes(TEXT_STRIP_BYTES))
                fb.write(_base_gif_frames[idx])
                fb.flush()

                if is_spinning.is_set():
                    frame_idx = (idx + 1) % n

            elapsed = time.time() - start_time
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        print("Display loop error:", e, flush=True)
    finally:
        fb.seek(0)
        fb.write(bytes(FB_WIDTH * FB_HEIGHT * 2))
        fb.flush()
        fb.close()
        print("Display loop stopped.", flush=True)


def start_display():
    global _display_thread
    if _display_running.is_set():
        return
    _preload_gif()  # one-time cost at boot
    _display_running.set()
    _display_thread = threading.Thread(target=_display_loop, daemon=True)
    _display_thread.start()

def stop_display():
    _display_running.clear()
    if _display_thread:
        _display_thread.join(timeout=2)

def start_spin():
    is_spinning.set()

def stop_spin():
    is_spinning.clear()
