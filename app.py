from flask import Flask, render_template, jsonify, request, send_from_directory
import os, sys, threading, subprocess
from werkzeug.utils import secure_filename
import requests, math
import vlc
import time
app = Flask(__name__, static_folder='templates', static_url_path='')

# Serve static files (JS, CSS, etc.)
@app.route('/<path:filename>')
def serve_static(filename):
    if os.path.exists(os.path.join('templates', filename)):
        return send_from_directory('templates', filename)
    return render_template('index.html')

@app.route('/')
def home():
    return render_template('index.html')





    

def get_stations(loc_id):
    
    radio_json = []

    try:
        response = requests.get('https://radio.garden/api/ara/content/page/' + loc_id)
        if response.status_code == 200:
            data = response.json()
            for channels in data['data']['content']:
                
                #print(channels['title'] + ": ")
                for item in channels['items']:
                    if item['page']['type'] == "channel":
                        
                        title = (item['page']['title'])
                        country = (item['page']['country']['title'])
                        url = ('http://radio.garden/api/ara/content/listen/' + item['page']['url'].split("/")[-1] + '/channel.mp3')
                        
                        radio_json.append({'title': title, 'country': country, 'url': url})
            

        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"A network error occurred: {e}")
    return radio_json


# helper for find_geo
def is_close(target_geo, given_geo):
	closeness = .50
	return math.dist(target_geo, given_geo) <= closeness

# helper for get_loc_id
def find_geo(json_obj, target_geo):
    if isinstance(json_obj, dict):
        if "geo" in json_obj and is_close(target_geo, json_obj["geo"]):
            return json_obj["id"]
        for value in json_obj.values():
            result = find_geo(value, target_geo)
            if result is not None:
                return result
    elif isinstance(json_obj, list):
        for item in json_obj:
            result = find_geo(item, target_geo)
            if result is not None:
                return result
    return None



# gets the id of the location
def get_loc_id():

	try:
		response = requests.get('http://radio.garden/api/ara/content/places')
    
		if response.status_code == 200:
			data = response.json()
		    # 52.28895497254308, 20.618328365871974	
			loc_id = ((find_geo(data, [  20.618328365871974	, 52.28895497254308])))
			print(loc_id)
			print(json.dumps(get_stations(loc_id)))
			
			#print(f"API Version: {data['apiVersion']}")
			#print(f"size: {data['data']['list'][0]['size']}")
		else:
			print(f"Failed to fetch data. Status code: {response.status_code}")

	except requests.exceptions.RequestException as e:
		print(f"A network error occurred: {e}")



@app.route('/get_radio_stations', methods=['POST'])
def get_radio_stations():
  data = request.get_json()
  lat = data.get('lat')
  lon = data.get('lon')
  stations_json = []
  try:
    response = requests.get('http://radio.garden/api/ara/content/places')    
    if response.status_code == 200:
      data = response.json()
		    # 52.28895497254308, 20.618328365871974	
      loc_id = ((find_geo(data, [float(lon), float(lat)])))
      print(loc_id)
      stations_json = (get_stations(loc_id))		
			#print(f"API Version: {data['apiVersion']}")
			#print(f"size: {data['data']['list'][0]['size']}")
    else:
      print(f"Failed to fetch data. Status code: {response.status_code}")
  except requests.exceptions.RequestException as e:
    print(f"A network error occurred: {e}")
  return jsonify({'status': '200, ok', 'stations_json': stations_json}), 200








import threading

current_player = None
stop_flag = threading.Event()

def play(url):
    global current_player
    stop_flag.clear()
    try:
        resp = requests.get(url, allow_redirects=True, timeout=10, stream=True)
        resolved_url = resp.url
        resp.close()
        print(f"Resolved stream URL: {resolved_url}")
        instance = vlc.Instance('--aout=alsa', '--alsa-audio-device=plughw:1,0')
        player = instance.media_player_new()
        current_player = player
        player.set_mrl(resolved_url)
        player.play()
        print("Streaming audio... Press Ctrl+C to stop.")
        while not stop_flag.is_set():
            time.sleep(1)
            state = player.get_state()
            print("VLC state:", state)
            if state in [vlc.State.Ended, vlc.State.Error]:
                break
    except Exception as e:
        print("Error in play():", e)
    finally:
        if current_player:
            current_player.stop()
        current_player = None

@app.route('/play_station', methods=['POST'])
def play_station():
    stop_station()

    data = request.get_json()
    station_url = data.get('url')
    radio_thread = threading.Thread(target=play, daemon=True, args=(str(station_url),))
    radio_thread.start()
    return jsonify({'status': '200, ok'}), 200

@app.route('/stop_station', methods=['POST'])
def stop_station():
    stop_flag.set()
    if current_player:
        current_player.stop()
    return jsonify({'status': '200, stopped'}), 200











ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Configure upload folder and limit file size (e.g., 16MB max)
UPLOAD_FOLDER = './uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Create the folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    # 1. Check if the file part is in the request
    if 'my_file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['my_file']

    # 2. Check if the user selected an empty file
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        # 3. Clean the filename to prevent directory traversal attacks
        filename = secure_filename(file.filename)

        # 4. Save the file to your folder
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        return jsonify({"status": f"File {filename} successfully uploaded!"}), 200

@app.route('/getImages', methods=['GET'])
def get_file():
	folder_path = UPLOAD_FOLDER
	files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
	return jsonify({"status": "200", "files": files})


@app.route('/displayImage', methods=['POST'])
def display_image():
    try:
        data = request.json
        image_path = data.get('imagePath')
        if not image_path:
            return jsonify({"status": "400 - missing imagePath"}), 400
        
        # Kill any existing display-image processes
        subprocess.run(["killall", "display-image.sh"], capture_output=True)
        
        # Start the wrapper script
        subprocess.Popen(["/usr/local/bin/display-image.sh", image_path])
        
        return jsonify({"status": "200"})
    except Exception as e:
        return jsonify({"status": f"555 - {str(e)}"}), 500

@app.route('/killDisplay', methods=['POST'])
def kill_display():
    try:
        subprocess.run(["killall", "display-image.sh"], capture_output=True)
        subprocess.run(["killall", "fbi"], capture_output=True)
        return jsonify({"status": "200 - Display killed"})
    except Exception as e:
        return jsonify({"status": f"555 - {str(e)}"}), 500



@app.route('/checkService', methods=['POST'])
def checkService():
	try:
		data = request.json
		service = data.get('serviceName')
		if not service:
			return jsonify({"status": "400 - missing service name"}), 400



		isRunning = subprocess.run(
                	["systemctl", "is-active", "--quiet", service],
            		check=False
        	)

		return jsonify({"status": "200","isRunning": isRunning.returncode == 0})  

	except Exception as e:
		return jsonify({"status": f"555 - {str(e)}"}), 500   




@app.route('/stopService', methods=['POST'])
def stopService():
    try:
        data = request.json
        service = data.get('serviceName')  # Should be 'dashboard' not 'dashboard.service'
        
        allowed_services = ['dashboard', 'flaskapp']
        if service not in allowed_services:
            return jsonify({"status": "400 - Service not allowed"}), 400
        
        result = subprocess.run(
            ["sudo", "systemctl", "stop", service],
            check=False,
            capture_output=True,
            text=True
        )
        
        return jsonify({
            "status": "200" if result.returncode == 0 else f"Failed - {result.stderr}",
            "isRunning": False if result.returncode == 0 else True
        })
    except Exception as e:
        return jsonify({"status": f"555 - {str(e)}"}), 500



@app.route('/startService', methods=['POST'])
def startService():
    try:
        data = request.json
        service = data.get('serviceName')  # Should be 'dashboard' not 'dashboard.service'
        
        allowed_services = ['dashboard', 'flaskapp']
        if service not in allowed_services:
            return jsonify({"status": "400 - Service not allowed"}), 400
        
        result = subprocess.run(
            ["sudo", "systemctl", "start", service],
            check=False,
            capture_output=True,
            text=True
        )
        
        return jsonify({
            "status": "200" if result.returncode == 0 else f"Failed - {result.stderr}",
            "isRunning": False if result.returncode != 0 else True
        })
    except Exception as e:
        return jsonify({"status": f"555 - {str(e)}"}), 500



if __name__ == '__main__':
    # Start the local development server
    app.run(host='0.0.0.0', port=8000, debug=True)
