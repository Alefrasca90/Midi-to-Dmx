import serial
import socket
import threading
import time
import struct

class DMXController:
    """
    Gestisce l'output DMX supportando sia USB-SERIAL (Enttec/OpenDMX) che ART-NET (Ethernet/Wifi).
    """
    def __init__(self):
        # Buffer Dati
        self.output_frame = bytearray([0] * 513)
        self.live_buffer = bytearray([0] * 513)
        self.scene_buffer = bytearray([0] * 513)
        self.chase_buffer = bytearray([0] * 513)
        self.cue_buffer = bytearray([0] * 513)
        
        # Stato Hardware
        self.mode = "serial" # 'serial' o 'artnet'
        self.running = True
        
        # Serial Params
        self.serial_port = None
        
        # ArtNet Params
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
        self.artnet_ip = "127.0.0.1"
        self.artnet_universe = 0
        self.artnet_header = bytearray()
        self._build_artnet_header()

        # Avvia Thread
        self.thread = threading.Thread(target=self._send_loop, daemon=True)
        self.thread.start()

    def _build_artnet_header(self):
        """Pre-calcola l'header Art-Net fisso per efficienza."""
        # Header ID "Art-Net" + 0x00
        header = b'Art-Net\x00'
        # OpCode Output (0x5000) Little Endian -> 0x00 0x50
        header += b'\x00\x50' 
        # Proto Version (14) -> 0x00 0x0e
        header += b'\x00\x0e'
        # Sequence (0) & Physical (0)
        header += b'\x00\x00'
        # Universe (Little Endian)
        header += struct.pack('<H', self.artnet_universe)
        # Length (512) Big Endian -> 0x02 0x00
        header += b'\x02\x00'
        self.artnet_header = header

    def connect_serial(self, port):
        """Connette via USB Seriale"""
        self.mode = "serial"
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.serial_port = serial.Serial(port, baudrate=250000, stopbits=2)
            return True
        except Exception as e:
            print(f"Errore Seriale: {e}")
            return False

    def connect_artnet(self, ip, universe):
        """Configura output Art-Net"""
        self.mode = "artnet"
        self.artnet_ip = ip
        self.artnet_universe = int(universe)
        self._build_artnet_header() # Ricostruisce header col nuovo universo
        return True

    def _send_loop(self):
        """Ciclo di invio a 40Hz (25ms)"""
        seq_count = 0
        while self.running:
            try:
                # 1. Calcolo HTP
                for i in range(1, 513):
                    self.output_frame[i] = max(
                        self.live_buffer[i], 
                        self.scene_buffer[i], 
                        self.chase_buffer[i], 
                        self.cue_buffer[i]
                    )
                
                # 2. Invio Hardware
                if self.mode == "serial" and self.serial_port and self.serial_port.is_open:
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)

                elif self.mode == "artnet":
                    # Costruzione pacchetto ArtDMX
                    # Aggiorna Sequence (opzionale ma consigliato)
                    seq_byte = seq_count.to_bytes(1, 'big')
                    # Ricostruiamo al volo solo le parti dinamiche se necessario, 
                    # ma per velocità usiamo l'header pre-calcolato e i dati (dal byte 1 al 512)
                    packet = self.artnet_header + self.output_frame[1:]
                    
                    self.socket.sendto(packet, (self.artnet_ip, 6454))
                    
                    seq_count = (seq_count + 1) % 256
                
                time.sleep(0.025) # ~40 FPS
                
            except Exception as e:
                # print(f"Errore loop: {e}")
                time.sleep(0.1)

    def stop(self):
        self.running = False
        if self.serial_port: self.serial_port.close()
        if self.socket: self.socket.close()