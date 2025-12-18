import mido
from PyQt6.QtCore import QObject, pyqtSignal

class MidiManager(QObject):
    learn_status_changed = pyqtSignal(bool, str)
    request_ui_refresh = pyqtSignal()
    
    def __init__(self, playback_engine, dmx_ctrl, data_store):
        super().__init__()
        self.engine = playback_engine
        self.dmx = dmx_ctrl
        self.data = data_store
        
        self.input_port = None
        self.is_learning = False
        self.learn_target = None
        self.selected_channels = set()

    def open_port(self, name):
        try:
            if self.input_port: self.input_port.close()
            self.input_port = mido.open_input(name, callback=self._callback)
            return True
        except: return False

    def toggle_learn(self, target="chans"):
        self.is_learning = not self.is_learning
        self.learn_target = target if self.is_learning else None
        self.learn_status_changed.emit(self.is_learning, self.learn_target)

    def _callback(self, msg):
        sig_key = None
        if msg.type == 'control_change': sig_key = f"cc_{msg.control}"
        elif msg.type in ['note_on', 'note_off']: sig_key = f"note_{msg.note}"
        
        if not sig_key: return

        if self.is_learning:
            if self.learn_target == "chans":
                self.data["map"][sig_key] = list(self.selected_channels)
            else:
                self.data["rem"][sig_key] = self.learn_target
            
            self.is_learning = False
            self.learn_status_changed.emit(False, None)
            self.request_ui_refresh.emit()
            return

        if sig_key in self.data["map"]:
            val = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.type=='note_on' and msg.velocity>0 else 0)
            for ch in self.data["map"][sig_key]:
                self.dmx.live_buffer[ch] = val
            self.request_ui_refresh.emit()

        elif sig_key in self.data["rem"]:
            if (msg.type == 'note_on' and msg.velocity > 0) or (msg.type == 'control_change' and msg.value > 0):
                target = self.data["rem"][sig_key].split(":", 1)
                t_type, t_name = target[0], target[1]
                if t_type == "sc": self.engine.toggle_scene(t_name)
                elif t_type == "ch": self.engine.toggle_chase(t_name)
                elif t_type == "cue": self.engine.toggle_cue(t_name)