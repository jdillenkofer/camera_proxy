import av
import logging
import Queue

logger = logging.getLogger(__name__)

class Decoder:
    def __init__(self):
        self.codec = av.CodecContext.create('h264', 'r')
        self.last_frame = None
        self.frame_callbacks = []
        self.queue = Queue()
        self.running = False

    def add_frame_callback(self, frame_callback):
        self.frame_callbacks.append(frame_callback)
    
    def remove_frame_callback(self, frame_callback):
        self.frame_callbacks.remove(frame_callback)
    
    def process(self):
        self.running = True
        while self.running:
            try:
                data = self.queue.get()
                
                frames = [(frame.to_image() for frame in self.codec.decode(packet) if not frame.is_corrupt) for packet in self.codec.parse(data) if not packet.is_corrupt]

                if frames != None and len(frames) > 0:
                    for frame_callback in self.frame_callbacks:
                        frame_callback(frames)
                    self.last_frame = frames[len(frames)-1]
                        
            except Exception as e:
                print(e)
    
    def stop(self):
        self.running = False

    def queue_data(self, data):
        self.queue.put(data)
        logger.debug("Decoder queue size %d", self.queue.qsize())