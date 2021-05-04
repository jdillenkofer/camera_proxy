import math
import random
import socket
import struct
import logging
import xml.etree.ElementTree as ElementTree
import netifaces

logger = logging.getLogger(__name__)

UDP_MESSAGE_ID_CTRL = 0x2a87cf10
UDP_MESSAGE_ID_ACK = 0x2a87cf20
UDP_MESSAGE_ID_DISCOVERY = 0x2a87cf3a

DISCOVERY_PORT_START=50000
DISCOVERY_PORT_END=60000

CLIENT_OS = 'WIN'
ETHERNET_MTU = 1350
#TODO:Find the right interface for internet & local lan
GATEWAYS = netifaces.gateways()
DEFAULT_GATEWAY_ADDRESS = None if GATEWAYS == None or GATEWAYS['default'] == None else GATEWAYS['default'][netifaces.AF_INET]
BINDING_IFACE_IP = '' if DEFAULT_GATEWAY_ADDRESS == None else netifaces.ifaddresses(DEFAULT_GATEWAY_ADDRESS[1])[netifaces.AF_INET][0]['addr']

P2P_RELAY_HOSTNAMES = [
    "p2p.reolink.com",
    "p2p1.reolink.com",
    "p2p2.reolink.com",
    "p2p3.reolink.com",
    "p2p14.reolink.com",
    "p2p15.reolink.com",
    "p2p6.reolink.com",
    "p2p7.reolink.com",
    "p2p8.reolink.com",
    "p2p9.reolink.com"
]

class BaichuanUdpLayer:
    def __init__(self, device_sid, client_id, ipaddress, communication_port=0):
        self.device_sid = device_sid
        self.client_id = client_id
        self.device_id = None
        self.communication_port = communication_port
        self.discovery_src_port = DISCOVERY_PORT_START
        self.connection_id = -1
        self.last_send_packet_id = 0
        self.last_received_packet_id = -1
        self.wait_acknowledgement = 0
        self.target_address = (ipaddress, None)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = (BINDING_IFACE_IP, self.communication_port)
        self.socket.bind(server_address)
        self.communication_port = self.socket.getsockname()[1]
        self.unack_messages = {}
        #Generate new client ID to say the cammera that instance is a a new client to broadcast information
        self.tid = random.randint(0, 4000)
        self.p2p_relay_hosts = self._lookup_available_p2p_hosts()
    
    def _lookup_available_p2p_hosts(self):
        relay_hosts = []
        for hostname in P2P_RELAY_HOSTNAMES:
            try:
                host = socket.gethostbyname(hostname)
                relay_hosts.append(host)
            except socket.gaierror:
                pass
        return relay_hosts
    
    def discover_device(self):
        self.socket.settimeout(0.2)
        retry = 25
        sender = (None, None)
        client_id = None
        while client_id != self.client_id and retry >= 0:
            retry -= 1
            logger.info("Sending discovery packet")
            self._send_discovery_broadcast()
            try:
                data, sender = self.socket.recvfrom(4096)
                (udp_message_id, size, unknown, tid, checksum) = struct.unpack_from("<iIIiI", data)
                if udp_message_id != UDP_MESSAGE_ID_DISCOVERY:
                    continue
                message = data[20:20+size]
                actual_checksum = self.calc_crc(message)
                if checksum != actual_checksum:
                    logger.warn("Invalid checksum - expected: %d actual: %d", checksum, actual_checksum)
                    continue
                message = self.de_or_encrypt_udp_message(message, tid).decode("utf-8")
                xml_root = ElementTree.fromstring(message)
                did_element = xml_root.find("D2C_C_R/did")
                cid_element = xml_root.find("D2C_C_R/cid")
                if did_element != None and cid_element != None: 
                    self.device_id = int(did_element.text)
                    logger.info("Device ID: %s", self.device_id)
                    client_id = int(cid_element.text)
                else:
                    continue
            except socket.timeout:
                continue
            logger.info("Received discovery packet answer from %s (%s)", sender[0], sender[1])

        if retry <= 0:
            if self.target_address[0] is None:
                self.p2p_discover()
            else:
                logger.info("Skipping p2p_discover because target was set. Local discovery only.")
        else:
            self.target_address = sender
            self.socket.settimeout(30)
    
    def p2p_discover(self):
        logger.info("Send P2P Discovery message")
        self.socket.settimeout(0.5) #P2P Discover can take more time to answer than locally
        register_address = (None, None)
        relay_address = (None, None)
        device_address = (None, None)
        log_address = (None, None)
        endpoint_address = (None, None)
        index = -1
        while True:                
            index += 1  
            if index >= len(self.p2p_relay_hosts):
                raise "No P2P host available to register"
            host = self.p2p_relay_hosts[index]
            self._send_p2p_discovery(host)
            try:
                data, sender = self.socket.recvfrom(4096)
                (udp_message_id, size, unknown, tid, checksum) = struct.unpack_from("<iIIiI", data)
                if udp_message_id != UDP_MESSAGE_ID_DISCOVERY:
                    continue
                message = data[20:20+size]
                actual_checksum = self.calc_crc(message)
                if checksum != actual_checksum:
                    logger.warn("Invalid checksum - expected: %d actual: %d", checksum, actual_checksum)
                    continue
                message = self.de_or_encrypt_udp_message(message, tid).decode("utf-8")
                xml_root = ElementTree.fromstring(message)
                register_address = (xml_root.find("M2C_Q_R/reg/ip"), xml_root.find("M2C_Q_R/reg/port"))
                relay_address = (xml_root.find("M2C_Q_R/relay/ip"), xml_root.find("M2C_Q_R/relay/port"))
                log_address = (xml_root.find("M2C_Q_R/log/ip"), xml_root.find("M2C_Q_R/log/port"))
                endpoint_address = (xml_root.find("M2C_Q_R/t/ip"), xml_root.find("M2C_Q_R/t/port"))
                if register_address[0] != None and relay_address[0] != None:
                    register_address = (register_address[0].text, int(register_address[1].text))
                    relay_address = (relay_address[0].text, int(relay_address[1].text))
                    log_address = (log_address[0].text, int(log_address[1].text))
                    endpoint_address = (endpoint_address[0].text, int(endpoint_address[1].text))
                    break
                else:
                    continue
            except socket.timeout:
                continue
        logger.info("P2P - Register address found, %s:%d", register_address[0], register_address[1])
        client_id = None
        device_id = None
        while client_id != self.client_id:
            self._send_p2p_register(register_address, relay_address)
            while device_id == None:
                try:
                    data, sender = self.socket.recvfrom(4096)
                    (udp_message_id, size, unknown, tid, checksum) = struct.unpack_from("<iIIiI", data)
                    if udp_message_id != UDP_MESSAGE_ID_DISCOVERY:
                        continue
                    message = data[20:20+size]
                    actual_checksum = self.calc_crc(message)
                    if checksum != actual_checksum:
                        logger.warn("Invalid checksum - expected: %d actual: %d", checksum, actual_checksum)
                        continue
                    message = self.de_or_encrypt_udp_message(message, tid).decode("utf-8")
                    xml_root = ElementTree.fromstring(message)
                    device_address_element = (xml_root.find("R2C_T/dev/ip"), xml_root.find("R2C_T/dev/port"))
                    cid_element = xml_root.find("R2C_T/cid")
                    connection_id_element = xml_root.find("R2C_T/sid")
                    connection_id_element = xml_root.find("D2C_T/sid") if connection_id_element == None else connection_id_element
                    cid_element = xml_root.find("D2C_T/cid") if cid_element == None else cid_element
                    device_element = xml_root.find("D2C_T/did")                    
                    if device_element == None:
                        device_element = xml_root.find("D2C_CFM/did")
                        cid_element = xml_root.find("D2C_CFM/cid") if cid_element == None else cid_element
                    if device_element == None:
                        device_element = xml_root.find("D2C_DISC/did")
                        cid_element = xml_root.find("D2C_DISC/cid") if cid_element == None else cid_element

                    if device_address_element[0] != None and cid_element != None and int(cid_element.text) == self.client_id and connection_id_element != None:
                        device_address = (device_address_element[0].text, int(device_address_element[1].text))
                        self.connection_id = int(connection_id_element.text)
                        self.target_address = device_address
                        self._send_p2p_local_connection()
                        client_id = int(cid_element.text)
                        if device_id != None:
                            break
                    if device_element != None and cid_element != None and int(cid_element.text) == self.client_id:
                        device_id = int(device_element.text)
                        client_id = int(cid_element.text)
                        if device_address[0] != None:
                            break
                except socket.timeout:
                    continue
        
        self.device_id = device_id

        logger.info("P2P - Device ID received, %d", device_id)
        
        self._send_p2p_remote_connection(log_address) #Announce we will connect locally
        self._send_p2p_dmap_connection(endpoint_address) #Announce we could connect remotely

        self.socket.settimeout(1)
        

    @staticmethod    
    def calc_crc(message):
        table = [0x0, 0x0, 0x0, 0x0, 0x96, 0x30, 0x7, 0x77, 0x2C, 0x61, 0xE, 0xEE, 0xBA, 0x51, 0x9, 0x99, 0x19, 0xC4, 0x6D, 0x7, 0x8F, 0xF4, 0x6A, 0x70, 0x35, 0xA5, 0x63, 0xE9, 0xA3, 0x95, 0x64, 0x9E, 0x32, 0x88, 0xDB, 0xE, 0xA4, 0xB8, 0xDC, 0x79, 0x1E, 0xE9, 0xD5, 0xE0, 0x88, 0xD9, 0xD2, 0x97, 0x2B, 0x4C, 0xB6, 0x9, 0xBD, 0x7C, 0xB1, 0x7E, 0x7, 0x2D, 0xB8, 0xE7, 0x91, 0x1D, 0xBF, 0x90, 0x64, 0x10, 0xB7, 0x1D, 0xF2, 0x20, 0xB0, 0x6A, 0x48, 0x71, 0xB9, 0xF3, 0xDE, 0x41, 0xBE, 0x84, 0x7D, 0xD4, 0xDA, 0x1A, 0xEB, 0xE4, 0xDD, 0x6D, 0x51, 0xB5, 0xD4, 0xF4, 0xC7, 0x85, 0xD3, 0x83, 0x56, 0x98, 0x6C, 0x13, 0xC0, 0xA8, 0x6B, 0x64, 0x7A, 0xF9, 0x62, 0xFD, 0xEC, 0xC9, 0x65, 0x8A, 0x4F, 0x5C, 0x1, 0x14, 0xD9, 0x6C, 0x6, 0x63, 0x63, 0x3D, 0xF, 0xFA, 0xF5, 0xD, 0x8, 0x8D, 0xC8, 0x20, 0x6E, 0x3B, 0x5E, 0x10, 0x69, 0x4C, 0xE4, 0x41, 0x60, 0xD5, 0x72, 0x71, 0x67, 0xA2, 0xD1, 0xE4, 0x3, 0x3C, 0x47, 0xD4, 0x4, 0x4B, 0xFD, 0x85, 0xD, 0xD2, 0x6B, 0xB5, 0xA, 0xA5, 0xFA, 0xA8, 0xB5, 0x35, 0x6C, 0x98, 0xB2, 0x42, 0xD6, 0xC9, 0xBB, 0xDB, 0x40, 0xF9, 0xBC, 0xAC, 0xE3, 0x6C, 0xD8, 0x32, 0x75, 0x5C, 0xDF, 0x45, 0xCF, 0xD, 0xD6, 0xDC, 0x59, 0x3D, 0xD1, 0xAB, 0xAC, 0x30, 0xD9, 0x26, 0x3A, 0x0, 0xDE, 0x51, 0x80, 0x51, 0xD7, 0xC8, 0x16, 0x61, 0xD0, 0xBF, 0xB5, 0xF4, 0xB4, 0x21, 0x23, 0xC4, 0xB3, 0x56, 0x99, 0x95, 0xBA, 0xCF, 0xF, 0xA5, 0xBD, 0xB8, 0x9E, 0xB8, 0x2, 0x28, 0x8, 0x88, 0x5, 0x5F, 0xB2, 0xD9, 0xC, 0xC6, 0x24, 0xE9, 0xB, 0xB1, 0x87, 0x7C, 0x6F, 0x2F, 0x11, 0x4C, 0x68, 0x58, 0xAB, 0x1D, 0x61, 0xC1, 0x3D, 0x2D, 0x66, 0xB6, 0x90, 0x41, 0xDC, 0x76, 0x6, 0x71, 0xDB, 0x1, 0xBC, 0x20, 0xD2, 0x98, 0x2A, 0x10, 0xD5, 0xEF, 0x89, 0x85, 0xB1, 0x71, 0x1F, 0xB5, 0xB6, 0x6, 0xA5, 0xE4, 0xBF, 0x9F, 0x33, 0xD4, 0xB8, 0xE8, 0xA2, 0xC9, 0x7, 0x78, 0x34, 0xF9, 0x0, 0xF, 0x8E, 0xA8, 0x9, 0x96, 0x18, 0x98, 0xE, 0xE1, 0xBB, 0xD, 0x6A, 0x7F, 0x2D, 0x3D, 0x6D, 0x8, 0x97, 0x6C, 0x64, 0x91, 0x1, 0x5C, 0x63, 0xE6, 0xF4, 0x51, 0x6B, 0x6B, 0x62, 0x61, 0x6C, 0x1C, 0xD8, 0x30, 0x65, 0x85, 0x4E, 0x0, 0x62, 0xF2, 0xED, 0x95, 0x6, 0x6C, 0x7B, 0xA5, 0x1, 0x1B, 0xC1, 0xF4, 0x8, 0x82, 0x57, 0xC4, 0xF, 0xF5, 0xC6, 0xD9, 0xB0, 0x65, 0x50, 0xE9, 0xB7, 0x12, 0xEA, 0xB8, 0xBE, 0x8B, 0x7C, 0x88, 0xB9, 0xFC, 0xDF, 0x1D, 0xDD, 0x62, 0x49, 0x2D, 0xDA, 0x15, 0xF3, 0x7C, 0xD3, 0x8C, 0x65, 0x4C, 0xD4, 0xFB, 0x58, 0x61, 0xB2, 0x4D, 0xCE, 0x51, 0xB5, 0x3A, 0x74, 0x0, 0xBC, 0xA3, 0xE2, 0x30, 0xBB, 0xD4, 0x41, 0xA5, 0xDF, 0x4A, 0xD7, 0x95, 0xD8, 0x3D, 0x6D, 0xC4, 0xD1, 0xA4, 0xFB, 0xF4, 0xD6, 0xD3, 0x6A, 0xE9, 0x69, 0x43, 0xFC, 0xD9, 0x6E, 0x34, 0x46, 0x88, 0x67, 0xAD, 0xD0, 0xB8, 0x60, 0xDA, 0x73, 0x2D, 0x4, 0x44, 0xE5, 0x1D, 0x3, 0x33, 0x5F, 0x4C, 0xA, 0xAA, 0xC9, 0x7C, 0xD, 0xDD, 0x3C, 0x71, 0x5, 0x50, 0xAA, 0x41, 0x2, 0x27, 0x10, 0x10, 0xB, 0xBE, 0x86, 0x20, 0xC, 0xC9, 0x25, 0xB5, 0x68, 0x57, 0xB3, 0x85, 0x6F, 0x20, 0x9, 0xD4, 0x66, 0xB9, 0x9F, 0xE4, 0x61, 0xCE, 0xE, 0xF9, 0xDE, 0x5E, 0x98, 0xC9, 0xD9, 0x29, 0x22, 0x98, 0xD0, 0xB0, 0xB4, 0xA8, 0xD7, 0xC7, 0x17, 0x3D, 0xB3, 0x59, 0x81, 0xD, 0xB4, 0x2E, 0x3B, 0x5C, 0xBD, 0xB7, 0xAD, 0x6C, 0xBA, 0xC0, 0x20, 0x83, 0xB8, 0xED, 0xB6, 0xB3, 0xBF, 0x9A, 0xC, 0xE2, 0xB6, 0x3, 0x9A, 0xD2, 0xB1, 0x74, 0x39, 0x47, 0xD5, 0xEA, 0xAF, 0x77, 0xD2, 0x9D, 0x15, 0x26, 0xDB, 0x4, 0x83, 0x16, 0xDC, 0x73, 0x12, 0xB, 0x63, 0xE3, 0x84, 0x3B, 0x64, 0x94, 0x3E, 0x6A, 0x6D, 0xD, 0xA8, 0x5A, 0x6A, 0x7A, 0xB, 0xCF, 0xE, 0xE4, 0x9D, 0xFF, 0x9, 0x93, 0x27, 0xAE, 0x0, 0xA, 0xB1, 0x9E, 0x7, 0x7D, 0x44, 0x93, 0xF, 0xF0, 0xD2, 0xA3, 0x8, 0x87, 0x68, 0xF2, 0x1, 0x1E, 0xFE, 0xC2, 0x6, 0x69, 0x5D, 0x57, 0x62, 0xF7, 0xCB, 0x67, 0x65, 0x80, 0x71, 0x36, 0x6C, 0x19, 0xE7, 0x6, 0x6B, 0x6E, 0x76, 0x1B, 0xD4, 0xFE, 0xE0, 0x2B, 0xD3, 0x89, 0x5A, 0x7A, 0xDA, 0x10, 0xCC, 0x4A, 0xDD, 0x67, 0x6F, 0xDF, 0xB9, 0xF9, 0xF9, 0xEF, 0xBE, 0x8E, 0x43, 0xBE, 0xB7, 0x17, 0xD5, 0x8E, 0xB0, 0x60, 0xE8, 0xA3, 0xD6, 0xD6, 0x7E, 0x93, 0xD1, 0xA1, 0xC4, 0xC2, 0xD8, 0x38, 0x52, 0xF2, 0xDF, 0x4F, 0xF1, 0x67, 0xBB, 0xD1, 0x67, 0x57, 0xBC, 0xA6, 0xDD, 0x6, 0xB5, 0x3F, 0x4B, 0x36, 0xB2, 0x48, 0xDA, 0x2B, 0xD, 0xD8, 0x4C, 0x1B, 0xA, 0xAF, 0xF6, 0x4A, 0x3, 0x36, 0x60, 0x7A, 0x4, 0x41, 0xC3, 0xEF, 0x60, 0xDF, 0x55, 0xDF, 0x67, 0xA8, 0xEF, 0x8E, 0x6E, 0x31, 0x79, 0xBE, 0x69, 0x46, 0x8C, 0xB3, 0x61, 0xCB, 0x1A, 0x83, 0x66, 0xBC, 0xA0, 0xD2, 0x6F, 0x25, 0x36, 0xE2, 0x68, 0x52, 0x95, 0x77, 0xC, 0xCC, 0x3, 0x47, 0xB, 0xBB, 0xB9, 0x16, 0x2, 0x22, 0x2F, 0x26, 0x5, 0x55, 0xBE, 0x3B, 0xBA, 0xC5, 0x28, 0xB, 0xBD, 0xB2, 0x92, 0x5A, 0xB4, 0x2B, 0x4, 0x6A, 0xB3, 0x5C, 0xA7, 0xFF, 0xD7, 0xC2, 0x31, 0xCF, 0xD0, 0xB5, 0x8B, 0x9E, 0xD9, 0x2C, 0x1D, 0xAE, 0xDE, 0x5B, 0xB0, 0xC2, 0x64, 0x9B, 0x26, 0xF2, 0x63, 0xEC, 0x9C, 0xA3, 0x6A, 0x75, 0xA, 0x93, 0x6D, 0x2, 0xA9, 0x6, 0x9, 0x9C, 0x3F, 0x36, 0xE, 0xEB, 0x85, 0x67, 0x7, 0x72, 0x13, 0x57, 0x0, 0x5, 0x82, 0x4A, 0xBF, 0x95, 0x14, 0x7A, 0xB8, 0xE2, 0xAE, 0x2B, 0xB1, 0x7B, 0x38, 0x1B, 0xB6, 0xC, 0x9B, 0x8E, 0xD2, 0x92, 0xD, 0xBE, 0xD5, 0xE5, 0xB7, 0xEF, 0xDC, 0x7C, 0x21, 0xDF, 0xDB, 0xB, 0xD4, 0xD2, 0xD3, 0x86, 0x42, 0xE2, 0xD4, 0xF1, 0xF8, 0xB3, 0xDD, 0x68, 0x6E, 0x83, 0xDA, 0x1F, 0xCD, 0x16, 0xBE, 0x81, 0x5B, 0x26, 0xB9, 0xF6, 0xE1, 0x77, 0xB0, 0x6F, 0x77, 0x47, 0xB7, 0x18, 0xE6, 0x5A, 0x8, 0x88, 0x70, 0x6A, 0xF, 0xFF, 0xCA, 0x3B, 0x6, 0x66, 0x5C, 0xB, 0x1, 0x11, 0xFF, 0x9E, 0x65, 0x8F, 0x69, 0xAE, 0x62, 0xF8, 0xD3, 0xFF, 0x6B, 0x61, 0x45, 0xCF, 0x6C, 0x16, 0x78, 0xE2, 0xA, 0xA0, 0xEE, 0xD2, 0xD, 0xD7, 0x54, 0x83, 0x4, 0x4E, 0xC2, 0xB3, 0x3, 0x39, 0x61, 0x26, 0x67, 0xA7, 0xF7, 0x16, 0x60, 0xD0, 0x4D, 0x47, 0x69, 0x49, 0xDB, 0x77, 0x6E, 0x3E, 0x4A, 0x6A, 0xD1, 0xAE, 0xDC, 0x5A, 0xD6, 0xD9, 0x66, 0xB, 0xDF, 0x40, 0xF0, 0x3B, 0xD8, 0x37, 0x53, 0xAE, 0xBC, 0xA9, 0xC5, 0x9E, 0xBB, 0xDE, 0x7F, 0xCF, 0xB2, 0x47, 0xE9, 0xFF, 0xB5, 0x30, 0x1C, 0xF2, 0xBD, 0xBD, 0x8A, 0xC2, 0xBA, 0xCA, 0x30, 0x93, 0xB3, 0x53, 0xA6, 0xA3, 0xB4, 0x24, 0x5, 0x36, 0xD0, 0xBA, 0x93, 0x6, 0xD7, 0xCD, 0x29, 0x57, 0xDE, 0x54, 0xBF, 0x67, 0xD9, 0x23, 0x2E, 0x7A, 0x66, 0xB3, 0xB8, 0x4A, 0x61, 0xC4, 0x2, 0x1B, 0x68, 0x5D, 0x94, 0x2B, 0x6F, 0x2A, 0x37, 0xBE, 0xB, 0xB4, 0xA1, 0x8E, 0xC, 0xC3, 0x1B, 0xDF, 0x5, 0x5A, 0x8D, 0xEF, 0x02, 0x2D]
        r = 0
        for i in range(len(message)):
            val = message[i]
            val = val ^ r
            val = val & 0xFF
            offset = val << 2
            val = table[offset + 3] << 24 | table[offset + 2] << 16 | table[offset + 1] << 8 | table[offset]
            r = val ^ (r >> 8)
        return r

    @staticmethod
    def de_or_encrypt_udp_message(message, tid):
        key = [
            0x1f2d3c4b, 0x5a6c7f8d, 
            0x38172e4b, 0x8271635a,
            0x863f1a2b, 0xa5c6f7d8, 
            0x8371e1b4, 0x17f2d3a5
        ]
        result = b''
        
        for i in range(0, 8):
            key[i] = key[i] + tid

        i = len(message) + 3
        if i < 0:
            i = len(message) + 6

        for x in range(0, i//4):
            index = x & 7
            xor_key_word = key[index]

            for b in range(0, 4):
                byte_index = x * 4 + b
                val = message[byte_index]
                key_byte = (xor_key_word >> (b * 8)) & 0xFF
                val = key_byte ^ val
                result += bytes([val & 0xFF])
                if byte_index >= len(message) - 1:
                    return result
        return result

    def recv_packet(self):
        message = None
        packet_id = None
        while True:
            data, sender = self.socket.recvfrom(4096)
            (udp_message_id, client_id, unknown, packet_id, size) = struct.unpack_from("<iIIiI", data)
            if client_id != self.client_id:
                    continue
            udp_header_len = 20
            message = data[udp_header_len:udp_header_len+size]
            if udp_message_id == UDP_MESSAGE_ID_CTRL:
                if packet_id == self.last_received_packet_id + 1:
                    self.last_received_packet_id = packet_id
                    self.send_acknowledgement()
                else:
                    continue
                break
            elif udp_message_id == UDP_MESSAGE_ID_ACK:
                self.handle_acknowledgement(data)
            elif udp_message_id == UDP_MESSAGE_ID_DISCOVERY:
                logger.info("Received discovery message from camera")
        return message

    def send_packet(self, baichuan_packet):
        MAX_SIZE = 1330
        baichuan_packets = []
        num_packets = math.ceil(len(baichuan_packet) / MAX_SIZE)
        for _ in range(num_packets):
            baichuan_packets.append(baichuan_packet[0:1330])
            baichuan_packet = baichuan_packet[1330:]

        for packet in baichuan_packets:
            raw_packet = b''
            raw_packet += UDP_MESSAGE_ID_CTRL.to_bytes(4, 'little')
            raw_packet += self.device_id.to_bytes(4, 'little')
            raw_packet += bytes([0x00, 0x00, 0x00, 0x00])
            raw_packet += self.last_send_packet_id.to_bytes(4, 'little')
            raw_packet += len(packet).to_bytes(4, 'little')
            raw_packet += packet

            self.unack_messages[self.last_send_packet_id] = raw_packet
            
            self.socket.sendto(raw_packet, self.target_address)
            self.last_send_packet_id += 1

    def handle_acknowledgement(self, data):
        (udp_message_id, client_id, _, _, packet_id, _, _) = struct.unpack_from("<iIiiIii", data)
        if udp_message_id != UDP_MESSAGE_ID_ACK or client_id != self.client_id:
            return
        if packet_id < self.last_send_packet_id - 1:
            self.wait_acknowledgement += 1
            # Give the camera some time to send
            # the correct acknowledged packet id
            if self.wait_acknowledgement > 10:
                self.resend_unacknowledged_packets(packet_id, self.last_send_packet_id - 1)
        elif self.wait_acknowledgement != 0:
            self.unack_messages = {}
            self.wait_acknowledgement = 0
        
    def resend_unacknowledged_packets(self, packet_id, max_message):
        for i in range(packet_id + 1, max_message + 1):
            raw_packet = self.unack_messages[i]
            self.socket.sendto(raw_packet, self.target_address)
    
    def send_acknowledgement(self):
        packet = b''
        packet += UDP_MESSAGE_ID_ACK.to_bytes(4, 'little')
        packet += self.device_id.to_bytes(4, 'little')
        x = 0
        packet += x.to_bytes(4, 'little')
        packet += x.to_bytes(4, 'little')
        packet += self.last_received_packet_id.to_bytes(4, 'little')
        packet += x.to_bytes(4, 'little')
        packet += x.to_bytes(4, 'little')

        self.socket.sendto(packet, self.target_address)

    def _send_p2p_discovery(self, host):

        xml_body = f"<P2P>\n<C2M_Q>\n<uid>{self.device_sid}</uid>\n<p>{CLIENT_OS}</p>\n</C2M_Q>\n</P2P>\n"
        xml_bytes = xml_body.encode("utf-8")

        enc_xml_bytes = self.de_or_encrypt_udp_message(xml_bytes, self.tid)
        checksum = self.calc_crc(enc_xml_bytes)

        discovery_message = b''
        discovery_message += UDP_MESSAGE_ID_DISCOVERY.to_bytes(4, 'little')
        discovery_message += len(xml_bytes).to_bytes(4, 'little')
        discovery_message += bytes([ 0x01, 0x00, 0x00, 0x00 ])
        discovery_message += self.tid.to_bytes(4, 'little')
        discovery_message += checksum.to_bytes(4, 'little')
        discovery_message += enc_xml_bytes

        self.socket.sendto(discovery_message, (host, 9999))

    def _send_p2p_register(self, register_address, relay_address):
        xml_body = f"<P2P>\n<C2R_C>\n<uid>{self.device_sid}</uid>\n<cli>\n<ip>{BINDING_IFACE_IP}</ip>\n<port>{self.communication_port}</port>\n</cli>\n<relay>\n<ip>{relay_address[0]}</ip>\n<port>{relay_address[1]}</port>\n</relay>\n<cid>{self.client_id}</cid>\n<debug>{0}</debug>\n<family>4</family>\n<p>{CLIENT_OS}</p>\n</C2R_C>\n</P2P>\n"
        xml_bytes = xml_body.encode("utf-8")

        enc_xml_bytes = self.de_or_encrypt_udp_message(xml_bytes, self.tid)
        checksum = self.calc_crc(enc_xml_bytes)

        discovery_message = b''
        discovery_message += UDP_MESSAGE_ID_DISCOVERY.to_bytes(4, 'little')
        discovery_message += len(xml_bytes).to_bytes(4, 'little')
        discovery_message += bytes([ 0x01, 0x00, 0x00, 0x00 ])
        discovery_message += self.tid.to_bytes(4, 'little')
        discovery_message += checksum.to_bytes(4, 'little')
        discovery_message += enc_xml_bytes

        self.socket.sendto(discovery_message, register_address)

    def _send_p2p_local_connection(self):

        xml_body = f"<P2P>\n<C2D_T>\n<sid>{self.connection_id}</sid>\n<conn>local</conn>\n<cid>{self.client_id}</cid>\n<mtu>{ETHERNET_MTU}</mtu>\n</C2D_T>\n</P2P>\n"
        xml_bytes = xml_body.encode("utf-8")

        enc_xml_bytes = self.de_or_encrypt_udp_message(xml_bytes, self.tid)
        checksum = self.calc_crc(enc_xml_bytes)

        discovery_message = b''
        discovery_message += UDP_MESSAGE_ID_DISCOVERY.to_bytes(4, 'little')
        discovery_message += len(xml_bytes).to_bytes(4, 'little')
        discovery_message += bytes([ 0x01, 0x00, 0x00, 0x00 ])
        discovery_message += self.tid.to_bytes(4, 'little')
        discovery_message += checksum.to_bytes(4, 'little')
        discovery_message += enc_xml_bytes

        self.socket.sendto(discovery_message, self.target_address)

    def _send_p2p_remote_connection(self, log_address):
        xml_body = f"<P2P>\n<C2R_CFM>\n<sid>{self.connection_id}</sid>\n<conn>local</conn>\n<rsp>0</rsp>\n<cid>{self.client_id}</cid>\n<did>{self.device_id}</did>\n</C2R_CFM>\n</P2P>\n"
        xml_bytes = xml_body.encode("utf-8")

        enc_xml_bytes = self.de_or_encrypt_udp_message(xml_bytes, self.tid)
        checksum = self.calc_crc(enc_xml_bytes)

        discovery_message = b''
        discovery_message += UDP_MESSAGE_ID_DISCOVERY.to_bytes(4, 'little')
        discovery_message += len(xml_bytes).to_bytes(4, 'little')
        discovery_message += bytes([ 0x01, 0x00, 0x00, 0x00 ])
        discovery_message += self.tid.to_bytes(4, 'little')
        discovery_message += checksum.to_bytes(4, 'little')
        discovery_message += enc_xml_bytes

        self.socket.sendto(discovery_message, log_address)

    def _send_p2p_dmap_connection(self, enpoint_address):
        xml_body = f"<P2P>\n<C2D_T>\n<sid>{self.connection_id}</sid>\n<conn>map</conn>\n<rsp>0</rsp>\n<cid>{self.client_id}</cid>\n<mtu>{ETHERNET_MTU}</mtu>\n</C2D_T>\n</P2P>\n"
        xml_bytes = xml_body.encode("utf-8")

        enc_xml_bytes = self.de_or_encrypt_udp_message(xml_bytes, self.tid)
        checksum = self.calc_crc(enc_xml_bytes)

        discovery_message = b''
        discovery_message += UDP_MESSAGE_ID_DISCOVERY.to_bytes(4, 'little')
        discovery_message += len(xml_bytes).to_bytes(4, 'little')
        discovery_message += bytes([ 0x01, 0x00, 0x00, 0x00 ])
        discovery_message += self.tid.to_bytes(4, 'little')
        discovery_message += checksum.to_bytes(4, 'little')
        discovery_message += enc_xml_bytes

        self.socket.sendto(discovery_message, enpoint_address)

    def _send_discovery_broadcast(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        server_address = (BINDING_IFACE_IP, self.discovery_src_port)
        sock.bind(server_address)

        xml_body = f"<P2P>\n<C2D_C>\n<uid>{self.device_sid}</uid>\n<cli>\n<port>{self.communication_port}</port>\n</cli>\n<cid>{self.client_id}</cid>\n<mtu>{ETHERNET_MTU}</mtu>\n<debug>{0}</debug>\n<p>{CLIENT_OS}</p>\n</C2D_C>\n</P2P>\n"
        xml_bytes = xml_body.encode("utf-8")

        enc_xml_bytes = self.de_or_encrypt_udp_message(xml_bytes, self.tid)
        checksum = self.calc_crc(enc_xml_bytes)

        discovery_message = b''
        discovery_message += UDP_MESSAGE_ID_DISCOVERY.to_bytes(4, 'little')
        discovery_message += len(xml_bytes).to_bytes(4, 'little')
        discovery_message += bytes([ 0x01, 0x00, 0x00, 0x00 ])
        discovery_message += self.tid.to_bytes(4, 'little')
        discovery_message += checksum.to_bytes(4, 'little')
        discovery_message += enc_xml_bytes
        
        remote_address = ("255.255.255.255", 2015)
        sock.sendto(discovery_message, remote_address)
        
        if self.discovery_src_port >= DISCOVERY_PORT_END:
            self.discovery_src_port = DISCOVERY_PORT_START - 1

        self.discovery_src_port += 1