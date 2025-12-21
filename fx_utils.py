import math
import colorsys

class FXUtils:
    @staticmethod
    def generate_steps(fixtures_data, fx_type, steps, spread):
        """
        Genera una lista di frame (step) per una chase basata su un algoritmo matematico.
        fixtures_data: Lista di dizionari fixture {'addr': int, 'profile': []}
        """
        generated_frames = []
        num_fix = len(fixtures_data)
        
        if num_fix == 0: return []

        for step_idx in range(steps):
            frame = {}
            # Tempo normalizzato dello step (0.0 -> 1.0)
            t_step = step_idx / steps 
            
            for fix_idx, fix in enumerate(fixtures_data):
                addr = fix["addr"]
                profile = fix["profile"]
                
                # Calcolo Fase: determina lo sfasamento tra i fari
                phase = 0
                if num_fix > 1:
                    phase = (fix_idx / (num_fix - 1)) * (spread / 100.0)
                
                # Onda sinusoidale base 0..1 usata per molti effetti
                wave = (math.sin(2 * math.pi * (t_step - phase)) + 1) / 2
                
                # --- LOGICA EFFETTI ---
                
                if "Rainbow" in fx_type:
                    # Scorre la ruota colore (Hue)
                    hue = (t_step + phase) % 1.0
                    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    r, g, b = int(r*255), int(g*255), int(b*255)
                    
                    for i, p_type in enumerate(profile):
                        if p_type == "Red": frame[str(addr+i)] = r
                        elif p_type == "Green": frame[str(addr+i)] = g
                        elif p_type == "Blue": frame[str(addr+i)] = b
                        elif p_type == "Dimmer": frame[str(addr+i)] = 255

                elif "Sine Wave" in fx_type:
                    # Dissolvenza morbida su/giù
                    val = int(wave * 255)
                    for i, p_type in enumerate(profile):
                        if p_type == "Dimmer": frame[str(addr+i)] = val
                        elif p_type in ["Red", "Green", "Blue", "White"]: frame[str(addr+i)] = val

                elif "Dimmer Chase" in fx_type:
                    # Acceso/Spento netto (Onda Quadra)
                    val = 255 if wave > 0.5 else 0
                    for i, p_type in enumerate(profile):
                        if p_type == "Dimmer": frame[str(addr+i)] = val
                        elif p_type in ["Red", "Green", "Blue"]: frame[str(addr+i)] = val

                elif "Police" in fx_type:
                    # Alternanza Rosso/Blu stile polizia
                    is_red = wave > 0.5
                    for i, p_type in enumerate(profile):
                        if p_type == "Red": frame[str(addr+i)] = 255 if is_red else 0
                        elif p_type == "Blue": frame[str(addr+i)] = 0 if is_red else 255
                        elif p_type == "Green": frame[str(addr+i)] = 0
                        elif p_type == "Dimmer": frame[str(addr+i)] = 255

                elif "Knight Rider" in fx_type:
                    # Effetto scanner avanti/indietro
                    ping_pong = 1 - abs((t_step * 2) % 2 - 1) # Va da 0 a 1 e torna a 0
                    target_pos = ping_pong * (num_fix - 1)
                    dist = abs(target_pos - fix_idx)
                    # Luminosità basata sulla distanza dal cursore virtuale
                    val = max(0, 255 - int(dist * 150))
                    
                    for i, p_type in enumerate(profile):
                        if p_type == "Red": frame[str(addr+i)] = val
                        elif p_type in ["Green", "Blue"]: frame[str(addr+i)] = 0
                        elif p_type == "Dimmer": frame[str(addr+i)] = 255

            generated_frames.append(frame)
            
        return generated_frames