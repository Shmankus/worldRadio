from flask import Flask, render_template, jsonify, request, send_from_directory
import os, sys, threading, subprocess
from werkzeug.utils import secure_filename
import requests, math
import vlc
import time
import json
import asyncio
import random

# draw_screen.py
from draw_screen import start_display, start_spin, stop_spin, set_text

# Needed for Shazam
from shazam_helper import call_song_recognition, get_song_name

app = Flask(__name__, static_folder='templates', static_url_path='')

# Checks for when station logic needs to stop
current_player = None
stop_flag = threading.Event()
song_recognition_cancel = threading.Event()

# Global variable caches
found_radio_stations = []
saved_radio_stations = []

# Global variables
SHAZAM_CHECK_INTERVAL = 20

""" HELPER FUNCTIONS """

def get_stations(loc_id):
    """
        Gets all of the stations given the geocoord loc_id 
    
        params:
            loc_id : ID from json that ties it to geocoords
        
        returns:
            radio_json : list of stations
            
    """
    global found_radio_stations
    radio_json = []
    radio_json.extend(read_saved_stations())
    radio_json.append({'title': '----------Found----------'})
    try:
        response = requests.get(f'https://radio.garden/api/ara/content/page/{loc_id}', timeout=5)
        if response.status_code == 200:
            temp_found_stations = []
            data = response.json()
            utc_offset = data['data'].get('utcOffset', 0)
            for channels in data['data'].get('content', []):
                for item in channels.get('items', []):
                    if item.get('page', {}).get('type') == "channel":
                        page = item['page']
                        title = page['title']
                        country = page.get('country', {}).get('title', '')
                        url = f'http://radio.garden/api/ara/content/listen/{page["url"].split("/")[-1]}/channel.mp3'
                        temp_found_stations.append({'title': title, 'country': country, 'utcOffset': utc_offset, 'url': url})
            found_radio_stations = temp_found_stations
            radio_json.extend(found_radio_stations)
    except Exception as e:
        print(f"Radio Garden Fetch Error: {e}")
    return radio_json

def _geo_distance(geo1, geo2):
    """ Distance of two coordinates """
    return math.hypot(geo1[0] - geo2[0], geo1[1] - geo2[1])

def _collect_candidates(json_obj, candidates):
    """
        Collects all candidates in JSON to find the shortest distance from requested coords

        params:
            json_obj : full json 
            candidates : current set of candidate nested objects

    """
    if isinstance(json_obj, dict):
        if "geo" in json_obj and "id" in json_obj:
            candidates.append((json_obj["id"], json_obj["geo"]))
        for value in json_obj.values():
            _collect_candidates(value, candidates)
    elif isinstance(json_obj, list):
        for item in json_obj:
            _collect_candidates(item, candidates)

def _find_geo(json_obj, target_geo):
    """
        gets min distance of all candidates and returns the loc_id

        params:
            json_obj : full json object from API
            target_geo : requested geocoords
        returns:
            best candidate loc_id
    """
    candidates = []
    _collect_candidates(json_obj, candidates)
    if not candidates:
        return None
    return min(candidates, key=lambda c: _geo_distance(target_geo, c[1]))[0]

def play(url, station_name=None, station_country=None, time_offset=None):

    """
    Handles audio stream connection and initiates background media playback loop.

    Parameters:
        url (str): Direct endpoint address of the media stream.
        station_name (str, optional): Label identifier for the active source.
        station_country (str, optional): Geographic origin metadata.
        time_offset (int, optional): Temporal variance value relative to UTC.

    Returns:
        None
    """

    global current_player
    stop_flag.clear()

    try:
        with requests.get(url, allow_redirects=True, timeout=5, stream=True) as resp:
            resolved_url = resp.url
        
        print(f"Resolved Stream: {resolved_url}")
        # plays current stream
        instance = vlc.Instance('--aout=alsa')
        player = instance.media_player_new()
        current_player = player
        player.set_mrl(resolved_url)
        player.play()
        
        set_text(station_name or "Now Playing", station_country or "", time_offset or 0, "Searching...", "Shazam")
        start_spin()
        
        last_call = time.time() - SHAZAM_CHECK_INTERVAL - 5  # Trigger lookups immediately upon connecting

        while not stop_flag.is_set():
            time.sleep(0.5)
            
            # Check if stop was requested during the sleep window
            if stop_flag.is_set():
                break

            state = player.get_state()
            if state in [vlc.State.Ended, vlc.State.Error]:
                break
             
            now = time.time()
            if now - last_call >= SHAZAM_CHECK_INTERVAL: # 30 second shazam check interval
                # last stop check
                if not stop_flag.is_set():
                    call_song_recognition(stop_flag,song_recognition_cancel, resolved_url, station_name, station_country, time_offset)
                last_call = now        
            

    except Exception as e:
        print("Error in play():", e)
    finally:
        song_recognition_cancel.set()
        stop_spin()
        set_text("Nothing Playing", "No Country", 0, "Unknown", "Unknown")
        if current_player:
            current_player.stop()
        current_player = None

def compile_new_stations():
    global saved_radio_stations, found_radio_stations
    return [{"title": "----------Saved----------"}] + saved_radio_stations + [{"title": "----------Found----------"}] + found_radio_stations

""" FLASK ROUTES """

@app.route('/<path:filename>')
def serve_static(filename):
    if os.path.exists(os.path.join('templates', filename)):
        return send_from_directory('templates', filename)
    return render_template('index.html')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search_random', methods=['POST'])
def search_random():
    """
        Parses the big json for a random index and finds the stations aligned with the coordinates/index

    """
    try:
        response = requests.get('http://radio.garden/api/ara/content/places', timeout=5)
        if response.status_code == 200:
            data = response.json()
            places_list = data['data']['list']
            chosen = random.choice(places_list)
            return jsonify({
                'status': '200, OK', 
                'stations_geo': chosen['geo'], 
                'new_stations': get_stations(chosen['id'])
            }), 200
        return jsonify({'status': '500 Downstream Error'}), 500
    except Exception as e:
        return jsonify({'status': f'500 Server Error: {e}'}), 500

@app.route('/get_radio_stations', methods=['POST'])
def get_radio_stations():
    """
    Gets all radio stations given a latitude and longitude.
    """
    data = request.get_json() or {}
    lat, lon = data.get('lat'), data.get('lon')
    if not lat or str(lat).strip() == "":
        return jsonify({'status': '200, ok', 'stations_json': []}), 200
    try:
        response = requests.get('http://radio.garden/api/ara/content/places', timeout=5)
        if response.status_code == 200:
            loc_id = _find_geo(response.json(), [float(lon), float(lat)])
            return jsonify({'status': '200, ok', 'stations_json': get_stations(loc_id)}), 200
    except Exception as e:
        return jsonify({'status': f'500 Error: {e}', 'stations_json': []}), 500
    return jsonify({'status': '200, ok', 'stations_json': []}), 200


@app.route('/play_station', methods=['POST'])
def play_station():
    """
    Spawns helper thread to play the requested station
    """
    stop_station()
    data = request.get_json() or {}
    time.sleep(1) # fixes async issue with shazam ???
    radio_thread = threading.Thread(
        target=play,
        daemon=True,
        args=(str(data.get('url')),),
        kwargs={
            'station_name': data.get('title'),
            'station_country': data.get('country'),
            'time_offset': data.get('time_offset')
        }
    )
    radio_thread.start()
    return jsonify({'status': '200, ok'}), 200


@app.route('/stop_station', methods=['POST'])
def stop_station():
    """
    Stops the currently playing station thread
    """
    stop_flag.set()
    if current_player:
        current_player.stop()
    return jsonify({'status': '200, stopped'}), 200

@app.route('/read_saved_stations', methods=['POST', 'GET'])
def read_saved_stations():
    """    
        Retrieves the saved stations from the file and adds needed title bar
        returns:
        List of saved radio station JSON objects        
    """
    global saved_radio_stations
    if not os.path.exists('saved_stations.json'):
        with open('saved_stations.json', 'w') as file:
            json.dump({"saved_stations": []}, file)
    try:
        with open('saved_stations.json', 'r') as file:
            file_data = json.load(file)
        saved_radio_stations = file_data.get('saved_stations', [])
    except Exception as e:
        print(f"JSON Read Error: {e}")
    return [{'title': '----------Saved----------'}] + saved_radio_stations

@app.route('/add_to_saved', methods=['POST'])
def add_to_saved():
    """
        Adds the requested station to the saved stations file

        returns:
            Status: 200 or 500
            new_stations: newly compiled list of stations including the new saved            
      
    """
    data = request.get_json() or {}
    new_entry = {
        'url': data.get('url'),
        'title': data.get('title'),
        'country': data.get('country'),
        'utcOffset': data.get('time_offset')
    }
    try:
        read_saved_stations()
        if not any(entry["title"] == new_entry['title'] for entry in saved_radio_stations):
            saved_radio_stations.append(new_entry)
            with open('saved_stations.json', 'w') as file:
                json.dump({"saved_stations": saved_radio_stations}, file, indent=4)
        return jsonify({'status': 'ok', 'new_stations': compile_new_stations()}), 200
    except Exception as e:
        return jsonify({'status': str(e)}), 500

@app.route('/remove_from_saved', methods=['POST'])
def remove_from_saved():
    """
        Removes the requested station from the saved stations file

        returns:
            status: 200 or 500
            new_stations: newly compiled list of stations excluding the requested station
    """    
    to_remove = request.get_json() or {}
    station_name = to_remove.get('title')
    try:
        read_saved_stations()
        global saved_radio_stations
        saved_radio_stations = [item for item in saved_radio_stations if item.get('title') != station_name]
        with open("saved_stations.json", "w") as file:
            json.dump({"saved_stations": saved_radio_stations}, file, indent=4)
        return jsonify({'status': 'ok', 'new_stations': compile_new_stations()}), 200
    except Exception as e:
        return jsonify({'status': str(e)}), 500

if __name__ == "__main__":
    start_display()
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)
