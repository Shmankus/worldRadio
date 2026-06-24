#!/usr/bin/env python3
import time
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from datetime import datetime, timedelta, timezone
FB_WIDTH = 240
FB_HEIGHT = 320
FB_PATH = "/dev/fb1"

DARK_RED = (80, 0, 0)
TEXT_COLOR = (255, 255, 255)

title_text = "Nothing Playing"
title_lock = threading.Lock()
country_text = "No Country"
country_lock = threading.Lock()
time_text = "00:00 AM"
time_lock = threading.Lock()

is_spinning = threading.Event()
_display_thread = None
_display_running = threading.Event()

# pre-composited frames: each entry is raw RGB565 bytes ready to write directly to fb1
_composited_frames = []
_frames_lock = threading.Lock()

# current frame index — module level so stop_spin() can read it instantly
_frame_idx = 0
_frame_lock = threading.Lock()

# cached background numpy array, rebuilt only when text changes
_bg_array = None
_bg_lock = threading.Lock()
_last_title = None
_last_country = None


# at the top of spin_image.py, after FB_WIDTH/FB_HEIGHT
TEXT_ZONE = FB_HEIGHT // 3
IMAGE_ZONE = FB_HEIGHT - TEXT_ZONE
GIF_SIZE = 180  # change this one number to resize
GIF_PASTE_X = (FB_WIDTH - GIF_SIZE) // 2
GIF_PASTE_Y = TEXT_ZONE + (IMAGE_ZONE - GIF_SIZE) // 2


def load_font(size=12):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except IOError:
        return ImageFont.load_default()

_font = None

def _build_background():
    """Render background + text into a numpy array. Called once + whenever text changes."""
    global _last_title, _last_country
    text_zone_height = FB_HEIGHT // 3

    with title_lock:
        t = title_text
    with country_lock:
        c = country_text
    with time_lock:
        d = time_text

    canvas_img = Image.new('RGB', (FB_WIDTH, FB_HEIGHT), DARK_RED)
    draw = ImageDraw.Draw(canvas_img)

    bbox = draw.textbbox((0, 0), t, font=_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((FB_WIDTH - tw) // 2, (text_zone_height - th) // 2 - th),
              t, font=_font, fill=TEXT_COLOR)

    bbox = draw.textbbox((0, 0), c, font=_font)
    cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((FB_WIDTH - cw) // 2, (text_zone_height - ch) // 2 + ch),
              c, font=_font, fill=TEXT_COLOR)

    


    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    



    _last_title = t
    _last_country = c
    return np.asarray(canvas_img).copy()

def _composite_frames_onto_bg(bg_array, frames_rgba):
    """Pre-composite all GIF frames onto the background array.
    Returns list of raw RGB565 bytes, one per frame, ready to write directly to fb."""
    size, paste_x, paste_y = GIF_SIZE, GIF_PASTE_X, GIF_PASTE_Y
    result = []
    for rgb, alpha in frames_rgba:
        canvas = bg_array.copy()
        mask = alpha > 0
        canvas[paste_y:paste_y+size, paste_x:paste_x+size][mask] = rgb[mask]
        r = canvas[:, :, 0].astype(np.uint16)
        g = canvas[:, :, 1].astype(np.uint16)
        b = canvas[:, :, 2].astype(np.uint16)
        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        result.append(rgb565.astype('<u2').tobytes())
    return result

def set_text(new_title, new_country, new_timeOffset):
    global title_text, country_text, time_text
    with title_lock:
        title_text = new_title
    with country_lock:
        country_text = new_country
    with time_lock:
        time_text = new_timeOffset


    # rebuild composited frames with new background text
    _rebuild_composited_frames()

def set_album_art(image_path):
    """Load GIF frames and pre-composite them onto the current background."""
    global _gif_frames_rgba
    img = Image.open(image_path)
    frames_rgba = []
    try:
        for gif_frame in ImageSequence.Iterator(img):
            f = gif_frame.convert('RGBA').resize((GIF_SIZE, GIF_SIZE))
            rgb = np.asarray(f.convert('RGB')).copy()
            alpha = np.asarray(f.split()[-1]).copy()
            frames_rgba.append((rgb, alpha))
    except EOFError:
        pass
    _gif_frames_rgba = frames_rgba
    print(f"Loaded {len(frames_rgba)} frames from {image_path}", flush=True)
    _rebuild_composited_frames()

_gif_frames_rgba = []

def _rebuild_composited_frames():
    """Rebuild pre-composited frames using current background + current GIF frames."""
    global _bg_array
    with _bg_lock:
        _bg_array = _build_background()
        composited = _composite_frames_onto_bg(_bg_array, _gif_frames_rgba)
    with _frames_lock:
        _composited_frames.clear()
        _composited_frames.extend(composited)
    print(f"Rebuilt {len(composited)} composited frames.", flush=True)

def _display_loop(fps=24):
    global _frame_idx, _last_title, _last_country
    frame_delay = 1.0 / fps
    last_minute = -1
    _cached_clock_frame = None

    from zoneinfo import ZoneInfo

    fb = open(FB_PATH, 'r+b')
    try:
        print("Display loop running.", flush=True)
        while _display_running.is_set():
            start = time.time()

            with title_lock:
                cur_title = title_text
            with country_lock:
                cur_country = country_text
            if cur_title != _last_title or cur_country != _last_country:
                _rebuild_composited_frames()
                _cached_clock_frame = None  # force clock redraw after rebuild

            with _frames_lock:
                frames = _composited_frames
                n = len(frames)

            if n > 0:
                with _frame_lock:
                    idx = _frame_idx % n

                now = datetime.now(timezone.utc)
                cur_minute = now.minute

                if cur_minute != last_minute or _cached_clock_frame is None:
                    last_minute = cur_minute

                    with time_lock:
                        offset_str = time_text
                    try:
                        total_minutes = int(offset_str)
                        hour_offset = total_minutes // 60
                        minute_offset = total_minutes % 60
                    except (ValueError, TypeError):
                        hour_offset = 0
                        minute_offset = 0

                    target_time = now + timedelta(hours=hour_offset, minutes=minute_offset)
                    time_str = target_time.strftime("%I:%M %p")

                    raw = frames[idx]
                    arr = np.frombuffer(raw, dtype='<u2').reshape(FB_HEIGHT, FB_WIDTH)
                    r = ((arr & 0xF800) >> 8).astype(np.uint8)
                    g = ((arr & 0x07E0) >> 3).astype(np.uint8)
                    b = ((arr & 0x001F) << 3).astype(np.uint8)
                    rgb_arr = np.stack([r, g, b], axis=2)
                    frame_img = Image.fromarray(rgb_arr, 'RGB')

                    draw = ImageDraw.Draw(frame_img)
                    bbox = draw.textbbox((0, 0), time_str, font=_font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    text_zone_height = FB_HEIGHT // 3
                    draw.text(((FB_WIDTH - tw) // 2,
                               (text_zone_height - th) // 2 + (th * 3)),
                              time_str, font=_font, fill=TEXT_COLOR)

                    arr2 = np.asarray(frame_img)
                    r2 = arr2[:, :, 0].astype(np.uint16)
                    g2 = arr2[:, :, 1].astype(np.uint16)
                    b2 = arr2[:, :, 2].astype(np.uint16)
                    rgb565 = ((r2 & 0xF8) << 8) | ((g2 & 0xFC) << 3) | (b2 >> 3)
                    _cached_clock_frame = rgb565.astype('<u2').tobytes()

                fb.seek(0)
                fb.write(_cached_clock_frame)
                fb.flush()

                if is_spinning.is_set():
                    with _frame_lock:
                        _frame_idx = (idx + 1) % n
            else:
                if _bg_array is not None:
                    with _bg_lock:
                        bg = _bg_array
                    r = bg[:, :, 0].astype(np.uint16)
                    g = bg[:, :, 1].astype(np.uint16)
                    b = bg[:, :, 2].astype(np.uint16)
                    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                    fb.seek(0)
                    fb.write(rgb565.astype('<u2').tobytes())
                    fb.flush()

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
    global _display_thread, _font
    if _display_running.is_set():
        return
    _font = load_font(12)
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
    # frame_idx is module-level, so it's already at the exact right frame right now
    is_spinning.clear()
