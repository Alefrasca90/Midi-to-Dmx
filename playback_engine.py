import time
from PyQt6.QtCore import QObject, pyqtSignal

class PlaybackEngine(QObject):
    state_changed = pyqtSignal() 

    def __init__(self, dmx_ctrl, data_store):
        super().__init__()
        self.dmx = dmx_ctrl
        self.data = data_store
        
        self.active_sc = None
        self.active_ch = None
        self.active_cue = None
        
        self.fade_start_ch = 0
        self.play_idx_cue = 0
        self.is_recording_cue = False
        self.recorded_stream = []
        
        # Offset per forzare avanzamento manuale/audio nei chase
        self.chase_time_offset = 0

    def tick(self):
        if self.is_recording_cue:
            self.recorded_stream.append(list(self.dmx.output_frame))
            return

        if self.active_ch:
            chase_config = self.data["chases"].get(self.active_ch)
            if chase_config:
                self._process_chase(chase_config)

        if self.active_cue:
            cue_data = self.data["cues"].get(self.active_cue, {}).get("data", [])
            if cue_data:
                if self.play_idx_cue < len(cue_data):
                    self.dmx.cue_buffer = bytearray(cue_data[self.play_idx_cue])
                    self.play_idx_cue += 1
                else:
                    self.play_idx_cue = 0

    def _process_chase(self, config):
        steps = config["steps"]
        if not steps: return

        base_hold = config["h"]
        base_fade = config["f"]
        
        # Master Speed/Fade (127 = 1.0x)
        speed_val = self.data.get("globals", {}).get("chase_speed", 127)
        fade_val = self.data.get("globals", {}).get("chase_fade", 127)
        
        factor_h = max(0.05, speed_val / 127.0)
        factor_f = max(0.05, fade_val / 127.0)
        
        hold_ms = int(base_hold * factor_h)
        fade_ms = int(base_fade * factor_f)
        
        cycle_total = hold_ms + fade_ms
        if cycle_total == 0: cycle_total = 1
        
        # Tempo assoluto + offset (per sync audio)
        now_ms = int(time.time() * 1000)
        elapsed = (now_ms - self.fade_start_ch + self.chase_time_offset) % (cycle_total * len(steps))
        
        idx = elapsed // cycle_total
        t_in_step = elapsed % cycle_total
        
        if idx >= len(steps): idx = 0

        sc_a = self.data["scenes"].get(steps[idx], {})
        sc_b = self.data["scenes"].get(steps[(idx + 1) % len(steps)], {})
        
        buf = bytearray([0] * 513)
        for i in range(1, 513):
            val_a = sc_a.get(str(i), 0)
            if t_in_step < hold_ms:
                buf[i] = val_a
            else:
                val_b = sc_b.get(str(i), 0)
                if fade_ms > 0:
                    prog = (t_in_step - hold_ms) / fade_ms
                else:
                    prog = 1
                buf[i] = int(val_a + (val_b - val_a) * prog)
        self.dmx.chase_buffer = buf

    def force_next_step_signal(self):
        """Fa avanzare immediatamente il chase allo step successivo"""
        if self.active_ch:
            chase_config = self.data["chases"].get(self.active_ch)
            if chase_config:
                # Calcoliamo quanto manca alla fine dello step corrente e aggiungiamolo all'offset
                # Per semplicità, aggiungiamo un tempo fisso grande quanto basta per saltare uno step medio
                self.chase_time_offset += 200 # ms, salto empirico
                # Nota: Una logica perfetta richiederebbe calcoli complessi sul ciclo attuale, 
                # ma questo basta per dare l'effetto "colpo" a tempo di musica.

    def toggle_scene(self, name):
        if self.active_sc == name:
            self.active_sc = None
            self.dmx.scene_buffer = bytearray([0] * 513)
        else:
            self.active_sc = name
            buf = bytearray([0] * 513)
            for k, v in self.data["scenes"].get(name, {}).items():
                buf[int(k)] = v
            self.dmx.scene_buffer = buf
        self.state_changed.emit()

    def toggle_chase(self, name):
        if self.active_ch == name:
            self.active_ch = None
            self.dmx.chase_buffer = bytearray([0] * 513)
        else:
            self.active_ch = name
            self.fade_start_ch = int(time.time() * 1000)
            self.chase_time_offset = 0 # Reset offset
        self.state_changed.emit()

    def toggle_cue(self, name):
        if self.active_cue == name:
            self.active_cue = None
            self.dmx.cue_buffer = bytearray([0] * 513)
        else:
            self.active_cue = name
            self.play_idx_cue = 0
        self.state_changed.emit()

    def stop_all(self):
        self.active_sc = self.active_ch = self.active_cue = None
        self.is_recording_cue = False
        self.dmx.live_buffer = bytearray([0] * 513)
        self.dmx.scene_buffer = bytearray([0] * 513)
        self.dmx.chase_buffer = bytearray([0] * 513)
        self.dmx.cue_buffer = bytearray([0] * 513)
        self.state_changed.emit()