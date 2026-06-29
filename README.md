# worldRadio 🌍📻

A Raspberry Pi internet radio player powered by the [Radio Garden](https://radio.garden) API, with a web-based control interface and a live display on a PiTFT touchscreen.

<img width="1512" height="2016" alt="world_radio" src="https://github.com/user-attachments/assets/f9b30529-24ca-400e-848a-786e0299902f" />

## Features

- **Location-based station discovery** — search for radio stations by latitude/longitude, finding the nearest broadcast cluster via the Radio Garden API
- **Random station mode** — pick a random location anywhere in the world and load its stations
- **Saved stations** — bookmark favorite stations; they persist across sessions via `saved_stations.json`
- **Web UI** — browser-accessible interface served on port 8000 for browsing, playing, and managing stations
- **PiTFT display** (`/dev/fb1`) — shows station name, country, and local time for the station's timezone, with an animated spinning vinyl GIF while audio is playing
- **ALSA audio output** via `python-vlc`, with automatic stream URL resolution before playback

## Hardware

- Raspberry Pi 1 Model B (or similar)
- [Adafruit PiTFT 2.8"](https://www.adafruit.com/product/1601) (240×320 framebuffer display at `/dev/fb1`)
- Speaker or audio output via the Pi's 3.5mm jack

## Project Structure

```
worldRadio/
├── app.py               # Flask server — API routes, VLC playback, station logic
├── draw_screen.py       # Framebuffer display engine — GIF animation, text rendering, RGB565 output
├── shazam_helper.py     # Shazam song byte recording to get song name and artist
├── saved_stations.json  # Persisted list of saved stations
├── templates/           # Frontend HTML/JS/CSS
├── uploads/             # Album art / GIF assets (e.g. vinyl.gif)
└── todo.txt             # Notes and future plans
```

## How It Works

`app.py` runs a Flask server that:
1. Queries the Radio Garden `/places` API to find the nearest station cluster to a given coordinate
2. Fetches all channels at that location and resolves their stream URLs
3. Plays audio in a background thread using `python-vlc` with ALSA output
4. Manages saved stations by reading/writing `saved_stations.json`

`draw_screen.py` runs a separate display thread that:
1. Pre-composites GIF frames onto a background with station name and country text
2. Renders frames as RGB565 and writes them directly to `/dev/fb1` at ~24fps
3. Displays a live clock adjusted to the playing station's UTC offset
4. Animates the vinyl GIF while a station is playing; freezes on the current frame when stopped

`shazam_helper.py` gets called by `app.py` on interval to grab current song info


## Setup

### Dependencies

```bash
pip install flask requests python-vlc Pillow numpy
```

VLC must also be installed on the system:

```bash
sudo apt install vlc
```

### Running

```bash
python app.py
```

The server starts on `http://0.0.0.0:8000`. Open it in a browser on any device on your local network. The PiTFT display activates automatically on startup.

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/get_radio_stations` | Get stations near a `{lat, lon}` coordinate |
| `POST` | `/search_random` | Load stations from a random global location |
| `POST` | `/play_station` | Start playing a station |
| `POST` | `/stop_station` | Stop playback |
| `POST` | `/add_to_saved` | Save a station to `saved_stations.json` |
| `POST` | `/remove_from_saved` | Remove a station from saved list |
| `POST` | `/read_saved_stations` | Retrieve the saved station list |

## Notes

- Radio Garden's API is unofficial and undocumented — behavior may change
- The display engine writes raw RGB565 bytes directly to the framebuffer for performance; no X11 or desktop environment required
- The `uploads/vinyl.gif` is the default idle/playing animation; swap it out with any GIF via `set_album_art()`
