import random

class AudioLink:
    def __init__(self, source_type, target_group, target_attr, min_v=0, max_v=255):
        self.source_type = source_type # "Bass", "Mid", "High", "Volume", "Kick (Trig)", "Snare (Trig)"
        self.target_group = target_group 
        self.target_attr = target_attr   # "Dimmer", "Red", "Green", "Blue", "Strobe", "Pan", "Tilt"
        
        self.min_val = min_v
        self.max_val = max_v
        
        self.current_value = 0.0
        self.decay_factor = 0.85 
        self.is_trigger = "Trig" in source_type
        
        if self.is_trigger:
            self.decay_factor = 0.90 

    def process(self, audio_data):
        # Mappa i nomi della combo box alle chiavi dei dati audio
        key_map = {
            "Bass (Low)": "Bass",
            "Mid (Voice)": "Mid",
            "High (Hat)": "High",
            "Volume": "Volume",
            "Kick (Trig)": "KickTrig",
            "Snare (Trig)": "SnareTrig"
        }
        
        data_key = key_map.get(self.source_type, self.source_type)
        
        if self.is_trigger:
            is_active = audio_data.get(data_key, False)
            if is_active:
                self.current_value = 255.0
            else:
                self.current_value *= self.decay_factor
                if self.current_value < 1: self.current_value = 0
            
            final_val = int(self.current_value)
            
        else:
            raw_val = audio_data.get(data_key, 0)
            
            smooth = 0.5
            if "Bass" in self.source_type: smooth = 0.2
            if "Mid" in self.source_type:  smooth = 0.1
            if "High" in self.source_type: smooth = 0.6
            
            self.current_value = (self.current_value * smooth) + (raw_val * (1.0 - smooth))
            final_val = int(self.current_value)

        range_span = self.max_val - self.min_val
        scaled_val = self.min_val + (final_val / 255.0) * range_span
        
        return max(0, min(255, int(scaled_val)))

class ReactionEngine:
    def __init__(self, data_store):
        self.data_store = data_store
        self.links = [] 

    def add_link(self, source, group, attr):
        link = AudioLink(source, group, attr)
        self.links.append(link)

    def remove_link_by_index(self, index):
        if 0 <= index < len(self.links):
            self.links.pop(index)

    def tick(self, audio_snapshot, dmx_controller):
        if not self.links: return

        for link in self.links:
            val = link.process(audio_snapshot)
            
            group_name = link.target_group
            channels = self.data_store["groups"].get(group_name, [])
            
            if not channels: continue
            
            for ch in channels:
                # Cerca se questo canale corrisponde all'attributo richiesto
                # Iteriamo sulle fixture per trovare a chi appartiene il canale
                real_target_ch = -1
                
                for fix_name, fix_data in self.data_store["fixtures"].items():
                    if isinstance(fix_data, int): continue 
                    
                    addr = fix_data["addr"]
                    profile = fix_data["profile"]
                    
                    if addr <= ch < addr + len(profile):
                        idx_inside = ch - addr
                        type_of_ch = profile[idx_inside]
                        
                        if type_of_ch == link.target_attr:
                            real_target_ch = ch
                            break
                
                if real_target_ch != -1:
                    dmx_controller.live_buffer[real_target_ch] = val