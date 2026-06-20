from flask import Flask, render_template, jsonify, request, send_from_directory
import os, sys, threading, subprocess
from werkzeug.utils import secure_filename

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
