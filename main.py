import sys
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
import data_manager
from gui_components import ChaseCreatorDialog, FixtureCreatorDialog, FXGeneratorDialog
from ui_builder import UIBuilder
from fx_utils import FXUtils

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Dati
        self.data_store = {
            "scenes": {}, "chases": {}, "cues": {}, 
            "show": [], "rem": {}, "map": {}, "groups": {},
            "fixtures": {}, 
            "globals": {"chase_speed": 127, "chase_fade": 127} 
        }
        self.selected_ch = set()
        self.current_active_group = None 

        # 2. Motori
        self.dmx = DMXController()
        self.playback = PlaybackEngine(self.dmx, self.data_store)
        self.midi = MidiManager(self.playback, self.dmx, self.data_store)
        
        # 3. Segnali
        self.midi.selected_channels = self.selected_ch
        self.playback.state_changed.connect(self._update_list_visual_selection)
        self.midi.learn_status_changed.connect(self.on_learn_status_change)
        self.midi.request_ui_refresh.connect(self.update_ui_from_engine) 
        self.midi.new_midi_message.connect(self.update_midi_label)

        # 4. Timer Show
        self.show_step_timer = QTimer()
        self.show_step_timer.setSingleShot(True)
        self.show_step_timer.timeout.connect(self.go_next_step)

        # 5. UI Builder (Delegato)
        self.ui_builder = UIBuilder()
        self.ui_builder.setup_ui(self)
        
        self.load_data()

        # 6. Loop
        self.timer_ui = QTimer(); self.timer_ui.timeout.connect(self.update_ui_frame); self.timer_ui.start(33)
        self.timer_engine = QTimer(); self.timer_engine.timeout.connect(self.playback.tick); self.timer_engine.start(40) 

    # --- CONNESSIONI ---
    def connect_serial(self):
        port = self.dmx_combo.currentText()
        if port and self.dmx.connect_serial(port):
            QMessageBox.information(self, "OK", f"Connesso USB: {port}")
            self.setWindowTitle("MIDI-DMX Pro [USB]")

    def connect_artnet(self):
        if self.dmx.connect_artnet(self.art_ip.text(), self.art_uni.text()):
            QMessageBox.information(self, "OK", "Art-Net Connected")
            self.setWindowTitle("MIDI-DMX Pro [ARTNET]")

    def connect_midi(self):
        err = self.midi.open_port(self.midi_combo.currentText())
        if not err:
            self.lbl_midi_monitor.setText("CONNECTED")
            self.lbl_midi_monitor.setStyleSheet("color: #2ecc71; border: 1px solid #2ecc71;")
        else:
            QMessageBox.critical(self, "Errore", str(err))

    # --- FX WIZARD ---
    def open_fx_wizard(self):
        selected_fixtures = [i.text() for i in self.f_list.selectedItems()]
        if not selected_fixtures:
            QMessageBox.warning(self, "Stop", "Seleziona fixtures!")
            return
        
        dlg = FXGeneratorDialog(len(selected_fixtures), self)
        if dlg.exec():
            # Parametri
            fx_type = dlg.combo_fx.currentText()
            steps = dlg.spin_steps.value()
            hold = dlg.spin_hold.value()
            spread = dlg.slider_spread.value()
            name = dlg.name_input.text()
            
            # Recupera dati fixtures
            fix_data_list = []
            for f in selected_fixtures:
                fdata = self.data_store["fixtures"].get(f)
                if isinstance(fdata, int): fdata = {"addr": fdata, "profile": ["Red", "Green", "Blue"]}
                if fdata: fix_data_list.append(fdata)
            
            # Genera step con la classe esterna
            new_steps = FXUtils.generate_steps(fix_data_list, fx_type, steps, spread)
            
            if new_steps:
                import time
                ts = int(time.time())
                step_names = []
                for i, data in enumerate(new_steps):
                    s_name = f"__fx_{name}_{ts}_{i+1}"
                    self.data_store["scenes"][s_name] = data
                    step_names.append(s_name)
                
                self.data_store["chases"][name] = {"steps": step_names, "h": hold, "f": int(hold*0.8)}
                self.ch_list.addItem(name)
                self.save_data()
                QMessageBox.information(self, "OK", "FX Creato!")

    # --- LOGICA CORE ---
    def action_blackout(self):
        self.show_step_timer.stop(); self.playback.stop_all()
        self.f_slider.setValue(0); self.f_input.setText("0"); self.f_label.setText("LIVE: 0 | 0%")
        self.show_list_widget.clearSelection()

    def update_ui_frame(self):
        mapped_ids = {ch for ids in self.data_store["map"].values() for ch in ids}
        # Colora gli item nelle liste se sono mappati MIDI (Arancione) o normali
        mapped_remotes = []
        for val in self.data_store["rem"].values():
            if isinstance(val, list):
                for v in val: 
                    if ":" in v: mapped_remotes.append(v.split(":")[1])
            elif ":" in val: mapped_remotes.append(val.split(":")[1])

        for lst in [self.s_list, self.ch_list, self.cue_list, self.g_list, self.f_list]:
            for row in range(lst.count()):
                item = lst.item(row)
                target_col = QColor("#e67e22") if item.text() in mapped_remotes else QColor("#ddd")
                if item.foreground().color() != target_col: item.setForeground(target_col)

        for i, cell in enumerate(self.cells):
            ch_num = i + 1; val = self.dmx.output_frame[ch_num]
            cell.update_view(val, ch_num in self.selected_ch, ch_num in mapped_ids)

    def fader_moved(self, val):
        self.f_label.setText(f"LIVE: {val} | {int(val/2.55)}%")
        if not self.f_input.hasFocus(): self.f_input.setText(str(val))
        for ch in self.selected_ch:
            self.dmx.live_buffer[ch] = val
            self.cells[ch-1].update_view(val, True, False, force=True)

    def manual_fader_input(self):
        try:
            val = int(self.f_input.text())
            if 0 <= val <= 255: self.f_slider.setValue(val)
        except: pass

    def toggle_cell(self, ch):
        if self.current_active_group: self.current_active_group = None; self.g_list.clearSelection()
        if self.f_list.selectedItems(): self.f_list.clearSelection(); self.btn_color_pick.setEnabled(False)
        if ch in self.selected_ch: self.selected_ch.remove(ch)
        else: self.selected_ch.add(ch)
        self.cells[ch-1].update_view(self.dmx.output_frame[ch], ch in self.selected_ch, False, force=True)

    # --- SPEED / FADE ---
    def on_speed_change(self, val):
        self.data_store["globals"]["chase_speed"] = val
        self.lbl_speed.setText(f"HOLD: {int(val/127*100)}%")
    def on_fade_change(self, val):
        self.data_store["globals"]["chase_fade"] = val
        self.lbl_fade.setText(f"FADE: {int(val/127*100)}%")
    
    def update_ui_from_engine(self):
        self.sl_speed.blockSignals(True); self.sl_speed.setValue(self.data_store["globals"]["chase_speed"]); self.on_speed_change(self.data_store["globals"]["chase_speed"]); self.sl_speed.blockSignals(False)
        self.sl_fade.blockSignals(True); self.sl_fade.setValue(self.data_store["globals"]["chase_fade"]); self.on_fade_change(self.data_store["globals"]["chase_fade"]); self.sl_fade.blockSignals(False)

    # --- FIXTURE / GRUPPI ---
    def create_fixture_action(self):
        dlg = FixtureCreatorDialog(self)
        if dlg.exec():
            name = dlg.name_input.text(); addr = dlg.addr_spin.value(); profile = dlg.get_profile()
            if name and profile:
                self.data_store["fixtures"][name] = {"addr": addr, "profile": profile}
                self.f_list.addItem(name); self.save_data()

    def on_fixture_selection_change(self):
        if self.current_active_group: self.current_active_group = None; self.g_list.clearSelection()
        self.selected_ch = set(); selected_items = self.f_list.selectedItems(); has_color = False
        for item in selected_items:
            data = self.data_store["fixtures"].get(item.text())
            if not data: continue
            if isinstance(data, int): start = data; prof = ["Red", "Green", "Blue"]
            else: start = data["addr"]; prof = data["profile"]
            for i, p in enumerate(prof):
                self.selected_ch.add(start + i)
                if p in ["Red", "Green", "Blue", "Dimmer"]: has_color = True
        self.btn_color_pick.setEnabled(has_color and len(selected_items)>0)
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
                    self.cells[start+i-1].update_view(v, True, False, force=True)

    def create_group_action(self):
        if not self.selected_ch: return
        name, ok = QInputDialog.getText(self, "Gruppo", "Nome:")
        if ok and name: self.data_store["groups"][name] = list(self.selected_ch); self.g_list.addItem(name); self.save_data()

    def select_group(self, name):
        self.f_list.clearSelection()
        
        # LOGICA TOGGLE
        if self.current_active_group == name: 
            self.selected_ch.clear(); self.current_active_group = None; self.g_list.clearSelection()
        else: 
            self.selected_ch = set(self.data_store["groups"].get(name, [])); self.current_active_group = name
        
        for cell in self.cells: cell.update_view(self.dmx.output_frame[cell.ch], cell.ch in self.selected_ch, False, force=True)

    # --- SCENE / CHASE / SHOW ---
    def save_scene_action(self):
        snap = {str(i): self.dmx.output_frame[i] for i in range(1, 513) if self.dmx.output_frame[i] > 0}
        name, ok = QInputDialog.getText(self, "Salva", "Nome Scena:")
        if ok and name: self.data_store["scenes"][name] = snap; self.s_list.addItem(name); self.save_data()

    def create_chase_action(self):
        dlg = ChaseCreatorDialog(self.data_store["scenes"], self)
        if dlg.exec():
            steps = [i.text() for i in dlg.list.selectedItems()]
            if steps:
                name, ok = QInputDialog.getText(self, "Nuovo", "Nome Chase:")
                if ok and name:
                    self.data_store["chases"][name] = {"steps": steps, "h": int(dlg.t_hold.text()), "f": int(dlg.t_fade.text())}
                    self.ch_list.addItem(name); self.save_data()

    def add_to_show(self, t, n):
        d, ok = QInputDialog.getInt(self, "Time", "Ms (0=Manual):", 0, 0, 999999)
        if ok:
            self.data_store["show"].append({"type": t, "name": n, "duration": d})
            self.refresh_show_list_widget(); self.save_data()

    def play_show_item(self, item):
        self.show_step_timer.stop()
        idx = self.show_list_widget.row(item); entry = self.data_store["show"][idx]
        if isinstance(entry, str): return
        t, n, d = entry["type"], entry["name"], entry.get("duration", 0)
        
        if t=="sc": self.playback.toggle_scene(n)
        elif t=="ch": self.playback.toggle_chase(n)
        elif t=="cue": self.playback.toggle_cue(n)
        
        self._update_list_visual_selection()
        if d > 0: self.btn_go.setText(f"AUTO ({d/1000}s)"); self.show_step_timer.start(d)
        else: self.btn_go.setText("GO / NEXT")

    def go_next_step(self):
        if not self.data_store["show"]: return
        row = (self.show_list_widget.currentRow() + 1) % len(self.data_store["show"])
        self.show_list_widget.setCurrentRow(row); self.play_show_item(self.show_list_widget.item(row))

    def refresh_show_list_widget(self):
        self.show_list_widget.clear()
        for i, e in enumerate(self.data_store["show"]):
            if isinstance(e, dict): self.show_list_widget.addItem(f"{i+1}. [{e['type'].upper()}] {e['name']} ({e.get('duration',0)}ms)")

    def toggle_rec(self):
        if self.playback.is_recording_cue:
            self.playback.is_recording_cue = False; self.btn_rec.setText("● REC")
            n, ok = QInputDialog.getText(self, "Salva", "Nome Cue:")
            if ok and n: self.data_store["cues"][n] = {"data": self.playback.recorded_stream}; self.cue_list.addItem(n); self.save_data()
        else: self.playback.recorded_stream = []; self.playback.is_recording_cue = True; self.btn_rec.setText("STOP")

    # --- MIDI & CONTEXT ---
    def reset_all_midi_channels(self):
        if QMessageBox.question(self, "Reset", "Reset MIDI Map?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.data_store["map"].clear(); self.save_data()

    def show_slider_context(self, pos, key):
        m = QMenu(); act = m.addAction("Mappa MIDI")
        target_str = f"global:{key}"; mapped_key = None
        for k, v in self.data_store["rem"].items():
            if isinstance(v, list):
                if target_str in v: mapped_key = k; break
            elif v == target_str: mapped_key = k; break
        
        if mapped_key: act_unmap = m.addAction(f"Rimuovi ({mapped_key})")
        res = m.exec(self.sender().mapToGlobal(pos))
        if res == act: self.midi.toggle_learn(target_str)
        elif mapped_key and res == act_unmap:
            val = self.data_store["rem"][mapped_key]
            if isinstance(val, list):
                if target_str in val: val.remove(target_str)
                if not val: del self.data_store["rem"][mapped_key]
            else: del self.data_store["rem"][mapped_key]
            self.save_data(); QMessageBox.information(self, "Info", "Rimosso")

    def show_context_menu(self, w, p, t):
        i = w.itemAt(p); 
        if not i: return
        m = QMenu(); m.addAction("Mappa MIDI").triggered.connect(lambda: self.midi.toggle_learn(f"{t}:{i.text()}"))
        if t not in ["grp", "fix"]: m.addAction("Add to Show").triggered.connect(lambda: self.add_to_show(t, i.text()))
        m.addAction("Delete").triggered.connect(lambda: [w.takeItem(w.row(i)), self.data_store[{"sc":"scenes","ch":"chases","cue":"cues","grp":"groups","fix":"fixtures"}[t]].pop(i.text(),None), self.save_data()])
        m.exec(w.mapToGlobal(p))

    def show_manager_context_menu(self, p):
        i = self.show_list_widget.itemAt(p)
        if i: QMenu().addAction("Remove").triggered.connect(lambda: [self.data_store["show"].pop(self.show_list_widget.row(i)), self.refresh_show_list_widget(), self.save_data()]); QMenu().exec(self.show_list_widget.mapToGlobal(p))

    def cell_context_menu(self, ch):
        m = QMenu(); m.addAction(f"CH {ch}").setEnabled(False)
        if len(self.selected_ch) > 1: m.addAction("Crea Gruppo").triggered.connect(self.create_group_action)
        # Rimozione mappatura MIDI della cella
        mapped_keys = []
        for key, channels in self.data_store["map"].items():
            if ch in channels: mapped_keys.append(key)
        if mapped_keys:
            for k in mapped_keys: m.addAction(f"Rimuovi MIDI {k}").triggered.connect(lambda _, k=k: self._remove_midi_mapping(k, ch))
        
        m.exec(self.cells[ch-1].mapToGlobal(self.cells[ch-1].rect().center()))

    def _remove_midi_mapping(self, midi_key, ch_to_remove):
        if midi_key in self.data_store["map"]:
            if ch_to_remove in self.data_store["map"][midi_key]:
                self.data_store["map"][midi_key].remove(ch_to_remove)
                if not self.data_store["map"][midi_key]: del self.data_store["map"][midi_key]
                self.save_data(); QMessageBox.information(self, "Info", "Rimosso")

    def update_midi_label(self, t): self.lbl_midi_monitor.setText(t); self.lbl_midi_monitor.setStyleSheet("color:#2ecc71; border:1px solid #2ecc71;")
    def on_learn_status_change(self, l, t): self.btn_learn.setText("WAIT..." if l else "LEARN"); self.btn_learn.setStyleSheet(f"background: {'#c0392b' if l else '#2c3e50'}; color: white;")
    
    # --- RESTORED VISUAL SELECTION FOR TOGGLE LOGIC ---
    def _update_list_visual_selection(self):
        # Scenes
        for i in range(self.s_list.count()):
            item = self.s_list.item(i)
            is_active = (item.text() == self.playback.active_sc)
            item.setSelected(is_active)
            if not is_active: item.setSelected(False) # Force deselect if not active

        # Chases
        for i in range(self.ch_list.count()):
            item = self.ch_list.item(i)
            is_active = (item.text() == self.playback.active_ch)
            item.setSelected(is_active)
            if not is_active: item.setSelected(False)

        # Cues
        for i in range(self.cue_list.count()):
            item = self.cue_list.item(i)
            is_active = (item.text() == self.playback.active_cue)
            item.setSelected(is_active)
            if not is_active: item.setSelected(False)

    def save_data(self): data_manager.save_studio_data(self.data_store)
    def load_data(self):
        d = data_manager.load_studio_data()
        if d: self.data_store.update(d); self.refresh_show_list_widget()
        self.s_list.addItems(self.data_store["scenes"].keys())
        self.ch_list.addItems(self.data_store["chases"].keys())
        self.cue_list.addItems(self.data_store["cues"].keys())
        self.g_list.addItems(self.data_store["groups"].keys())
        self.f_list.addItems(self.data_store["fixtures"].keys())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())