import struct
import hashlib
import xml.etree.ElementTree as ElementTree

BAICHUAN_MAGIC = 0x0abcdef0
BAICHUAN_MESSAGE_ID_LOGIN = 0x01
BAICHUAN_MESSAGE_ID_VIDEO = 0x03
BAICHUAN_MESSAGE_ID_VIDEO_INPUT = 0x4e
BAICHUAN_MESSAGE_ID_PING = 0x5d
BAICHUAN_MESSAGE_ID_BATTERY_INFO = 0xfc

MAINSTREAM = "mainStream"
SUBSTREAM = "subStream"

MESSAGE_CLASS_TO_HEADER_LENGTH = {
  0x6514:20,
  0x6614:20,
  0x6414:24,
  0x0000:24,
}

class BaichuanControlLayer:
    def __init__(self, username, password, udp_layer):
        self.username = username
        self.password = password
        self.udp_layer = udp_layer
        self.encryption_offset = 0
        self.modern_message_id_to_binary_mode = {}
        self.recv_buffer = b''
    
    @staticmethod
    def xml_decrypt(message, offset):
        xml_key = [0x1F, 0x2D, 0x3C, 0x4B, 0x5A, 0x69, 0x78, 0xFF]
        result = b''
        for i in range(len(message)):
            val = (message[i] ^ xml_key[(i + offset) % 8]) ^ (offset & 0xFF)
            result += bytes([val])
        return result
    
    @staticmethod
    def md5_hash(str, zero_last):
        m = hashlib.new('md5')
        m.update(str.encode("utf-8"))
        digest = m.hexdigest().upper()
        if zero_last:
            return digest[:31] + "\0"
        return digest[:31]
    
    def send_legacy_login_packet(self):
        # Login messages are 1836 bytes total, username/password
        # take up 32 chars each, 1772 zeros follow
        TOTAL_BYTES = 1836
        md5_username = self.md5_hash(self.username, zero_last=True)
        md5_password = self.md5_hash(self.password, zero_last=True)

        login_message_header = b''
        login_message_header += BAICHUAN_MAGIC.to_bytes(4, 'little')
        login_message_header += BAICHUAN_MESSAGE_ID_LOGIN.to_bytes(4, 'little')
        login_message_header += bytes([0x2c, 0x07, 0x00, 0x00])
        login_message_header += bytes([0x00, 0x00, 0x00, 0x01])
        login_message_header += bytes([0x01])
        login_message_header += bytes([0xdc])
        login_message_header += bytes([0x14, 0x65])

        login_message_body = b''
        login_message_body += md5_username.encode("utf-8")
        login_message_body += md5_password.encode("utf-8")
        login_message_body += b'\0'* (TOTAL_BYTES - len(login_message_body))

        login_message_buffer = b''
        login_message_buffer += login_message_header
        login_message_buffer += login_message_body
        self.udp_layer.send_packet(login_message_buffer)

    def send_modern_login_packet(self, nonce):
        md5_username = self.md5_hash(self.username + nonce, zero_last=False)
        md5_password = self.md5_hash(self.password + nonce, zero_last=False)
        xml_body = f"<?xml version=\"1.0\" encoding=\"UTF-8\" ?>\n<body>\n<LoginUser version=\"1.1\">\n<userName>{md5_username}</userName>\n<password>{md5_password}</password>\n<userVer>1</userVer>\n</LoginUser>\n<LoginNet version=\"1.1\"><type>LAN</type>\n<udpPort>0</udpPort>\n</LoginNet>\n</body>\n"
        xml_bytes = xml_body.encode("utf-8")
        encrypted_xml_body = self.xml_decrypt(xml_bytes, self.encryption_offset)

        login_message_header = b''
        login_message_header += BAICHUAN_MAGIC.to_bytes(4, 'little')
        login_message_header += BAICHUAN_MESSAGE_ID_LOGIN.to_bytes(4, 'little')
        login_message_header += len(encrypted_xml_body).to_bytes(4, 'little')
        login_message_header += self.encryption_offset.to_bytes(4, 'little')
        login_message_header += bytes([0x00, 0x00])
        login_message_header += bytes([0x14, 0x64])
        login_message_header += bytes([0x00, 0x00, 0x00, 0x00])

        login_message_buffer = b''
        login_message_buffer += login_message_header
        login_message_buffer += encrypted_xml_body
        self.udp_layer.send_packet(login_message_buffer)

    def start_video(self, stream):
        xml_body = f"<?xml version=\"1.0\" encoding=\"UTF-8\" ?>\n<body>\n<Preview version=\"1.1\">\n<channelId>0</channelId>\n<handle>0</handle>\n<streamType>{stream}</streamType>\n</Preview>\n</body>\n"
        xml_bytes = xml_body.encode("utf-8")
        encrypted_xml_body = self.xml_decrypt(xml_bytes, self.encryption_offset)

        video_message_header = b''
        video_message_header += BAICHUAN_MAGIC.to_bytes(4, 'little')
        video_message_header += BAICHUAN_MESSAGE_ID_VIDEO.to_bytes(4, 'little')
        video_message_header += len(encrypted_xml_body).to_bytes(4, 'little')
        video_message_header += self.encryption_offset.to_bytes(4, 'little')
        video_message_header += bytes([0x00, 0x00])
        video_message_header += bytes([0x14, 0x64])
        video_message_header += bytes([0x00, 0x00, 0x00, 0x00])

        video_message_buffer = b''
        video_message_buffer += video_message_header
        video_message_buffer += encrypted_xml_body
        self.udp_layer.send_packet(video_message_buffer)

    def ping(self):
        ping_message_buffer = b''
        ping_message_buffer += BAICHUAN_MAGIC.to_bytes(4, 'little')
        ping_message_buffer += BAICHUAN_MESSAGE_ID_PING.to_bytes(4, 'little')
        x = 0
        ping_message_buffer += x.to_bytes(4, 'little')
        ping_message_buffer += self.encryption_offset.to_bytes(4, 'little')
        ping_message_buffer += bytes([0x00, 0x00])
        ping_message_buffer += bytes([0x14, 0x64])
        ping_message_buffer += bytes([0x00, 0x00, 0x00, 0x00])
        self.udp_layer.send_packet(ping_message_buffer)
    
    @staticmethod
    def has_bin_offset(message_class):
        return message_class == 0x6414 or message_class == 0x0000
    
    def _recv_next_udp_packet(self):
        packet = None
        if len(self.recv_buffer) > 0:
            packet = self.recv_buffer
            self.recv_buffer = b''
        else:
            packet = self.udp_layer.recv_packet()
        return packet

    def set_binary_mode(self, modern_message_id, binary_mode):
        self.modern_message_id_to_binary_mode[modern_message_id] = binary_mode
    
    def is_in_binary_mode(self, modern_message_id):
        return (modern_message_id in self.modern_message_id_to_binary_mode) and self.modern_message_id_to_binary_mode[modern_message_id]
    
    def recv_packet(self):
        modern_message_id = None
        message_class = None
        message = b''
        binary_data = b''
        while True:
            packet = self._recv_next_udp_packet()
            (magic, modern_message_id, message_len, encryption_offset, encrypted, _, message_class) = struct.unpack_from("<iIIIBBH", packet)
            self.encryption_offset = encryption_offset
            if magic != BAICHUAN_MAGIC:
                break
            header_len = MESSAGE_CLASS_TO_HEADER_LENGTH[message_class]
            bin_offset = 0
            if self.has_bin_offset(message_class):
                (bin_offset, ) = struct.unpack_from("<I", packet[20:])
                if bin_offset != 0:
                    self.set_binary_mode(modern_message_id, True)
            
            max_packet_size = None
            if self.is_in_binary_mode(modern_message_id):
                if bin_offset != 0:
                    message += packet[header_len:header_len+bin_offset]
                max_packet_size = min(len(packet[header_len+bin_offset:]), message_len - len(message) - len(binary_data))
                binary_data += packet[header_len+bin_offset:header_len+bin_offset+max_packet_size]
            else:
                max_packet_size = min(len(packet[header_len:]), message_len - len(message) - len(binary_data))
                message += packet[header_len:header_len+max_packet_size]
            self.recv_buffer += packet[header_len+max_packet_size:]

            while len(message) + len(binary_data) < message_len:
                packet = self._recv_next_udp_packet()
                max_packet_size = min(len(packet), message_len - len(message) - len(binary_data))
                if self.is_in_binary_mode(modern_message_id):
                    binary_data += packet[:max_packet_size]
                else:
                    message += packet[:max_packet_size]
                self.recv_buffer += packet[max_packet_size:]
            break
        if encrypted or message_class == 0x6414 and len(message) > 0:
            message = self.xml_decrypt(message, self.encryption_offset)
        try:
            str_message = message.decode("utf-8")
            xml_root = ElementTree.fromstring(str_message)
            binary_data_element = xml_root.find("binaryData")
            if binary_data_element != None:
                self.set_binary_mode(modern_message_id, binary_data_element.text == "1")
        except:
            pass
        return (modern_message_id, message_class, message, binary_data)