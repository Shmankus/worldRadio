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
BG_COLOR = (35, 15, 20)        # Deep cherry
ACCENT_COLOR = (255, 45, 85)   # Neon pink/red line accent
TEXT_MAIN = (240, 240, 255)    # Crisp off-white
TEXT_MUTED = (130, 120, 150)   # Muted lavender/grey for labels

GIF_SIZE = 180
GIF_PASTE_X = (FB_WIDTH - GIF_SIZE) // 2
GIF_PASTE_Y = 135 

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
gif_path_to_load = None
state_changed = False

# Background Loader State
_pending_frames = None
_pending_ready = threading.Event()

def load_font(size=12):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except IOError:
        return ImageFont.load_default()

font_large = load_font(15)
font_small = load_font(11)

def set_text(new_title, new_country, new_timeOffset, new_song_name, new_artist_name):
    global title_text, country_text, time_offset_str, song_name, artist_name, state_changed
    with _state_lock:
        title_text = " ".join(new_title.strip().split()) if new_title else "Nothing Playing"
        country_text = " ".join(new_country.strip().split()) if new_country else "No Country"
        time_offset_str = str(new_timeOffset)
        song_name = " ".join(new_song_name.strip().split()) if new_song_name else "Unknown"
        artist_name = " ".join(new_artist_name.strip().split()) if new_artist_name else "Unknown"
        state_changed = True

def set_gif(image_path):
    global gif_path_to_load, state_changed
    with _state_lock:
        gif_path_to_load = image_path
        state_changed = True

def _rgb_to_rgb565(rgb_array):
    """Vectorized conversion of RGB arrays into raw RGB565 bytes."""
    r = rgb_array[:, :, 0].astype(np.uint16)
    g = rgb_array[:, :, 1].astype(np.uint16)
    b = rgb_array[:, :, 2].astype(np.uint16)
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.astype('<u2').tobytes()

def _build_static_ui_base(title, country, song, artist):
    """Generates the static base image background template."""
    canvas = Image.new('RGB', (FB_WIDTH, FB_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, FB_WIDTH, 4], fill=ACCENT_COLOR)

    bbox_t = draw.textbbox((0, 0), title, font=font_large)
    draw.text(((FB_WIDTH - (bbox_t[2] - bbox_t[0])) // 2, 12), title, font=font_large, fill=TEXT_MAIN)

    bbox_c = draw.textbbox((0, 0), country, font=font_small)
    draw.text(((FB_WIDTH - (bbox_c[2] - bbox_c[0])) // 2, 34), country, font=font_small, fill=TEXT_MUTED)

    draw.line([(20, 56), (FB_WIDTH - 20, 56)], fill=(40, 35, 60), width=1)
    draw.line([(20, 106), (FB_WIDTH - 20, 106)], fill=(40, 35, 60), width=1)

    full_track_str = f"{song} - {artist}"
    bbox_track = draw.textbbox((0, 0), full_track_str, font=font_small)
    track_w = bbox_track[2] - bbox_track[0]
    
    if track_w > (FB_WIDTH - 20):
        full_track_str = full_track_str[:28] + "..."
        bbox_track = draw.textbbox((0, 0), full_track_str, font=font_small)
        track_w = bbox_track[2] - bbox_track[0]

    draw.text(((FB_WIDTH - track_w) // 2, 114), full_track_str, font=font_small, fill=TEXT_MAIN)
    return canvas

def _render_clock_strip_bytes(est_str, dest_str):
    """Generates just the dynamic dual clock row as a raw sub-segment byte slice."""
    strip_h = 40  
    canvas = Image.new('RGB', (FB_WIDTH, strip_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.text((20, 5), "LOCAL", font=font_small, fill=TEXT_MUTED)
    draw.text((20, 19), est_str, font=font_large, fill=TEXT_MAIN)

    bbox_dest_lbl = draw.textbbox((0, 0), "DESTINATION", font=font_small)
    draw.text((FB_WIDTH - 20 - (bbox_dest_lbl[2]-bbox_dest_lbl[0]), 5), "DESTINATION", font=font_small, fill=TEXT_MUTED)
    bbox_dest = draw.textbbox((0, 0), dest_str, font=font_large)
    draw.text((FB_WIDTH - 20 - (bbox_dest[2]-bbox_dest[0]), 19), dest_str, font=font_large, fill=ACCENT_COLOR)

    return _rgb_to_rgb565(np.asarray(canvas))

def _async_asset_loader(title, country, song, artist, gif_path):
    """Worker task that compiles frames at low system priority to protect the display loop thread."""
    global _pending_frames
    staging_frames = []
    gif_to_try = gif_path if gif_path else "uploads/vinyl.gif"
    
    base_canvas = _build_static_ui_base(title, country, song, artist)

    try:
        img = Image.open(gif_to_try)
        for f in ImageSequence.Iterator(img):
            rgba_f = f.convert('RGBA').resize((GIF_SIZE, GIF_SIZE))
            rgb_f = rgba_f.convert('RGB')
            frame_canvas = base_canvas.copy()
            frame_canvas.paste(rgb_f, (GIF_PASTE_X, GIF_PASTE_Y), rgba_f)
            staging_frames.append(bytearray(_rgb_to_rgb565(np.asarray(frame_canvas))))
            # Sleep slightly between frames to yield CPU to the render thread
            time.sleep(0.005)
    except Exception as e:
        print(f"Async loader failed caching asset {gif_to_try}: {e}")
        try:
            img = Image.open("uploads/vinyl.gif")
            for f in ImageSequence.Iterator(img):
                rgba_f = f.convert('RGBA').resize((GIF_SIZE, GIF_SIZE))
                rgb_f = rgba_f.convert('RGB')
                frame_canvas = base_canvas.copy()
                frame_canvas.paste(rgb_f, (GIF_PASTE_X, GIF_PASTE_Y), rgba_f)
                staging_frames.append(bytearray(_rgb_to_rgb565(np.asarray(frame_canvas))))
                time.sleep(0.005)
        except Exception as fb_e:
            print(f"Critical asset fallback failure: {fb_e}")

    if not staging_frames:
        staging_frames.append(bytearray(_rgb_to_rgb565(np.asarray(base_canvas))))

    _pending_frames = staging_frames
    _pending_ready.set()

def _display_loop(fps=30):
    frame_delay = 1.0 / fps
    last_minute = -1
    frame_idx = 0

    cached_raw_frames = []      
    clock_bytes_cache = b""     

    CLOCK_START_Y = 61
    CLOCK_STRIP_SIZE = 40 * FB_WIDTH * 2  
    CLOCK_START_BYTE = CLOCK_START_Y * FB_WIDTH * 2
    CLOCK_END_BYTE = CLOCK_START_BYTE + CLOCK_STRIP_SIZE

    local_title, local_country = "Nothing Playing", "No Country"
    local_song, local_artist = "Unknown", "Unknown"

    try:
        fb = open(FB_PATH, 'r+b')
        print("Hardware display loop loaded with non-blocking async pipeline.", flush=True)

        while _display_running.is_set():
            start_time = time.time()

            # 1. Thread state checking
            global state_changed, gif_path_to_load, _pending_frames
            with _state_lock:
                if state_changed:
                    local_title = title_text
                    local_country = country_text
                    local_offset = time_offset_str
                    local_song = song_name
                    local_artist = artist_name
                    local_gif_path = gif_path_to_load
                    gif_path_to_load = None
                    state_changed = False
                    
                    # Fire off the worker thread to compute everything in the background
                    _pending_ready.clear()
                    t = threading.Thread(
                        target=_async_asset_loader, 
                        args=(local_title, local_country, local_song, local_artist, local_gif_path),
                        daemon=True
                    )
                    t.start()

            # Check if the worker thread has safely cooked up the new frames
            if _pending_ready.is_set():
                if _pending_frames:
                    cached_raw_frames = _pending_frames
                    _pending_frames = None
                    frame_idx = 0
                    last_minute = -1  # Force clock slice recalculation
                _pending_ready.clear()

            # 2. Time-Keeping Management Tick
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
                clock_bytes_cache = _render_clock_strip_bytes(est_time_str, dest_time_str)

            # 3. Fast Blit Action Step
            n = len(cached_raw_frames)
            if n > 0:
                idx = frame_idx % n
                display_buffer = cached_raw_frames[idx]
                
                display_buffer[CLOCK_START_BYTE:CLOCK_END_BYTE] = clock_bytes_cache

                fb.seek(0)
                fb.write(display_buffer)
                fb.flush()

                if is_spinning.is_set():
                    frame_idx = (idx + 1) % n

            elapsed = time.time() - start_time
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        print("Error encountered in optimized display execution loop:", e, flush=True)
    finally:
        fb.seek(0)
        fb.write(bytes(FB_WIDTH * FB_HEIGHT * 2))
        fb.flush()
        fb.close()
        print("Display loop stopped safely, hardware screen cleared.", flush=True)

def start_display():
    global _display_thread
    if _display_running.is_set():
        return
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
