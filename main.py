import sys, time, json, threading, os, mido, serial, serial.tools.list_ports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QComboBox, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel, QScrollArea, 
                             QGridLayout, QMessageBox, QMenu, QSlider, QListWidget, 
                             QInputDialog, QLineEdit, QDialog)
from PyQt6.QtGui import QIntValidator
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
        except: 
            return False

    def _send_loop(self):
        while self.running:
            if self.serial_port:
                try:
                    for i in range(1, 513):
                        # Logica HTP (Highest Takes Precedence)
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

# --- FINESTRA CREAZIONE CHASE ---
class ChaseCreatorDialog(QDialog):
    def __init__(self, scenes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuovo Chase")
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Seleziona Scene (CTRL per multiple):"))
        self.list = QListWidget()
        self.list.addItems(scenes.keys())
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list)
        
        layout.addWidget(QLabel("Tempo Tenuta (ms):"))
        self.t_hold = QLineEdit("1000")
        layout.addWidget(self.t_hold)
        
        layout.addWidget(QLabel("Tempo Fade (ms):"))
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
        self.scenes = {}
        self.chases = {}
        self.active_scene = None
        self.active_chase = None
        self.is_learning = False
        self.last_sig = None

        self.setWindowTitle("MIDI-DMX Studio Pro")
        self.resize(1400, 900)
        self.setStyleSheet("background-color: #0a0a0a; color: #DDD;")

        # Layout Principale
        main_layout = QHBoxLayout()
        
        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        side_l = QVBoxLayout(sidebar)
        
        # Sezione Hardware
        side_l.addWidget(QLabel("<b>1. HARDWARE</b>"))
        self.midi_combo = QComboBox()
        self.midi_combo.addItems(mido.get_input_names())
        side_l.addWidget(self.midi_combo)
        
        self.dmx_combo = QComboBox()
        self.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        side_l.addWidget(self.dmx_combo)
        
        self.btn_conn = QPushButton("CONNETTI")
        self.btn_conn.clicked.connect(self.connect_hw)
        side_l.addWidget(self.btn_conn)

        # Sezione Live
        side_l.addSpacing(15)
        side_l.addWidget(QLabel("<b>2. LIVE CONTROL</b>"))
        self.s_label = QLabel("VAL: 0 | 0%")
        self.s_label.hide()
        side_l.addWidget(self.s_label)
        
        self.m_input = QLineEdit()
        self.m_input.setValidator(QIntValidator(0, 255))
        self.m_input.hide()
        self.m_input.returnPressed.connect(self.manual_val_entry)
        side_l.addWidget(self.m_input)
        
        self.s_live = QSlider(Qt.Orientation.Horizontal)
        self.s_live.setRange(0, 255)
        self.s_live.hide()
        self.s_live.valueChanged.connect(self.slider_moved)
        side_l.addWidget(self.s_live)
        
        self.b_learn = QPushButton("LEARN MIDI")
        self.b_learn.clicked.connect(self.toggle_learn)
        self.b_learn.setEnabled(False)
        side_l.addWidget(self.b_learn)

        # Sezione Scene
        side_l.addSpacing(15)
        side_l.addWidget(QLabel("<b>3. SCENE</b>"))
        btn_save_sc = QPushButton("SALVA SCENA")
        btn_save_sc.setStyleSheet("background-color: #27ae60;")
        btn_save_sc.clicked.connect(self.save_scene)
        side_l.addWidget(btn_save_sc)
        
        self.s_list = QListWidget()
        self.s_list.itemClicked.connect(self.toggle_scene_active)
        self.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.s_list.customContextMenuRequested.connect(self.scene_context_menu)
        side_l.addWidget(self.s_list)

        # Sezione Chase
        side_l.addSpacing(15)
        side_l.addWidget(QLabel("<b>4. CHASES</b>"))
        btn_new_ch = QPushButton("NUOVO CHASE")
        btn_new_ch.setStyleSheet("background-color: #2980b9;")
        btn_new_ch.clicked.connect(self.create_chase)
        side_l.addWidget(btn_new_ch)
        
        self.c_list = QListWidget()
        self.c_list.itemClicked.connect(self.toggle_chase_active)
        self.c_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.c_list.customContextMenuRequested.connect(self.chase_context_menu)
        side_l.addWidget(self.c_list)

        # Blackout
        side_l.addSpacing(15)
        btn_bl = QPushButton("BLACKOUT")
        btn_bl.setStyleSheet("background-color: #c0392b; font-weight: bold;")
        btn_bl.clicked.connect(self.blackout)
        side_l.addWidget(btn_bl)
        side_l.addStretch()

        # Monitor Canali
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_container = QWidget()
        self.grid = QGridLayout(grid_container)
        self.cells = []
        for i in range(512):
            cell = DMXCell(i+1)
            cell.clicked.connect(self.toggle_channel_selection)
            cell.rightClicked.connect(self.channel_midi_menu)
            self.grid.addWidget(cell, i//9, i%9)
            self.cells.append(cell)
        
        scroll.setWidget(grid_container)
        main_layout.addWidget(sidebar)
        main_layout.addWidget(scroll)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Timer e Dati
        self.load_data()
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(40)
        
        self.chase_timer = QTimer()
        self.chase_timer.timeout.connect(self.process_fade_engine)
        self.fade_start_time = 0

    # --- LOGICA CHASE & FADE ---
    def process_fade_engine(self):
        if not self.active_chase: return
        ch = self.chases[self.active_chase]
        steps, hold, fade = ch["steps"], ch["hold"], ch["fade"]
        
        cycle_ms = hold + fade
        total_ms = cycle_ms * len(steps)
        elapsed = (int(time.time() * 1000) - self.fade_start_time) % total_ms
        
        step_idx = elapsed // cycle_ms
        sub_elapsed = elapsed % cycle_ms
        
        curr_data = self.scenes[steps[step_idx]]
        next_data = self.scenes[steps[(step_idx + 1) % len(steps)]]
        
        new_buf = bytearray([0] * 513)
        for i in range(1, 513):
            v1 = curr_data.get(str(i), 0)
            v2 = next_data.get(str(i), 0)
            
            if sub_elapsed < hold:
                val = v1
            else:
                p = (sub_elapsed - hold) / fade
                val = int(v1 + (v2 - v1) * p)
            new_buf[i] = val
        self.dmx.chase_buffer = new_buf

    def toggle_chase_active(self, item):
        name = item.text()
        if self.active_chase == name:
            self.active_chase = None
            self.chase_timer.stop()
            self.dmx.chase_buffer = bytearray([0] * 513)
            self.c_list.clearSelection()
        else:
            self.active_chase = name
            self.fade_start_time = int(time.time() * 1000)
            self.chase_timer.start(40)

    def chase_context_menu(self, pos):
        item = self.c_list.itemAt(pos)
        if not item: return
        menu = QMenu()
        del_act = menu.addAction("Elimina Chase")
        if menu.exec(self.c_list.mapToGlobal(pos)) == del_act:
            name = item.text()
            if self.active_chase == name:
                self.active_chase = None
                self.chase_timer.stop()
                self.dmx.chase_buffer = bytearray([0] * 513)
            del self.chases[name]
            self.c_list.takeItem(self.c_list.row(item))
            self.save_data()

    # --- LOGICA SCENE ---
    def scene_context_menu(self, pos):
        item = self.s_list.itemAt(pos)
        if not item: return
        menu = QMenu()
        del_act = menu.addAction("Elimina Scena")
        if menu.exec(self.s_list.mapToGlobal(pos)) == del_act:
            name = item.text()
            if self.active_scene == name:
                self.active_scene = None
                self.dmx.scene_buffer = bytearray([0] * 513)
            del self.scenes[name]
            self.s_list.takeItem(self.s_list.row(item))
            self.save_data()

    # --- RESTANTI FUNZIONI (UI, MIDI, HARDWARE) ---
    def update_ui(self):
        mapped = set()
        for t in self.mappings.values(): mapped.update(t)
        
        for i in range(512):
            ch = i + 1
            val = max(self.dmx.live_buffer[ch], self.dmx.scene_buffer[ch], self.dmx.chase_buffer[ch])
            
            is_sel = ch in self.selected_ch
            border = "2px solid #f1c40f" if is_sel else "1px solid #1a1a1a"
            
            color = "#2ecc71" if ch in mapped else "#444"
            val_col = "#e67e22" if ch in mapped else "#444"
            
            self.cells[i].setText(f"<b><font color='{color}'>CH {ch}:</font></b><br><font color='{val_col}'>{val} ({int(val/2.55)}%)</font>")
            self.cells[i].setStyleSheet(f"background-color: #0a0a0a; border: {border}; font-size: 9px; border-radius: 2px;")
            
        if not self.is_learning and self.last_sig:
            self.mappings[self.last_sig] = list(self.selected_ch)
            self.last_sig = None
            self.save_data()

    def channel_midi_menu(self, ch):
        menu = QMenu()
        act = menu.addAction(f"Scollega MIDI dal Canale {ch}")
        if menu.exec(self.cells[ch-1].mapToGlobal(self.cells[ch-1].rect().center())) == act:
            for sig in list(self.mappings.keys()):
                if ch in self.mappings[sig]:
                    self.mappings[sig].remove(ch)
                    if not self.mappings[sig]: del self.mappings[sig]
            self.save_data()

    def toggle_channel_selection(self, ch):
        if ch in self.selected_ch: self.selected_ch.remove(ch)
        else: self.selected_ch.add(ch)
        vis = len(self.selected_ch) > 0
        self.s_live.setVisible(vis); self.s_label.setVisible(vis); self.m_input.setVisible(vis); self.b_learn.setEnabled(vis)

    def slider_moved(self, v):
        self.s_label.setText(f"VAL: {v} | {int(v/2.55)}%")
        self.m_input.setText(str(v))
        for c in self.selected_ch: self.dmx.live_buffer[c] = v

    def manual_val_entry(self):
        val = int(self.m_input.text() or 0)
        self.s_live.setValue(val)

    def save_scene(self):
        frame = {str(i): max(self.dmx.live_buffer[i], self.dmx.scene_buffer[i], self.dmx.chase_buffer[i]) for i in range(1, 513)}
        name, ok = QInputDialog.getText(self, 'Salva Scena', 'Nome:')
        if ok and name:
            self.scenes[name] = frame
            if not self.s_list.findItems(name, Qt.MatchFlag.MatchExactly): self.s_list.addItem(name)
            self.save_data()

    def toggle_scene_active(self, item):
        name = item.text()
        if self.active_scene == name:
            self.active_scene = None
            self.dmx.scene_buffer = bytearray([0] * 513)
            self.s_list.clearSelection()
        else:
            self.active_scene = name
            buf = bytearray([0] * 513)
            for c, v in self.scenes[name].items(): buf[int(c)] = v
            self.dmx.scene_buffer = buf
            self.dmx.live_buffer = bytearray([0] * 513)

    def create_chase(self):
        if not self.scenes:
            QMessageBox.warning(self, "Errore", "Crea prima delle scene!")
            return
        d = ChaseCreatorDialog(self.scenes, self)
        if d.exec():
            steps = [i.text() for i in d.list.selectedItems()]
            if steps:
                name, ok = QInputDialog.getText(self, 'Salva Chase', 'Nome:')
                if ok and name:
                    self.chases[name] = {"steps": steps, "hold": int(d.t_hold.text()), "fade": int(d.t_fade.text())}
                    self.c_list.addItem(name)
                    self.save_data()

    def blackout(self):
        self.dmx.live_buffer = bytearray([0]*513)
        self.dmx.scene_buffer = bytearray([0]*513)
        self.dmx.chase_buffer = bytearray([0]*513)
        self.active_scene = self.active_chase = None
        self.chase_timer.stop()
        self.s_list.clearSelection()
        self.c_list.clearSelection()

    def connect_hw(self):
        try:
            mido.open_input(self.midi_combo.currentText(), callback=self.midi_callback)
            if self.dmx.connect(self.dmx_combo.currentText()):
                self.btn_conn.setStyleSheet("background-color: #27ae60;")
        except: pass

    def midi_callback(self, msg):
        sig = None
        if msg.type == 'control_change': sig = f"cc_{msg.control}"
        elif msg.type in ['note_on', 'note_off']: sig = f"note_{msg.note}"
        
        if not sig: return
        if self.is_learning:
            self.last_sig = sig
            self.is_learning = False
        elif sig in self.mappings:
            val = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.type == 'note_on' and msg.velocity > 0 else 0)
            for c in self.mappings[sig]: self.dmx.live_buffer[c] = val

    def toggle_learn(self):
        self.is_learning = not self.is_learning
        self.b_learn.setText("ANNULLA" if self.is_learning else "LEARN MIDI")

    def save_data(self):
        with open("studio_data.json", "w") as f:
            json.dump({"mappings": self.mappings, "scenes": self.scenes, "chases": self.chases}, f)

    def load_data(self):
        if os.path.exists("studio_data.json"):
            with open("studio_data.json", "r") as f:
                d = json.load(f)
                self.mappings = d.get("mappings", {})
                self.scenes = d.get("scenes", {})
                self.chases = d.get("chases", {})
                for s in self.scenes: self.s_list.addItem(s)
                for c in self.chases: self.c_list.addItem(c)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())