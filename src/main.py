import json
import io
import time
import logging
import argparse
import threading
import math
from datetime import datetime
from multiprocessing import SimpleQueue as Queue
from flask import Flask, send_file, request, Response, abort
from PIL import Image
from camera_stream_manager import CameraStreamManager

app = Flask(__name__)

logger = logging.getLogger(__name__)

def load_settings_from_file(filename):
    settings = {}
    with open(filename) as settings_file:
        settings = json.load(settings_file)
    return settings

settings = load_settings_from_file("settings.json")
camera_settings = settings["cameras"]

camera_stream_manager = CameraStreamManager(camera_settings)

def stop_camera_daemon():
    global camera_stream_manager
    while True:
        with camera_stream_manager.stream_lock:
            for stream in camera_stream_manager.streams:
                name = stream["name"]
                last_accessed = stream["last_accessed"]
                if (datetime.now() - last_accessed).total_seconds() > 30:
                    logger.info("Stopping camera stream %s", name)
                    #camera_stream_manager.stop_decoding_camera_stream(name)
        time.sleep(5)

stop_camera_daemon_thread = threading.Thread(target=stop_camera_daemon, name="StopCameraDaemon", daemon=True)
stop_camera_daemon_thread.start()

def start_camera_stream(name):
    camera_stream_manager.update_last_accessed_timestamp(name)
    stream = None
    if not camera_stream_manager.is_stream_running(name):
        stream = camera_stream_manager.start_decoding_camera_stream(name)
    
    if stream is None:
        stream = camera_stream_manager.get_stream_by_name(name)
    return stream

@app.route('/api/v1/cameras/<name>/stream', methods=["GET"])
def get_image_stream_from_camera(name):
    stream = start_camera_stream(name)
    
    if stream is None:
        abort(404)
    decoder = stream["decoder"]
    queue = Queue()
    frame_callback = lambda x: queue.put(x)
    decoder.add_frame_callback(frame_callback)

    def frame_generator():
        try:
            output = io.BytesIO()
            frameCounter = 0
            lasFrameSentTime = datetime.now()
            while True:
                camera_stream_manager.update_last_accessed_timestamp(name)

                frames = queue.get()
                
                for frame in frames:
                    frame.save(output, 'JPEG')
                    length = output.tell()
                    output.seek(0)
                    
                    yield (b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\nContent-Length: ' + str(length).encode() + b'\r\n\r\n' + output.read() + b'\r\n')
                    
                    #Reset output buffer
                    output.truncate()
                    output.seek(0)

                frameCounter += len(frames)

                elapsed = (datetime.now() - lasFrameSentTime).total_seconds()
                if elapsed >= 1:
                    logger.debug("Stream Queue Size: %d", queue.qsize())
                    logger.info("FPS: %d", math.floor(frameCounter/elapsed))
                    frameCounter = 0
                    lasFrameSentTime = datetime.now()
                
        finally:
            decoder.remove_frame_callback(frame_callback)
    return Response(frame_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/v1/cameras/<name>', methods=["GET"])
def get_image_from_camera(name):
    stream = start_camera_stream(name)
    
    if stream is None:
        abort(404)
    decoder = stream["decoder"]

    thumbnail_requested = request.args.get('thumbnail') != None

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
    backup_image = stream["backup_image"]
    if backup_image != None:
        return send_file(backup_image)
    else:
        abort(404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='A small webserver to extract images from reolink cameras.')
    parser.add_argument("--debug", dest="debug", action="store_true", help="Starts the server in debug mode.")
    parser.add_argument("--port", dest="port", help="Set the webserver port.", default=8000, type=int, choices=range(0,65536), metavar="{0..65535}")
    parser.set_defaults(debug=False)
    
    args = parser.parse_args()
    debug = args.debug
    port = args.port
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    app.run(debug=debug, port=port, host='0.0.0.0')
else:
    logging.basicConfig(level=logging.DEBUG)
