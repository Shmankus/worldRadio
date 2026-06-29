import threading, time, httpx, asyncio
from shazamio import Shazam
from draw_screen import start_display, start_spin, stop_spin, set_text
current_station_url = None
counter_lock = threading.Lock()
failed_match_count = 0


SHAZAM_CHUNK_SIZE = 80000

def call_song_recognition(stop_flag,song_recognition_cancel, resolved_url, station_name, station_country, time_offset):
    global current_station_url, failed_match_count

    song_recognition_cancel.set()
    song_recognition_cancel = threading.Event()

    with counter_lock:
        if current_station_url != resolved_url:
            current_station_url = resolved_url
            failed_match_count = 0

    t = threading.Thread(
        target=get_song_name,
        args=(resolved_url, station_name, station_country, time_offset, song_recognition_cancel, stop_flag),
        daemon=True
    )
    t.start()

def get_song_name(resolved_url, station_name, station_country, time_offset, cancel_flag, stop_flag):
    global failed_match_count
  

    try:
        os.nice(19)
    except:
        pass

    if cancel_flag.is_set() or stop_flag.is_set():
        print("Shazam thread killed", flush=True)
        return

    # 3 second buffer for new station
    time.sleep(3.0)

    # Check if the station was changed or stopped
    if cancel_flag.is_set() or stop_flag.is_set():
        return

    CHUNK_SIZE = SHAZAM_CHUNK_SIZE
    audio_bytes = b""

    try:
        limits = httpx.Limits(max_keepalive_connections=1, max_connections=1)
        with httpx.Client(follow_redirects=True, timeout=5.0, limits=limits) as client:
            # Check again right before opening the stream connection
            if cancel_flag.is_set() or stop_flag.is_set():
                print("Shazam thread killed", flush=True)
                return

            with client.stream("GET", resolved_url) as response:
                first_chunk = True
                for chunk in response.iter_bytes():
                    if cancel_flag.is_set() or stop_flag.is_set():
                        print("Shazam thread killed", flush=True)
                        return

                    if first_chunk:
                        first_chunk = False
                        continue

                    audio_bytes += chunk
                    if len(audio_bytes) >= CHUNK_SIZE:
                        break
    except Exception as e:
        if cancel_flag.is_set() or stop_flag.is_set():
            return
        print(f"Stream collection interrupted: {e}", flush=True)
        return

    # check after gathering song bytes
    if cancel_flag.is_set() or stop_flag.is_set() or len(audio_bytes) < 50000:
        print("Shazam thread killed due to not enough bytes", flush=True)
        return

    # Actual giving shazam sound bytes and recieving the song details
    try:
        shazam = Shazam()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(shazam.recognize(audio_bytes))
        finally:
            loop.close()

        if cancel_flag.is_set() or stop_flag.is_set():
            print("Shazam thread killed after shazam read", flush=True)
            return

        if result and 'track' in result:
            track_title = result['track']['title']
            artist = result['track']['subtitle']
            print(f"Found: {artist} - {track_title}", flush=True)
            set_text(station_name or "Now Playing", station_country or "", time_offset or 0, track_title, artist)
            # erase attempts
            with counter_lock:
                failed_match_count = 0
        # attempt logic
        else:
            with counter_lock:
                failed_match_count += 1
                if failed_match_count >= 3:
                    print("Match not found. Max retries exceeded.", flush=True)
                    set_text(station_name or "Now Playing", station_country or "", time_offset or 0, "Unknown Track", "Unknown Artist")
                else:
                    print(f"Retrying shazam: {failed_match_count}/3")

    except Exception as e:
        print(f"Recognition Engine Fault: {e}", flush=True)
