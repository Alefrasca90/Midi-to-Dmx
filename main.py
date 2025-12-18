import sys
import time
import json
import threading
import os
import mido
import serial
import serial.tools.list_ports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QComboBox, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel, QSpinBox, 
                             QScrollArea, QGridLayout, QMessageBox)
from PyQt6.QtCore import QTimer, Qt

# --- LOGICA DMX (Gestione Seriale) ---
class DMXController:
    def __init__(self):
        self.serial_port = None
        self.dmx_frame = bytearray([0] * 513)
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
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.dmx_frame)
                    time.sleep(0.025)
                except: self.running = False

    def set_channel(self, channel, value):
        if 1 <= channel <= 512:
            self.dmx_frame[channel] = max(0, min(255, value))

    def blackout(self):
        for i in range(1, 513):
            self.dmx_frame[i] = 0

# --- LOGICA MIDI (Input & Learn) ---
class MIDIManager:
    def __init__(self, dmx_controller):
        self.dmx = dmx_controller
        self.input_port = None
        self.mappings = {} # {"cc_7": 1, "note_60": 12}
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
                self.dmx.set_channel(self.mappings[sig_id], val)

# --- INTERFACCIA GRAFICA ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dmx = DMXController()
        self.midi = MIDIManager(self.dmx)
        self.setWindowTitle("MIDI-to-DMX Pro Mapper")
        self.resize(1150, 700)
        self.setStyleSheet("background-color: #0a0a0a; color: #DDD;")

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # --- PANNELLO CONTROLLI ---
        left_container = QWidget()
        left_container.setFixedWidth(210)
        controls = QVBoxLayout(left_container)
        
        controls.addWidget(QLabel("<b>HARDWARE</b>"))
        self.midi_combo = QComboBox()
        self.midi_combo.addItems(mido.get_input_names())
        controls.addWidget(self.midi_combo)

        self.dmx_combo = QComboBox()
        self.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        controls.addWidget(self.dmx_combo)

        self.btn_conn = QPushButton("CONNETTI")
        self.btn_conn.clicked.connect(self.connect_hw)
        self.btn_conn.setStyleSheet("background-color: #2c3e50; padding: 8px; font-weight: bold;")
        controls.addWidget(self.btn_conn)

        controls.addSpacing(20)
        controls.addWidget(QLabel("<b>MAPPING</b>"))
        self.spin_ch = QSpinBox(); self.spin_ch.setRange(1, 512)
        controls.addWidget(QLabel("Canale DMX Target:"))
        controls.addWidget(self.spin_ch)

        self.btn_learn = QPushButton("LEARN MIDI")
        self.btn_learn.clicked.connect(self.start_learn)
        self.btn_learn.setStyleSheet("background-color: #2980b9; padding: 8px;")
        controls.addWidget(self.btn_learn)

        self.btn_save = QPushButton("SALVA CONFIG")
        self.btn_save.clicked.connect(self.save_cfg)
        controls.addWidget(self.btn_save)

        self.btn_blackout = QPushButton("BLACKOUT")
        self.btn_blackout.clicked.connect(self.dmx.blackout)
        self.btn_blackout.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 12px; margin-top: 10px;")
        controls.addWidget(self.btn_blackout)

        controls.addStretch()
        
        # --- MONITOR 512 CANALI ---
        monitor_container = QVBoxLayout()
        monitor_container.addWidget(QLabel("<b>DMX MONITOR (Canali Mappati in Colore)</b>"))
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: 1px solid #333; background-color: #000;")
        
        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        
        self.cells = []
        for i in range(512):
            cell = QLabel()
            cell.setFixedSize(85, 25) 
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Layout griglia a 9 colonne
            row, col = i // 9, i % 9
            self.grid_layout.addWidget(cell, row, col)
            self.cells.append(cell)
        
        scroll.setWidget(grid_widget)
        monitor_container.addWidget(scroll)

        main_layout.addWidget(left_container)
        main_layout.addLayout(monitor_container)
        
        container = QWidget(); container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Caricamento configurazione esistente
        if os.path.exists("mappings.json"):
            try:
                with open("mappings.json", "r") as f:
                    self.midi.mappings = json.load(f)
            except: pass

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)

    def connect_hw(self):
        m_ok = self.midi.open_port(self.midi_combo.currentText())
        d_ok = self.dmx.connect(self.dmx_combo.currentText())
        if m_ok and d_ok:
            self.btn_conn.setText("SISTEMA ONLINE ✅")
            self.btn_conn.setStyleSheet("background-color: #27ae60; padding: 8px;")

    def start_learn(self):
        self.midi.is_learning = True
        self.midi.last_signal = None
        self.btn_learn.setText("WAIT MIDI...")
        self.btn_learn.setStyleSheet("background-color: #f39c12; padding: 8px;")

    def update_ui(self):
        # Set dei canali mappati per controllo rapido
        mapped_channels = set(self.midi.mappings.values())
        
        for i in range(512):
            ch_num = i + 1
            val = self.dmx.dmx_frame[ch_num]
            
            if ch_num in mapped_channels:
                # CANALE MAPPATO: Testo Verde e Arancione
                rich_text = f"<b><font color='#2ecc71'>CH {ch_num}:</font></b> <font color='#e67e22'>{val}</font>"
                
                # Feedback di sfondo se il segnale è attivo (>0)
                if val > 0:
                    bg_intensity = int(val / 6) + 20
                    style = f"background-color: rgb(0, {bg_intensity}, {bg_intensity+10}); border: 1px solid #444;"
                else:
                    style = "background-color: #1a1a1a; border: 1px solid #333;"
            else:
                # CANALE NON MAPPATO: Grigio spento
                rich_text = f"<font color='#444'>CH {ch_num}: {val}</font>"
                style = "background-color: #0a0a0a; border: 1px solid #1a1a1a;"
            
            self.cells[i].setText(rich_text)
            self.cells[i].setStyleSheet(style + " font-size: 10px; font-family: Arial;")
        
        # Gestione chiusura fase Learn
        if not self.midi.is_learning and self.midi.last_signal:
            self.midi.mappings[self.midi.last_signal] = self.spin_ch.value()
            self.midi.last_signal = None
            self.btn_learn.setText("LEARN MIDI")
            self.btn_learn.setStyleSheet("background-color: #2980b9; padding: 8px;")
            # Salvataggio automatico dopo ogni mapping
            self.save_cfg(silent=True)

    def save_cfg(self, silent=False):
        try:
            with open("mappings.json", "w") as f:
                json.dump(self.midi.mappings, f)
            if not silent:
                QMessageBox.information(self, "Salvataggio", "Configurazione salvata!")
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "Errore", f"Impossibile salvare: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())