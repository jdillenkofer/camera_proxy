from queue import Full
import av
import logging
from SimpleQueue import SimpleQueue as Queue
from datetime import datetime, time, timedelta

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
        self.last_data_logged = None
        self.avg_process_time = 0
        self.reduction_factor = 1
        self.last_data_processed = None

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
                    self.last_data_processed = datetime.now()
                    avg_decode_time = avg(timings[0])
                    avg_dispatch_time = avg(timings[1])
                    self.avg_process_time = avg_decode_time + avg_dispatch_time
                    self._calc_reduction_factor()
                    self._log_timings()
                    if self.queue.empty():
                        break
                    data = self.queue.get_nowait()

                
                logger.debug("Process - Reduction Factor: %.2f, Acquire Lock: %.4fs, Frame Decoding: %.4fs, Dispatch frames: %.4fs, Dequeue Count: %d",self.reduction_factor, time_acquire_lock, avg_decode_time, avg_dispatch_time, len(timings[1]))
                        
            except Exception as ex:
                logger.warning("Unexpected exception occured: %s, Traceback = ".format(str(ex)), exc_info=True)
    
    def stop(self):
        self.running = False
        self.queue._count.release()

    def _log_timings(self):
        if self.last_data_logged != None:
            elapsed = (datetime.now() - self.last_data_logged).total_seconds()
            if(elapsed >= 5):
                logger.info("Decoder - Reduction Factor: %.2f, Queue size: %d, Processing time avg: %.4fs", self.reduction_factor, self.queue.qsize(), self.avg_process_time)
                self.last_data_logged = datetime.now()
        else:
            self.last_data_logged = datetime.now()

    def _calc_reduction_factor(self):
        #Calculate the reduction factor in order to keep the queue balanced to distach data
        q_maxlen = self.queue.maxlen
        q_len = self.queue.qsize()
        q_percent_full = q_len/q_maxlen
        self.reduction_factor = 1 - q_percent_full
    
    def _should_queue_data(self):
        #According to the reduction factor, time spent for processing
        #return intervalving data to be queued
        #TODO: For the next feature, enhance the calculation in order to select proper frames to drop (Intra-coded and/or Predicted ones)
        if self.reduction_factor == 1 or self.last_data_processed == None:
            return True
        
        if self.reduction_factor == 0:
            return False

        dt_delta = self.last_data_processed + (timedelta(seconds=self.queue.qsize()*(self.avg_process_time/self.reduction_factor)))

        return datetime.now() > dt_delta

    def queue_data(self, data):
        try:
            if (data == None or len(data) == 0) or not self._should_queue_data():
                return
            self.queue.put(data)
        except Full:
            logger.info("Decoder queue size is FULL: %d", self.queue.qsize())
