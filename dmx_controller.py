import serial
import time
import threading

class DMXController:
    def __init__(self):
        self.serial_port = None
        self.dmx_frame = bytearray([0] * 513) # 0 = start code + 512 canali
        self.running = False
        self.chases = {} # Esempio: {"chase1": [[ch1_val, ch2_val], [ch1_val, ch2_val]]}
        self.active_chase = None
        self.chase_step = 0
        self.chase_speed = 0.5 # Secondi tra uno step e l'altro

    def connect(self, port):
        try:
            self.serial_port = serial.Serial(port, baudrate=250000, stopbits=2)
            self.running = True
            threading.Thread(target=self._send_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"Errore connessione DMX: {e}")
            return False

    def _send_loop(self):
        """Invia il segnale a ~40Hz (standard DMX)"""
        while self.running:
            if self.serial_port:
                # BREAK
                self.serial_port.break_condition = True
                time.sleep(0.0001)
                self.serial_port.break_condition = False
                # Dati
                self.serial_port.write(self.dmx_frame)
                time.sleep(0.025) # Refresh rate

    def set_channel(self, channel, value):
        if 1 <= channel <= 512:
            self.dmx_frame[channel] = max(0, min(255, value))


    def play_chase(self, name):
        self.active_chase = name
        self.chase_step = 0
        self._run_chase_logic()

    def _run_chase_logic(self):
        if self.active_chase and self.active_chase in self.chases:
            step_data = self.chases[self.active_chase][self.chase_step]
            # step_data è una lista di (canale, valore)
            for channel, value in step_data:
                self.set_channel(channel, value)
            
            # Incrementa lo step o ricomincia
            self.chase_step = (self.chase_step + 1) % len(self.chases[self.active_chase])
            
            # Richiama se stessa dopo il delay
            threading.Timer(self.chase_speed, self._run_chase_logic).start()

    def stop_chase(self):
        self.active_chase = None