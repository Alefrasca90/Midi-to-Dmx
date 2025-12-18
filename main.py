import sys
import time
import json
import threading
import os
import mido
import serial
import serial.tools.list_ports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QComboBox, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel, QScrollArea, 
                             QGridLayout, QMessageBox, QMenu, QSlider, QListWidget, 
                             QInputDialog, QLineEdit, QDialog)
from PyQt6.QtGui import QIntValidator, QColor
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

# --- COMPONENTE CELLA DMX ---
class DMXCell(QLabel):
    clicked = pyqtSignal(int)
    rightClicked = pyqtSignal(int)
    
    def __init__(self, ch, parent=None):
        super().__init__(parent)
        self.ch = ch
        self.setFixedSize(95, 35)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ch)
        elif e.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit(self.ch)

# --- MOTORE DMX ---
class DMXController:
    def __init__(self):
        self.serial_port = None
        self.output_frame = bytearray([0] * 513)
        self.live_buffer = bytearray([0] * 513)
        self.scene_buffer = bytearray([0] * 513)
        self.chase_buffer = bytearray([0] * 513)
        self.running = False

    def connect(self, port):
        try:
            self.serial_port = serial.Serial(port, baudrate=250000, stopbits=2)
            self.running = True
            threading.Thread(target=self._send_loop, daemon=True).start()
            return True
        except Exception:
            return False

    def _send_loop(self):
        while self.running:
            if self.serial_port:
                try:
                    for i in range(1, 513):
                        self.output_frame[i] = max(self.live_buffer[i], 
                                                  self.scene_buffer[i], 
                                                  self.chase_buffer[i])
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                    time.sleep(0.025)
                except Exception:
                    self.running = False

# --- DIALOG CREAZIONE CHASE ---
class ChaseCreatorDialog(QDialog):
    def __init__(self, scenes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuovo Chase")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Seleziona Scene (CTRL+Click):"))
        self.list = QListWidget()
        self.list.addItems(scenes.keys())
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list)
        layout.addWidget(QLabel("Hold (ms):"))
        self.t_hold = QLineEdit("1000")
        layout.addWidget(self.t_hold)
        layout.addWidget(QLabel("Fade (ms):"))
        self.t_fade = QLineEdit("500")
        layout.addWidget(self.t_fade)
        btn = QPushButton("Conferma")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

# --- APPLICAZIONE PRINCIPALE ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dmx = DMXController()
        self.selected_ch = set()
        self.mappings = {}
        self.remote_mappings = {}
        self.scenes = {}
        self.chases = {}
        self.active_scene = None
        self.active_chase = None
        self.is_learning = False
        self.learn_target = None 

        self.setWindowTitle("MIDI-DMX Studio - Advanced Toggle")
        self.resize(1300, 850)
        self.setStyleSheet("background-color: #0a0a0a; color: #DDD;")

        main_layout = QHBoxLayout()
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        side_layout = QVBoxLayout(sidebar)
        
        # 1. Hardware
        side_layout.addWidget(QLabel("<b>1. HARDWARE</b>"))
        self.midi_combo = QComboBox()
        self.midi_combo.addItems(mido.get_input_names())
        side_layout.addWidget(self.midi_combo)
        self.dmx_combo = QComboBox()
        self.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        side_layout.addWidget(self.dmx_combo)
        self.btn_conn = QPushButton("CONNETTI")
        self.btn_conn.clicked.connect(self.connect_hw)
        side_layout.addWidget(self.btn_conn)

        # MIDI Mapping Toggle Button
        side_layout.addSpacing(15)
        side_layout.addWidget(QLabel("<b>2. MIDI MAPPING</b>"))
        self.btn_learn = QPushButton("LEARN CHANNELS")
        self.btn_learn.clicked.connect(self.toggle_learn_mode)
        self.btn_learn.setStyleSheet("background-color: #444;")
        side_layout.addWidget(self.btn_learn)
        
        # 3. Scene
        side_layout.addSpacing(15)
        side_layout.addWidget(QLabel("<b>3. SCENE</b>"))
        btn_save_sc = QPushButton("SALVA SCENA")
        btn_save_sc.clicked.connect(self.save_scene)
        btn_save_sc.setStyleSheet("background-color: #27ae60;")
        side_layout.addWidget(btn_save_sc)
        self.s_list = QListWidget()
        self.s_list.itemClicked.connect(self.handle_scene_click)
        self.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.s_list.customContextMenuRequested.connect(self.scene_menu)
        side_layout.addWidget(self.s_list)

        # 4. Chase
        side_layout.addSpacing(15)
        side_layout.addWidget(QLabel("<b>4. CHASES</b>"))
        btn_new_ch = QPushButton("NUOVO CHASE")
        btn_new_ch.clicked.connect(self.create_chase)
        btn_new_ch.setStyleSheet("background-color: #2980b9;")
        side_layout.addWidget(btn_new_ch)
        self.c_list = QListWidget()
        self.c_list.itemClicked.connect(self.handle_chase_click)
        self.c_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.c_list.customContextMenuRequested.connect(self.chase_menu)
        side_layout.addWidget(self.c_list)

        side_layout.addSpacing(20)
        btn_bl = QPushButton("BLACKOUT")
        btn_bl.clicked.connect(self.blackout)
        btn_bl.setStyleSheet("background-color: #c0392b; font-weight: bold;")
        side_layout.addWidget(btn_bl)
        side_layout.addStretch()

        # Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        self.grid = QGridLayout(grid_widget)
        self.cells = []
        for i in range(512):
            c = DMXCell(i+1)
            c.clicked.connect(self.toggle_selection)
            self.grid.addWidget(c, i//9, i%9)
            self.cells.append(c)
        scroll.setWidget(grid_widget)
        main_layout.addWidget(sidebar)
        main_layout.addWidget(scroll)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.load_data()
        self.timer_ui = QTimer()
        self.timer_ui.timeout.connect(self.update_ui)
        self.timer_ui.start(50)
        self.timer_chase = QTimer()
        self.timer_chase.timeout.connect(self.process_fade)
        self.fade_start_time = 0

    # --- LOGICA TOGGLE LEARN ---
    def toggle_learn_mode(self):
        if not self.is_learning:
            self.is_learning = True
            if self.learn_target is None: self.learn_target = "channels"
            self.btn_learn.setText("ANNULLA LEARN")
            self.btn_learn.setStyleSheet("background-color: #c0392b; color: white;")
        else:
            self.is_learning = False
            self.learn_target = None
            self.btn_learn.setText("LEARN CHANNELS")
            self.btn_learn.setStyleSheet("background-color: #444; color: #DDD;")

    def midi_callback(self, msg):
        sig = None
        if msg.type == 'control_change': sig = f"cc_{msg.control}"
        elif msg.type in ['note_on', 'note_off']: sig = f"note_{msg.note}"
        if not sig: return

        if self.is_learning:
            if self.learn_target == "channels": self.mappings[sig] = list(self.selected_ch)
            else: self.remote_mappings[sig] = self.learn_target
            self.save_data()
            QTimer.singleShot(0, self.toggle_learn_mode)
            return

        if sig in self.mappings:
            val = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.type == 'note_on' and msg.velocity > 0 else 0)
            for c in self.mappings[sig]: self.dmx.live_buffer[c] = val
        elif sig in self.remote_mappings:
            t = self.remote_mappings[sig]
            if msg.type in ['note_on', 'control_change'] and (getattr(msg, 'velocity', 127) > 0 or getattr(msg, 'value', 0) > 0):
                if t.startswith("sc:"): self.activate_scene(t[3:])
                elif t.startswith("ch:"): self.activate_chase_name(t[3:])

    # --- LOGICA TOGGLE LISTE ---
    def handle_scene_click(self, item):
        self.activate_scene(item.text())

    def handle_chase_click(self, item):
        self.activate_chase_name(item.text())

    def activate_scene(self, name):
        if self.active_scene == name:
            self.active_scene = None
            self.dmx.scene_buffer = bytearray([0]*513)
        else:
            self.active_scene = name
            buf = bytearray([0]*513)
            for c, v in self.scenes[name].items(): buf[int(c)] = v
            self.dmx.scene_buffer = buf
            self.dmx.live_buffer = bytearray([0]*513)
        self.refresh_list_highlights()

    def activate_chase_name(self, name):
        if self.active_chase == name:
            self.active_chase = None
            self.timer_chase.stop()
            self.dmx.chase_buffer = bytearray([0]*513)
        else:
            self.active_chase = name
            self.fade_start_time = int(time.time() * 1000)
            self.timer_chase.start(40)
        self.refresh_list_highlights()

    def refresh_list_highlights(self):
        # Evidenzia l'elemento attivo nella UI
        for i in range(self.s_list.count()):
            it = self.s_list.item(i)
            it.setSelected(it.text() == self.active_scene)
        for i in range(self.c_list.count()):
            it = self.c_list.item(i)
            it.setSelected(it.text() == self.active_chase)

    # --- MENU E CORE ---
    def scene_menu(self, pos):
        item = self.s_list.itemAt(pos)
        if not item: return
        menu = QMenu(); m1 = menu.addAction("Assegna MIDI (Learn)"); m2 = menu.addAction("Rimuovi MIDI"); m3 = menu.addAction("Elimina Scena")
        res = menu.exec(self.s_list.mapToGlobal(pos))
        if res == m1: self.learn_target = f"sc:{item.text()}"; self.toggle_learn_mode()
        elif res == m2: self.remove_remote_map(f"sc:{item.text()}")
        elif res == m3:
            if self.active_scene == item.text(): self.active_scene = None; self.dmx.scene_buffer = bytearray([0]*513)
            del self.scenes[item.text()]; self.s_list.takeItem(self.s_list.row(item)); self.save_data()

    def chase_menu(self, pos):
        item = self.c_list.itemAt(pos)
        if not item: return
        menu = QMenu(); m1 = menu.addAction("Assegna MIDI (Learn)"); m2 = menu.addAction("Rimuovi MIDI"); m3 = menu.addAction("Elimina Chase")
        res = menu.exec(self.c_list.mapToGlobal(pos))
        if res == m1: self.learn_target = f"ch:{item.text()}"; self.toggle_learn_mode()
        elif res == m2: self.remove_remote_map(f"ch:{item.text()}")
        elif res == m3:
            if self.active_chase == item.text(): self.active_chase = None; self.timer_chase.stop()
            del self.chases[item.text()]; self.c_list.takeItem(self.c_list.row(item)); self.save_data()

    def remove_remote_map(self, target_str):
        for k in list(self.remote_mappings.keys()):
            if self.remote_mappings[k] == target_str: del self.remote_mappings[k]
        self.save_data()

    def process_fade(self):
        if not self.active_chase: return
        c = self.chases[self.active_chase]
        steps, hold, fade = c["steps"], c["hold"], c["fade"]
        cycle = hold + fade; elapsed = (int(time.time() * 1000) - self.fade_start_time) % (cycle * len(steps))
        idx = elapsed // cycle; sub = elapsed % cycle
        s1 = self.scenes[steps[idx]]; s2 = self.scenes[steps[(idx + 1) % len(steps)]]
        nb = bytearray([0]*513)
        for i in range(1, 513):
            v1, v2 = s1.get(str(i), 0), s2.get(str(i), 0)
            nb[i] = v1 if sub < hold else int(v1 + (v2 - v1) * ((sub - hold) / fade))
        self.dmx.chase_buffer = nb

    def update_ui(self):
        map_ch = set()
        for t in self.mappings.values(): map_ch.update(t)
        rem_map_sc = {v[3:] for v in self.remote_mappings.values() if v.startswith("sc:")}
        rem_map_ch = {v[3:] for v in self.remote_mappings.values() if v.startswith("ch:")}

        for i in range(512):
            ch = i + 1; val = max(self.dmx.live_buffer[ch], self.dmx.scene_buffer[ch], self.dmx.chase_buffer[ch])
            sel = "2px solid #f1c40f" if ch in self.selected_ch else "1px solid #1a1a1a"
            col = "#2ecc71" if ch in map_ch else "#444"
            self.cells[i].setText(f"<b><font color='{col}'>CH {ch}:</font></b><br>{val}")
            self.cells[i].setStyleSheet(f"background-color: #0a0a0a; border: {sel}; font-size: 9px; border-radius: 2px;")
        
        # Aggiorna colori liste per Mapping MIDI
        for i in range(self.s_list.count()):
            it = self.s_list.item(i)
            it.setForeground(QColor("#e67e22") if it.text() in rem_map_sc else QColor("#DDD"))
        for i in range(self.c_list.count()):
            it = self.c_list.item(i)
            it.setForeground(QColor("#e67e22") if it.text() in rem_map_ch else QColor("#DDD"))

    def toggle_selection(self, ch):
        if ch in self.selected_ch: self.selected_ch.remove(ch)
        else: self.selected_ch.add(ch)

    def save_scene(self):
        frame = {str(i): max(self.dmx.live_buffer[i], self.dmx.scene_buffer[i], self.dmx.chase_buffer[i]) for i in range(1, 513)}
        name, ok = QInputDialog.getText(self, 'Salva', 'Nome Scena:')
        if ok and name:
            self.scenes[name] = frame
            if not self.s_list.findItems(name, Qt.MatchFlag.MatchExactly): self.s_list.addItem(name)
            self.save_data()

    def create_chase(self):
        d = ChaseCreatorDialog(self.scenes, self)
        if d.exec():
            steps = [i.text() for i in d.list.selectedItems()]
            if steps:
                name, ok = QInputDialog.getText(self, 'Salva', 'Nome Chase:')
                if ok and name:
                    self.chases[name] = {"steps": steps, "hold": int(d.t_hold.text()), "fade": int(d.t_fade.text())}
                    self.c_list.addItem(name); self.save_data()

    def blackout(self):
        self.dmx.live_buffer = bytearray([0]*513); self.dmx.scene_buffer = bytearray([0]*513); self.dmx.chase_buffer = bytearray([0]*513)
        self.active_scene = self.active_chase = None; self.timer_chase.stop(); self.refresh_list_highlights()

    def connect_hw(self):
        try:
            mido.open_input(self.midi_combo.currentText(), callback=self.midi_callback)
            if self.dmx.connect(self.dmx_combo.currentText()): self.btn_conn.setStyleSheet("background-color: #27ae60;")
        except Exception: pass

    def save_data(self):
        with open("studio_data.json", "w") as f:
            json.dump({"ch_map": self.mappings, "rem_map": self.remote_mappings, "scenes": self.scenes, "chases": self.chases}, f)

    def load_data(self):
        if os.path.exists("studio_data.json"):
            with open("studio_data.json", "r") as f:
                d = json.load(f); self.mappings = d.get("ch_map", {}); self.remote_mappings = d.get("rem_map", {})
                self.scenes = d.get("scenes", {}); self.chases = d.get("chases", {})
                for s in self.scenes: self.s_list.addItem(s)
                for c in self.chases: self.c_list.addItem(c)

if __name__ == "__main__":
    app = QApplication(sys.argv); w = MainWindow(); w.show(); sys.exit(app.exec())