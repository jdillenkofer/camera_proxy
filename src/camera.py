import random
import socket
import struct
import logging
import xml.etree.ElementTree as ElementTree
import baichuan_udp_layer
import baichuan_control_layer
from datetime import datetime

MAX_INT32 = 0x7FFFFFFF

logger = logging.getLogger(__name__)

class Camera:
    def __init__(self, device_sid, username, password):
        self.device_sid = device_sid
        self.username = username
        self.password = password
        self.is_running = False

    def start(self, handle_video_stream):
        self.is_running = True
        while self.is_running:
            try:
                self._start_stream(handle_video_stream)
            except Exception as e:
                logger.error("Exception occured: %s Trying to reconnect the camera stream...", e)
    
    def _start_stream(self, handle_video_stream):
        client_id = random.randint(0, MAX_INT32)

        udp_layer = baichuan_udp_layer.BaichuanUdpLayer(self.device_sid, client_id)
        control_layer = baichuan_control_layer.BaichuanControlLayer(self.username, self.password, udp_layer)

        udp_layer.discover_device()

        logger.info("Sending legacy login packet")
        # send legacy login
        control_layer.send_legacy_login_packet()

        # recv nonce
        logger.info("Receiving nonce packet")
        nonce = None
        while nonce == None:
            (modern_message_id, _, message, _) = control_layer.recv_packet()
            if modern_message_id != baichuan_control_layer.BAICHUAN_MESSAGE_ID_LOGIN:
                continue
            xml_root = ElementTree.fromstring(message)
            nonce_element = xml_root.find("Encryption/nonce")
            if nonce_element != None:
                nonce = nonce_element.text
        logger.info("Received nonce: %s", nonce)    
        # send modern login hashed with nonce

        logger.info("Sending modern login packet")
        control_layer.send_modern_login_packet(nonce)
        while True:
            (modern_message_id, _, message, binary_data) = control_layer.recv_packet()
            if modern_message_id == baichuan_control_layer.BAICHUAN_MESSAGE_ID_VIDEO_INPUT:
                break
        
        logger.info("Send start video cmd")
        control_layer.start_video(baichuan_control_layer.MAINSTREAM)
        video_stream = b''

        i = 0
        udp_layer.socket.settimeout(5)
        while self.is_running:
            (modern_message_id, _, message, binary_data) = control_layer.recv_packet()
            I_FRAME = 0x63643030
            P_FRAME = 0x63643130
            VIDEO_INFO_V1 = 0x31303031
            VIDEO_INFO_V2 = 0x32303031
            BC_AAC_FRAME = 0x62773530
            I_FRAME_HEADER_SIZE = 32
            P_FRAME_HEADER_SIZE = 24
            if modern_message_id == baichuan_control_layer.BAICHUAN_MESSAGE_ID_VIDEO and len(binary_data) > 0:
                video_data = binary_data
                (frame_magic, ) = struct.unpack_from("<i", video_data)
                VIDEO_TYPE_H264 = 0x34363248
                # https://www.wasteofcash.com/BCConvert/BC_fileformat.txt
                if frame_magic == I_FRAME:
                    # 4 bytes magic
                    # 4 bytes video type (eg H264 or H265)
                    # 4 bytes data size
                    # 4 bytes unknown
                    # 4 bytes nano Seconds / clock cycles?
                    # 4 bytes unknown
                    # 4 bytes POSIX time_t 32bit UTC time (seconds since 00:00:00 Jan 1 1970)
                    # 4 bytes unknown
                    (magic, video_type, data_size, _, _, _, utc_time, _) = struct.unpack_from("<iIIIIIII", video_data)
                    timestamp = datetime.utcfromtimestamp(utc_time).strftime('%Y-%m-%d %H:%M:%S')
                    logger.debug("I Frame found")
                    video_stream_data = video_data[I_FRAME_HEADER_SIZE:I_FRAME_HEADER_SIZE+data_size]
                    if video_type == VIDEO_TYPE_H264:
                        video_stream += video_stream_data
                elif frame_magic == P_FRAME:
                    # 4 bytes magic
                    # 4 bytes video type (eg H264 or H265)
                    # 4 bytes data size
                    # 4 bytes unknown
                    # 4 bytes nano Seconds / clock cycles?
                    # 4 bytes unknown
                    (magic, video_type, data_size, _, _, _) = struct.unpack_from("<iIIIII", video_data)
                    logger.debug("P Frame found")
                    video_stream_data = video_data[P_FRAME_HEADER_SIZE:P_FRAME_HEADER_SIZE+data_size]
                    if video_type == VIDEO_TYPE_H264:
                        video_stream += video_stream_data
                elif frame_magic == VIDEO_INFO_V1 or frame_magic == VIDEO_INFO_V2:
                    # print("VIDEO_INFO")
                    pass
                elif frame_magic == BC_AAC_FRAME:
                    BC_AAC_FRAME_HEADER_SIZE = 8
                    (audio_magic, l_size, r_size) = struct.unpack_from("<iHH", binary_data)
                    logger.debug("AAC Frame found (l_size %d, r_size %d)", l_size, r_size)
                    # audio_data = binary_data[BC_AAC_FRAME_HEADER_SIZE: BC_AAC_FRAME_HEADER_SIZE + l_size + r_size]
                else:
                    video_stream += binary_data
            elif modern_message_id == baichuan_control_layer.BAICHUAN_MESSAGE_ID_BATTERY_INFO:
                decoded_message = message.decode("utf-8")
                xml_root = ElementTree.fromstring(decoded_message)
                battery_percent_element = xml_root.find("BatteryList/BatteryInfo/batteryPercent")
                if battery_percent_element != None:
                    logger.info("Battery Percentage: %s", battery_percent_element.text)
            elif modern_message_id == baichuan_control_layer.BAICHUAN_MESSAGE_ID_PING:
                logger.debug("Received pong")
                pass
            else:
                logger.debug("Received unhandled message. modern_message_id: %d", modern_message_id)
                pass

            handle_video_stream(video_stream)
            video_stream = b''

            if i % 16 == 0:
                logger.debug("Sending ping")
                control_layer.ping()
            i += 1

    def stop(self):
        self.is_running = False