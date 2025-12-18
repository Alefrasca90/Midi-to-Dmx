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
                             QGridLayout, QMessageBox, QMenu)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

# --- CLASSE CELLA CON SELEZIONE MULTIPLA ---
class DMXCell(QLabel):
    clicked = pyqtSignal(int)
    rightClicked = pyqtSignal(int)

    def __init__(self, channel_index, parent=None):
        super().__init__(parent)
        self.channel_index = channel_index
        self.setFixedSize(85, 25)
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
                        self.output_frame[i] = self.live_buffer[i]
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                    time.sleep(0.025)
                except: self.running = False

    def blackout(self):
        for i in range(513): self.live_buffer[i] = 0

# --- LOGICA MIDI ---
class MIDIManager:
    def __init__(self, dmx_controller):
        self.dmx = dmx_controller
        self.input_port = None
        self.mappings = {} 
        self.is_learning = False
        self.last_signal = None

    def open_port(self, name):
        try:
            if self.input_port: self.input_port.close()
            self.input_port = mido.open_input(name, callback=self._callback)
            return True
        except: return False

    def _callback(self, msg):
        sig_id = None
        val = 0
        if msg.type == 'control_change':
            sig_id = f"cc_{msg.control}"
            val = int(msg.value * 2.007)
        elif msg.type in ['note_on', 'note_off']:
            sig_id = f"note_{msg.note}"
            val = 255 if msg.type == 'note_on' and msg.velocity > 0 else 0

        if sig_id:
            if self.is_learning:
                self.last_signal = sig_id
                self.is_learning = False
            elif sig_id in self.mappings:
                targets = self.mappings[sig_id]
                for ch in targets:
                    self.dmx.live_buffer[ch] = val

# --- INTERFACCIA GRAFICA ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dmx = DMXController()
        self.midi = MIDIManager(self.dmx)
        self.selected_channels = set()
        
        self.setWindowTitle("MIDI-DMX Mapper Pro")
        self.resize(1150, 750)
        self.setStyleSheet("background-color: #0a0a0a; color: #DDD;")

        main_layout = QHBoxLayout()
        
        # --- PANNELLO CONTROLLI ---
        left_widget = QWidget()
        left_widget.setFixedWidth(220)
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
        self.btn_conn.setStyleSheet("background-color: #2c3e50; padding: 8px;")
        controls.addWidget(self.btn_conn)

        controls.addSpacing(20)
        controls.addWidget(QLabel("<b>2. MAPPING</b>"))
        self.info_label = QLabel("Seleziona i canali nella griglia")
        self.info_label.setStyleSheet("color: #aaa; font-style: italic;")
        controls.addWidget(self.info_label)

        self.btn_learn = QPushButton("LEARN MIDI")
        self.btn_learn.clicked.connect(self.toggle_learn) # Chiamata al nuovo metodo toggle
        self.btn_learn.setStyleSheet("background-color: #2980b9; padding: 10px;")
        self.btn_learn.setEnabled(False)
        controls.addWidget(self.btn_learn)

        self.btn_clear_sel = QPushButton("DESELEZIONA TUTTO")
        self.btn_clear_sel.clicked.connect(self.clear_selection)
        controls.addWidget(self.btn_clear_sel)

        self.btn_blackout = QPushButton("BLACKOUT")
        self.btn_blackout.clicked.connect(self.dmx.blackout)
        self.btn_blackout.setStyleSheet("background-color: #c0392b; font-weight: bold; padding: 12px; margin-top: 10px;")
        controls.addWidget(self.btn_blackout)
        
        controls.addStretch()

        # --- MONITOR 512 CANALI ---
        monitor_container = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: 1px solid #333; background-color: #000;")
        
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
        self.timer = QTimer(); self.timer.timeout.connect(self.update_ui); self.timer.start(100)

    def toggle_learn(self):
        """Attiva o disattiva il MIDI learning"""
        if not self.midi.is_learning:
            # Attiva Learning
            if self.selected_channels:
                self.midi.is_learning = True
                self.btn_learn.setText("ANNULLA LEARN (In ascolto...)")
                self.btn_learn.setStyleSheet("background-color: #f39c12; font-weight: bold; color: black;")
        else:
            # Disattiva/Annulla Learning
            self.midi.is_learning = False
            self.midi.last_signal = None
            count = len(self.selected_channels)
            self.btn_learn.setText(f"LEARN MIDI PER {count} CH")
            self.btn_learn.setStyleSheet("background-color: #2980b9;")

    def toggle_selection(self, ch_num):
        if ch_num in self.selected_channels:
            self.selected_channels.remove(ch_num)
        else:
            self.selected_channels.add(ch_num)
        
        count = len(self.selected_channels)
        self.info_label.setText(f"Selezionati: {count}" if count > 0 else "Nessun canale selezionato")
        self.btn_learn.setEnabled(count > 0)
        
        if not self.midi.is_learning:
            self.btn_learn.setText(f"LEARN MIDI PER {count} CH" if count > 0 else "LEARN MIDI")

    def clear_selection(self):
        self.selected_channels.clear()
        self.toggle_selection(None)

    def show_context_menu(self, ch_num):
        menu = QMenu(self)
        del_act = menu.addAction(f"Scollega MIDI da Canale {ch_num}")
        action = menu.exec(self.cells[ch_num-1].mapToGlobal(self.cells[ch_num-1].rect().center()))
        if action == del_act:
            for sig in list(self.midi.mappings.keys()):
                if ch_num in self.midi.mappings[sig]:
                    self.midi.mappings[sig].remove(ch_num)
                    if not self.midi.mappings[sig]: del self.midi.mappings[sig]
            self.save_data()

    def connect_hw(self):
        if self.midi.open_port(self.midi_combo.currentText()) and self.dmx.connect(self.dmx_combo.currentText()):
            self.btn_conn.setStyleSheet("background-color: #27ae60;")
            self.btn_conn.setText("ONLINE ✅")

    def update_ui(self):
        all_mapped_chans = set()
        for targets in self.midi.mappings.values():
            all_mapped_chans.update(targets)
        
        for i in range(512):
            ch_num = i + 1
            val = self.dmx.output_frame[ch_num]
            
            if ch_num in self.selected_channels:
                border = "2px solid #f1c40f"
            elif ch_num in all_mapped_chans:
                border = "1px solid #444"
            else:
                border = "1px solid #1a1a1a"

            if ch_num in all_mapped_chans:
                text = f"<b><font color='#2ecc71'>CH {ch_num}:</font></b> <font color='#e67e22'>{val}</font>"
                bg = f"background-color: rgb(0, {int(val/6)+20}, {int(val/5)+40});" if val > 0 else "background-color: #1a1a1a;"
            else:
                text = f"<font color='#444'>CH {ch_num}: {val}</font>"
                bg = "background-color: #0a0a0a;"

            self.cells[i].setText(text)
            self.cells[i].setStyleSheet(f"{bg} border: {border}; font-size: 10px; border-radius: 2px;")

        # Se il MIDI manager ha catturato un segnale (is_learning diventa False internamente)
        if not self.midi.is_learning and self.midi.last_signal:
            self.midi.mappings[self.midi.last_signal] = list(self.selected_channels)
            self.midi.last_signal = None
            count = len(self.selected_channels)
            self.btn_learn.setText(f"LEARN MIDI PER {count} CH")
            self.btn_learn.setStyleSheet("background-color: #2980b9;")
            self.save_data()

    def _load_data(self):
        if os.path.exists("mappings.json"):
            with open("mappings.json", "r") as f:
                self.midi.mappings = json.load(f)

    def save_data(self):
        with open("mappings.json", "w") as f:
            json.dump(self.midi.mappings, f)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())