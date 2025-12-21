import mido
from PyQt6.QtCore import QObject, pyqtSignal

class MidiManager(QObject):
    learn_status_changed = pyqtSignal(bool, str)
    request_ui_refresh = pyqtSignal()
    new_midi_message = pyqtSignal(str)
    
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
            print(f"[MIDI] Tentativo connessione a: {name}")
            self.input_port = mido.open_input(name, callback=self._callback)
            print(f"[MIDI] Connesso con successo a: {name}")
            return None 
        except Exception as e:
            err_msg = str(e)
            print(f"[MIDI] ERRORE CONNESSIONE: {err_msg}")
            return err_msg

    def toggle_learn(self, target="chans"):
        self.is_learning = not self.is_learning
        self.learn_target = target if self.is_learning else None
        self.learn_status_changed.emit(self.is_learning, self.learn_target)

    def _callback(self, msg):
        # DEBUG LOG
        try:
            debug_parts = [msg.type]
            if hasattr(msg, 'channel'): debug_parts.append(f"Ch:{msg.channel}")
            if hasattr(msg, 'control'): debug_parts.append(f"CC:{msg.control}")
            if hasattr(msg, 'note'): debug_parts.append(f"Note:{msg.note}")
            if hasattr(msg, 'value'): debug_parts.append(f"Val:{msg.value}")
            self.new_midi_message.emit(" ".join(debug_parts))
        except: pass

        sig_key = None
        if msg.type == 'control_change': sig_key = f"cc_{msg.control}"
        elif msg.type in ['note_on', 'note_off']: sig_key = f"note_{msg.note}"
        
        if not sig_key: return

        # --- LEARNING MODE (MODIFICATO PER MULTI-MAPPING) ---
        if self.is_learning:
            if self.learn_target == "chans":
                # Mappatura canali diretti (Grid) - Questa resta esclusiva per semplicità
                self.data["map"][sig_key] = list(self.selected_channels)
            else:
                # Mappatura Remota (Scene, Chase, Global) - SUPPORTO LISTE
                if sig_key in self.data["rem"]:
                    current = self.data["rem"][sig_key]
                    # Se è già una lista, aggiungi. Se è stringa, converti in lista.
                    if isinstance(current, list):
                        if self.learn_target not in current:
                            current.append(self.learn_target)
                    elif current != self.learn_target:
                        self.data["rem"][sig_key] = [current, self.learn_target]
                else:
                    # Nuova mappatura
                    self.data["rem"][sig_key] = self.learn_target
            
            self.is_learning = False
            self.learn_status_changed.emit(False, None)
            self.request_ui_refresh.emit()
            return

        # --- EXECUTION MODE ---

        # 1. Direct Channel Mapping
        if sig_key in self.data["map"]:
            val = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.type=='note_on' and msg.velocity>0 else 0)
            for ch in self.data["map"][sig_key]:
                self.dmx.live_buffer[ch] = val
            self.request_ui_refresh.emit()

        # 2. Remote Triggers (Gestione Liste)
        if sig_key in self.data["rem"]:
            # Normalizza tutto a lista per iterare facilmente
            targets = self.data["rem"][sig_key]
            if not isinstance(targets, list):
                targets = [targets]

            needs_refresh = False
            
            for full_target in targets:
                target = full_target.split(":", 1)
                t_type, t_name = target[0], target[1]
                
                # Calcolo valore raw
                raw_val = 0
                if msg.type == 'control_change':
                    raw_val = int(msg.value * 2.007)
                elif msg.type == 'note_on' and msg.velocity > 0:
                    raw_val = 255

                # Esecuzione in base al tipo
                if t_type == "grp":
                    group_chans = self.data["groups"].get(t_name, [])
                    for ch in group_chans:
                        self.dmx.live_buffer[ch] = raw_val
                    needs_refresh = True
                
                elif t_type == "global":
                    if t_name in self.data["globals"]:
                        self.data["globals"][t_name] = raw_val
                        needs_refresh = True

                # Trigger standard (solo se superano soglia o note on)
                elif (msg.type == 'note_on' and msg.velocity > 0) or (msg.type == 'control_change' and msg.value > 64):
                    if t_type == "sc": self.engine.toggle_scene(t_name)
                    elif t_type == "ch": self.engine.toggle_chase(t_name)
                    elif t_type == "cue": self.engine.toggle_cue(t_name)
            
            if needs_refresh:
                self.request_ui_refresh.emit()