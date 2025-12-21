import sys
import math
import colorsys
import serial.tools.list_ports
import mido
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QComboBox, QPushButton, QVBoxLayout, 
    QHBoxLayout, QWidget, QLabel, QScrollArea, QGridLayout, QMenu, 
    QListWidget, QInputDialog, QLineEdit, QMessageBox, QSlider, QFrame, QTabWidget,
    QColorDialog, QAbstractItemView
)
from PyQt6.QtGui import QColor, QIntValidator, QFont, QAction
from PyQt6.QtCore import QTimer, Qt

# IMPORT MODULI LOCALI
from dmx_engine import DMXController
from playback_engine import PlaybackEngine
from midi_manager import MidiManager
import data_manager
from gui_components import DMXCell, ChaseCreatorDialog, FixtureCreatorDialog, FXGeneratorDialog, GRID_COLUMNS

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Dati Iniziali
        self.data_store = {
            "scenes": {}, "chases": {}, "cues": {}, 
            "show": [], "rem": {}, "map": {}, "groups": {},
            "fixtures": {}, 
            "globals": {"chase_speed": 127, "chase_fade": 127} 
        }
        self.selected_ch = set()
        self.current_active_group = None 
        # Nota: La selezione fixture è gestita dalla lista multipla, non serve una var singola

        # 2. Inizializzazione Motori
        self.dmx = DMXController()
        self.playback = PlaybackEngine(self.dmx, self.data_store)
        self.midi = MidiManager(self.playback, self.dmx, self.data_store)
        
        # 3. Collegamento Segnali
        self.midi.selected_channels = self.selected_ch
        self.playback.state_changed.connect(self._update_list_visual_selection)
        self.midi.learn_status_changed.connect(self.on_learn_status_change)
        self.midi.request_ui_refresh.connect(self.update_ui_from_engine) 
        self.midi.new_midi_message.connect(self.update_midi_label)

        # 4. Timer Automazione Show
        self.show_step_timer = QTimer()
        self.show_step_timer.setSingleShot(True)
        self.show_step_timer.timeout.connect(self.go_next_step)

        # 5. Costruzione Interfaccia
        self.init_interface()
        self.load_data()

        # 6. Loop Principali (UI e Engine)
        self.timer_ui = QTimer()
        self.timer_ui.timeout.connect(self.update_ui_frame)
        self.timer_ui.start(33) # ~30 FPS per la GUI
        
        self.timer_engine = QTimer()
        self.timer_engine.timeout.connect(self.playback.tick)
        self.timer_engine.start(40) # 25 FPS per il DMX

    def init_interface(self):
        self.setWindowTitle("MIDI-DMX Pro v.16.1 - Full FX Suite")
        self.resize(1200, 800)
        
        # Stile CSS Scuro
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; }
            QLabel { color: #888; }
            QListWidget { 
                background-color: #141414; border: 1px solid #2a2a2a; color: #ddd; outline: none;
            }
            QListWidget::item:selected { 
                background-color: #2ecc71; color: black; border: none;
            }
            QLineEdit {
                background-color: #1a1a1a; color: #ddd; border: 1px solid #333; padding: 4px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #333; height: 8px; background: #1a1a1a; margin: 2px 0; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3498db; border: 1px solid #3498db; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px;
            }
            QTabWidget::pane { border: 1px solid #333; }
            QTabBar::tab { background: #222; color: #888; padding: 5px; }
            QTabBar::tab:selected { background: #333; color: white; border-bottom: 2px solid #3498db; }
            QMenu { background-color: #222; color: white; border: 1px solid #555; }
            QMenu::item:selected { background-color: #3498db; }
        """)
        
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(central)
        
        # --- PANNELLO SINISTRO (Hardware, Live, Risorse) ---
        left = QVBoxLayout()
        panel_l = QWidget(); panel_l.setFixedWidth(260); panel_l.setLayout(left)
        
        # 1. Output Setup
        left.addWidget(QLabel("<b>1. OUTPUT SETUP</b>"))
        self.hw_tabs = QTabWidget()
        self.hw_tabs.setFixedHeight(140)
        
        # Tab Seriale
        tab_ser = QWidget(); l_ser = QVBoxLayout(tab_ser)
        self.dmx_combo = QComboBox()
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
            self.dmx_combo.addItems(ports)
        except: pass
        btn_conn_ser = QPushButton("CONNETTI SERIALE")
        btn_conn_ser.clicked.connect(self.connect_serial)
        l_ser.addWidget(QLabel("Porta DMX (USB):"))
        l_ser.addWidget(self.dmx_combo)
        l_ser.addWidget(btn_conn_ser)
        self.hw_tabs.addTab(tab_ser, "USB DMX")
        
        # Tab ArtNet
        tab_art = QWidget(); l_art = QVBoxLayout(tab_art)
        row_ip = QHBoxLayout()
        self.art_ip = QLineEdit("127.0.0.1")
        self.art_uni = QLineEdit("0"); self.art_uni.setFixedWidth(30)
        row_ip.addWidget(QLabel("IP:")); row_ip.addWidget(self.art_ip)
        row_ip.addWidget(QLabel("Uni:")); row_ip.addWidget(self.art_uni)
        btn_conn_art = QPushButton("ATTIVA ART-NET")
        btn_conn_art.clicked.connect(self.connect_artnet)
        l_art.addLayout(row_ip)
        l_art.addWidget(btn_conn_art)
        self.hw_tabs.addTab(tab_art, "ART-NET")
        
        left.addWidget(self.hw_tabs)
        
        # MIDI Setup
        midi_box = QHBoxLayout()
        self.midi_combo = QComboBox()
        try:
            self.midi_combo.addItems(mido.get_input_names())
        except: pass
        btn_midi = QPushButton("OK"); btn_midi.setFixedWidth(40)
        btn_midi.clicked.connect(self.connect_midi)
        midi_box.addWidget(QLabel("MIDI IN:"))
        midi_box.addWidget(self.midi_combo)
        midi_box.addWidget(btn_midi)
        left.addLayout(midi_box)
        
        self.lbl_midi_monitor = QLabel("DISCONNECTED")
        self.lbl_midi_monitor.setStyleSheet("color: #666; font-size: 11px; border: 1px solid #333; padding: 2px;")
        self.lbl_midi_monitor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.lbl_midi_monitor)
        
        left.addSpacing(10)
        
        # 2. Live Control
        left.addWidget(QLabel("<b>2. LIVE CONTROL</b>"))
        self.f_label = QLabel("LIVE: 0 | 0%")
        self.f_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        left.addWidget(self.f_label)
        
        fader_layout = QHBoxLayout()
        self.f_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_slider.setRange(0, 255); self.f_slider.setFixedHeight(25)
        self.f_slider.valueChanged.connect(self.fader_moved)
        
        self.f_input = QLineEdit(); self.f_input.setFixedWidth(40); self.f_input.setPlaceholderText("0")
        self.f_input.returnPressed.connect(self.manual_fader_input)
        
        fader_layout.addWidget(self.f_slider)
        fader_layout.addWidget(self.f_input)
        left.addLayout(fader_layout)
        
        self.btn_learn = QPushButton("LEARN MIDI CHANNELS")
        self.btn_learn.clicked.connect(lambda: self.midi.toggle_learn("chans"))
        left.addWidget(self.btn_learn)
        
        self.btn_reset_map = QPushButton("ELIMINA TUTTE LE MAPPATURE MIDI")
        self.btn_reset_map.setStyleSheet("color: #c0392b; border: 1px solid #555; margin-top: 5px;")
        self.btn_reset_map.clicked.connect(self.reset_all_midi_channels)
        left.addWidget(self.btn_reset_map)
        
        left.addSpacing(10)

        # 3. Risorse (Tab Scene, Gruppi, Fixture)
        left.addWidget(QLabel("<b>3. RISORSE</b>"))
        self.sg_tabs = QTabWidget()
        self.sg_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #333; }")
        
        # -- Tab SCENE --
        tab_sc = QWidget(); l_sc = QVBoxLayout(tab_sc); l_sc.setContentsMargins(2,2,2,2)
        btn_save_sc = QPushButton("SALVA SCENA CORRENTE")
        btn_save_sc.setStyleSheet("background-color: #1e3d24; color: #ccc; border: 1px solid #2ecc71;")
        btn_save_sc.clicked.connect(self.save_scene_action)
        
        self.s_list = QListWidget()
        self.s_list.itemClicked.connect(lambda i: self.playback.toggle_scene(i.text()))
        self.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.s_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.s_list, p, "sc"))
        
        l_sc.addWidget(btn_save_sc)
        l_sc.addWidget(self.s_list)
        self.sg_tabs.addTab(tab_sc, "SCENE")
        
        # -- Tab GRUPPI --
        tab_gr = QWidget(); l_gr = QVBoxLayout(tab_gr); l_gr.setContentsMargins(2,2,2,2)
        btn_mk_gr = QPushButton("CREA GRUPPO")
        btn_mk_gr.setStyleSheet("background-color: #2c3e50; color: #3498db; border: 1px solid #3498db;")
        btn_mk_gr.clicked.connect(self.create_group_action)
        
        self.g_list = QListWidget()
        self.g_list.itemClicked.connect(lambda i: self.select_group(i.text()))
        self.g_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.g_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.g_list, p, "grp"))
        
        l_gr.addWidget(btn_mk_gr)
        l_gr.addWidget(self.g_list)
        self.sg_tabs.addTab(tab_gr, "GRUPPI")

        # -- Tab FIXTURES --
        tab_fix = QWidget(); l_fix = QVBoxLayout(tab_fix); l_fix.setContentsMargins(2,2,2,2)
        
        btn_new_fix = QPushButton("NUOVA FIXTURE")
        btn_new_fix.clicked.connect(self.create_fixture_action)
        
        self.btn_color_pick = QPushButton("🎨 PICK COLOR")
        self.btn_color_pick.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        self.btn_color_pick.clicked.connect(self.open_live_color_picker)
        self.btn_color_pick.setEnabled(False) 

        self.f_list = QListWidget()
        self.f_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.f_list.itemSelectionChanged.connect(self.on_fixture_selection_change)
        
        self.f_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.f_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.f_list, p, "fix"))

        l_fix.addWidget(btn_new_fix)
        l_fix.addWidget(self.btn_color_pick)
        l_fix.addWidget(self.f_list)
        self.sg_tabs.addTab(tab_fix, "FIXTURES")
        
        left.addWidget(self.sg_tabs)
        main_layout.addWidget(panel_l)
        
        # --- PANNELLO CENTRALE (Griglia) ---
        self.cells = []
        grid_w = QWidget(); grid_w.setStyleSheet("background-color: #050505;")
        grid = QGridLayout(grid_w); grid.setSpacing(2); grid.setContentsMargins(5, 5, 5, 5)
        
        for i in range(512):
            c = DMXCell(i + 1)
            c.clicked.connect(self.toggle_cell)
            c.right_clicked.connect(self.cell_context_menu)
            grid.addWidget(c, i // GRID_COLUMNS, i % GRID_COLUMNS)
            self.cells.append(c)
        
        scroll = QScrollArea()
        scroll.setWidget(grid_w)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        main_layout.addWidget(scroll)
        
        # --- PANNELLO DESTRO (Chase, Cue, Show) ---
        right = QVBoxLayout()
        panel_r = QWidget(); panel_r.setFixedWidth(280); panel_r.setLayout(right)
        
        # 4. Chase
        right.addWidget(QLabel("<b>4. CHASE (SEQUENZE)</b>"))
        
        chase_btns = QHBoxLayout()
        btn_mk_ch = QPushButton("MANUALE")
        btn_mk_ch.clicked.connect(self.create_chase_action)
        
        btn_wiz = QPushButton("✨ FX WIZARD")
        btn_wiz.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")
        btn_wiz.clicked.connect(self.open_fx_wizard)
        
        chase_btns.addWidget(btn_mk_ch)
        chase_btns.addWidget(btn_wiz)
        right.addLayout(chase_btns)
        
        self.ch_list = QListWidget(); self.ch_list.setFixedHeight(120)
        self.ch_list.itemClicked.connect(lambda i: self.playback.toggle_chase(i.text()))
        self.ch_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ch_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.ch_list, p, "ch"))
        right.addWidget(self.ch_list)

        # Slider Master Speed/Fade
        speed_box = QWidget(); speed_box.setStyleSheet("background-color: #1a1a1a; border-radius: 4px; margin-top: 5px;")
        l_spd = QVBoxLayout(speed_box); l_spd.setSpacing(2); l_spd.setContentsMargins(5,5,5,5)
        
        self.lbl_speed = QLabel("HOLD TIME %: 100%")
        l_spd.addWidget(self.lbl_speed)
        self.sl_speed = QSlider(Qt.Orientation.Horizontal); self.sl_speed.setRange(0, 255); self.sl_speed.setValue(127)
        self.sl_speed.valueChanged.connect(self.on_speed_change)
        self.sl_speed.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sl_speed.customContextMenuRequested.connect(lambda p: self.show_slider_context(p, "chase_speed"))
        l_spd.addWidget(self.sl_speed)
        
        self.lbl_fade = QLabel("FADE TIME %: 100%")
        l_spd.addWidget(self.lbl_fade)
        self.sl_fade = QSlider(Qt.Orientation.Horizontal); self.sl_fade.setRange(0, 255); self.sl_fade.setValue(127)
        self.sl_fade.valueChanged.connect(self.on_fade_change)
        self.sl_fade.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sl_fade.customContextMenuRequested.connect(lambda p: self.show_slider_context(p, "chase_fade"))
        l_spd.addWidget(self.sl_fade)
        
        right.addWidget(speed_box)

        # 5. Cues
        right.addWidget(QLabel("<b>5. CUES (LIVE)</b>"))
        self.btn_rec = QPushButton("● REGISTRA CUE")
        self.btn_rec.setStyleSheet("color: #e74c3c; font-weight: bold; background-color: #222;")
        self.btn_rec.clicked.connect(self.toggle_rec)
        right.addWidget(self.btn_rec)
        
        self.cue_list = QListWidget(); self.cue_list.setFixedHeight(120)
        self.cue_list.itemClicked.connect(lambda i: self.playback.toggle_cue(i.text()))
        self.cue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cue_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.cue_list, p, "cue"))
        right.addWidget(self.cue_list)
        
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setStyleSheet("color: #444;")
        right.addWidget(line)

        # 6. Show Manager
        right.addWidget(QLabel("<b>6. SHOW MANAGER</b>"))
        self.show_list_widget = QListWidget()
        self.show_list_widget.itemDoubleClicked.connect(self.play_show_item)
        self.show_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.show_list_widget.customContextMenuRequested.connect(self.show_manager_context_menu)
        right.addWidget(self.show_list_widget)
        
        self.btn_go = QPushButton("GO / NEXT ▶")
        self.btn_go.setFixedHeight(45)
        self.btn_go.clicked.connect(self.go_next_step)
        self.btn_go.setStyleSheet("background-color: #d35400; color: white; font-weight: bold; font-size: 14px; border: 1px solid #a04000;")
        right.addWidget(self.btn_go)

        self.btn_bo = QPushButton("MASTER BLACKOUT")
        self.btn_bo.setFixedHeight(40)
        self.btn_bo.setStyleSheet("background-color: #6d0000; color: white; border: 1px solid #a00; font-weight: bold;")
        self.btn_bo.clicked.connect(self.action_blackout)
        right.addWidget(self.btn_bo)

        main_layout.addWidget(panel_r)

    # ==========================
    # LOGICA DI CONNESSIONE
    # ==========================
    def connect_serial(self):
        port = self.dmx_combo.currentText()
        if not port: return
        if self.dmx.connect_serial(port):
            QMessageBox.information(self, "OK", f"Connesso via USB a {port}")
            self.setWindowTitle("MIDI-DMX Pro [MODE: USB SERIAL]")

    def connect_artnet(self):
        ip = self.art_ip.text()
        uni = self.art_uni.text()
        if self.dmx.connect_artnet(ip, uni):
            QMessageBox.information(self, "OK", f"Art-Net Attivo\nTarget: {ip} | Uni: {uni}")
            self.setWindowTitle("MIDI-DMX Pro [MODE: ART-NET]")

    def connect_midi(self):
        port_name = self.midi_combo.currentText()
        if not port_name: return
        error_msg = self.midi.open_port(port_name)
        if error_msg is None:
            self.lbl_midi_monitor.setText(f"OK: {port_name[:15]}...")
            self.lbl_midi_monitor.setStyleSheet("color: #2ecc71; border: 1px solid #2ecc71; font-weight: bold;")
            QMessageBox.information(self, "MIDI Connesso", f"Dispositivo collegato:\n{port_name}")
        else:
            self.lbl_midi_monitor.setText("ERROR")
            self.lbl_midi_monitor.setStyleSheet("color: #e74c3c; border: 1px solid #e74c3c; font-weight: bold;")
            QMessageBox.critical(self, "Errore MIDI", f"Errore: {error_msg}")

    # ==========================
    # LOGICA FX WIZARD
    # ==========================
    def open_fx_wizard(self):
        selected_fixtures = [i.text() for i in self.f_list.selectedItems()]
        if not selected_fixtures:
            QMessageBox.warning(self, "Attenzione", "Seleziona prima le Fixture dalla lista su cui applicare l'effetto!")
            return
        
        dlg = FXGeneratorDialog(len(selected_fixtures), self)
        if dlg.exec():
            # Raccolta parametri
            fx_type = dlg.combo_fx.currentText()
            num_steps = dlg.spin_steps.value()
            hold_time = dlg.spin_hold.value()
            spread = dlg.slider_spread.value()
            chase_name = dlg.name_input.text()
            
            # Generazione Step
            new_steps = self.generate_fx_steps(selected_fixtures, fx_type, num_steps, spread)
            
            if new_steps:
                # 1. Salva ogni step come "Scena Nascosta" (prefisso __fx_)
                step_names = []
                import time
                timestamp = int(time.time())
                
                for i, step_data in enumerate(new_steps):
                    s_name = f"__fx_{chase_name}_{timestamp}_{i+1}"
                    self.data_store["scenes"][s_name] = step_data
                    step_names.append(s_name)
                
                # 2. Crea la Chase
                self.data_store["chases"][chase_name] = {
                    "steps": step_names,
                    "h": hold_time,
                    "f": int(hold_time * 0.8) # Fade default un po' meno dell'hold per fluidità
                }
                
                self.ch_list.addItem(chase_name)
                self.save_data()
                QMessageBox.information(self, "Successo", f"Chase '{chase_name}' creata con {num_steps} step!")

    def generate_fx_steps(self, fixtures, fx_type, steps, spread):
        generated_frames = []
        
        fix_objects = [] 
        for f_name in fixtures:
            fdata = self.data_store["fixtures"].get(f_name)
            if fdata:
                if isinstance(fdata, int): fdata = {"addr": fdata, "profile": ["Red", "Green", "Blue"]}
                fix_objects.append(fdata)
        
        num_fix = len(fix_objects)
        if num_fix == 0: return []

        for step_idx in range(steps):
            frame = {}
            t_step = step_idx / steps 
            
            for fix_idx, fix in enumerate(fix_objects):
                addr = fix["addr"]
                profile = fix["profile"]
                
                phase = 0
                if num_fix > 1:
                    phase = (fix_idx / (num_fix - 1)) * (spread / 100.0)
                
                wave = (math.sin(2 * math.pi * (t_step - phase)) + 1) / 2
                
                if "Rainbow" in fx_type:
                    hue = (t_step + phase) % 1.0
                    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    r, g, b = int(r*255), int(g*255), int(b*255)
                    
                    for i, p_type in enumerate(profile):
                        if p_type == "Red": frame[str(addr+i)] = r
                        elif p_type == "Green": frame[str(addr+i)] = g
                        elif p_type == "Blue": frame[str(addr+i)] = b
                        elif p_type == "Dimmer": frame[str(addr+i)] = 255

                elif "Sine Wave" in fx_type:
                    val = int(wave * 255)
                    for i, p_type in enumerate(profile):
                        if p_type == "Dimmer": frame[str(addr+i)] = val
                        elif p_type in ["Red", "Green", "Blue", "White"]: frame[str(addr+i)] = val

                elif "Dimmer Chase" in fx_type:
                    val = 255 if wave > 0.5 else 0
                    for i, p_type in enumerate(profile):
                        if p_type == "Dimmer": frame[str(addr+i)] = val
                        elif p_type in ["Red", "Green", "Blue"]: frame[str(addr+i)] = val

                elif "Police" in fx_type:
                    is_red = wave > 0.5
                    for i, p_type in enumerate(profile):
                        if p_type == "Red": frame[str(addr+i)] = 255 if is_red else 0
                        elif p_type == "Blue": frame[str(addr+i)] = 0 if is_red else 255
                        elif p_type == "Green": frame[str(addr+i)] = 0
                        elif p_type == "Dimmer": frame[str(addr+i)] = 255

                elif "Knight Rider" in fx_type:
                    ping_pong = 1 - abs((t_step * 2) % 2 - 1) 
                    target_pos = ping_pong * (num_fix - 1)
                    dist = abs(target_pos - fix_idx)
                    val = max(0, 255 - int(dist * 150)) 
                    
                    for i, p_type in enumerate(profile):
                        if p_type == "Red": frame[str(addr+i)] = val 
                        elif p_type in ["Green", "Blue"]: frame[str(addr+i)] = 0
                        elif p_type == "Dimmer": frame[str(addr+i)] = 255

            generated_frames.append(frame)
            
        return generated_frames

    # ==========================
    # LOGICA FIXTURE E SELEZIONE
    # ==========================
    def create_fixture_action(self):
        dlg = FixtureCreatorDialog(self)
        if dlg.exec():
            name = dlg.name_input.text()
            addr = dlg.addr_spin.value()
            profile = dlg.get_profile()
            
            if name and profile:
                self.data_store["fixtures"][name] = {
                    "addr": addr,
                    "profile": profile
                }
                self.f_list.addItem(name)
                self.save_data()
                QMessageBox.information(self, "OK", f"Fixture '{name}' creata.")

    def on_fixture_selection_change(self):
        if self.current_active_group:
            self.current_active_group = None
            self.g_list.clearSelection()

        self.selected_ch = set()
        selected_items = self.f_list.selectedItems()
        has_any_color = False

        for item in selected_items:
            name = item.text()
            fix_data = self.data_store["fixtures"].get(name)
            if not fix_data: continue
            
            if isinstance(fix_data, int):
                start = fix_data; profile = ["Red", "Green", "Blue"]
            else:
                start = fix_data["addr"]; profile = fix_data["profile"]
            
            for i, p in enumerate(profile):
                self.selected_ch.add(start + i)
                if p in ["Red", "Green", "Blue", "Dimmer"]:
                    has_any_color = True
        
        self.btn_color_pick.setEnabled(has_any_color and len(selected_items) > 0)
        
        for cell in self.cells:
            is_sel = cell.ch in self.selected_ch
            cell.update_view(self.dmx.output_frame[cell.ch], is_sel, False, force=True)

    def select_fixture(self, item):
        # Questo metodo viene chiamato al click singolo, ma la logica vera è in itemSelectionChanged
        pass 

    def open_live_color_picker(self):
        if not self.f_list.selectedItems(): return
        color_dlg = QColorDialog(self)
        color_dlg.setOption(QColorDialog.ColorDialogOption.NoButtons)
        color_dlg.currentColorChanged.connect(self.apply_live_color)
        color_dlg.exec()

    def apply_live_color(self, color):
        selected_items = self.f_list.selectedItems()
        if not selected_items: return
        
        r, g, b = color.red(), color.green(), color.blue()
        
        for item in selected_items:
            name = item.text()
            fix_data = self.data_store["fixtures"].get(name)
            if not fix_data: continue
            
            if isinstance(fix_data, int):
                start = fix_data; profile = ["Red", "Green", "Blue"]
            else:
                start = fix_data["addr"]; profile = fix_data["profile"]
            
            for i, ch_type in enumerate(profile):
                val = -1
                if ch_type == "Red": val = r
                elif ch_type == "Green": val = g
                elif ch_type == "Blue": val = b
                elif ch_type == "Dimmer": val = 255
                elif ch_type == "White": val = 0
                
                if val >= 0:
                    ch_idx = start + i
                    if ch_idx <= 512:
                        self.dmx.live_buffer[ch_idx] = val
                        self.cells[ch_idx-1].update_view(val, True, False, force=True)

    # ==========================
    # LOGICA SCENE, GRUPPI E CUE
    # ==========================
    def save_scene_action(self):
        snap = {str(i): self.dmx.output_frame[i] for i in range(1, 513) if self.dmx.output_frame[i] > 0}
        name, ok = QInputDialog.getText(self, "Salva", "Nome Scena:")
        if ok and name:
            self.data_store["scenes"][name] = snap
            if not self.s_list.findItems(name, Qt.MatchFlag.MatchExactly): self.s_list.addItem(name)
            self.save_data()

    def create_chase_action(self):
        if not self.data_store["scenes"]: 
            QMessageBox.warning(self, "Attenzione", "Crea prima delle scene!"); return
        dlg = ChaseCreatorDialog(self.data_store["scenes"], self)
        if dlg.exec():
            steps = [i.text() for i in dlg.list.selectedItems()]
            if steps:
                name, ok = QInputDialog.getText(self, "Nuovo Chase", "Nome Sequenza:")
                if ok and name:
                    self.data_store["chases"][name] = {"steps": steps, "h": int(dlg.t_hold.text()), "f": int(dlg.t_fade.text())}
                    self.ch_list.addItem(name); self.save_data()

    def create_group_action(self):
        if not self.selected_ch: 
            QMessageBox.warning(self, "Info", "Seleziona almeno un canale per creare un gruppo.")
            return
        name, ok = QInputDialog.getText(self, "Nuovo Gruppo", "Nome Gruppo:")
        if ok and name:
            self.data_store["groups"][name] = list(self.selected_ch)
            self.g_list.addItem(name)
            self.save_data()

    def select_group(self, name):
        # Quando selezioni un gruppo, pulisci la selezione fixture
        self.f_list.clearSelection()
        
        if self.current_active_group == name:
            self.selected_ch.clear(); self.current_active_group = None; self.g_list.clearSelection()
        else:
            channels = self.data_store["groups"].get(name, [])
            self.selected_ch = set(channels)
            self.current_active_group = name
        
        for cell in self.cells:
            is_sel = cell.ch in self.selected_ch
            cell.update_view(self.dmx.output_frame[cell.ch], is_sel, False, force=True)

    def toggle_cell(self, ch):
        # Reset selezioni liste se si interagisce con la griglia
        if self.current_active_group: 
            self.current_active_group = None; self.g_list.clearSelection()
        if self.f_list.selectedItems():
            self.f_list.clearSelection(); self.btn_color_pick.setEnabled(False)

        if ch in self.selected_ch: self.selected_ch.remove(ch)
        else: self.selected_ch.add(ch)
        self.cells[ch-1].update_view(self.dmx.output_frame[ch], ch in self.selected_ch, False, force=True)

    def toggle_rec(self):
        if self.playback.is_recording_cue:
            self.playback.is_recording_cue = False
            self.btn_rec.setText("● REGISTRA CUE")
            self.btn_rec.setStyleSheet("color: #e74c3c; background-color: #222; font-weight: bold;")
            name, ok = QInputDialog.getText(self, "Salva", "Nome Cue:")
            if ok and name:
                self.data_store["cues"][name] = {"data": self.playback.recorded_stream}
                self.cue_list.addItem(name); self.save_data()
        else:
            self.playback.recorded_stream = []
            self.playback.is_recording_cue = True
            self.btn_rec.setText("STOP REC")
            self.btn_rec.setStyleSheet("background-color: #c0392b; color: #fff; font-weight: bold;")

    # ==========================
    # SHOW MANAGER & PLAYBACK
    # ==========================
    def add_to_show(self, type_key, name):
        duration = 0
        if type_key == "cue":
            cue_data = self.data_store["cues"].get(name, {}).get("data", [])
            duration = len(cue_data) * 40
            obj = {"type": type_key, "name": name, "duration": duration}
            self.data_store["show"].append(obj)
            self.refresh_show_list_widget(); self.save_data()
            QMessageBox.information(self, "Cue Aggiunta", f"Cue aggiunta con durata fissa: {duration/1000}s")
        else:
            duration, ok = QInputDialog.getInt(self, "Durata Step", f"Inserisci durata in ms per '{name}':\n(0 = Manuale)", value=0, min=0, max=3600000)
            if ok:
                obj = {"type": type_key, "name": name, "duration": duration}
                self.data_store["show"].append(obj)
                self.refresh_show_list_widget(); self.save_data()

    def play_show_item(self, item):
        self.show_step_timer.stop()
        row_idx = self.show_list_widget.row(item)
        entry = self.data_store["show"][row_idx]
        if isinstance(entry, str): return 

        t_type = entry.get("type")
        name = entry.get("name")
        duration = entry.get("duration", 0)
        
        if t_type == "sc": self.playback.toggle_scene(name)
        elif t_type == "ch": self.playback.toggle_chase(name)
        elif t_type == "cue": self.playback.toggle_cue(name)
        
        self._update_list_visual_selection()
        if duration > 0:
            self.btn_go.setText(f"AUTO NEXT ({duration/1000}s) ▶")
            self.show_step_timer.start(duration)
        else:
            self.btn_go.setText("GO / NEXT ▶")

    def go_next_step(self):
        if not self.data_store["show"]: return
        curr_row = self.show_list_widget.currentRow()
        next_row = (curr_row + 1) % len(self.data_store["show"])
        self.show_list_widget.setCurrentRow(next_row)
        self.play_show_item(self.show_list_widget.item(next_row))

    def refresh_show_list_widget(self):
        self.show_list_widget.clear()
        for i, entry in enumerate(self.data_store["show"]):
            if isinstance(entry, str):
                try: t, n = entry.split(":", 1); entry = {"type": t, "name": n, "duration": 0}
                except: continue
            t_type = entry.get("type", "?").upper()
            name = entry.get("name", "Unknown")
            dur = entry.get("duration", 0)
            time_str = f"FIXED ({dur/1000}s)" if t_type == "CUE" else ("MANUAL" if dur == 0 else f"{dur/1000}s")
            self.show_list_widget.addItem(f"{i+1}. [{t_type}] {name}  -- ⏱ {time_str}")

    # ==========================
    # LOGICA DI SISTEMA E UPDATE
    # ==========================
    def action_blackout(self):
        self.show_step_timer.stop()
        self.btn_go.setText("GO / NEXT ▶")
        self.playback.stop_all()
        self.f_slider.blockSignals(True); self.f_slider.setValue(0); self.f_slider.blockSignals(False)
        self.f_input.setText("0"); self.f_label.setText("LIVE: 0 | 0%")
        self.show_list_widget.clearSelection(); self.show_list_widget.setCurrentRow(-1)

    def on_speed_change(self, val):
        self.data_store["globals"]["chase_speed"] = val
        pct = int((val / 127) * 100)
        self.lbl_speed.setText(f"HOLD TIME %: {pct}%")

    def on_fade_change(self, val):
        self.data_store["globals"]["chase_fade"] = val
        pct = int((val / 127) * 100)
        self.lbl_fade.setText(f"FADE TIME %: {pct}%")

    def update_ui_from_engine(self):
        self.sl_speed.blockSignals(True)
        self.sl_speed.setValue(self.data_store["globals"]["chase_speed"])
        self.on_speed_change(self.data_store["globals"]["chase_speed"])
        self.sl_speed.blockSignals(False)
        
        self.sl_fade.blockSignals(True)
        self.sl_fade.setValue(self.data_store["globals"]["chase_fade"])
        self.on_fade_change(self.data_store["globals"]["chase_fade"])
        self.sl_fade.blockSignals(False)

    def update_ui_frame(self):
        mapped_ids = {ch for ids in self.data_store["map"].values() for ch in ids}
        mapped_remote_names = []
        for val in self.data_store["rem"].values():
            if isinstance(val, list):
                for item in val:
                     if ":" in item: mapped_remote_names.append(item.split(":", 1)[1])
            elif ":" in val: mapped_remote_names.append(val.split(":", 1)[1])

        for i, cell in enumerate(self.cells):
            ch_num = i + 1; val = self.dmx.output_frame[ch_num]
            cell.update_view(val, ch_num in self.selected_ch, ch_num in mapped_ids)

        for lst in [self.s_list, self.ch_list, self.cue_list, self.g_list, self.f_list]:
            for row in range(lst.count()):
                item = lst.item(row)
                target_color = QColor("#e67e22") if item.text() in mapped_remote_names else QColor("#ddd")
                if item.foreground().color() != target_color: item.setForeground(target_color)

    def fader_moved(self, val):
        self.f_label.setText(f"LIVE: {val} | {int(val/2.55)}%")
        if not self.f_input.hasFocus(): self.f_input.setText(str(val))
        if self.selected_ch:
            for ch in self.selected_ch:
                self.dmx.live_buffer[ch] = val
                self.cells[ch-1].update_view(val, True, False, force=True)

    def manual_fader_input(self):
        try:
            val = int(self.f_input.text() or 0)
            if 0 <= val <= 255: self.f_slider.setValue(val)
        except ValueError: pass

    # ==========================
    # CONTEXT MENUS E HELPERS
    # ==========================
    def show_slider_context(self, pos, target_key):
        menu = QMenu()
        act_learn = menu.addAction("Mappa a Controller MIDI")
        target_str = f"global:{target_key}"
        mapped_key = None
        for k, v in self.data_store["rem"].items():
            if isinstance(v, list):
                if target_str in v: mapped_key = k; break
            elif v == target_str: mapped_key = k; break
        
        if mapped_key: act_unmap = menu.addAction(f"❌ Rimuovi MIDI ({mapped_key})")
        
        res = menu.exec(self.sender().mapToGlobal(pos))
        if res == act_learn: self.midi.toggle_learn(target_str)
        elif mapped_key and res == act_unmap:
            val = self.data_store["rem"][mapped_key]
            if isinstance(val, list):
                if target_str in val: val.remove(target_str)
                if not val: del self.data_store["rem"][mapped_key]
            else: del self.data_store["rem"][mapped_key]
            self.save_data(); QMessageBox.information(self, "Info", "Mapping rimosso")

    def show_context_menu(self, widget, pos, type_key):
        item = widget.itemAt(pos)
        if not item: return
        menu = QMenu()
        act_learn = menu.addAction("Mappa a Pulsante MIDI")
        
        target_str = f"{type_key}:{item.text()}"
        mapped_key = None
        for k, v in self.data_store["rem"].items():
            if isinstance(v, list):
                if target_str in v: mapped_key = k; break
            elif v == target_str: mapped_key = k; break
        
        if mapped_key: act_unmap = menu.addAction(f"❌ Rimuovi Trigger MIDI ({mapped_key})")
        
        menu.addSeparator()
        if type_key not in ["grp", "fix"]: act_show = menu.addAction("Aggiungi a Show Manager")
        act_del = menu.addAction("Elimina Elemento")
        
        res = menu.exec(widget.mapToGlobal(pos))
        if res == act_learn: self.midi.toggle_learn(target_str)
        elif mapped_key and res == act_unmap:
            val = self.data_store["rem"][mapped_key]
            if isinstance(val, list):
                if target_str in val: val.remove(target_str)
                if not val: del self.data_store["rem"][mapped_key]
            else: del self.data_store["rem"][mapped_key]
            self.save_data(); QMessageBox.information(self, "Info", "Trigger MIDI Rimosso")
        elif type_key not in ["grp", "fix"] and res == act_show: self.add_to_show(type_key, item.text())
        elif res == act_del: 
            widget.takeItem(widget.row(item))
            key_map = {"sc": "scenes", "ch": "chases", "cue": "cues", "grp": "groups", "fix": "fixtures"}
            self.data_store[key_map[type_key]].pop(item.text(), None)
            self.save_data()

    def show_manager_context_menu(self, pos):
        item = self.show_list_widget.itemAt(pos)
        if not item: return
        row = self.show_list_widget.row(item)
        entry = self.data_store["show"][row]
        if isinstance(entry, str):
            t, n = entry.split(":", 1); entry = {"type": t, "name": n, "duration": 0}
            self.data_store["show"][row] = entry

        menu = QMenu()
        act_time = menu.addAction("Modifica Durata Step")
        act_del = menu.addAction("Rimuovi da Show")
        res = menu.exec(self.show_list_widget.mapToGlobal(pos))
        if res == act_del: self.data_store["show"].pop(row); self.refresh_show_list_widget(); self.save_data()
        elif res == act_time:
            if entry["type"] == "cue": QMessageBox.warning(self, "Block", "Durata Cue fissa.")
            else:
                curr_dur = entry.get("duration", 0)
                new_dur, ok = QInputDialog.getInt(self, "Modifica", "Nuova durata ms:", value=curr_dur, min=0, max=3600000)
                if ok: entry["duration"] = new_dur; self.data_store["show"][row] = entry; self.refresh_show_list_widget(); self.save_data()

    def cell_context_menu(self, ch):
        menu = QMenu(self)
        menu.addAction(QAction(f"CANALE {ch}", self)).setEnabled(False); menu.addSeparator()

        mapped_keys = []
        for key, channels in self.data_store["map"].items():
            if ch in channels: mapped_keys.append(key)
        
        if mapped_keys:
            menu.addAction(QAction("Mappato su:", self)).setEnabled(False)
            for k in mapped_keys:
                act = menu.addAction(f"❌ Rimuovi MIDI: {k}")
                act.triggered.connect(lambda _, k=k: self._remove_midi_mapping(k, ch))
        else: menu.addAction("Nessun MIDI assegnato").setEnabled(False)
        
        menu.addSeparator()
        if len(self.selected_ch) > 1 and ch in self.selected_ch:
             menu.addAction(f"Crea Gruppo da {len(self.selected_ch)} ch").triggered.connect(self.create_group_action)
        
        menu.exec(self.cells[ch-1].mapToGlobal(self.cells[ch-1].rect().center()))

    def _remove_midi_mapping(self, midi_key, ch_to_remove):
        if midi_key in self.data_store["map"]:
            if ch_to_remove in self.data_store["map"][midi_key]:
                self.data_store["map"][midi_key].remove(ch_to_remove)
                if not self.data_store["map"][midi_key]: del self.data_store["map"][midi_key]
                self.save_data(); QMessageBox.information(self, "Info", "Rimosso")

    def reset_all_midi_channels(self):
        reply = QMessageBox.question(self, "Conferma Eliminazione", 
                                     "Vuoi davvero CANCELLARE TUTTE le mappature MIDI dei canali?\n\nI quadrati sulla griglia perderanno il controllo MIDI.\nQuesta operazione non può essere annullata.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.data_store["map"].clear()
            self.save_data()
            QMessageBox.information(self, "Reset Completato", "Tutte le mappature MIDI dei canali sono state rimosse.")

    def on_learn_status_change(self, is_learning, target):
        if is_learning:
            self.btn_learn.setText("WAITING MIDI...")
            self.btn_learn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        else:
            self.btn_learn.setText("LEARN MIDI CHANNELS")
            self.btn_learn.setStyleSheet("background-color: #2c3e50; color: #ccc;")
            self.save_data()
    
    def update_midi_label(self, text):
        self.lbl_midi_monitor.setText(text)
        self.lbl_midi_monitor.setStyleSheet("color: #2ecc71; font-size: 11px; border: 1px solid #2ecc71; padding: 2px;")

    def _update_list_visual_selection(self):
        for i in range(self.s_list.count()): self.s_list.item(i).setSelected(self.s_list.item(i).text() == self.playback.active_sc)
        for i in range(self.ch_list.count()): self.ch_list.item(i).setSelected(self.ch_list.item(i).text() == self.playback.active_ch)
        for i in range(self.cue_list.count()): self.cue_list.item(i).setSelected(self.cue_list.item(i).text() == self.playback.active_cue)

    def save_data(self): data_manager.save_studio_data(self.data_store)
    def load_data(self):
        d = data_manager.load_studio_data()
        if d:
            self.data_store.update(d)
            if "globals" not in self.data_store: self.data_store["globals"] = {"chase_speed": 127, "chase_fade": 127}
            if "fixtures" not in self.data_store: self.data_store["fixtures"] = {}
            
            self.s_list.clear(); self.ch_list.clear(); self.cue_list.clear(); self.g_list.clear(); self.f_list.clear()
            self.s_list.addItems(self.data_store.get("scenes", {}).keys())
            self.ch_list.addItems(self.data_store.get("chases", {}).keys())
            self.cue_list.addItems(self.data_store.get("cues", {}).keys())
            self.g_list.addItems(self.data_store.get("groups", {}).keys())
            self.f_list.addItems(self.data_store.get("fixtures", {}).keys())
            self.refresh_show_list_widget()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())