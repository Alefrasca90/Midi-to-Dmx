import time
import numpy as np
import pyaudio
from PyQt6.QtCore import QThread, pyqtSignal

class AudioReactor(QThread):
    # Segnale emesso ~40 volte al secondo:
    # is_beat (bool): True se è stato rilevato un colpo di cassa
    # volume (int): 0-255 livello volume generale
    # spectrum (list): [bassi, medi, alti] valori 0-255
    data_processed = pyqtSignal(bool, int, list)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.device_index = None
        self.gain = 1.0
        
        # Parametri Audio
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100
        
        self.p = pyaudio.PyAudio()
        
        # Variabili per Beat Detection
        self.bass_history = []
        self.last_beat_time = 0
        self.beat_threshold = 1.3 # Quanto deve essere più forte della media per essere un beat

    def get_devices(self):
        """Ritorna lista dispositivi input (indice, nome)"""
        devices = []
        try:
            info = self.p.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            for i in range(0, numdevices):
                dev_info = self.p.get_device_info_by_host_api_device_index(0, i)
                if dev_info.get('maxInputChannels') > 0:
                    devices.append((i, dev_info.get('name')))
        except: pass
        return devices

    def set_device(self, index):
        self.device_index = index

    def run(self):
        if self.device_index is None: return
        
        self.running = True
        stream = None
        
        try:
            stream = self.p.open(format=self.FORMAT,
                                 channels=self.CHANNELS,
                                 rate=self.RATE,
                                 input=True,
                                 input_device_index=self.device_index,
                                 frames_per_buffer=self.CHUNK)
            
            while self.running:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    
                    # 1. Volume RMS (Root Mean Square)
                    rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
                    vol_norm = min(255, int((rms / 1000) * 255 * self.gain))
                    
                    # 2. FFT (Analisi Spettro)
                    fft_data = np.fft.rfft(audio_data)
                    fft_freq = np.fft.rfftfreq(self.CHUNK, 1.0/self.RATE)
                    magnitude = np.abs(fft_data)
                    
                    # Bande di frequenza
                    # Bassi: < 150Hz
                    # Medi: 150Hz - 2500Hz
                    # Alti: > 2500Hz
                    bass_mask = (fft_freq < 150)
                    mid_mask = (fft_freq >= 150) & (fft_freq < 2500)
                    high_mask = (fft_freq >= 2500)
                    
                    bass_energy = np.mean(magnitude[bass_mask]) if np.any(bass_mask) else 0
                    mid_energy = np.mean(magnitude[mid_mask]) if np.any(mid_mask) else 0
                    high_energy = np.mean(magnitude[high_mask]) if np.any(high_mask) else 0
                    
                    # Normalizzazione visuale (valori empirici)
                    b_val = min(255, int((bass_energy / 10000) * 255 * self.gain))
                    m_val = min(255, int((mid_energy / 5000) * 255 * self.gain))
                    h_val = min(255, int((high_energy / 2000) * 255 * self.gain))
                    
                    # 3. Beat Detection (Semplice)
                    is_beat = False
                    self.bass_history.append(bass_energy)
                    if len(self.bass_history) > 20: # ~0.5 secondi di storia
                        self.bass_history.pop(0)
                        
                    avg_energy = np.mean(self.bass_history)
                    
                    # Se l'energia attuale supera la media * threshold e c'è abbastanza volume
                    if bass_energy > avg_energy * self.beat_threshold and bass_energy > 2000:
                        # Debounce (max 1 beat ogni 0.25s)
                        if (time.time() - self.last_beat_time) > 0.25:
                            is_beat = True
                            self.last_beat_time = time.time()
                    
                    self.data_processed.emit(is_beat, vol_norm, [b_val, m_val, h_val])
                    
                except Exception as e:
                    print(f"Audio processing error: {e}")
                    break
                    
        except Exception as e:
            print(f"Audio Stream Error: {e}")
        
        finally:
            if stream:
                stream.stop_stream()
                stream.close()

    def stop(self):
        self.running = False
        self.wait()