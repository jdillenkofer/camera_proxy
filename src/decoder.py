from queue import Full
import av
import logging
from SimpleQueue import SimpleQueue as Queue
from datetime import datetime, time

logger = logging.getLogger(__name__)

def avg(list):
    length = len(list)
    return (sum(list)/length) if length > 0 else 0

class Decoder:
    def __init__(self):
        self.codec = av.CodecContext.create('h264', 'r')
        self.last_frame = None
        self.frame_callbacks = []
        self.queue = Queue(500)
        self.running = False
        self.last_data_queued = None

    def add_frame_callback(self, frame_callback):
        self.frame_callbacks.append(frame_callback)
    
    def remove_frame_callback(self, frame_callback):
        self.frame_callbacks.remove(frame_callback)

    def _dispatch_frames(self, frames):
        if frames == None or len(frames) == 0:
            return
        for frame_callback in self.frame_callbacks:
            frame_callback(frames)
        self.last_frame = frames[len(frames)-1]

    def _parse_decode_binary(self, data):
        return [frame.to_image() for packet in self.codec.parse(data) if packet.is_corrupt == False for frame in self.codec.decode(packet) if frame.is_corrupt == False]
    
    def process(self):
        self.running = True
        logger.info("Decoder deamon started")
        while self.running:
            try:
                timing = datetime.now()

                data = self.queue.get()

                if data == None or len(data) == 0:
                    continue

                time_acquire_lock = (datetime.now() - timing).total_seconds()
                
                
                timings=([], [])

                while True:
                    timing = datetime.now()
                    frames = self._parse_decode_binary(data)
                    timings[0].append((datetime.now() - timing).total_seconds())
                    timing = datetime.now()
                    self._dispatch_frames(frames)
                    timings[1].append((datetime.now() - timing).total_seconds())
                    if self.queue.empty() or data == None or len(data) == 0:
                        break
                    data = self.queue.get_nowait()

                    
                logger.info("Process - Acquire Lock: %.4fs, Frame Decoding: %.4fs, Dispatch frames: %.4fs, Dequeue Count: %d", time_acquire_lock, avg(timings[0]), avg(timings[1]), len(timings[1]))
                        
            except Exception as ex:
                logger.warning("Unexpected exception occured: %s, Traceback = ".format(str(ex)), exc_info=True)
    
    def stop(self):
        self.running = False
        self.queue._count.release()

    def _log_queued_time(self):
        #logger.debug("Decoder queue size %d", self.queue.qsize())
        if self.last_data_queued != None:
            elapsed = (datetime.now() - self.last_data_queued).total_seconds()
            if(elapsed >= 5):
                logger.info("Decoder queue size: %d", self.queue.qsize())
                self.last_data_queued = datetime.now()
        else:
            self.last_data_queued = datetime.now()

    def queue_data(self, data):
        try:
            self.queue.put(data)
            self._log_queued_time()
        except Full:
            logger.info("Decoder queue size is FULL: %d", self.queue.qsize())
