import av

class Decoder:
    def __init__(self):
        self.codec = av.CodecContext.create('h264', 'r')
        self.last_frame = None
        self.frame_callbacks = []

    def add_frame_callback(self, frame_callback):
        self.frame_callbacks.append(frame_callback)

    def handle_packet(self, stream):
        try:
            packets = self.codec.parse(stream)
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