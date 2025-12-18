from PyQt6.QtWidgets import (QMainWindow, QComboBox, QPushButton, 
                             QVBoxLayout, QWidget, QLabel, QSpinBox, QMessageBox)
from PyQt6.QtCore import QTimer
import mido
import serial.tools.list_ports

class MainWindow(QMainWindow):
    def __init__(self, midi_mgr, dmx_ctrl):
        super().__init__()
        self.midi_mgr = midi_mgr
        self.dmx_ctrl = dmx_ctrl
        self.setWindowTitle("MIDI-DMX Pro: Real-Time Mapper")
        self.setMinimumWidth(400)

        # Timer per monitorare la fase di Learn
        self.learn_timer = QTimer()
        self.learn_timer.timeout.connect(self.check_learn_status)

        layout = QVBoxLayout()

        # Selezione Hardware
        layout.addWidget(QLabel("<b>Configurazione Hardware</b>"))
        
        self.midi_combo = QComboBox()
        self.midi_combo.addItems(mido.get_input_names())
        layout.addWidget(QLabel("Input MIDI:"))
        layout.addWidget(self.midi_combo)

        self.dmx_combo = QComboBox()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.dmx_combo.addItems(ports)
        layout.addWidget(QLabel("Output USB-DMX:"))
        layout.addWidget(self.dmx_combo)

        self.btn_connect = QPushButton("CONNETTI DISPOSITIVI")
        self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_connect.clicked.connect(self.start_bridge)
        layout.addWidget(self.btn_connect)

        layout.addSpacing(20)

        # Sezione Mapping
        layout.addWidget(QLabel("<b>Mappatura Automatica</b>"))
        
        self.dmx_spin = QSpinBox()
        self.dmx_spin.setRange(1, 512)
        layout.addWidget(QLabel("Seleziona Canale DMX bersaglio:"))
        layout.addWidget(self.dmx_spin)

        self.btn_learn = QPushButton("ATTIVA LEARN MIDI")
        self.btn_learn.clicked.connect(self.start_learn_process)
        layout.addWidget(self.btn_learn)

        # Log delle mappature attive
        self.lbl_status = QLabel("Stato: Pronto")
        layout.addWidget(self.lbl_status)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Pulsanti File
        self.btn_save = QPushButton("SALVA CONFIGURAZIONE")
        self.btn_save.clicked.connect(lambda: self.midi_mgr.save_mappings())
        layout.addWidget(self.btn_save)

        self.btn_load = QPushButton("CARICA CONFIGURAZIONE")
        self.btn_load.clicked.connect(self.load_and_refresh)
        layout.addWidget(self.btn_load)

        layout.addSpacing(20)
        layout.addWidget(QLabel("<b>Controllo Chase (Sequenze)</b>"))

        self.btn_chase1 = QPushButton("START CHASE 1 (Test)")
        # In un caso reale, mapperesti un Note_On a questa funzione
        self.btn_chase1.clicked.connect(self.toggle_test_chase)
        layout.addWidget(self.btn_chase1)

    def start_bridge(self):
        dmx_ok = self.dmx_ctrl.connect(self.dmx_combo.currentText())
        midi_ok = self.midi_mgr.open_port(self.midi_combo.currentText())
        
        if dmx_ok and midi_ok:
            self.lbl_status.setText("Stato: Connesso e Operativo")
            self.btn_connect.setEnabled(False)
        else:
            QMessageBox.critical(self, "Errore", "Impossibile connettersi ai dispositivi selezionati.")

    def start_learn_process(self):
        if not self.midi_mgr.input_port:
            QMessageBox.warning(self, "Attenzione", "Connetti prima i dispositivi!")
            return
            
        self.midi_mgr.is_learning = True
        self.midi_mgr.last_learned_signal = None
        self.btn_learn.setText("ASCOLTO MIDI... (Muovi un controllo)")
        self.btn_learn.setStyleSheet("background-color: #ff9800;")
        self.learn_timer.start(100) # Controlla ogni 100ms

    def check_learn_status(self):
        # Se il manager ha catturato un segnale, is_learning diventa False (vedi midi_logic)
        if not self.midi_mgr.is_learning and self.midi_mgr.last_learned_signal:
            self.learn_timer.stop()
            
            sig = self.midi_mgr.last_learned_signal
            dmx_ch = self.dmx_spin.value()
            
            # Salva la mappatura
            self.midi_mgr.mappings[sig] = dmx_ch
            
            self.btn_learn.setText("ATTIVA LEARN MIDI")
            self.btn_learn.setStyleSheet("")
            self.lbl_status.setText(f"Mappato: {sig} -> Canale DMX {dmx_ch}")
            print(f"Mappatura salvata: {self.midi_mgr.mappings}")

    def load_and_refresh(self):
        self.midi_mgr.load_mappings()
        self.lbl_status.setText(f"Caricate {len(self.midi_mgr.mappings)} mappature")

    def toggle_test_chase(self):
        if self.dmx_ctrl.active_chase:
            self.dmx_ctrl.stop_chase()
            self.btn_chase1.setText("START CHASE 1")
        else:
            # Definiamo un chase di test: alterna canali 1 e 2 al massimo
            self.dmx_ctrl.chases["test"] = [
                [(1, 255), (2, 0)],
                [(1, 0), (2, 255)]
            ]
            self.dmx_ctrl.play_chase("test")
            self.btn_chase1.setText("STOP CHASE 1")