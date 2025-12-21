import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal
import time

class AudioReactor(QThread):
    # Segnale: is_kick, is_snare, volume_norm, [bass, mid, high]
    data_processed = pyqtSignal(bool, bool, int, list)

    def __init__(self):
        super().__init__()
        self.device_index = None
        self.running = False
        self.gain = 1.0 # Slider utente (moltiplicatore extra)
        
        # --- AUTO GAIN CONTROL (AGC) ---
        # Serve a rendere il segnale indipendente dal volume di Windows
        self.rolling_peak = 0.01 # Valore massimo recente
        self.agc_decay = 0.995   # Quanto velocemente si adatta se abbassi il volume (Lento)
        
        # Parametri Audio
        self.samplerate = 44100
        self.blocksize = 1024 # Buffer size
        
        # Filtri energetici per Beat Detection
        self.bass_energy = 0
        self.mid_energy = 0
        self.high_energy = 0
        
        # Soglie dinamiche (per Kick/Snare)
        self.kick_threshold = 0.6
        self.snare_threshold = 0.6

    def get_devices(self):
        """Restituisce lista device (idx, name)"""
        try:
            devices = sd.query_devices()
            input_devices = []
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    # Filtra nomi strani se necessario
                    input_devices.append((i, d['name']))
            return input_devices
        except:
            return []

    def set_device(self, index):
        self.device_index = index

    def run(self):
        self.running = True
        try:
            with sd.InputStream(device=self.device_index, channels=1, callback=self.audio_callback,
                                blocksize=self.blocksize, samplerate=self.samplerate):
                while self.running:
                    self.msleep(10)
        except Exception as e:
            print(f"Audio Error: {e}")
            self.running = False

    def stop(self):
        self.running = False
        self.wait()

    def audio_callback(self, indata, frames, time_info, status):
        if not self.running: return
        
        # 1. Copia dati e rimuovi DC offset
        audio_data = indata[:, 0].copy()
        audio_data -= np.mean(audio_data) # Centra l'onda
        
        # 2. AUTO GAIN CONTROL (Il cuore della stabilità)
        # Trova il picco attuale
        current_peak = np.max(np.abs(audio_data))
        
        # Aggiorna il picco "storico" (Rolling Peak)
        if current_peak > self.rolling_peak:
            # Se il segnale sale, adattati subito (Attack veloce)
            self.rolling_peak = current_peak
        else:
            # Se il segnale scende, adattati lentamente (Decay lento)
            # Questo evita che il "silenzio" venga amplificato a rumore
            self.rolling_peak *= self.agc_decay
            
        # Protezione divisione per zero
        if self.rolling_peak < 0.001: self.rolling_peak = 0.001
        
        # NORMALIZZAZIONE: Porta il segnale a un livello standard (0.0 - 1.0)
        # Ora l'audio è indipendente dal volume di Windows!
        normalized_audio = audio_data / self.rolling_peak
        
        # Applica Gain Utente (Slider UI)
        # Moltiplichiamo per 2.0 di base per avere un segnale bello caldo
        normalized_audio *= (self.gain * 2.0)
        
        # 3. FFT (Analisi Spettro su Audio Normalizzato)
        fft_data = np.fft.rfft(normalized_audio * np.hanning(len(normalized_audio)))
        fft_mag = np.abs(fft_data)
        
        # Mapping Frequenze (Indici approssimativi per 44.1kHz / 1024 buffer)
        # Bass: 20-150Hz -> idx 1-4
        # Mid: 200-2000Hz -> idx 5-40
        # High: 2kHz-10kHz -> idx 40-200
        
        b_idx = slice(1, 5)
        m_idx = slice(5, 45)
        h_idx = slice(45, 250)
        
        bass_raw = np.sum(fft_mag[b_idx])
        mid_raw  = np.sum(fft_mag[m_idx])
        high_raw = np.sum(fft_mag[h_idx])
        
        # 4. Smoothing Energie
        self.bass_energy = (self.bass_energy * 0.6) + (bass_raw * 0.4)
        self.mid_energy  = (self.mid_energy * 0.6) + (mid_raw * 0.4)
        self.high_energy = (self.high_energy * 0.6) + (high_raw * 0.4)
        
        # 5. Beat Detection (Soglie Dinamiche)
        # Se l'energia istantanea supera la media recente * threshold
        is_kick = False
        is_snare = False
        
        # Logica semplice ma efficace su segnale normalizzato
        if self.bass_energy > 8 and bass_raw > (self.bass_energy * 1.3):
            is_kick = True
            
        if self.high_energy > 5 and high_raw > (self.high_energy * 1.3):
            is_snare = True
            
        # 6. Scaling finale per UI (0-255)
        # Usiamo tanh per saturazione morbida (non taglia di netto a 255)
        def scale(val):
            return int(np.tanh(val / 30.0) * 255)

        vol_disp = int(np.mean(np.abs(normalized_audio)) * 255 * 2) # Volume medio per barra
        vol_disp = min(255, vol_disp)
        
        spec_list = [
            scale(self.bass_energy),
            scale(self.mid_energy),
            scale(self.high_energy)
        ]
        
        self.data_processed.emit(is_kick, is_snare, vol_disp, spec_list)