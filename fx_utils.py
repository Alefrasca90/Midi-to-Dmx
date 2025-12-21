import math
import colorsys
import random

class FXUtils:
    @staticmethod
    def generate_steps(fixtures_data, fx_type, steps, spread, palette):
        """
        Genera i frame.
        palette: Lista di tuple colore [(r,g,b), (r,g,b), ...]
        """
        generated_frames = []
        num_fix = len(fixtures_data)
        if num_fix == 0: return []
        
        # Se la palette è vuota, metti bianco di default
        if not palette: palette = [(255, 255, 255)]

        for step_idx in range(steps):
            frame = {}
            t_step = step_idx / steps 
            
            for fix_idx, fix in enumerate(fixtures_data):
                addr = fix["addr"]
                profile = fix["profile"]
                
                # Fase per onde
                phase = 0
                if num_fix > 1:
                    phase = (fix_idx / (num_fix - 1)) * (spread / 100.0)
                
                # Seleziona colore dalla palette in base all'indice fixture (o altro pattern)
                # Cycling: Fixture 1 -> Colore 1, Fixture 2 -> Colore 2, etc.
                color_idx = fix_idx % len(palette)
                pr, pg, pb = palette[color_idx]

                # Calcoli Onda
                wave_sin = (math.sin(2 * math.pi * (t_step - phase)) + 1) / 2
                wave_sq = 1.0 if wave_sin > 0.5 else 0.0
                
                # --- ALGORITMI ---
                
                r, g, b, dim = 0, 0, 0, 0

                # 1. BLINDER (Flash & Fade) - NUOVO
                if "Blinder" in fx_type:
                    # Dente di sega invertito: parte da 1.0 e scende a 0.0 nello step
                    # Ignoriamo la fase per i blinder solitamente (colpo unico), 
                    # MA se c'è spread, facciamo blinder sequenziale!
                    
                    # Calcoliamo posizione locale nell'onda
                    local_t = (t_step - phase) % 1.0
                    
                    # Curva di decadimento esponenziale per realismo
                    # intensity = max(0, 1.0 - local_t * 2) # Decadimento veloce
                    intensity = math.exp(-5 * local_t) 
                    
                    # I blinder di solito sono Bianchi o Ambra
                    # Usiamo la palette se definita, altrimenti forza bianco caldo
                    r = int(pr * intensity)
                    g = int(pg * intensity)
                    b = int(pb * intensity)
                    dim = int(255 * intensity)

                # 2. COLOR PULSE
                elif "Color Pulse" in fx_type:
                    r = int(pr * wave_sin)
                    g = int(pg * wave_sin)
                    b = int(pb * wave_sin)
                    dim = int(255 * wave_sin)

                # 3. COLOR CHASE
                elif "Color Chase" in fx_type:
                    r = int(pr * wave_sq)
                    g = int(pg * wave_sq)
                    b = int(pb * wave_sq)
                    dim = 255 if wave_sq > 0 else 0

                # 4. SPARKLE
                elif "Sparkle" in fx_type:
                    is_spark = random.random() > 0.90
                    mult = 1.0 if is_spark else 0.05
                    r, g, b = int(pr * mult), int(pg * mult), int(pb * mult)
                    dim = 255 if is_spark else 20

                # 5. FIRE
                elif "Fire" in fx_type:
                    flicker = random.uniform(0.5, 1.0)
                    r = int(255 * flicker)
                    g = int(100 * flicker * random.uniform(0.0, 1.0))
                    b = 0
                    dim = 255

                # 6. KNIGHT RIDER
                elif "Knight Rider" in fx_type:
                    ping_pong = 1 - abs((t_step * 2) % 2 - 1)
                    target_pos = ping_pong * (num_fix - 1)
                    dist = abs(target_pos - fix_idx)
                    val_norm = max(0, 1.0 - (dist * 0.8))
                    r = int(pr * val_norm)
                    g = int(pg * val_norm)
                    b = int(pb * val_norm)
                    dim = int(255 * val_norm)

                # 7. STROBE
                elif "Strobe" in fx_type:
                    is_on = random.choice([True, False])
                    if is_on: r, g, b, dim = pr, pg, pb, 255
                    else: r, g, b, dim = 0, 0, 0, 0

                # 8. RAINBOW / POLICE (Override palette)
                elif "Rainbow" in fx_type:
                    hue = (t_step + phase) % 1.0
                    tr, tg, tb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    r, g, b, dim = int(tr*255), int(tg*255), int(tb*255), 255
                elif "Police" in fx_type:
                    is_red = wave_sin > 0.5
                    if is_red: r, g, b = 255, 0, 0
                    else: r, g, b = 0, 0, 255
                    dim = 255

                # --- MAPPING ---
                for i, p_type in enumerate(profile):
                    val = 0
                    if p_type == "Red": val = r
                    elif p_type == "Green": val = g
                    elif p_type == "Blue": val = b
                    elif p_type == "White": val = 0 # O derivato da palette se RGBW
                    elif p_type == "Dimmer": val = dim
                    elif p_type == "Strobe": val = 0
                    
                    frame[str(addr+i)] = val

            generated_frames.append(frame)
            
        return generated_frames