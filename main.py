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
                             QInputDialog, QLineEdit, QDialog, QListWidgetItem)
from PyQt6.QtGui import QIntValidator
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

# --- CLASSE CELLA ---
class DMXCell(QLabel):
    clicked = pyqtSignal(int)
    rightClicked = pyqtSignal(int)

    def __init__(self, channel_index, parent=None):
        super().__init__(parent)
        self.channel_index = channel_index
        self.setFixedSize(95, 35) 
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.channel_index)
        elif event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit(self.channel_index)

# --- LOGICA DMX ---
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
        except: return False

    def _send_loop(self):
        while self.running:
            if self.serial_port:
                try:
                    for i in range(1, 513):
                        # HTP: Massimo tra Live, Scene e Chase
                        self.output_frame[i] = max(self.live_buffer[i], 
                                                  self.scene_buffer[i], 
                                                  self.chase_buffer[i])
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                    time.sleep(0.025)
                except: self.running = False

# --- DIALOG CREAZIONE CHASE ---
class ChaseCreatorDialog(QDialog):
    def __init__(self, scenes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crea Nuovo Chase")
        self.setFixedSize(300, 400)
        self.layout = QVBoxLayout(self)
        
        self.layout.addWidget(QLabel("Seleziona Scene (in ordine):"))
        self.list_widget = QListWidget()
        self.list_widget.addItems(scenes.keys())
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.layout.addWidget(self.list_widget)
        
        self.layout.addWidget(QLabel("Tempo Step (ms):"))
        self.time_input = QLineEdit("500")
        self.time_input.setValidator(QIntValidator(50, 5000))
        self.layout.addWidget(self.time_input)
        
        self.btn_save = QPushButton("Salva Chase")
        self.btn_save.clicked.connect(self.accept)
        self.layout.addWidget(self.btn_save)

    def get_data(self):
        steps = [item.text() for item in self.list_widget.selectedItems()]
        return steps, int(self.time_input.text())

# --- INTERFACCIA PRINCIPALE ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dmx = DMXController()
        self.selected_channels = set()
        self.mappings = {} 
        self.scenes = {} 
        self.chases = {} 
        self.active_scene = None
        self.active_chase = None
        self.is_learning = False
        
        self.setWindowTitle("MIDI-DMX Pro Studio - Chase Engine")
        self.resize(1400, 900)
        self.setStyleSheet("background-color: #0a0a0a; color: #DDD;")

        main_layout = QHBoxLayout()
        
        # --- SIDEBAR ---
        left_widget = QWidget(); left_widget.setFixedWidth(240)
        controls = QVBoxLayout(left_widget)
        
        # Hardware
        controls.addWidget(QLabel("<b>1. HARDWARE</b>"))
        self.midi_combo = QComboBox(); self.midi_combo.addItems(mido.get_input_names())
        controls.addWidget(self.midi_combo)
        self.dmx_combo = QComboBox(); self.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        controls.addWidget(self.dmx_combo)
        self.btn_conn = QPushButton("CONNETTI"); self.btn_conn.clicked.connect(self.connect_hw)
        controls.addWidget(self.btn_conn)

        # Live
        controls.addSpacing(15)
        controls.addWidget(QLabel("<b>2. LIVE CONTROL</b>"))
        self.slider_label = QLabel("VAL: 0 | 0%"); self.slider_label.hide()
        controls.addWidget(self.slider_label)
        self.manual_input = QLineEdit(); self.manual_input.setValidator(QIntValidator(0, 255)); self.manual_input.hide()
        self.manual_input.returnPressed.connect(self.manual_val_entered)
        controls.addWidget(self.manual_input)
        self.live_slider = QSlider(Qt.Orientation.Horizontal); self.live_slider.setRange(0, 255); self.live_slider.hide()
        self.live_slider.valueChanged.connect(self.slider_moved)
        controls.addWidget(self.live_slider)
        self.btn_learn = QPushButton("LEARN MIDI"); self.btn_learn.clicked.connect(self.toggle_learn); self.btn_learn.setEnabled(False)
        controls.addWidget(self.btn_learn)

        # Scene
        controls.addSpacing(15)
        controls.addWidget(QLabel("<b>3. SCENE</b>"))
        btn_save_scene = QPushButton("SALVA SCENA"); btn_save_scene.clicked.connect(self.save_current_scene)
        btn_save_scene.setStyleSheet("background-color: #27ae60; font-weight: bold;"); controls.addWidget(btn_save_scene)
        self.scene_list = QListWidget(); self.scene_list.itemClicked.connect(self.toggle_scene)
        controls.addWidget(self.scene_list)

        # Chases
        controls.addSpacing(15)
        controls.addWidget(QLabel("<b>4. CHASES</b>"))
        btn_new_chase = QPushButton("NUOVO CHASE"); btn_new_chase.clicked.connect(self.create_chase)
        btn_new_chase.setStyleSheet("background-color: #2980b9; font-weight: bold;"); controls.addWidget(btn_new_chase)
        self.chase_list = QListWidget(); self.chase_list.itemClicked.connect(self.toggle_chase)
        controls.addWidget(self.chase_list)

        btn_blackout = QPushButton("BLACKOUT"); btn_blackout.clicked.connect(self.blackout_all)
        btn_blackout.setStyleSheet("background-color: #c0392b; font-weight: bold; margin-top: 10px;"); controls.addWidget(btn_blackout)
        
        controls.addStretch()

        # --- GRID ---
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        grid_widget = QWidget(); self.grid_layout = QGridLayout(grid_widget)
        self.cells = []
        for i in range(512):
            cell = DMXCell(i + 1); cell.clicked.connect(self.toggle_selection)
            self.grid_layout.addWidget(cell, i // 9, i % 9); self.cells.append(cell)
        scroll.setWidget(grid_widget)

        main_layout.addWidget(left_widget); main_layout.addWidget(scroll)
        container = QWidget(); container.setLayout(main_layout); self.setCentralWidget(container)

        self._load_data()
        self.timer_ui = QTimer(); self.timer_ui.timeout.connect(self.update_ui); self.timer_ui.start(50)
        
        # Motore Chase
        self.chase_timer = QTimer(); self.chase_timer.timeout.connect(self.process_chase)
        self.current_chase_step = 0

    # --- LOGICA CHASE ---
    def create_chase(self):
        if not self.scenes:
            QMessageBox.warning(self, "Errore", "Crea almeno una scena prima!")
            return
        dialog = ChaseCreatorDialog(self.scenes, self)
        if dialog.exec():
            steps, speed = dialog.get_data()
            if steps:
                name, ok = QInputDialog.getText(self, "Nome Chase", "Inserisci nome:")
                if ok and name:
                    self.chases[name] = {"steps": steps, "speed": speed}
                    self.chase_list.addItem(name)
                    self.save_data()

    def toggle_chase(self, item):
        name = item.text()
        if self.active_chase == name:
            self.active_chase = None
            self.chase_timer.stop()
            self.dmx.chase_buffer = bytearray([0] * 513)
            self.chase_list.clearSelection()
        else:
            self.active_chase = name
            self.current_chase_step = 0
            self.chase_timer.start(self.chases[name]["speed"])
            # Feedback visivo
            for i in range(self.chase_list.count()):
                self.chase_list.item(i).setBackground(Qt.GlobalColor.transparent)
            item.setBackground(Qt.GlobalColor.darkBlue)

    def process_chase(self):
        if not self.active_chase: return
        chase = self.chases[self.active_chase]
        step_scene_name = chase["steps"][self.current_chase_step]
        scene_data = self.scenes.get(step_scene_name, {})
        
        new_buf = bytearray([0] * 513)
        for ch, val in scene_data.items():
            new_buf[int(ch)] = val
        self.dmx.chase_buffer = new_buf
        
        self.current_chase_step = (self.current_chase_step + 1) % len(chase["steps"])

    # --- RESTANTE LOGICA (Invariata) ---
    def slider_moved(self, val):
        self.slider_label.setText(f"VAL: {val} | {int((val/255)*100)}%")
        self.manual_input.setText(str(val))
        for ch in self.selected_channels: self.dmx.live_buffer[ch] = val

    def manual_val_entered(self):
        self.live_slider.setValue(int(self.manual_input.text() or 0))

    def toggle_selection(self, ch_num):
        if ch_num in self.selected_channels: self.selected_channels.remove(ch_num)
        else: self.selected_channels.add(ch_num)
        vis = len(self.selected_channels) > 0
        self.live_slider.setVisible(vis); self.slider_label.setVisible(vis); self.manual_input.setVisible(vis); self.btn_learn.setEnabled(vis)

    def save_current_scene(self):
        frame = {str(i): max(self.dmx.live_buffer[i], self.dmx.scene_buffer[i], self.dmx.chase_buffer[i]) for i in range(1, 513)}
        name, ok = QInputDialog.getText(self, 'Salva Scena', 'Nome:')
        if ok and name:
            self.scenes[name] = frame
            if not self.scene_list.findItems(name, Qt.MatchFlag.MatchExactly): self.scene_list.addItem(name)
            self.save_data()

    def toggle_scene(self, item):
        name = item.text()
        if self.active_scene == name:
            self.active_scene = None; self.dmx.scene_buffer = bytearray([0] * 513)
            self.scene_list.clearSelection()
        else:
            self.active_scene = name; new_buf = bytearray([0] * 513)
            for ch, val in self.scenes[name].items(): new_buf[int(ch)] = val
            self.dmx.scene_buffer = new_buf; self.dmx.live_buffer = bytearray([0] * 513)

    def update_ui(self):
        mapped = set()
        for t in self.mappings.values(): mapped.update(t)
        for i in range(512):
            ch = i + 1; val = max(self.dmx.live_buffer[ch], self.dmx.scene_buffer[ch], self.dmx.chase_buffer[ch])
            border = "2px solid #f1c40f" if ch in self.selected_channels else "1px solid #1a1a1a"
            color = "#2ecc71" if ch in mapped else "#444"
            val_color = "#e67e22" if ch in mapped else "#444"
            self.cells[i].setText(f"<b><font color='{color}'>CH {ch}:</font></b><br><font color='{val_color}'>{val} ({int((val/255)*100)}%)</font>")
            self.cells[i].setStyleSheet(f"background-color: #0a0a0a; border: {border}; font-size: 9px; border-radius: 2px;")

    def blackout_all(self):
        self.dmx.live_buffer = bytearray([0] * 513); self.dmx.scene_buffer = bytearray([0] * 513)
        self.dmx.chase_buffer = bytearray([0] * 513); self.active_scene = None; self.active_chase = None
        self.chase_timer.stop(); self.scene_list.clearSelection(); self.chase_list.clearSelection()

    def connect_hw(self):
        if self.dmx.connect(self.dmx_combo.currentText()): self.btn_conn.setStyleSheet("background-color: #27ae60;")

    def toggle_learn(self):
        self.is_learning = not self.is_learning
        self.btn_learn.setText("ANNULLA" if self.is_learning else "LEARN MIDI")

    def _load_data(self):
        if os.path.exists("studio_data.json"):
            with open("studio_data.json", "r") as f:
                d = json.load(f); self.mappings = d.get("mappings", {}); self.scenes = d.get("scenes", {})
                self.chases = d.get("chases", {})
                for s in self.scenes: self.scene_list.addItem(s)
                for c in self.chases: self.chase_list.addItem(c)

    def save_data(self):
        with open("studio_data.json", "w") as f:
            json.dump({"mappings": self.mappings, "scenes": self.scenes, "chases": self.chases}, f)

if __name__ == "__main__":
    app = QApplication(sys.argv); w = MainWindow(); w.show(); sys.exit(app.exec())