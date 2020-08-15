import threading
from datetime import datetime
from camera import Camera
from decoder import Decoder

class CameraStreamManager:
    def __init__(self, camera_settings):
        self.camera_settings = camera_settings
        self.streams = []
        self.stream_lock = threading.RLock()
    
    def start_decoding_camera_stream(self, camera_name):
        camera_settings = self.get_camera_settings_by_name(camera_name)
        if camera_settings is None:
            return None
        
        stream = self.get_stream_by_name(camera_name)
        if stream is not None:
            return stream
        
        device_sid = camera_settings["deviceSid"]
        username = camera_settings["username"]
        password = camera_settings["password"]
        
        camera = Camera(device_sid, username, password)
        decoder = Decoder()
        def start_camera():
            camera.start(lambda data: decoder.handle_packet(data))
        
        camera_thread = threading.Thread(target=start_camera, name="CameraThread", daemon=True)
        camera_thread.start()

        stream = {}
        stream["name"] = camera_name
        stream["camera"] = camera
        stream["camera_thread"] = camera_thread
        stream["decoder"] = decoder
        stream["last_accessed"] = datetime.now()
        with self.stream_lock:
            self.streams.append(stream)
        return stream

    def stop_decoding_camera_stream(self, camera_name):
        stream = self.get_stream_by_name(camera_name)
        if stream is None:
            return False
        
        with self.stream_lock:
            self.streams.remove(stream)
        camera = stream["camera"]
        camera_thread = stream["camera_thread"]
        camera.stop()
        camera_thread.join()
        return True
    
    def is_stream_running(self, camera_name):
        return self.get_stream_by_name(camera_name) != None

    def update_last_accessed_timestamp(self, camera_name):
        stream = self.get_stream_by_name(camera_name)
        if stream is not None:
            stream["last_accessed"] = datetime.now()

    def get_camera_settings_by_name(self, camera_name):
        for camera_settings in self.camera_settings:
            if camera_settings["name"] == camera_name:
                return camera_settings
        return None
    
    def get_stream_by_name(self, camera_name):
        with self.stream_lock:
            for stream in self.streams:
                if stream["name"] == camera_name:
                    return stream
        return None