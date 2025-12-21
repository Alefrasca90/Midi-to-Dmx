import sys
import time # Importante per il limitatore
import serial.tools.list_ports
import mido
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QInputDialog, QMessageBox, QColorDialog
)
from PyQt6.QtGui import QColor, QAction, QFont 
from PyQt6.QtCore import QTimer, Qt

# MODULI INTERNI
from dmx_engine import DMXController
from playback_engine import PlaybackEngine
from midi_manager import MidiManager
from audio_engine import AudioReactor
from procedural_engine import ProceduralEngine 
import data_manager
from gui_components import ChaseCreatorDialog, FixtureCreatorDialog, FXGeneratorDialog
from ui_builder import UIBuilder
from fx_utils import FXUtils

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Inizializzazione Dati
        self.data_store = {
            "scenes": {}, "chases": {}, "cues": {}, 
            "show": [], "rem": {}, "map": {}, "groups": {},
            "fixtures": {}, 
            "globals": {"chase_speed": 127, "chase_fade": 127} 
        }
        self.selected_ch = set()
        self.current_active_group = None 
        
        # Variabile per limitare gli aggiornamenti della grafica (Anti-Freeze)
        self.last_ui_update_time = 0

        # 2. Motori
        self.dmx = DMXController()
        self.playback = PlaybackEngine(self.dmx, self.data_store)
        self.midi = MidiManager(self.playback, self.dmx, self.data_store)
        self.audio = AudioReactor()
        self.procedural = ProceduralEngine(self.data_store)
        
        # 3. Segnali
        self.midi.selected_channels = self.selected_ch
        self.playback.state_changed.connect(self._update_list_visual_selection)
        self.midi.learn_status_changed.connect(self.on_learn_status_change)
        self.midi.request_ui_refresh.connect(self.update_ui_from_engine) 
        self.midi.new_midi_message.connect(self.update_midi_label)
        
        # Collegamento Audio
        self.audio.data_processed.connect(self.on_audio_data)

        # 4. Timer Show
        self.show_step_timer = QTimer()
        self.show_step_timer.setSingleShot(True)
        self.show_step_timer.timeout.connect(self.go_next_step)

        # 5. COSTRUZIONE INTERFACCIA
        self.ui_builder = UIBuilder()
        self.ui_builder.setup_ui(self)
        
        # Connessioni UI extra (Inspector)
        if hasattr(self, 'sl_fx_threshold'):
            self.sl_fx_threshold.valueChanged.connect(self.on_fx_threshold_change)
        if hasattr(self, 'list_active_fx'):
            self.list_active_fx.itemClicked.connect(self.on_fx_list_click)

        # 6. Avvio
        self.refresh_audio_devices()
        self.load_data()

        # 7. Loop UI (30fps) e Engine (DMX)
        self.timer_ui = QTimer(); self.timer_ui.timeout.connect(self.update_ui_frame); self.timer_ui.start(33)
        self.timer_engine = QTimer(); self.timer_engine.timeout.connect(self.engine_tick); self.timer_engine.start(25) 

    # --- ENGINE TICK ---
    def engine_tick(self):
        # Playback classico (Scene/Chase)
        self.playback.tick()

    # --- PROCEDURAL FX LOGIC ---
    def add_gen_effect(self):
        if not hasattr(self, 'combo_fx_type'): return
        fx_type = self.combo_fx_type.currentText()
        
        # Prendi fixtures dalla lista nel tab Audio
        selected_items = self.list_fx_fixtures.selectedItems()
        target_list = [i.text() for i in selected_items]
        
        if not target_list:
            QMessageBox.warning(self, "Attenzione", "Seleziona almeno una Fixture dalla lista nel tab Audio!")
            return
            
        self.procedural.add_effect(fx_type, target_list)
        count = len(target_list)
        if hasattr(self, 'list_active_fx'):
            self.list_active_fx.addItem(f"{fx_type} -> [{count} fixtures]")

    def remove_gen_effect(self):
        if not hasattr(self, 'list_active_fx'): return
        row = self.list_active_fx.currentRow()
        if row >= 0:
            self.procedural.remove_effect(row)
            self.list_active_fx.takeItem(row)

    def on_fx_list_click(self, item):
        # Carica i dati nell'inspector quando clicchi un effetto
        row = self.list_active_fx.row(item)
        fx = self.procedural.get_active_effect(row)
        if fx and hasattr(self, 'sl_fx_threshold'):
            val = int(fx.threshold * 255)
            self.sl_fx_threshold.blockSignals(True)
            self.sl_fx_threshold.setValue(val)
            self.sl_fx_threshold.blockSignals(False)

    def on_fx_threshold_change(self, val):
        # Aggiorna la soglia in tempo reale
        row = self.list_active_fx.currentRow()
        fx = self.procedural.get_active_effect(row)
        if fx:
            fx.threshold = val / 255.0

    # --- AUDIO LOGIC (OTTIMIZZATA) ---
    def refresh_audio_devices(self):
        if not hasattr(self, 'audio_combo'): return
        try:
            self.audio_combo.clear()
            devs = self.audio.get_devices()
            for idx, name in devs:
                self.audio_combo.addItem(f"{idx}: {name}", idx)
            if self.audio_combo.count() == 0:
                self.audio_combo.addItem("Nessun Input Trovato", -1)
        except: pass

    def toggle_audio_engine(self):
        if not hasattr(self, 'btn_audio_start'): return
        if self.btn_audio_start.isChecked():
            idx = self.audio_combo.currentData()
            if idx is not None and idx != -1:
                self.audio.set_device(idx)
                self.audio.start()
                self.btn_audio_start.setText("STOP")
                self.btn_audio_start.setStyleSheet("background-color: #e74c3c; color: white;")
        else:
            self.audio.stop()
            self.btn_audio_start.setText("ATTIVA")
            self.btn_audio_start.setStyleSheet("background-color: #2c3e50; color: #ccc;")

    def on_gain_change(self, val):
        self.audio.gain = val / 5.0 

    def on_audio_data(self, is_kick, is_snare, vol, spectrum):
        # 1. CALCOLO LUCI (Sempre alla massima velocità)
        audio_snapshot = {
            'Bass': spectrum[0], 'Mid': spectrum[1], 'High': spectrum[2],
            'Volume': vol, 'KickTrig': is_kick, 'SnareTrig': is_snare
        }
        
        # Calcola gli effetti procedurali e scrivi sul DMX
        try:
            self.procedural.tick(audio_snapshot, self.dmx)
        except Exception as e:
            print(f"Errore Procedural: {e}")

        # 2. AGGIORNAMENTO GRAFICA (Limitato a ~30 FPS per non bloccare PC)
        current_time = time.time()
        if current_time - self.last_ui_update_time > 0.033: # 33ms = ~30fps
            self.last_ui_update_time = current_time
            
            if hasattr(self, 'prog_vol'): self.prog_vol.setValue(vol)
            if hasattr(self, 'pb_bass'): self.pb_bass.setValue(spectrum[0])
            if hasattr(self, 'pb_mid'): self.pb_mid.setValue(spectrum[1])
            if hasattr(self, 'pb_high'): self.pb_high.setValue(spectrum[2])
            
            # Update Inspector Bar (se selezionato)
            if hasattr(self, 'list_active_fx') and hasattr(self, 'pb_fx_signal'):
                row = self.list_active_fx.currentRow()
                fx = self.procedural.get_active_effect(row)
                if fx: self.pb_fx_signal.setValue(int(fx.current_signal))
                else: self.pb_fx_signal.setValue(0)

    # --- CONNESSIONI ---
    def connect_serial(self):
        if not hasattr(self, 'dmx_combo'): return
        port = self.dmx_combo.currentText()
        if port and self.dmx.connect_serial(port): QMessageBox.information(self, "OK", f"Connesso USB: {port}")
    
    def connect_artnet(self):
        if not hasattr(self, 'art_ip'): return
        if self.dmx.connect_artnet(self.art_ip.text(), self.art_uni.text()): QMessageBox.information(self, "OK", "Art-Net OK")
    
    def connect_midi(self):
        if not hasattr(self, 'midi_combo'): return
        if not self.midi.open_port(self.midi_combo.currentText()): 
            if hasattr(self, 'lbl_midi_monitor'): self.lbl_midi_monitor.setText("CONNECTED")
        else: QMessageBox.critical(self, "Errore", "Errore MIDI")

    # --- CORE UI LOGIC ---
    def action_blackout(self):
        self.show_step_timer.stop()
        self.playback.stop_all()
        # Spegni anche gli effetti procedurali
        for fx in self.procedural.active_effects: fx.active = False
        
        if hasattr(self, 'f_slider'): self.f_slider.setValue(0)
        if hasattr(self, 'f_input'): self.f_input.setText("0")
        if hasattr(self, 'f_label'): self.f_label.setText("LIVE: 0 | 0%")
        if hasattr(self, 'show_list_widget'): self.show_list_widget.clearSelection()

    def update_ui_frame(self):
        # Aggiorna la griglia DMX
        mapped_ids = {ch for ids in self.data_store["map"].values() for ch in ids}
        if hasattr(self, 'cells'):
            for i, cell in enumerate(self.cells):
                ch_num = i + 1; val = self.dmx.output_frame[ch_num]
                cell.update_view(val, ch_num in self.selected_ch, ch_num in mapped_ids)

    def fader_moved(self, val):
        if hasattr(self, 'f_label'): self.f_label.setText(f"LIVE: {val} | {int(val/2.55)}%")
        if hasattr(self, 'f_input') and not self.f_input.hasFocus(): self.f_input.setText(str(val))
        for ch in self.selected_ch: 
            self.dmx.live_buffer[ch] = val
            if hasattr(self, 'cells'): self.cells[ch-1].update_view(val, True, False, force=True)

    def manual_fader_input(self):
        try:
            val = int(self.f_input.text())
            if 0 <= val <= 255: self.f_slider.setValue(val)
        except: pass

    def toggle_cell(self, ch):
        if self.current_active_group: 
            self.current_active_group = None
            if hasattr(self, 'g_list'): self.g_list.clearSelection()
        
        if hasattr(self, 'f_list') and self.f_list.selectedItems(): 
            self.f_list.clearSelection()
            if hasattr(self, 'btn_color_pick'): self.btn_color_pick.setEnabled(False)
            
        if ch in self.selected_ch: self.selected_ch.remove(ch)
        else: self.selected_ch.add(ch)
        
        if hasattr(self, 'cells'):
            self.cells[ch-1].update_view(self.dmx.output_frame[ch], ch in self.selected_ch, False, force=True)

    def on_speed_change(self, val): 
        self.data_store["globals"]["chase_speed"] = val
        if hasattr(self, 'lbl_speed'): self.lbl_speed.setText(f"SPEED: {int(val/127*100)}%")
        
    def on_fade_change(self, val): self.data_store["globals"]["chase_fade"] = val
    def update_ui_from_engine(self): pass

    # --- FIXTURE / GRUPPI / SCENE ---
    def create_fixture_action(self):
        dlg = FixtureCreatorDialog(self)
        if dlg.exec():
            name = dlg.name_input.text(); addr = dlg.addr_spin.value(); profile = dlg.get_profile()
            if name and profile: 
                self.data_store["fixtures"][name] = {"addr": addr, "profile": profile}
                if hasattr(self, 'f_list'): self.f_list.addItem(name)
                if hasattr(self, 'list_fx_fixtures'): self.list_fx_fixtures.addItem(name)
                self.save_data()

    def on_fixture_selection_change(self):
        if self.current_active_group: 
            self.current_active_group = None
            if hasattr(self, 'g_list'): self.g_list.clearSelection()
        self.selected_ch = set(); selected_items = self.f_list.selectedItems(); has_color = False
        for item in selected_items:
            data = self.data_store["fixtures"].get(item.text())
            if not data: continue
            if isinstance(data, int): start = data; prof = ["Red", "Green", "Blue"]
            else: start = data["addr"]; prof = data["profile"]
            for i, p in enumerate(prof):
                self.selected_ch.add(start + i)
                if p in ["Red", "Green", "Blue", "Dimmer"]: has_color = True
        if hasattr(self, 'btn_color_pick'): self.btn_color_pick.setEnabled(has_color and len(selected_items)>0)
        if hasattr(self, 'cells'):
            for cell in self.cells: cell.update_view(self.dmx.output_frame[cell.ch], cell.ch in self.selected_ch, False, force=True)

    def open_live_color_picker(self):
        if not self.f_list.selectedItems(): return
        cd = QColorDialog(self); cd.setOption(QColorDialog.ColorDialogOption.NoButtons)
        cd.currentColorChanged.connect(self.apply_live_color); cd.exec()

    def apply_live_color(self, c):
        items = self.f_list.selectedItems()
        if not items: return
        r, g, b = c.red(), c.green(), c.blue()
        for item in items:
            data = self.data_store["fixtures"].get(item.text())
            if not data: continue
            if isinstance(data, int): start=data; prof=["Red","Green","Blue"]
            else: start=data["addr"]; prof=data["profile"]
            for i, p in enumerate(prof):
                v = -1
                if p=="Red": v=r
                elif p=="Green": v=g
                elif p=="Blue": v=b
                elif p=="Dimmer": v=255
                elif p=="White": v=0
                if v>=0 and start+i<=512: 
                    self.dmx.live_buffer[start+i] = v
                    if hasattr(self, 'cells'): self.cells[start+i-1].update_view(v, True, False, force=True)

    def create_group_action(self):
        if not self.selected_ch: return
        name, ok = QInputDialog.getText(self, "Gruppo", "Nome:")
        if ok and name: 
            self.data_store["groups"][name] = list(self.selected_ch)
            if hasattr(self, 'g_list'): self.g_list.addItem(name)
            self.save_data()

    def select_group(self, name):
        if hasattr(self, 'f_list'): self.f_list.clearSelection()
        if self.current_active_group == name: 
            self.selected_ch.clear(); self.current_active_group = None
            if hasattr(self, 'g_list'): self.g_list.clearSelection()
        else: 
            self.selected_ch = set(self.data_store["groups"].get(name, [])); self.current_active_group = name
        if hasattr(self, 'cells'):
            for cell in self.cells: cell.update_view(self.dmx.output_frame[cell.ch], cell.ch in self.selected_ch, False, force=True)

    def save_scene_action(self):
        snap = {str(i): self.dmx.output_frame[i] for i in range(1, 513) if self.dmx.output_frame[i] > 0}
        name, ok = QInputDialog.getText(self, "Salva", "Nome Scena:")
        if ok and name: 
            self.data_store["scenes"][name] = snap
            if hasattr(self, 's_list'): self.s_list.addItem(name)
            self.save_data()

    def create_chase_action(self):
        dlg = ChaseCreatorDialog(self.data_store["scenes"], self)
        if dlg.exec():
            steps = [i.text() for i in dlg.list.selectedItems()]
            if steps:
                name, ok = QInputDialog.getText(self, "Nuovo", "Nome Chase:")
                if ok and name: 
                    self.data_store["chases"][name] = {"steps": steps, "h": int(dlg.t_hold.text()), "f": int(dlg.t_fade.text())}
                    if hasattr(self, 'ch_list'): self.ch_list.addItem(name)
                    self.save_data()

    def add_to_show(self, t, n): pass 
    def play_show_item(self, item): 
        # (Logica base show)
        pass 
    def go_next_step(self): pass 
    def refresh_show_list_widget(self): pass 

    def toggle_rec(self):
        if self.playback.is_recording_cue:
            self.playback.is_recording_cue = False
            if hasattr(self, 'btn_rec'): self.btn_rec.setText("● REC")
            n, ok = QInputDialog.getText(self, "Salva", "Nome Cue:")
            if ok and n: 
                self.data_store["cues"][n] = {"data": self.playback.recorded_stream}
                if hasattr(self, 'cue_list'): self.cue_list.addItem(n)
                self.save_data()
        else: 
            self.playback.recorded_stream = []
            self.playback.is_recording_cue = True
            if hasattr(self, 'btn_rec'): self.btn_rec.setText("STOP")

    def reset_all_midi_channels(self):
        if QMessageBox.question(self, "Reset", "Reset MIDI Map?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: self.data_store["map"].clear(); self.save_data()

    def show_slider_context(self, pos, key):
        # (Gestione menu contestuale per MIDI mapping su slider)
        pass

    def show_context_menu(self, w, p, t):
        i = w.itemAt(p); 
        if not i: return
        m = QMenu(); m.addAction("Mappa MIDI").triggered.connect(lambda: self.midi.toggle_learn(f"{t}:{i.text()}"))
        m.addAction("Delete").triggered.connect(lambda: [w.takeItem(w.row(i)), self.data_store[{"sc":"scenes","ch":"chases","cue":"cues","grp":"groups","fix":"fixtures"}[t]].pop(i.text(),None), self.save_data()])
        m.exec(w.mapToGlobal(p))

    def show_manager_context_menu(self, p): pass

    def cell_context_menu(self, ch):
        # Menu tasto destro sulle celle
        pass

    def _remove_midi_mapping(self, midi_key, ch_to_remove): pass

    def update_midi_label(self, t): 
        if hasattr(self, 'lbl_midi_monitor'): 
            self.lbl_midi_monitor.setText(t)
            self.lbl_midi_monitor.setStyleSheet("color:#2ecc71; border:1px solid #2ecc71;")
    
    def on_learn_status_change(self, l, t): 
        if hasattr(self, 'btn_learn'): 
            self.btn_learn.setText("WAIT..." if l else "LEARN")
            self.btn_learn.setStyleSheet(f"background: {'#c0392b' if l else '#2c3e50'}; color: white;")
    
    def _update_list_visual_selection(self):
        if hasattr(self, 's_list'):
            for i in range(self.s_list.count()): item = self.s_list.item(i); item.setSelected(item.text() == self.playback.active_sc)
    
    def save_data(self): data_manager.save_studio_data(self.data_store)
    
    def load_data(self):
        try:
            d = data_manager.load_studio_data()
            if d: self.data_store.update(d)
            
            # Safe population
            if hasattr(self, 's_list'): self.s_list.addItems(self.data_store.get("scenes", {}).keys())
            if hasattr(self, 'ch_list'): self.ch_list.addItems(self.data_store.get("chases", {}).keys())
            if hasattr(self, 'cue_list'): self.cue_list.addItems(self.data_store.get("cues", {}).keys())
            if hasattr(self, 'g_list'): self.g_list.addItems(self.data_store.get("groups", {}).keys())
            if hasattr(self, 'f_list'): self.f_list.addItems(self.data_store.get("fixtures", {}).keys())
            
            if hasattr(self, 'list_fx_fixtures'):
                self.list_fx_fixtures.clear()
                self.list_fx_fixtures.addItems(self.data_store.get("fixtures", {}).keys())
        except Exception as e:
            print(f"Error loading data: {e}")

    # --- FIX WIZARD ALIAS ---
    def open_fx_wizard(self): 
        # Riapre il vecchio wizard se necessario, altrimenti lo ignora
        if not hasattr(self, 'f_list'): return
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())