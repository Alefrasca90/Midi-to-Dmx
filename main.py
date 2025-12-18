import sys
import time
import json
import threading
import os
import mido
import serial
import serial.tools.list_ports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QComboBox, QPushButton, 
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QScrollArea, 
    QGridLayout, QMenu, QListWidget, QInputDialog, QLineEdit, 
    QDialog, QMessageBox, QSlider, QFrame
)
from PyQt6.QtGui import QColor, QIntValidator, QFont
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

# =============================================================================
# COSTANTI E CONFIGURAZIONI INTERFACCIA
# =============================================================================
CELL_WIDTH = 75
CELL_HEIGHT = 42
GRID_COLUMNS = 12
UPDATE_UI_MS = 45
ENGINE_TICK_MS = 40

# =============================================================================
# COMPONENTE CELLA DMX (MONITOR COMPATTO E PROFESSIONALE)
# =============================================================================
class DMXCell(QLabel):
    """
    Rappresenta un singolo canale DMX nella griglia.
    Visualizza ID, Valore e Percentuale.
    """
    clicked = pyqtSignal(int)
    
    def __init__(self, ch, parent=None):
        super().__init__(parent)
        self.ch = ch
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Plain)
        self.setStyleSheet("""
            background-color: #0d0d0d; 
            border: 1px solid #333; 
            border-radius: 2px;
            color: #fff;
        """)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ch)

# =============================================================================
# MOTORE DMX - GESTIONE HARDWARE E LOGICA HTP
# =============================================================================
class DMXController:
    """
    Gestisce la comunicazione seriale e la fusione dei 4 buffer DMX
    seguendo la logica Highest Takes Precedence.
    """
    def __init__(self):
        self.serial_port = None
        self.output_frame = bytearray([0] * 513)
        self.live_buffer = bytearray([0] * 513)
        self.scene_buffer = bytearray([0] * 513)
        self.chase_buffer = bytearray([0] * 513)
        self.cue_buffer = bytearray([0] * 513)
        self.running = False
        self.thread = None

    def connect(self, port):
        try:
            self.serial_port = serial.Serial(port, baudrate=250000, stopbits=2)
            self.running = True
            self.thread = threading.Thread(target=self._send_loop, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            print(f"Errore connessione Seriale: {e}")
            return False

    def _send_loop(self):
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    # Fusione HTP (Highest Takes Precedence)
                    for i in range(1, 513):
                        self.output_frame[i] = max(
                            self.live_buffer[i], 
                            self.scene_buffer[i], 
                            self.chase_buffer[i], 
                            self.cue_buffer[i]
                        )
                    
                    # Generazione segnale DMX (Break + MAB + Data)
                    self.serial_port.break_condition = True
                    time.sleep(0.0001)
                    self.serial_port.break_condition = False
                    self.serial_port.write(self.output_frame)
                    
                    # Frame rate di circa 40Hz (25ms)
                    time.sleep(0.025)
                except Exception as e:
                    print(f"Errore invio DMX: {e}")
                    self.running = False

    def stop(self):
        self.running = False
        if self.serial_port:
            self.serial_port.close()

# =============================================================================
# DIALOG CREAZIONE CHASE (LIV. 2)
# =============================================================================
class ChaseCreatorDialog(QDialog):
    def __init__(self, scenes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuratore Sequenza Chase")
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        
        header = QLabel("<b>Seleziona le Scene per gli Step:</b>")
        layout.addWidget(header)
        
        self.list = QListWidget()
        self.list.addItems(scenes.keys())
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list)
        
        # Campi Tempi
        time_layout = QGridLayout()
        
        time_layout.addWidget(QLabel("Tempo di Hold (ms):"), 0, 0)
        self.t_hold = QLineEdit("1000")
        self.t_hold.setValidator(QIntValidator(1, 60000))
        time_layout.addWidget(self.t_hold, 0, 1)
        
        time_layout.addWidget(QLabel("Tempo di Fade (ms):"), 1, 0)
        self.t_fade = QLineEdit("500")
        self.t_fade.setValidator(QIntValidator(0, 60000))
        time_layout.addWidget(self.t_fade, 1, 1)
        
        layout.addLayout(time_layout)
        
        self.btn_confirm = QPushButton("CONFERMA E CREA CHASE")
        self.btn_confirm.setFixedHeight(35)
        self.btn_confirm.clicked.connect(self.accept)
        layout.addWidget(self.btn_confirm)

# =============================================================================
# CLASSE PRINCIPALE - SOFTWARE DI CONTROLLO
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # --- Inizializzazione Core ---
        self.dmx = DMXController()
        self.selected_ch = set()
        
        # --- Database Dati ---
        self.mappings = {}         # MIDI CC -> Lista Canali
        self.remote_mappings = {}  # MIDI CC/Note -> "tipo:nome"
        self.scenes = {}           # Livello 1
        self.chases = {}           # Livello 2
        self.cues = {}             # Livello 3
        self.show_list = []        # Livello 4 (Show Manager)
        
        # --- Stati Runtime ---
        self.active_sc = None
        self.active_ch = None
        self.active_cue = None
        
        self.is_recording_cue = False
        self.wait_trigger = False
        self.recorded_stream = []
        self.is_learning = False
        self.learn_target = None 
        
        self.play_idx_cue = 0
        self.fade_start_ch = 0

        # --- Caricamento UI e Dati ---
        self.init_interface()
        self.load_all_data()
        
        # --- Timers ---
        self.timer_ui = QTimer()
        self.timer_ui.timeout.connect(self.update_ui_frame)
        self.timer_ui.start(UPDATE_UI_MS)
        
        self.timer_engine = QTimer()
        self.timer_engine.timeout.connect(self.engine_tick)

    def init_interface(self):
        """Costruisce il layout completo dell'applicazione."""
        self.setWindowTitle("MIDI-DMX Studio Pro v.3.0 - Professional Logic")
        self.resize(1650, 950)
        
        # Stile Generale Dark
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; }
            QLabel { color: #888; font-size: 11px; }
            QPushButton { 
                background-color: #2a2a2a; 
                color: #ccc; 
                border: 1px solid #444; 
                padding: 6px; 
                font-size: 11px; 
            }
            QPushButton:hover { background-color: #3a3a3a; }
            QPushButton:pressed { background-color: #1a1a1a; }
            QListWidget { 
                background-color: #141414; 
                border: 1px solid #2a2a2a; 
                color: #ddd; 
                font-size: 11px; 
                outline: none;
            }
            QListWidget::item:selected { 
                background-color: #2980b9; 
                color: white; 
            }
            QComboBox { 
                background-color: #1a1a1a; 
                color: #ddd; 
                border: 1px solid #333; 
                padding: 3px;
            }
            QLineEdit { 
                background-color: #1a1a1a; 
                color: #ddd; 
                border: 1px solid #333; 
                padding: 4px;
            }
        """)

        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # ---------------------------------------------------------
        # SIDEBAR SINISTRA: HARDWARE, LIVE, SCENE
        # ---------------------------------------------------------
        sidebar_left = QWidget()
        sidebar_left.setFixedWidth(230)
        layout_left = QVBoxLayout(sidebar_left)
        layout_left.setSpacing(15)
        
        # Sezione 1: Hardware
        layout_left.addWidget(QLabel("<b style='color: #eee;'>1. HARDWARE</b>"))
        
        self.midi_combo = QComboBox()
        self.midi_combo.addItems(mido.get_input_names())
        layout_left.addWidget(QLabel("MIDI Input Device:"))
        layout_left.addWidget(self.midi_combo)
        
        self.dmx_combo = QComboBox()
        ports = serial.tools.list_ports.comports()
        self.dmx_combo.addItems([p.device for p in ports])
        layout_left.addWidget(QLabel("DMX Serial Port:"))
        layout_left.addWidget(self.dmx_combo)
        
        self.btn_connect = QPushButton("CONNETTI SISTEMA")
        self.btn_connect.setFixedHeight(35)
        self.btn_connect.clicked.connect(self.connect_hardware)
        layout_left.addWidget(self.btn_connect)

        # Sezione 2: Live Control
        layout_left.addWidget(QLabel("<b style='color: #eee;'>2. LIVE CONTROL</b>"))
        
        self.f_label = QLabel("LIVE: 0 | 0%")
        self.f_label.setStyleSheet("color: #3498db; font-weight: bold;")
        layout_left.addWidget(self.f_label)
        
        self.f_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_slider.setRange(0, 255)
        self.f_slider.setFixedHeight(25)
        self.f_slider.valueChanged.connect(self.fader_moved)
        layout_left.addWidget(self.f_slider)
        
        self.f_input = QLineEdit()
        self.f_input.setPlaceholderText("Valore 0-255")
        self.f_input.setValidator(QIntValidator(0, 255))
        self.f_input.returnPressed.connect(self.manual_fader_input)
        layout_left.addWidget(self.f_input)
        
        self.btn_learn = QPushButton("LEARN MIDI CHANNELS")
        self.btn_learn.setFixedHeight(35)
        self.btn_learn.clicked.connect(self.toggle_learn_mode)
        layout_left.addWidget(self.btn_learn)

        # Sezione 3: Scene (Livello 1)
        layout_left.addWidget(QLabel("<b style='color: #eee;'>3. SCENE STATICHE</b>"))
        
        btn_save_sc = QPushButton("SALVA SCENA")
        btn_save_sc.setFixedHeight(30)
        btn_save_sc.clicked.connect(self.save_scene_action)
        btn_save_sc.setStyleSheet("background-color: #1e3d24; border-color: #2ecc71;")
        layout_left.addWidget(btn_save_sc)
        
        self.s_list = QListWidget()
        self.s_list.itemClicked.connect(lambda i: self.toggle_scene(i.text()))
        self.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.s_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.s_list, p, "sc"))
        layout_left.addWidget(self.s_list)
        
        layout_left.addStretch()

        # ---------------------------------------------------------
        # CENTRO: GRID MONITOR (512 CANALI)
        # ---------------------------------------------------------
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background-color: #050505;")
        
        grid_container = QWidget()
        self.grid_layout = QGridLayout(grid_container)
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        
        self.cells = []
        for i in range(512):
            cell = DMXCell(i + 1)
            cell.clicked.connect(self.toggle_channel_selection)
            self.grid_layout.addWidget(cell, i // GRID_COLUMNS, i % GRID_COLUMNS)
            self.cells.append(cell)
            
        scroll_area.setWidget(grid_container)

        # ---------------------------------------------------------
        # SIDEBAR DESTRA: CHASE, CUES, SHOW, BLACKOUT
        # ---------------------------------------------------------
        sidebar_right = QWidget()
        sidebar_right.setFixedWidth(260)
        l_right = QVBoxLayout(sidebar_right)
        l_right.setSpacing(15)
        
        # Sezione 4: Chase (Livello 2)
        l_right.addWidget(QLabel("<b style='color: #eee;'>4. CHASE (SEQUENZE)</b>"))
        
        btn_create_ch = QPushButton("CREA CHASE STEP")
        btn_create_ch.setFixedHeight(30)
        btn_create_ch.clicked.connect(self.create_chase_action)
        l_right.addWidget(btn_create_ch)
        
        self.ch_list = QListWidget()
        self.ch_list.itemClicked.connect(lambda i: self.toggle_chase(i.text()))
        self.ch_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ch_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.ch_list, p, "ch"))
        l_right.addWidget(self.ch_list)

        # Sezione 5: Cues (Livello 3)
        l_right.addWidget(QLabel("<b style='color: #eee;'>5. CUES (LIVE PERFORMANCE)</b>"))
        
        self.btn_rec = QPushButton("● REGISTRA CUE")
        self.btn_rec.setFixedHeight(40)
        self.btn_rec.clicked.connect(self.toggle_cue_recording)
        self.btn_rec.setStyleSheet("color: #e74c3c; font-weight: bold;")
        l_right.addWidget(self.btn_rec)
        
        self.cue_list = QListWidget()
        self.cue_list.itemClicked.connect(lambda i: self.toggle_cue(i.text()))
        self.cue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cue_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.cue_list, p, "cue"))
        l_right.addWidget(self.cue_list)

        # Sezione 6: Show Manager (Livello 4)
        l_right.addWidget(QLabel("<b style='color: #eee;'>6. SHOW MANAGER</b>"))
        
        self.show_list_widget = QListWidget()
        self.show_list_widget.itemDoubleClicked.connect(self.play_show_item)
        l_right.addWidget(self.show_list_widget)
        
        self.btn_go = QPushButton("GO / NEXT")
        self.btn_go.setFixedHeight(50)
        self.btn_go.clicked.connect(self.go_next_step)
        self.btn_go.setStyleSheet("background-color: #8c4a00; color: white; font-weight: bold; font-size: 14px;")
        l_right.addWidget(self.btn_go)
        
        # Blackout
        self.btn_blackout = QPushButton("MASTER BLACKOUT")
        self.btn_blackout.setFixedHeight(40)
        self.btn_blackout.clicked.connect(self.execute_blackout)
        self.btn_blackout.setStyleSheet("background-color: #6d0000; color: white; border: 1px solid #a00;")
        l_right.addWidget(self.btn_blackout)

        # Composizione Finale
        main_layout.addWidget(sidebar_left)
        main_layout.addWidget(scroll_area)
        main_layout.addWidget(sidebar_right)
        
        self.setCentralWidget(central_widget)

    # =========================================================================
    # LOGICA AGGIORNAMENTO MONITOR (RIPRISTINO FORMATTAZIONE)
    # =========================================================================
    def update_ui_frame(self):
        """Aggiorna ogni cella della griglia con i valori correnti HTP."""
        
        # Identificazione canali mappati MIDI
        mapped_channels = set()
        for ch_list in self.mappings.values():
            for channel_id in ch_list:
                mapped_channels.add(channel_id)
        
        # Identificazione scene/chase mappati MIDI (Arancione)
        mapped_remote_names = []
        for value in self.remote_mappings.values():
            if ":" in value:
                mapped_remote_names.append(value.split(":", 1)[1])
        
        # Loop su 512 Canali
        for i in range(512):
            ch_num = i + 1
            dmx_val = self.dmx.output_frame[ch_num]
            percentage = int(dmx_val / 2.55)
            
            # Stile Dinamico
            is_selected = ch_num in self.selected_ch
            is_mapped = ch_num in mapped_channels
            
            border_style = "2px solid #f1c40f" if is_selected else "1px solid #333"
            id_color = "#2ecc71" if is_mapped else "#666"
            
            # FORMATO: CH X: \n Valore (Percentuale%)
            html_text = (
                f"<b><font color='{id_color}'>CH {ch_num}:</font></b><br>"
                f"<span style='font-size: 11px; color: #FFF;'>{dmx_val} ({percentage}%)</span>"
            )
            
            self.cells[i].setText(html_text)
            self.cells[i].setStyleSheet(f"""
                background-color: #0d0d0d; 
                border: {border_style}; 
                border-radius: 2px;
            """)

        # Feedback visivo sulle liste (Arancione per mappati MIDI)
        for list_widget in [self.s_list, self.ch_list, self.cue_list]:
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item.text() in mapped_remote_names:
                    item.setForeground(QColor("#e67e22")) # Arancione
                else:
                    item.setForeground(QColor("#DDD")) # Grigio chiaro

    # =========================================================================
    # MOTORE LOGICO (ENGINE TICK)
    # =========================================================================
    def engine_tick(self):
        """Elabora le animazioni, i fade e le registrazioni ogni 40ms."""
        
        # Gestione Registrazione Performance (LIV. 3)
        if self.is_recording_cue:
            # Cattura l'intero frame di output corrente (HTP)
            self.recorded_stream.append(list(self.dmx.output_frame))
            return

        # Gestione Chaser con Interpolazione (LIV. 2)
        if self.active_ch:
            chase_config = self.chases.get(self.active_ch)
            if chase_config:
                steps = chase_config["steps"]
                hold_ms = chase_config["h"]
                fade_ms = chase_config["f"]
                
                cycle_total = hold_ms + fade_ms
                all_steps_time = cycle_total * len(steps)
                
                # Tempo trascorso dall'avvio del chase
                now_ms = int(time.time() * 1000)
                elapsed = (now_ms - self.fade_start_ch) % all_steps_time
                
                current_step_idx = elapsed // cycle_total
                time_in_step = elapsed % cycle_total
                
                # Nomi Scene Step Corrente e Successivo
                scene_a_name = steps[current_step_idx]
                scene_b_name = steps[(current_step_idx + 1) % len(steps)]
                
                scene_a_data = self.scenes.get(scene_a_name, {})
                scene_b_data = self.scenes.get(scene_b_name, {})
                
                new_chase_buffer = bytearray([0] * 513)
                
                for i in range(1, 513):
                    val_a = scene_a_data.get(str(i), 0)
                    val_b = scene_b_data.get(str(i), 0)
                    
                    if time_in_step < hold_ms:
                        # Fase di HOLD: Valore statico
                        new_chase_buffer[i] = val_a
                    else:
                        # Fase di FADE: Interpolazione lineare
                        progress = (time_in_step - hold_ms) / fade_ms
                        interp_val = int(val_a + (val_b - val_a) * progress)
                        new_chase_buffer[i] = interp_val
                        
                self.dmx.chase_buffer = new_chase_buffer

        # Gestione Riproduzione Performance Cue (LIV. 3)
        if self.active_cue:
            stream_data = self.cues[self.active_cue]["data"]
            if self.play_idx_cue < len(stream_data):
                self.dmx.cue_buffer = bytearray(stream_data[self.play_idx_cue])
                self.play_idx_cue += 1
            else:
                self.play_idx_cue = 0 # Loop Cue

    # =========================================================================
    # GESTIONE LIVE CONTROL E FADER
    # =========================================================================
    def fader_moved(self, value):
        """Aggiorna il buffer LIVE e forza il refresh dell'output DMX."""
        self.f_label.setText(f"LIVE: {value} | {int(value/2.55)}%")
        self.f_input.setText(str(value))
        
        # Scrittura nel buffer Live per i canali selezionati
        for ch_id in self.selected_ch:
            self.dmx.live_buffer[ch_id] = value
            
        # Trigger HTP immediato per risposta visiva istantanea
        self._refresh_dmx_output_now()

    def manual_fader_input(self):
        """Converte l'input testuale in valore fader."""
        try:
            val = int(self.f_input.text() or 0)
            self.f_slider.setValue(val)
        except ValueError:
            pass

    def _refresh_dmx_output_now(self):
        """Ricalcola l'output frame immediatamente (fuori dal thread seriale)."""
        for i in range(1, 513):
            self.dmx.output_frame[i] = max(
                self.dmx.live_buffer[i], 
                self.dmx.scene_buffer[i], 
                self.dmx.chase_buffer[i], 
                self.dmx.cue_buffer[i]
            )

    def toggle_channel_selection(self, ch_id):
        """Aggiunge o rimuove un canale dalla selezione corrente."""
        if ch_id in self.selected_ch:
            self.selected_ch.remove(ch_id)
        else:
            self.selected_ch.add(ch_id)

    # =========================================================================
    # GESTIONE DATI E JSON
    # =========================================================================
    def save_all_to_disk(self):
        """Salva l'intero database dello studio in un file JSON."""
        package = {
            "sc": self.scenes, 
            "ch": self.chases, 
            "cue": self.cues, 
            "show": self.show_list, 
            "rem": self.remote_mappings, 
            "map": self.mappings
        }
        try:
            with open("studio_data.json", "w") as f:
                json.dump(package, f)
        except Exception as e:
            print(f"Errore scrittura disco: {e}")

    def load_all_data(self):
        """Carica i dati e popola le liste della UI."""
        if not os.path.exists("studio_data.json"):
            return
            
        try:
            with open("studio_data.json", "r") as f:
                d = json.load(f)
                
                # Caricamento dizionari con compatibilità nomi vecchi
                self.scenes = d.get("sc", d.get("scenes", {}))
                self.chases = d.get("ch", d.get("chases", {}))
                self.cues = d.get("cue", {})
                self.show_list = d.get("show", [])
                self.remote_mappings = d.get("rem", {})
                self.mappings = d.get("map", {})
                
                # Pulizia UI
                self.s_list.clear()
                self.ch_list.clear()
                self.cue_list.clear()
                self.show_list_widget.clear()
                
                # Ripopolamento Liste
                for s_name in self.scenes:
                    self.s_list.addItem(s_name)
                    
                for c_name in self.chases:
                    self.ch_list.addItem(c_name)
                    
                for q_name in self.cues:
                    self.cue_list.addItem(q_name)
                    
                for i, entry in enumerate(self.show_list):
                    if ":" in entry:
                        t, n = entry.split(":", 1)
                        label = f"{i+1}. [{t.upper()}] {n}"
                        self.show_list_widget.addItem(label)
                        
        except Exception as e:
            print(f"Errore durante il caricamento dati: {e}")

    # =========================================================================
    # MIDI LOGIC E LEARN MODE
    # =========================================================================
    def toggle_learn_mode(self):
        """Attiva o disattiva la modalità di apprendimento MIDI."""
        self.is_learning = not self.is_learning
        
        if self.is_learning:
            self.btn_learn.setText("WAITING MIDI (CLICK TO CANCEL)")
            self.btn_learn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
            # Se non specificato diversamente, il target è il controllo fader
            if self.learn_target is None:
                self.learn_target = "chans"
        else:
            self.btn_learn.setText("LEARN MIDI CHANNELS")
            self.btn_learn.setStyleSheet("background-color: #2c3e50;")
            self.learn_target = None

    def midi_callback(self, msg):
        """Gestore eventi MIDI in ingresso."""
        
        # Identificazione del segnale (CC o Note)
        signal_key = None
        if msg.type == 'control_change':
            signal_key = f"cc_{msg.control}"
        elif msg.type in ['note_on', 'note_off']:
            signal_key = f"note_{msg.note}"
            
        if not signal_key:
            return
            
        # Trigger Registrazione Performance
        if self.wait_trigger:
            QTimer.singleShot(0, self.start_recording_now)
            
        # Logica di Apprendimento (Learn Mode)
        if self.is_learning:
            if self.learn_target == "chans":
                # Mappa CC alla lista di canali selezionati
                self.mappings[signal_key] = list(self.selected_ch)
            else:
                # Mappa CC/Note a una scena/chase/cue specifico
                self.remote_mappings[signal_key] = self.learn_target
                
            self.is_learning = False
            self.save_all_to_disk()
            QTimer.singleShot(0, self.toggle_learn_mode)
            return

        # Logica di Esecuzione (Playback)
        if signal_key in self.mappings:
            # Conversione valore MIDI 0-127 -> DMX 0-255
            dmx_val = int(msg.value * 2.007) if msg.type == 'control_change' else (255 if msg.type == 'note_on' and msg.velocity > 0 else 0)
            for ch_id in self.mappings[signal_key]:
                self.dmx.live_buffer[ch_id] = dmx_val
            self._refresh_dmx_output_now()
            
        elif signal_key in self.remote_mappings:
            # Attivazione spezzoni via remoto
            target = self.remote_mappings[signal_key].split(":", 1)
            # Attivazione solo su pressione (Note On con velocity > 0 o CC con valore > 0)
            is_active_signal = (msg.type == 'note_on' and msg.velocity > 0) or (msg.type == 'control_change' and msg.value > 0)
            
            if is_active_signal:
                t_type, t_name = target[0], target[1]
                if t_type == "sc": QTimer.singleShot(0, lambda: self.toggle_scene(t_name))
                elif t_type == "ch": QTimer.singleShot(0, lambda: self.toggle_chase(t_name))
                elif t_type == "cue": QTimer.singleShot(0, lambda: self.toggle_cue(t_name))

    # =========================================================================
    # AZIONI DI ATTIVAZIONE (LIV. 1, 2, 3)
    # =========================================================================
    def toggle_scene(self, name):
        """Attiva o disattiva una scena statica."""
        if self.active_sc == name:
            self.active_sc = None
            self.dmx.scene_buffer = bytearray([0] * 513)
        else:
            self.active_sc = name
            temp_buf = bytearray([0] * 513)
            scene_data = self.scenes.get(name, {})
            for ch_str, val in scene_data.items():
                temp_buf[int(ch_str)] = val
            self.dmx.scene_buffer = temp_buf
        self._update_list_visual_selection()

    def toggle_chase(self, name):
        """Attiva o disattiva un chase a step."""
        if self.active_ch == name:
            self.active_ch = None
            self.dmx.chase_buffer = bytearray([0] * 513)
        else:
            self.active_ch = name
            self.fade_start_ch = int(time.time() * 1000)
            self.timer_engine.start(ENGINE_TICK_MS)
        self._update_list_visual_selection()

    def toggle_cue(self, name):
        """Attiva o disattiva una registrazione performance."""
        if self.active_cue == name:
            self.active_cue = None
            self.dmx.cue_buffer = bytearray([0] * 513)
        else:
            self.active_cue = name
            self.play_idx_cue = 0
            self.timer_engine.start(ENGINE_TICK_MS)
        self._update_list_visual_selection()

    def _update_list_visual_selection(self):
        """Sincronizza l'evidenziazione delle liste con gli elementi attivi."""
        for i in range(self.s_list.count()):
            self.s_list.item(i).setSelected(self.s_list.item(i).text() == self.active_sc)
        for i in range(self.ch_list.count()):
            self.ch_list.item(i).setSelected(self.ch_list.item(i).text() == self.active_ch)
        for i in range(self.cue_list.count()):
            self.cue_list.item(i).setSelected(self.cue_list.item(i).text() == self.active_cue)

    # =========================================================================
    # REGISTRAZIONE PERFORMANCE (CUE LIV. 3)
    # =========================================================================
    def toggle_cue_recording(self):
        """Gestisce l'avvio e il salvataggio delle registrazioni mistiche."""
        if not self.is_recording_cue and not self.wait_trigger:
            # Fase di attesa trigger
            self.wait_trigger = True
            self.btn_rec.setText("ATTESA MIDI TRIGGER...")
            self.btn_rec.setStyleSheet("background-color: #f1c40f; color: #000; font-weight: bold;")
            self.recorded_stream = []
            
        elif self.is_recording_cue:
            # Fase di stop e salvataggio
            self.is_recording_cue = False
            self.timer_engine.stop()
            self.btn_rec.setText("● REGISTRA CUE")
            self.btn_rec.setStyleSheet("color: #e74c3c; background-color: #222;")
            
            name, ok = QInputDialog.getText(self, "Salva Performance", "Inserisci nome Cue:")
            if ok and name:
                self.cues[name] = {"data": self.recorded_stream}
                self.cue_list.addItem(name)
                self.save_all_to_disk()
        else:
            # Annullamento fase di attesa
            self.wait_trigger = False
            self.btn_rec.setText("● REGISTRA CUE")

    def start_recording_now(self):
        """Avviata non appena viene ricevuto un segnale MIDI durante l'attesa."""
        self.wait_trigger = False
        self.is_recording_cue = True
        self.btn_rec.setText("REGISTRAZIONE IN CORSO...")
        self.btn_rec.setStyleSheet("background-color: #c0392b; color: #fff; font-weight: bold;")
        self.timer_engine.start(ENGINE_TICK_MS)

    # =========================================================================
    # SHOW MANAGER (LIV. 4)
    # =========================================================================
    def play_show_item(self, item):
        """Esegue l'elemento dello show manager selezionato."""
        row_idx = self.show_list_widget.row(item)
        self.show_list_widget.setCurrentRow(row_idx)
        
        entry_string = self.show_list[row_idx]
        type_prefix, item_name = entry_string.split(":", 1)
        
        if type_prefix == "sc":
            self.toggle_scene(item_name)
        elif type_prefix == "ch":
            self.toggle_chase(item_name)
        elif type_prefix == "cue":
            self.toggle_cue(item_name)

    def go_next_step(self):
        """Avanza al prossimo spezzone nella scaletta dello show."""
        if not self.show_list:
            return
        current_row = self.show_list_widget.currentRow()
        next_row = (current_row + 1) % len(self.show_list)
        self.play_show_item(self.show_list_widget.item(next_row))

    # =========================================================================
    # MENÙ CONTESTUALI E HELPERS AZIONI
    # =========================================================================
    def show_context_menu(self, widget, pos, t_type):
        """Gestisce il tasto destro sulle liste spezzoni."""
        item = widget.itemAt(pos)
        if not item:
            return
            
        menu = QMenu()
        act_midi = menu.addAction("Mappa a Pulsante MIDI")
        act_show = menu.addAction("Aggiungi a Scaletta Show")
        act_del = menu.addAction("Elimina Elemento")
        
        res = menu.exec(widget.mapToGlobal(pos))
        
        if res == act_midi:
            self.is_learning = True
            self.learn_target = f"{t_type}:{item.text()}"
            self.toggle_learn_mode()
            
        elif res == act_show:
            entry = f"{t_type}:{item.text()}"
            self.show_list.append(entry)
            label = f"{len(self.show_list)}. [{t_type.upper()}] {item.text()}"
            self.show_list_widget.addItem(label)
            self.save_all_to_disk()
            
        elif res == act_del:
            name = item.text()
            # Rimozione dal database logico
            if t_type == "sc": self.scenes.pop(name, None)
            elif t_type == "ch": self.chases.pop(name, None)
            elif t_type == "cue": self.cues.pop(name, None)
            # Rimozione dalla UI
            widget.takeItem(widget.row(item))
            self.save_all_to_disk()

    def save_scene_action(self):
        """Cattura lo stato DMX corrente come scena statica."""
        # Catturiamo solo canali con valore > 0 per ottimizzare il JSON
        snapshot = {}
        for i in range(1, 513):
            if self.dmx.output_frame[i] > 0:
                snapshot[str(i)] = self.dmx.output_frame[i]
                
        name, ok = QInputDialog.getText(self, 'Salva Scena', 'Nome della Scena:')
        if ok and name:
            self.scenes[name] = snapshot
            if not self.s_list.findItems(name, Qt.MatchFlag.MatchExactly):
                self.s_list.addItem(name)
            self.save_all_to_disk()

    def create_chase_action(self):
        """Avvia il dialog per creare un nuovo chase a step."""
        if not self.scenes:
            QMessageBox.warning(self, "Attenzione", "Devi creare almeno una scena prima!")
            return
            
        dialog = ChaseCreatorDialog(self.scenes, self)
        if dialog.exec():
            selected_items = dialog.list.selectedItems()
            step_names = [item.text() for item in selected_items]
            
            if not step_names:
                return
                
            name, ok = QInputDialog.getText(self, 'Nuovo Chase', 'Nome della Sequenza:')
            if ok and name:
                self.chases[name] = {
                    "steps": step_names, 
                    "h": int(dialog.t_hold.text()), 
                    "f": int(dialog.t_fade.text())
                }
                self.ch_list.addItem(name)
                self.save_all_to_disk()

    def execute_blackout(self):
        """Azzera tutti i buffer e ferma ogni esecuzione."""
        self.dmx.live_buffer = bytearray([0] * 513)
        self.dmx.scene_buffer = bytearray([0] * 513)
        self.dmx.chase_buffer = bytearray([0] * 513)
        self.dmx.cue_buffer = bytearray([0] * 513)
        
        self.active_sc = self.active_ch = self.active_cue = None
        self.timer_engine.stop()
        self._refresh_dmx_output_now()
        self._update_list_visual_selection()

    def connect_hardware(self):
        """Tenta la connessione MIDI e DMX."""
        try:
            # Connessione MIDI
            midi_name = self.midi_combo.currentText()
            if midi_name:
                mido.open_input(midi_name, callback=self.midi_callback)
            
            # Connessione DMX
            dmx_port = self.dmx_combo.currentText()
            if self.dmx.connect(dmx_port):
                self.btn_connect.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
                self.btn_connect.setText("SISTEMA ONLINE")
            else:
                QMessageBox.critical(self, "Errore", "Impossibile aprire la porta DMX!")
        except Exception as e:
            QMessageBox.critical(self, "Errore Critico", f"Errore inizializzazione: {e}")

# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Font di sistema per uniformità
    app.setFont(QFont("Segoe UI", 9))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())