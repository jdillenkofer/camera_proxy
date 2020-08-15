import json
import io
import time
import logging
import argparse
import threading
from queue import Queue
from datetime import datetime
from camera import Camera
from flask import Flask, send_file, request, Response
from PIL import Image
from decoder import Decoder

app = Flask(__name__)

logger = logging.getLogger(__name__)

def load_secrets_from_file(filename):
    secrets = {}
    with open(filename) as secret_file:
        secrets = json.load(secret_file)
    return secrets

secrets = load_secrets_from_file("secrets.json")
device_sid = secrets["deviceSid"]
username = secrets["username"]
password = secrets["password"]

decoder = Decoder()
camera = None
camera_thread = None
last_accessed = datetime.now()

def start_decoding_camera_stream():
    global decoder
    global camera
    global camera_thread
    decoder = Decoder()
    camera = Camera(device_sid, username, password)
    def start_camera():
        camera.start(lambda data: decoder.handle_packet(data))
        
    camera_thread = threading.Thread(target=start_camera, name="CameraThread", daemon=True)
    camera_thread.start()

def is_decoding_camera_stream():
    global camera_thread
    return camera_thread != None

def stop_decoding_camera_stream():
    global decoder
    global camera
    global camera_thread
    decoder = Decoder()
    camera.stop()
    camera_thread.join()
    camera = None
    camera_thread = None

def update_last_accessed_timestamp():
    global last_accessed
    last_accessed = datetime.now()

def stop_camera_daemon():
    global last_accessed
    while True:
        if is_decoding_camera_stream() and last_accessed != None and (datetime.now() - last_accessed).total_seconds() > 45:
            logger.info("Stopping camera stream")
            stop_decoding_camera_stream()
        time.sleep(5)

stop_camera_daemon_thread = threading.Thread(target=stop_camera_daemon, name="StopCameraDaemon", daemon=True)
stop_camera_daemon_thread.start()

@app.route('/api/v1/cameras/door/stream', methods=["GET"])
def get_image_stream_from_camera():
    update_last_accessed_timestamp()
    if not is_decoding_camera_stream():
        start_decoding_camera_stream()
    
    queue = Queue()
    decoder.add_frame_callback(lambda x: queue.put(x))

    def frame_generator():
        while True:
            update_last_accessed_timestamp()
            frame = queue.get()
            output = io.BytesIO()
            frame.save(output, 'JPEG')
            output.seek(0)
            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + output.read() + b'\r\n')
    return Response(frame_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/v1/cameras/door', methods=["GET"])
def get_image_from_camera():
    thumbnail_requested = request.args.get('thumbnail') != None

    update_last_accessed_timestamp()
    if not is_decoding_camera_stream():
        start_decoding_camera_stream()
    
    i = 0
    while i < 100:
        last_frame = decoder.last_frame
        if last_frame != None:
            output = io.BytesIO()
            last_frame_clone = last_frame.copy()
            if thumbnail_requested:
                last_frame_clone.thumbnail((800, 474), Image.ANTIALIAS)
            last_frame_clone.save(output, 'JPEG')
            output.seek(0)
            return send_file(output, mimetype='image/jpeg')
        else:
            time.sleep(0.1)
            i += 1
    return send_file("../public/images/klingel.jpg")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='A small webserver to extract images from the reolink argus 2 camera.')
    parser.add_argument("--debug", dest="debug", action="store_true", help="Starts the server in debug mode.")
    parser.add_argument("--port", dest="port", help="Set the webserver port.", default=8000, type=int, choices=range(0,65536), metavar="{0..65535}")
    parser.set_defaults(debug=False)
    
    args = parser.parse_args()
    debug = args.debug
    port = args.port
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    app.run(debug=debug, port=port, host='0.0.0.0')
