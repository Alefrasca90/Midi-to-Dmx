import serial
import threading
import time

class DMXController:
    """
    Gestisce la logica HTP e l'invio seriale.
    ORA: Il calcolo dei valori (HTP) è sempre attivo, anche offline.
    """
    def __init__(self):
        self.serial_port = None
        # Buffer Dati
        self.output_frame = bytearray([0] * 513)
        self.live_buffer = bytearray([0] * 513)
        self.scene_buffer = bytearray([0] * 513)
        self.chase_buffer = bytearray([0] * 513)
        self.cue_buffer = bytearray([0] * 513)
        
        self.running = True
        # Avvia SUBITO il thread di calcolo, così la GUI vede i dati anche offline
        self.thread = threading.Thread(target=self._send_loop, daemon=True)
        self.thread.start()

    def connect(self, port):
        """Apre la connessione alla porta seriale fisica."""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            
            self.serial_port = serial.Serial(port, baudrate=250000, stopbits=2)
            return True
        except Exception as e:
            print(f"Errore connessione Seriale: {e}")
            return False

    def _send_loop(self):
        """Ciclo continuo a 40Hz: Calcola HTP e, se connesso, invia DMX."""
        while self.running:
            try:
                # 1. FUSIONE HTP (Highest Takes Precedence)
                # Questo deve avvenire SEMPRE per aggiornare la grafica
                for i in range(1, 513):
                    self.output_frame[i] = max(
                        self.live_buffer[i], 
                        self.scene_buffer[i], 
                        self.chase_buffer[i], 
                        self.cue_buffer[i]
                    )
                
                # 2. INVIO HARDWARE (Solo se la porta è aperta)
                if self.serial_port and self.serial_port.is_open:
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                
                # Mantiene il loop a circa 40Hz
                time.sleep(0.025)
                
            except Exception as e:
                print(f"Errore nel loop DMX: {e}")
                time.sleep(1) # Attende prima di riprovare in caso di errore

    def stop(self):
        self.running = False
        if self.serial_port:
            self.serial_port.close()