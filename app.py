from flask import Flask, render_template, jsonify, request, send_from_directory
import os, sys, threading, subprocess
from werkzeug.utils import secure_filename
import requests, math
import vlc
import time
from draw_screen import start_display, start_spin, stop_spin, set_text, set_album_art
import json
app = Flask(__name__, static_folder='templates', static_url_path='')

current_player = None
stop_flag = threading.Event()

# Global variables
found_radio_stations = []
saved_radio_stations = []

""" HELPER FUNCTIONS """






def get_stations(loc_id):
    """
        Gets all of the stations through a fetch to the radio garden API
    
        
        returns:
            radio_json : list of stations
            
    """
    global found_radio_stations
    radio_json = []
    radio_json.extend(read_saved_stations())
    radio_json.append({'title': '----------Found----------'}) 
    try:
        response = requests.get('https://radio.garden/api/ara/content/page/' + loc_id)
        if response.status_code == 200:
            temp_found_stations = []
            data = response.json()
            utc_offset = (data['data']['utcOffset']) 
            for channels in data['data']['content']:
                
                #print(channels['title'] + ": ")
                for item in channels['items']:
                    if item['page']['type'] == "channel":
                        
                        title = (item['page']['title'])
                        country = (item['page']['country']['title'])
                        url = ('http://radio.garden/api/ara/content/listen/' + item['page']['url'].split("/")[-1] + '/channel.mp3')
                        temp_found_stations.append({'title': title, 'country': country,'utcOffset': utc_offset, 'url': url})
            found_radio_stations = temp_found_stations
            radio_json.extend(found_radio_stations)

        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"A network error occurred: {e}")
    return radio_json



def _geo_distance(geo1, geo2):
    """Euclidean distance between two geo points (dict or sequence)."""
    if isinstance(geo1, dict):
        return math.hypot(geo1["lat"] - geo2["lat"], geo1["lon"] - geo2["lon"])
    return math.hypot(geo1[0] - geo2[0], geo1[1] - geo2[1])


def _collect_candidates(json_obj, candidates):
    """Recursively gather all (id, geo) pairs from the JSON structure."""
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
        gets min distance of all candidates
        
        returns:
            best candidate
    """
    candidates = []
    _collect_candidates(json_obj, candidates)
    if not candidates:
        return None
    return min(candidates, key=lambda c: _geo_distance(target_geo, c[1]))[0]



def play(url, station_name=None, station_country=None, time_offset=None, album_art_path="uploads/vinyl.gif"):
    """
        Plays the requested song
        Spawns player instance 
       
    """
    global current_player
    stop_flag.clear()
    try:
        resp = requests.get(url, allow_redirects=True, timeout=10, stream=True)
        resolved_url = resp.url
        resp.close()
        print(f"Resolved stream URL: {resolved_url}")
        instance = vlc.Instance('--aout=alsa')
        player = instance.media_player_new()
        current_player = player
        player.set_mrl(resolved_url)
        player.play()

        set_text(station_name or "Now Playing", station_country or "", time_offset or 0)
        start_spin()

        while not stop_flag.is_set():
            time.sleep(0.1)
            state = player.get_state()
            if state in [vlc.State.Ended, vlc.State.Error]:
                break
    except Exception as e:
        print("Error in play():", e)
    finally:
        stop_spin()
        set_text("Nothing Playing", "No Country", 0)  # only runs when actually stopping
        if current_player:
            current_player.stop()
        current_player = None



def write_json(new_data, filename):
    
    with open(filename, 'r') as file:
        file_data = json.load(file)
    entry_exists = any(entry["title"] == new_data['title'] for entry in file_data["saved_stations"])

    if (not entry_exists):
        with open(filename, 'w') as file:
            file_data["saved_stations"].append(new_data)
            json.dump(file_data, file, indent=4)
            global saved_radio_stations
            saved_radio_stations = file_data["saved_stations"]
            
        return jsonify({'status': 'ok', 'new_stations': compile_new_stations()}), 200
    else:
        return jsonify({'status': 'ok', 'new_stations': compile_new_stations()}), 200


def compile_new_stations():
    """
        Compiles new list of saved stations (called after removal and addition)
    
        returns: 
            station_list
    """    

    global saved_radio_stations
    global found_radio_stations

    station_list = []
    station_list.append({"title": "----------Saved----------"})
    station_list.extend(saved_radio_stations)
    station_list.append({"title": "----------Found----------"})
    station_list.extend(found_radio_stations)

    return station_list


""" FLASK ROUTES """

import random
# Serve static files (JS, CSS, etc.)
@app.route('/<path:filename>')
def serve_static(filename):
    if os.path.exists(os.path.join('templates', filename)):
        return send_from_directory('templates', filename)
    return render_template('index.html')

# serves root
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search_random', methods=['POST'])
def search_random():
    stations_json = []
    
    try: 
        response = requests.get('http://radio.garden/api/ara/content/places')   
        if response.status_code == 200:
            data = response.json()
            list_length = len(data['data']['list'])
            station_index = random.randint(0,list_length-1)
            
            station_code = data['data']['list'][station_index]['id']
            station_geo = data['data']['list'][station_index]['geo']  
            stations_json = get_stations(station_code)
            


        else:
            return jsonify({'status': '500, radio garden /places is down or cant connnect to server'}), 500
   

        return jsonify({'status': '200, OK', 'stations_geo' : station_geo , 'new_stations' : stations_json  , 'debug': "station cluster index: " + str(station_index) + ": Station code: " + station_code}), 200 
    
    except Exception as e:
        return jsonify({'status': '500, Flask server error' + str(e)}), 500   


@app.route('/get_radio_stations', methods=['POST'])
def get_radio_stations():
    """
        Gets all radio stations given a latitude and longitude
        
        returns:
            status : 200 or 500
            stations_json
    """
    data = request.get_json()
    lat = data.get('lat')
    lon = data.get('lon')
    stations_json = []
    try:
        response = requests.get('http://radio.garden/api/ara/content/places')    
        if response.status_code == 200:
            data = response.json()
            loc_id = ((_find_geo(data, [float(lon), float(lat)])))
            stations_json = (get_stations(loc_id))		
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        return jsonify({'status': '500, get_radio_stations ERROR', 'stations_json': stations_json}), 500  
    return jsonify({'status': '200, ok', 'stations_json': stations_json}), 200


@app.route('/play_station', methods=['POST'])
def play_station():
    """
        Spawns helper thread to play the requested station

        returns:
            status : 200 

    """
    stop_station()
    data = request.get_json()
    station_url = data.get('url')
    station_name = data.get('title')
    station_country = data.get('country')
    time_offset = data.get('time_offset')
    radio_thread = threading.Thread(
        target=play,
        daemon=True,
        args=(str(station_url),),
        kwargs={'station_name': station_name, 'station_country':station_country, 'time_offset': time_offset}
    )
    radio_thread.start()
    return jsonify({'status': '200, ok'}), 200

@app.route('/stop_station', methods=['POST'])
def stop_station():
    """
        Stops the currently playing station thread

        returns:
            status : 200

    """
    stop_flag.set()
    if current_player:
        current_player.stop()
    return jsonify({'status': '200, stopped'}), 200

@app.route('/read_saved_stations', methods=['POST'])
def read_saved_stations():
    """    
        Retrieves the saved stations from the file and adds needed title bar

        returns:
            List of saved radio station JSON objects        
    """
    global saved_radio_stations
    saved = [{'title': '----------Saved----------'}]
    temp_saved = []
    
    with open('saved_stations.json', 'r') as file:
        file_data = json.load(file)
    
    for entry in file_data['saved_stations']:
        temp_saved.append(entry)
    saved_radio_stations = temp_saved
    saved.extend(saved_radio_stations)
    
    return saved

@app.route('/add_to_saved', methods=['POST'])
def add_to_saved():
    """
        Adds the requested station to the saved stations file
    
        returns:
            Status: 200 or 500
            new_stations: newly compiled list of stations including the new saved            
      
    """
    data = request.get_json()
    station_url = data.get('url')
    station_name = data.get('title')
    station_country = data.get('country')
    time_offset = data.get('time_offset')
    new_entry = {
    'url' : station_url,
    'title' : station_name,
    'country' : station_country,
    'time_offset' : time_offset
    }  
    try:
        global saved_radio_stations
        status = write_json(new_entry, 'saved_stations.json')
        return status
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
    to_remove = request.get_json()
    station_name = to_remove.get('title')
    
    try:
        with open("saved_stations.json", "r") as file:
            data = json.load(file)

        for index, item in enumerate(data["saved_stations"]):
            if item.get('title') == station_name:
                data["saved_stations"].pop(index)
                break  # Stop looping after the first match is deleted
        with open("saved_stations.json", "w") as file:
            json.dump(data, file, indent=4)
        global saved_radio_stations
        saved_radio_stations = data["saved_stations"]
        return jsonify({'status': 'ok', 'new_stations': compile_new_stations()}), 200
    except Exception as e:
        return jsonify({'status': str(e)}), 500


if __name__ == "__main__":
    start_display()  # screen comes alive as soon as Flask starts
    set_album_art("uploads/vinyl.gif")  # default art shown even when idle
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=False)

