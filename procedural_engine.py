import time
import math
import random
import colorsys

class SmoothValue:
    def __init__(self, decay=0.9, attack=0.5):
        self.value = 0.0
        self.decay = decay
        self.attack = attack
    def update(self, target):
        if target > self.value: self.value += (target - self.value) * self.attack
        else: self.value *= self.decay
        return self.value

class GenerativeEffect:
    def __init__(self, name, target_list, data_store):
        self.name = name
        self.target_list = target_list
        self.data = data_store
        self.active = True
        self.intensity = 1.0
        self.phase = 0.0
        
        # PARAMETRI PER L'UTENTE
        self.threshold = 0.2 # Soglia di attivazione (0.0 - 1.0)
        self.current_signal = 0.0 # Valore da mostrare nella barra UI (0-255)
        
        self.smoother = SmoothValue(decay=0.92, attack=0.3) 

    def get_fixtures_data(self):
        fixtures = []
        for name in self.target_list:
            fdata = self.data["fixtures"].get(name)
            if fdata and isinstance(fdata, dict): fixtures.append(fdata)
        fixtures.sort(key=lambda x: x["addr"])
        return fixtures

    def apply_pixel(self, buffer, addr, profile, r, g, b, dim, strobe=0):
        for i, p_type in enumerate(profile):
            val = 0
            if p_type == "Red": val = r
            elif p_type == "Green": val = g
            elif p_type == "Blue": val = b
            elif p_type == "White": val = max(0, (r+g+b - 240))
            elif p_type == "Dimmer": val = dim
            elif p_type == "Strobe": val = strobe
            
            val = int(val * self.intensity)
            target_ch = addr + i
            current = buffer.get(target_ch, 0)
            buffer[target_ch] = max(current, val)

    def tick(self, audio, render_buffer):
        pass

# --- ALGORITMI RISCRITTI ---

class FX_SpectralEQ(GenerativeEffect):
    """
    Divide le fixture fisicamente:
    Sinistra = Bassi (Rosso) | Centro = Medi (Verde) | Destra = Alti (Blu)
    """
    def tick(self, audio, render_buffer):
        fixtures = self.get_fixtures_data()
        count = len(fixtures)
        if count == 0: return
        
        # Segnale medio per la visualizzazione UI
        avg_signal = (audio['Bass'] + audio['Mid'] + audio['High']) / 3
        self.current_signal = avg_signal 

        for i, fix in enumerate(fixtures):
            pos = i / count # 0.0 a 1.0
            
            r, g, b, dim = 0, 0, 0, 0
            val = 0
            
            # Logica Posizionale
            if pos < 0.33: # BASSI
                val = audio['Bass']
                # Applica soglia solo ai bassi se vuoi, qui lo facciamo pulito
                if val < (self.threshold * 255): val = 0
                r = 255
            elif pos < 0.66: # MEDI
                val = audio['Mid']
                if val < (self.threshold * 255): val = 0
                g = 255
            else: # ALTI
                val = audio['High']
                if val < (self.threshold * 255): val = 0
                b = 255
            
            # Dimmer proporzionale al volume
            dim = val
            
            self.apply_pixel(render_buffer, fix["addr"], fix["profile"], r, g, b, dim)

class FX_SnareExplosion(GenerativeEffect):
    """
    Buio totale. Flash Bianco su Rullante.
    """
    def __init__(self, name, targets, data):
        super().__init__(name, targets, data)
        self.decay = 0.0

    def tick(self, audio, render_buffer):
        # Trigger diretto
        is_snare = audio['SnareTrig']
        
        # Mostra nella UI se c'è il trigger
        self.current_signal = 255 if is_snare else 0
        
        # Usa la soglia dell'utente per filtrare falsi positivi
        # Nota: SnareTrig è booleano, ma potremmo usare l'energia High come fallback
        high_energy = audio['High'] / 255.0
        
        trigger = False
        if is_snare: trigger = True
        # Se l'utente alza molto la soglia, richiediamo anche alta energia sugli alti
        if self.threshold > 0.5 and high_energy < self.threshold:
            trigger = False

        if trigger:
            self.decay = 255.0
        else:
            self.decay *= 0.75 # Fade out molto veloce
            
        if self.decay < 10: return
        
        val = int(self.decay)
        fixtures = self.get_fixtures_data()
        for fix in fixtures:
            # Bianco Ghiaccio (RGB 255,255,255)
            self.apply_pixel(render_buffer, fix["addr"], fix["profile"], 255, 255, 255, val)

class FX_BassWave(GenerativeEffect):
    def tick(self, audio, render_buffer):
        bass = audio['Bass'] / 255.0
        self.current_signal = audio['Bass']
        
        # Se il basso è sotto soglia, l'onda si ferma o si spegne
        if bass < self.threshold:
            brightness_mult = 0.1 # Minima luce di fondo
        else:
            brightness_mult = 1.0
            
        self.phase += 0.05 + (bass * 0.15)
        
        fixtures = self.get_fixtures_data()
        for i, fix in enumerate(fixtures):
            pos = i / len(fixtures)
            wave = (math.sin(self.phase - (pos * 3.0)) + 1) / 2 
            
            # Colore
            if wave > 0.8 and bass > self.threshold:
                r, g, b = 255, 50, 0 # Picco Rosso
            else:
                r, g, b = int(100*wave), 0, 200 # Fondo Viola
            
            dim = int(wave * 255 * brightness_mult)
            self.apply_pixel(render_buffer, fix["addr"], fix["profile"], r, g, b, dim)

class FX_SmartSolo(GenerativeEffect):
    def __init__(self, name, targets, data):
        super().__init__(name, targets, data)
        self.hue = 0.1 

    def tick(self, audio, render_buffer):
        mid = audio['Mid']
        self.current_signal = mid
        
        # SOGLIA FONDAMENTALE QUI:
        # Se i medi non superano la soglia impostata dallo slider, spegni
        target = mid if mid > (self.threshold * 255) else 0
        
        val = self.smoother.update(target)
        if val < 5: return

        self.hue = (self.hue + 0.001) % 1.0
        rgb = colorsys.hsv_to_rgb(self.hue, 0.9, 1.0)
        r, g, b = [int(c * 255) for c in rgb]
        
        fixtures = self.get_fixtures_data()
        for fix in fixtures:
            self.apply_pixel(render_buffer, fix["addr"], fix["profile"], r, g, b, int(val))

# --- MOTORE ---
class ProceduralEngine:
    def __init__(self, data_store):
        self.data_store = data_store
        self.active_effects = []

    def add_effect(self, type_key, target_list):
        if not target_list: return
        fx = None
        if "Bass Wave" in type_key: fx = FX_BassWave(type_key, target_list, self.data_store)
        elif "Spectral" in type_key: fx = FX_SpectralEQ(type_key, target_list, self.data_store)
        elif "Snare" in type_key: fx = FX_SnareExplosion(type_key, target_list, self.data_store)
        elif "Smart Solo" in type_key: fx = FX_SmartSolo(type_key, target_list, self.data_store)
        if fx: self.active_effects.append(fx)

    def remove_effect(self, index):
        if 0 <= index < len(self.active_effects):
            self.active_effects.pop(index)
    
    def get_active_effect(self, index):
        if 0 <= index < len(self.active_effects):
            return self.active_effects[index]
        return None

    def tick(self, audio_data, dmx_controller):
        render_layer = {}
        # 1. Blackout selettivo
        involved_channels = set()
        for fx in self.active_effects:
            if fx.active:
                for fix_data in fx.get_fixtures_data():
                    start = fix_data["addr"]
                    length = len(fix_data["profile"])
                    for c in range(start, start + length):
                        involved_channels.add(c)
        for ch in involved_channels:
            if ch < 513: dmx_controller.live_buffer[ch] = 0
        
        # 2. Rendering
        for fx in self.active_effects:
            if fx.active:
                fx.tick(audio_data, render_layer)
        
        # 3. Output
        for ch, val in render_layer.items():
            if ch < 513: dmx_controller.live_buffer[ch] = val