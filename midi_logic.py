import mido
import json
import os

class MIDIManager:
    def __init__(self, dmx_controller):
        self.dmx = dmx_controller
        self.input_port = None
        self.mappings = {}  # Esempio: {'cc_7': 1, 'note_60': 12}
        self.is_learning = False
        self.last_learned_signal = None

    def open_port(self, port_name):
        try:
            if self.input_port:
                self.input_port.close()
            self.input_port = mido.open_input(port_name, callback=self._handle_message)
            return True
        except Exception as e:
            print(f"Errore apertura porta MIDI: {e}")
            return False

    def _handle_message(self, msg):
        sig_id = None
        val = 0

        # Riconoscimento del tipo di messaggio
        if msg.type == 'control_change':
            sig_id = f"cc_{msg.control}"
            val = int(msg.value * 2.007) # Scala 0-127 a 0-255
        elif msg.type == 'note_on':
            if msg.velocity > 0: # Alcuni controller usano note_on con velocity 0 come note_off
                sig_id = f"note_{msg.note}"
                val = 255
        elif msg.type == 'note_off':
            sig_id = f"note_{msg.note}"
            val = 0

        if sig_id:
            if self.is_learning:
                # Cattura il segnale e ferma il modo learn
                self.last_learned_signal = sig_id
                self.is_learning = False 
            elif sig_id in self.mappings:
                # Modalità normale: invio al DMX
                target_dmx_ch = self.mappings[sig_id]
                self.dmx.set_channel(target_dmx_ch, val)

    def save_mappings(self, filename="mapping_store.json"):
        with open(filename, 'w') as f:
            json.dump(self.mappings, f)
        print("Mappature salvate.")

    def load_mappings(self, filename="mapping_store.json"):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                self.mappings = json.load(f)
            print("Mappature caricate.")