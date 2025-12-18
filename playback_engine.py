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
            if self.play_idx_cue < len(cue_data):
                self.dmx.cue_buffer = bytearray(cue_data[self.play_idx_cue])
                self.play_idx_cue += 1
            else:
                self.play_idx_cue = 0

    def _process_chase(self, config):
        steps = config["steps"]
        hold_ms = config["h"]
        fade_ms = config["f"]
        cycle_total = hold_ms + fade_ms
        
        now_ms = int(time.time() * 1000)
        elapsed = (now_ms - self.fade_start_ch) % (cycle_total * len(steps))
        
        idx = elapsed // cycle_total
        t_in_step = elapsed % cycle_total
        
        sc_a = self.data["scenes"].get(steps[idx], {})
        sc_b = self.data["scenes"].get(steps[(idx + 1) % len(steps)], {})
        
        buf = bytearray([0] * 513)
        for i in range(1, 513):
            val_a = sc_a.get(str(i), 0)
            if t_in_step < hold_ms:
                buf[i] = val_a
            else:
                val_b = sc_b.get(str(i), 0)
                prog = (t_in_step - hold_ms) / fade_ms
                buf[i] = int(val_a + (val_b - val_a) * prog)
        self.dmx.chase_buffer = buf

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
        """Ferma tutto e azzera TUTTI i buffer, incluso quello live."""
        self.active_sc = self.active_ch = self.active_cue = None
        self.is_recording_cue = False
        
        # FIX: Azzera anche il buffer live (manuale)
        self.dmx.live_buffer = bytearray([0] * 513)
        self.dmx.scene_buffer = bytearray([0] * 513)
        self.dmx.chase_buffer = bytearray([0] * 513)
        self.dmx.cue_buffer = bytearray([0] * 513)
        
        self.state_changed.emit()