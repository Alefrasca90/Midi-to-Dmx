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
                             QInputDialog, QLineEdit)
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
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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
        self.running = False

    def connect(self, port):
        try:
            self.serial_port = serial.Serial(port, baudrate=250000, stopbits=2)
            self.running = True
            threading.Thread(target=self._send_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"Errore DMX: {e}")
            return False

    def _send_loop(self):
        while self.running:
            if self.serial_port:
                try:
                    for i in range(1, 513):
                        self.output_frame[i] = max(self.live_buffer[i], self.scene_buffer[i])
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                    time.sleep(0.025)
                except: self.running = False

# --- INTERFACCIA E LOGICA ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dmx = DMXController()
        self.selected_channels = set()
        self.mappings = {} 
        self.scenes = {} 
        self.active_scene_name = None
        self.is_learning = False
        self.midi_input = None

        self.setWindowTitle("MIDI-DMX Pro Studio - Scene Master")
        self.resize(1300, 850)
        self.setStyleSheet("background-color: #0a0a0a; color: #DDD;")

        main_layout = QHBoxLayout()
        
        # --- PANNELLO CONTROLLI ---
        left_widget = QWidget()
        left_widget.setFixedWidth(230)
        controls = QVBoxLayout(left_widget)
        
        controls.addWidget(QLabel("<b>1. HARDWARE</b>"))
        self.midi_combo = QComboBox()
        self.midi_combo.addItems(mido.get_input_names())
        controls.addWidget(self.midi_combo)
        
        self.dmx_combo = QComboBox()
        self.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        controls.addWidget(self.dmx_combo)
        
        self.btn_conn = QPushButton("CONNETTI")
        self.btn_conn.clicked.connect(self.connect_hw)
        controls.addWidget(self.btn_conn)

        controls.addSpacing(20)
        controls.addWidget(QLabel("<b>2. LIVE CONTROL</b>"))
        
        self.slider_label = QLabel("VAL: 0 | 0%")
        self.slider_label.setStyleSheet("color: #e67e22; font-weight: bold;")
        self.slider_label.hide()
        controls.addWidget(self.slider_label)
        
        self.manual_input = QLineEdit()
        self.manual_input.setValidator(QIntValidator(0, 255))
        self.manual_input.setStyleSheet("background: #222; color: #fff; border: 1px solid #444; padding: 3px;")
        self.manual_input.returnPressed.connect(self.manual_val_entered)
        self.manual_input.hide()
        controls.addWidget(self.manual_input)

        self.live_slider = QSlider(Qt.Orientation.Horizontal)
        self.live_slider.setRange(0, 255)
        self.live_slider.hide()
        self.live_slider.valueChanged.connect(self.slider_moved)
        controls.addWidget(self.live_slider)

        self.btn_learn = QPushButton("LEARN MIDI")
        self.btn_learn.clicked.connect(self.toggle_learn)
        self.btn_learn.setEnabled(False)
        controls.addWidget(self.btn_learn)

        controls.addSpacing(20)
        controls.addWidget(QLabel("<b>3. SCENE</b>"))
        
        self.btn_save_scene = QPushButton("SALVA SCENA ATTUALE")
        self.btn_save_scene.clicked.connect(self.save_current_scene)
        self.btn_save_scene.setStyleSheet("background-color: #27ae60; font-weight: bold; padding: 10px;")
        controls.addWidget(self.btn_save_scene)
        
        self.scene_list = QListWidget()
        self.scene_list.itemClicked.connect(self.toggle_scene_activation)
        self.scene_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.scene_list.customContextMenuRequested.connect(self.scene_context_menu)
        controls.addWidget(self.scene_list)

        self.btn_blackout = QPushButton("BLACKOUT")
        self.btn_blackout.clicked.connect(self.blackout_all)
        self.btn_blackout.setStyleSheet("background-color: #c0392b; font-weight: bold; padding: 10px;")
        controls.addWidget(self.btn_blackout)
        
        controls.addStretch()

        # --- MONITOR 512 CANALI ---
        monitor_container = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(2)
        self.cells = []
        for i in range(512):
            cell = DMXCell(i + 1)
            cell.clicked.connect(self.toggle_selection)
            cell.rightClicked.connect(self.show_context_menu)
            self.grid_layout.addWidget(cell, i // 9, i % 9)
            self.cells.append(cell)
        scroll.setWidget(grid_widget)
        monitor_container.addWidget(scroll)

        main_layout.addWidget(left_widget)
        main_layout.addLayout(monitor_container)
        
        container = QWidget(); container.setLayout(main_layout)
        self.setCentralWidget(container)

        self._load_data()
        self.timer = QTimer(); self.timer.timeout.connect(self.update_ui); self.timer.start(50)

    # --- LOGICA SLIDER ---
    def slider_moved(self, val):
        perc = int((val / 255) * 100)
        self.slider_label.setText(f"VAL: {val} | {perc}%")
        self.manual_input.setText(str(val))
        for ch in self.selected_channels:
            self.dmx.live_buffer[ch] = val

    def manual_val_entered(self):
        txt = self.manual_input.text()
        if txt: self.live_slider.setValue(int(txt))

    def toggle_selection(self, ch_num):
        if ch_num in self.selected_channels: self.selected_channels.remove(ch_num)
        else: self.selected_channels.add(ch_num)
        visible = len(self.selected_channels) > 0
        self.live_slider.setVisible(visible)
        self.slider_label.setVisible(visible)
        self.manual_input.setVisible(visible)
        self.btn_learn.setEnabled(visible)

    # --- LOGICA SCENE ---
    def save_current_scene(self):
        # Salviamo lo stato ESATTO di tutti i 512 canali
        current_frame = {str(i): max(self.dmx.live_buffer[i], self.dmx.scene_buffer[i]) for i in range(1, 513)}
        name, ok = QInputDialog.getText(self, 'Salva Scena', 'Nome scena:')
        if ok and name:
            self.scenes[name] = current_frame
            if not self.scene_list.findItems(name, Qt.MatchFlag.MatchExactly):
                self.scene_list.addItem(name)
            self.save_data()

    def toggle_scene_activation(self, item):
        name = item.text()
        if self.active_scene_name == name:
            # DISATTIVAZIONE
            self.active_scene_name = None
            self.dmx.scene_buffer = bytearray([0] * 513)
            self.scene_list.clearSelection()
        else:
            # ATTIVAZIONE: Azzera il buffer "live" per far posto alla scena
            self.active_scene_name = name
            new_buf = bytearray([0] * 513)
            data = self.scenes.get(name, {})
            for ch_str, val in data.items():
                new_buf[int(ch_str)] = val
            
            # Applichiamo la scena e puliamo i comandi live precedenti
            self.dmx.scene_buffer = new_buf
            self.dmx.live_buffer = bytearray([0] * 513)
            self.live_slider.setValue(0)

    def update_ui(self):
        mapped_chans = set()
        for targets in self.mappings.values(): mapped_chans.update(targets)
        
        for i in range(512):
            ch = i + 1
            # Visualizziamo il massimo reale tra i buffer
            val = max(self.dmx.live_buffer[ch], self.dmx.scene_buffer[ch])
            perc = int((val / 255) * 100)
            
            is_sel = ch in self.selected_channels
            is_map = ch in mapped_chans
            
            border = "2px solid #f1c40f" if is_sel else "1px solid #1a1a1a"
            
            if is_map:
                content = f"<b><font color='#2ecc71'>CH {ch}:</font></b><br><font color='#e67e22'>{val} ({perc}%)</font>"
            else:
                content = f"<font color='#444'>CH {ch}:<br>{val} ({perc}%)</font>"
            
            self.cells[i].setText(content)
            self.cells[i].setStyleSheet(f"background-color: #0a0a0a; border: {border}; font-size: 9px; border-radius: 2px;")

    # --- LOGICA MIDI E HARDWARE ---
    def midi_callback(self, msg):
        if self.is_learning:
            sig_id = f"cc_{msg.control}" if msg.type == 'control_change' else f"note_{msg.note}"
            self.mappings[sig_id] = list(self.selected_channels)
            self.is_learning = False
            self.save_data()
        else:
            sig_id = f"cc_{getattr(msg, 'control', -1)}" if msg.type == 'control_change' else f"note_{getattr(msg, 'note', -1)}"
            if sig_id in self.mappings:
                val = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.velocity > 0 else 0)
                for ch in self.mappings[sig_id]: self.dmx.live_buffer[ch] = val

    def toggle_learn(self):
        self.is_learning = not self.is_learning
        self.btn_learn.setText("ANNULLA LEARN" if self.is_learning else "LEARN MIDI")

    def blackout_all(self):
        for i in range(513): self.dmx.live_buffer[i] = 0
        self.dmx.scene_buffer = bytearray([0] * 513)
        self.active_scene_name = None
        self.scene_list.clearSelection()

    def connect_hw(self):
        try:
            self.midi_input = mido.open_input(self.midi_combo.currentText(), callback=self.midi_callback)
            self.dmx.connect(self.dmx_combo.currentText())
            self.btn_conn.setStyleSheet("background-color: #27ae60;")
        except: pass

    def show_context_menu(self, ch_num):
        menu = QMenu(self)
        del_act = menu.addAction(f"Cancella mapping Ch {ch_num}")
        if menu.exec(self.cells[ch_num-1].mapToGlobal(self.cells[ch_num-1].rect().center())) == del_act:
            for sig in list(self.mappings.keys()):
                if ch_num in self.mappings[sig]:
                    self.mappings[sig].remove(ch_num)
                    if not self.mappings[sig]: del self.mappings[sig]
            self.save_data()

    def scene_context_menu(self, pos):
        item = self.scene_list.itemAt(pos)
        if not item: return
        menu = QMenu()
        del_act = menu.addAction("Elimina Scena")
        if menu.exec(self.scene_list.mapToGlobal(pos)) == del_act:
            if self.active_scene_name == item.text():
                self.active_scene_name = None
                self.dmx.scene_buffer = bytearray([0] * 513)
            del self.scenes[item.text()]
            self.scene_list.takeItem(self.scene_list.row(item))
            self.save_data()

    def _load_data(self):
        if os.path.exists("studio_data.json"):
            with open("studio_data.json", "r") as f:
                data = json.load(f)
                self.mappings = data.get("mappings", {})
                self.scenes = data.get("scenes", {})
                for name in self.scenes: self.scene_list.addItem(name)

    def save_data(self):
        with open("studio_data.json", "w") as f:
            json.dump({"mappings": self.mappings, "scenes": self.scenes}, f)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())