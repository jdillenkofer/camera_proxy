import av
import logging
from SimpleQueue import SimpleQueue as Queue

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
                packets = self.codec.parse(data)
                for packet in packets:
                    if packet.is_corrupt:
                        continue
                    frames = self.codec.decode(packet)
                    for frame in frames:
                        if frame.is_corrupt:
                            continue
                        image = frame.to_image()
                        for frame_callback in self.frame_callbacks:
                            frame_callback(image)
                        self.last_frame = image
            except Exception as e:
                print(e)
    
    def stop(self):
        self.running = False

    def queue_data(self, data):
        self.queue.put(data)
        logger.debug("Decoder queue size %d", self.queue.qsize())