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
                             QGridLayout, QMenu, QListWidget, QInputDialog, QLineEdit, QDialog)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

# --- COMPONENTE CELLA DMX ---
class DMXCell(QLabel):
    clicked = pyqtSignal(int)
    def __init__(self, ch, parent=None):
        super().__init__(parent)
        self.ch = ch
        self.setFixedSize(95, 38)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ch)

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
        except:
            return False

    def _send_loop(self):
        while self.running:
            if self.serial_port:
                try:
                    for i in range(1, 513):
                        # Logica HTP: Il valore massimo tra i buffer vince
                        self.output_frame[i] = max(self.live_buffer[i], 
                                                  self.scene_buffer[i], 
                                                  self.chase_buffer[i])
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                    time.sleep(0.025)
                except:
                    self.running = False

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
        
        # Logica Recording Mistica
        self.is_recording = False
        self.waiting_trigger = False
        self.recorded_stream = []

        self.setWindowTitle("MIDI-DMX Studio Pro")
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

        # 2. MIDI & REC
        side_layout.addSpacing(15)
        side_layout.addWidget(QLabel("<b>2. MIDI & RECORDING</b>"))
        self.btn_learn = QPushButton("LEARN CHANNELS")
        self.btn_learn.clicked.connect(self.toggle_learn_mode)
        self.btn_learn.setStyleSheet("background-color: #333;")
        side_layout.addWidget(self.btn_learn)
        
        self.btn_rec = QPushButton("REC LIVE SHOW")
        self.btn_rec.clicked.connect(self.toggle_live_rec)
        self.btn_rec.setStyleSheet("background-color: #444; color: #ff4757; font-weight: bold;")
        side_layout.addWidget(self.btn_rec)

        # 3. Liste
        side_layout.addSpacing(15)
        side_layout.addWidget(QLabel("<b>3. SCENE</b>"))
        btn_s = QPushButton("SALVA SCENA STATIC")
        btn_s.clicked.connect(self.save_static_scene)
        side_layout.addWidget(btn_s)
        
        self.s_list = QListWidget()
        self.s_list.itemClicked.connect(self.handle_sc_click)
        self.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.s_list.customContextMenuRequested.connect(self.scene_menu)
        side_layout.addWidget(self.s_list)

        side_layout.addSpacing(15)
        side_layout.addWidget(QLabel("<b>4. CHASES / RECORDINGS</b>"))
        self.c_list = QListWidget()
        self.c_list.itemClicked.connect(self.handle_ch_click)
        self.c_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.c_list.customContextMenuRequested.connect(self.chase_menu)
        side_layout.addWidget(self.c_list)

        side_layout.addSpacing(20)
        btn_bl = QPushButton("BLACKOUT")
        btn_bl.clicked.connect(self.blackout)
        btn_bl.setStyleSheet("background-color: #c0392b; font-weight: bold;")
        side_layout.addWidget(btn_bl)
        side_layout.addStretch()

        # Grid Monitor
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
        
        self.timer_engine = QTimer()
        self.timer_engine.timeout.connect(self.engine_tick)
        self.play_idx = 0
        self.fade_start_time = 0

    # --- ENGINE TICK (GESTISCE FADE, CHASE E RECORDING) ---
    def engine_tick(self):
        if self.is_recording:
            # Cattura lo snapshot corrente di tutto l'universo
            self.recorded_stream.append(list(self.dmx.output_frame))
            return

        if not self.active_chase:
            return
            
        ch = self.chases[self.active_chase]
        
        # Caso A: Registrazione Live (Stream di frame)
        if ch.get("type") == "stream":
            stream = ch["data"]
            self.dmx.chase_buffer = bytearray(stream[self.play_idx])
            self.play_idx = (self.play_idx + 1) % len(stream)
            
        # Caso B: Chase Classico (Fade + Hold)
        else:
            steps, hold, fade = ch["steps"], ch["hold"], ch["fade"]
            cycle = hold + fade
            elapsed = (int(time.time() * 1000) - self.fade_start_time) % (cycle * len(steps))
            idx = elapsed // cycle
            sub = elapsed % cycle
            s1 = self.scenes[steps[idx]]
            s2 = self.scenes[steps[(idx + 1) % len(steps)]]
            
            nb = bytearray([0]*513)
            for i in range(1, 513):
                v1, v2 = s1.get(str(i), 0), s2.get(str(i), 0)
                if sub < hold:
                    nb[i] = v1
                else:
                    # Interpolazione lineare per il Fade
                    p = (sub - hold) / fade
                    nb[i] = int(v1 + (v2 - v1) * p)
            self.dmx.chase_buffer = nb

    # --- REGISTRAZIONE LIVE ---
    def toggle_live_rec(self):
        if not self.is_recording and not self.waiting_trigger:
            self.waiting_trigger = True
            self.btn_rec.setText("WAITING MIDI...")
            self.btn_rec.setStyleSheet("background-color: #f1c40f; color: black;")
            self.recorded_stream = []
        elif self.is_recording:
            self.is_recording = False
            self.timer_engine.stop()
            self.btn_rec.setText("REC LIVE SHOW")
            self.btn_rec.setStyleSheet("background-color: #444; color: #ff4757;")
            if self.recorded_stream:
                n, ok = QInputDialog.getText(self, "Salva", "Nome Registrazione:")
                if ok and n:
                    self.chases[n] = {"type": "stream", "data": self.recorded_stream}
                    self.c_list.addItem(n)
                    self.save_data()
        else:
            self.waiting_trigger = False
            self.btn_rec.setText("REC LIVE SHOW")

    def start_real_rec(self):
        self.waiting_trigger = False
        self.is_recording = True
        self.btn_rec.setText("● RECORDING...")
        self.btn_rec.setStyleSheet("background-color: #ff4757; color: white;")
        self.timer_engine.start(40)

    # --- MIDI & LEARN ---
    def toggle_learn_mode(self):
        self.is_learning = not self.is_learning
        if not self.is_learning:
            self.learn_target = None
        elif self.learn_target is None:
            self.learn_target = "channels"
        self.btn_learn.setText("ANNULLA LEARN" if self.is_learning else "LEARN CHANNELS")
        self.btn_learn.setStyleSheet(f"background-color: {'#c0392b' if self.is_learning else '#333'};")

    def midi_callback(self, msg):
        sig = f"cc_{msg.control}" if msg.type == 'control_change' else f"note_{msg.note}" if msg.type in ['note_on', 'note_off'] else None
        if not sig:
            return
        
        # Trigger registrazione live al primo segnale
        if self.waiting_trigger:
            QTimer.singleShot(0, self.start_real_rec)
            
        if self.is_learning:
            if self.learn_target == "channels":
                self.mappings[sig] = list(self.selected_ch)
            else:
                self.remote_mappings[sig] = self.learn_target
            self.save_data()
            QTimer.singleShot(0, self.toggle_learn_mode)
            return
            
        if sig in self.mappings:
            v = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.type == 'note_on' and msg.velocity > 0 else 0)
            for c in self.mappings[sig]:
                self.dmx.live_buffer[c] = v
        elif sig in self.remote_mappings:
            t = self.remote_mappings[sig]
            # Attivazione solo su segnale positivo
            if msg.type in ['note_on', 'control_change'] and (getattr(msg, 'velocity', 127) > 0 or getattr(msg, 'value', 0) > 0):
                if t.startswith("sc:"): self.activate_scene(t[3:])
                elif t.startswith("ch:"): self.activate_chase(t[3:])

    # --- UI & LOGICA LISTE ---
    def handle_sc_click(self, item):
        self.activate_scene(item.text())

    def handle_ch_click(self, item):
        self.activate_chase(item.text())

    def activate_scene(self, name):
        if self.active_scene == name:
            self.active_scene = None
            self.dmx.scene_buffer = bytearray([0]*513)
        else:
            self.active_scene = name
            b = bytearray([0]*513)
            sc = self.scenes.get(name, {})
            for c, v in sc.items():
                b[int(c)] = v
            self.dmx.scene_buffer = b
            self.dmx.live_buffer = bytearray([0]*513)
        self.refresh_list_highlights()

    def activate_chase(self, name):
        if self.active_chase == name:
            self.active_chase = None
            self.timer_engine.stop()
            self.dmx.chase_buffer = bytearray([0]*513)
        else:
            self.active_chase = name
            self.play_idx = 0
            self.fade_start_time = int(time.time()*1000)
            self.timer_engine.start(40)
        self.refresh_list_highlights()

    def refresh_list_highlights(self):
        for i in range(self.s_list.count()):
            self.s_list.item(i).setSelected(self.s_list.item(i).text() == self.active_scene)
        for i in range(self.c_list.count()):
            self.c_list.item(i).setSelected(self.c_list.item(i).text() == self.active_chase)

    def update_ui(self):
        # Canali mappati (Verdi)
        mapped_ch = set()
        for t in self.mappings.values():
            mapped_ch.update(t)
        
        # Liste mappate (Arancioni)
        rem_sc = {v[3:] for v in self.remote_mappings.values() if v.startswith("sc:")}
        rem_ch = {v[3:] for v in self.remote_mappings.values() if v.startswith("ch:")}

        for i in range(512):
            ch = i+1
            val = self.dmx.output_frame[ch]
            sel = "2px solid #f1c40f" if ch in self.selected_ch else "1px solid #1a1a1a"
            col = "#2ecc71" if ch in mapped_ch else "#444"
            self.cells[i].setText(f"<b><font color='{col}'>CH {ch}</font></b><br>{val}")
            self.cells[i].setStyleSheet(f"background-color: #0a0a0a; border: {sel}; font-size: 9px; border-radius: 2px;")
        
        for i in range(self.s_list.count()):
            item = self.s_list.item(i)
            item.setForeground(QColor("#e67e22") if item.text() in rem_sc else QColor("#DDD"))
            
        for i in range(self.c_list.count()):
            item = self.c_list.item(i)
            item.setForeground(QColor("#e67e22") if item.text() in rem_ch else QColor("#DDD"))

    # --- MENU CONTESTUALI ---
    def scene_menu(self, pos):
        item = self.s_list.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        m1 = menu.addAction("Assegna MIDI")
        m2 = menu.addAction("Rimuovi MIDI")
        m3 = menu.addAction("Elimina Scena")
        res = menu.exec(self.s_list.mapToGlobal(pos))
        if res == m1:
            self.learn_target = f"sc:{item.text()}"
            self.toggle_learn_mode()
        elif res == m2:
            self.remove_remote(f"sc:{item.text()}")
        elif res == m3:
            del self.scenes[item.text()]
            self.s_list.takeItem(self.s_list.row(item))
            self.save_data()

    def chase_menu(self, pos):
        item = self.c_list.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        m1 = menu.addAction("Assegna MIDI")
        m2 = menu.addAction("Rimuovi MIDI")
        m3 = menu.addAction("Elimina Chase")
        res = menu.exec(self.c_list.mapToGlobal(pos))
        if res == m1:
            self.learn_target = f"ch:{item.text()}"
            self.toggle_learn_mode()
        elif res == m2:
            self.remove_remote(f"ch:{item.text()}")
        elif res == m3:
            if self.active_chase == item.text():
                self.active_chase = None
                self.timer_engine.stop()
            del self.chases[item.text()]
            self.c_list.takeItem(self.c_list.row(item))
            self.save_data()

    def remove_remote(self, target):
        for k in list(self.remote_mappings.keys()):
            if self.remote_mappings[k] == target:
                del self.remote_mappings[k]
        self.save_data()

    # --- UTILS ---
    def toggle_selection(self, ch):
        if ch in self.selected_ch:
            self.selected_ch.remove(ch)
        else:
            self.selected_ch.add(ch)

    def save_static_scene(self):
        f = {str(i): self.dmx.output_frame[i] for i in range(1, 513)}
        n, ok = QInputDialog.getText(self, 'Salva', 'Nome Scena:')
        if ok and n:
            self.scenes[n] = f
            if not self.s_list.findItems(n, Qt.MatchFlag.MatchExactly):
                self.s_list.addItem(n)
            self.save_data()

    def blackout(self):
        self.dmx.live_buffer = bytearray([0]*513)
        self.dmx.scene_buffer = bytearray([0]*513)
        self.dmx.chase_buffer = bytearray([0]*513)
        self.active_scene = self.active_chase = None
        self.timer_engine.stop()
        self.refresh_list_highlights()

    def connect_hw(self):
        try:
            mido.open_input(self.midi_combo.currentText(), callback=self.midi_callback)
            if self.dmx.connect(self.dmx_combo.currentText()):
                self.btn_conn.setStyleSheet("background-color: #27ae60;")
        except:
            pass

    def save_data(self):
        with open("studio_data.json", "w") as f:
            json.dump({
                "ch_map": self.mappings, 
                "rem_map": self.remote_mappings, 
                "scenes": self.scenes, 
                "chases": self.chases
            }, f)

    def load_data(self):
        if os.path.exists("studio_data.json"):
            with open("studio_data.json", "r") as f:
                d = json.load(f)
                self.mappings = d.get("ch_map", {})
                self.remote_mappings = d.get("rem_map", {})
                self.scenes = d.get("scenes", {})
                self.chases = d.get("chases", {})
                for s in self.scenes: self.s_list.addItem(s)
                for c in self.chases: self.c_list.addItem(c)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())