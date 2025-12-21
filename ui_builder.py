from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QComboBox, 
    QPushButton, QLineEdit, QListWidget, QSlider, QGridLayout, QScrollArea,
    QAbstractItemView, QCheckBox, QProgressBar, QGroupBox, QFrame, QTableWidget,
    QHeaderView, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, QSize
import serial.tools.list_ports
import mido
from gui_components import DMXCell, GRID_COLUMNS

class UIBuilder:
    def setup_ui(self, mw):
        mw.setWindowTitle("MIDI-DMX Pro v.31 - No Overlap")
        mw.resize(1450, 950) 
        
        # STILE GRAFICO
        mw.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            QLabel { color: #b0b0b0; font-family: 'Segoe UI', sans-serif; font-size: 12px; margin: 0; }
            
            QListWidget { 
                background-color: #1e1e1e; border: 1px solid #333; color: #e0e0e0; 
                border-radius: 4px; padding: 2px;
            }
            QListWidget::item:selected { background-color: #2980b9; color: white; border: none; }
            
            QLineEdit, QComboBox { 
                background-color: #252525; color: #ddd; border: 1px solid #444; 
                padding: 4px; border-radius: 4px; min-height: 22px; font-size: 12px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            
            QPushButton { 
                background-color: #333; color: #ddd; border: 1px solid #555; 
                padding: 6px; border-radius: 4px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #444; border-color: #3498db; }
            QPushButton:pressed { background-color: #3498db; color: white; }
            QPushButton:checked { background-color: #e67e22; color: white; border-color: #d35400; }
            
            QSlider::groove:horizontal { border: 1px solid #333; height: 4px; background: #1a1a1a; margin: 0; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3498db; border: 1px solid #3498db; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            
            QTabWidget::pane { border: 1px solid #333; background-color: #1a1a1a; }
            QTabBar::tab { background: #222; color: #888; padding: 8px 15px; margin-right: 2px; }
            QTabBar::tab:selected { background: #333; color: white; border-top: 2px solid #e67e22; }
            
            QGroupBox { border: 1px solid #444; margin-top: 15px; padding-top: 15px; font-weight: bold; color: #888; }
            QProgressBar { border: 1px solid #333; background-color: #111; text-align: center; border-radius: 2px; }
            
            /* Scrollbar Ben Definita per non confondersi */
            QScrollBar:vertical { border-left: 1px solid #333; background: #1a1a1a; width: 16px; margin: 0px; }
            QScrollBar::handle:vertical { background: #555; min-height: 20px; border-radius: 4px; margin: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        mw.setCentralWidget(central)
        
        self._build_left_panel(mw, layout)
        self._build_center_panel(mw, layout)
        self._build_right_panel(mw, layout)

    def _build_left_panel(self, mw, parent_layout):
        # 1. ALLARGATO A 480px per evitare troncamenti
        left_container = QWidget(); left_container.setFixedWidth(480)
        left_layout = QVBoxLayout(left_container); left_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Forza la barra verticale sempre visibile così lo spazio è calcolato in anticipo
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        content = QWidget()
        content.setMinimumHeight(900) 
        l_content = QVBoxLayout(content)
        l_content.setSpacing(10)
        # 2. MARGINE DESTRO DI 25px: Riserva spazio per la scrollbar così non copre nulla
        l_content.setContentsMargins(5, 5, 25, 5)
        
        mw.main_tabs = QTabWidget()
        
        # --- TAB 1: AUDIO FX ---
        t_aud = QWidget(); l_aud = QVBoxLayout(t_aud); l_aud.setSpacing(10); l_aud.setContentsMargins(5, 10, 5, 10)
        
        # MONITOR
        gb_mon = QGroupBox("MONITOR")
        l_mon = QVBoxLayout(gb_mon); l_mon.setSpacing(5)
        h_in = QHBoxLayout()
        mw.audio_combo = QComboBox(); mw.audio_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        mw.btn_audio_start = QPushButton("ON/OFF"); mw.btn_audio_start.setCheckable(True); mw.btn_audio_start.setFixedWidth(60)
        mw.btn_audio_start.clicked.connect(mw.toggle_audio_engine)
        h_in.addWidget(mw.audio_combo); h_in.addWidget(mw.btn_audio_start)
        l_mon.addLayout(h_in)
        
        vis_grid = QGridLayout(); vis_grid.setVerticalSpacing(4)
        mw.pb_bass = QProgressBar(); mw.pb_bass.setFixedHeight(4); mw.pb_bass.setRange(0, 255); mw.pb_bass.setTextVisible(False); mw.pb_bass.setStyleSheet("QProgressBar::chunk{background:#e74c3c}")
        mw.pb_mid = QProgressBar(); mw.pb_mid.setFixedHeight(4); mw.pb_mid.setRange(0, 255); mw.pb_mid.setTextVisible(False); mw.pb_mid.setStyleSheet("QProgressBar::chunk{background:#f1c40f}")
        mw.pb_high = QProgressBar(); mw.pb_high.setFixedHeight(4); mw.pb_high.setRange(0, 255); mw.pb_high.setTextVisible(False); mw.pb_high.setStyleSheet("QProgressBar::chunk{background:#3498db}")
        mw.prog_vol = QProgressBar(); mw.prog_vol.setFixedHeight(4); mw.prog_vol.setRange(0, 255); mw.prog_vol.setTextVisible(False); mw.prog_vol.setStyleSheet("QProgressBar::chunk{background:#fff}")
        vis_grid.addWidget(QLabel("LO"),0,0); vis_grid.addWidget(mw.pb_bass,0,1)
        vis_grid.addWidget(QLabel("MID"),1,0); vis_grid.addWidget(mw.pb_mid,1,1)
        vis_grid.addWidget(QLabel("HI"),2,0); vis_grid.addWidget(mw.pb_high,2,1)
        vis_grid.addWidget(QLabel("VOL"),3,0); vis_grid.addWidget(mw.prog_vol,3,1)
        l_mon.addLayout(vis_grid)
        
        h_gn = QHBoxLayout()
        mw.sl_gain = QSlider(Qt.Orientation.Horizontal); mw.sl_gain.setRange(1, 100); mw.sl_gain.setValue(20)
        mw.sl_gain.valueChanged.connect(mw.on_gain_change)
        h_gn.addWidget(QLabel("Gain:")); h_gn.addWidget(mw.sl_gain)
        l_mon.addLayout(h_gn)
        l_aud.addWidget(gb_mon)
        
        # GENERATORE
        gb_gen = QGroupBox("GENERATORE SMART")
        l_gen = QVBoxLayout(gb_gen); l_gen.setSpacing(8)
        
        l_gen.addWidget(QLabel("Lista Effetti:"))
        mw.list_active_fx = QListWidget(); mw.list_active_fx.setFixedHeight(70)
        l_gen.addWidget(mw.list_active_fx)
        
        # INSPECTOR
        insp_frame = QFrame()
        insp_frame.setMinimumHeight(130) 
        insp_frame.setStyleSheet("background-color: #1a1a1a; border: 1px solid #444; border-radius: 4px;")
        l_insp = QVBoxLayout(insp_frame); l_insp.setSpacing(8); l_insp.setContentsMargins(10, 8, 10, 8)
        
        l_insp.addWidget(QLabel("<b>IMPOSTAZIONI EFFETTO</b>"))
        
        h_r1 = QHBoxLayout()
        h_r1.addWidget(QLabel("Input:"))
        mw.pb_fx_signal = QProgressBar(); mw.pb_fx_signal.setRange(0, 255); mw.pb_fx_signal.setFixedHeight(8); mw.pb_fx_signal.setTextVisible(False)
        mw.pb_fx_signal.setStyleSheet("QProgressBar::chunk{background:#2ecc71}") 
        h_r1.addWidget(mw.pb_fx_signal)
        l_insp.addLayout(h_r1)
        
        h_r2 = QHBoxLayout()
        h_r2.addWidget(QLabel("Soglia:"))
        mw.sl_fx_threshold = QSlider(Qt.Orientation.Horizontal); mw.sl_fx_threshold.setRange(0, 255); mw.sl_fx_threshold.setValue(50)
        mw.sl_fx_threshold.setStyleSheet("QSlider::handle:horizontal { background: #f1c40f; width: 14px; margin: -5px 0; border-radius: 7px; }")
        h_r2.addWidget(mw.sl_fx_threshold)
        l_insp.addLayout(h_r2)
        
        btn_rem = QPushButton("RIMUOVI"); btn_rem.setFixedHeight(25)
        btn_rem.setStyleSheet("background-color: #c0392b; color: white; padding: 2px;")
        btn_rem.clicked.connect(mw.remove_gen_effect)
        l_insp.addWidget(btn_rem)
        
        l_gen.addWidget(insp_frame)
        
        l_gen.addWidget(QLabel("Nuovo Effetto:"))
        mw.combo_fx_type = QComboBox()
        mw.combo_fx_type.addItems(["Bass Wave (Viola/Rosso)", "Spectral EQ (Posizionale L-R)", "Snare Explosion (Flash)", "Smart Solo (Spotlight)", "Clean Bass (Pulse)", "Sidechain Pad (Atmosphere)"])
        l_gen.addWidget(mw.combo_fx_type)
        
        l_gen.addWidget(QLabel("Fixtures:"))
        mw.list_fx_fixtures = QListWidget(); mw.list_fx_fixtures.setFixedHeight(80)
        mw.list_fx_fixtures.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        l_gen.addWidget(mw.list_fx_fixtures)
        
        btn_add = QPushButton("AGGIUNGI"); btn_add.setFixedHeight(30)
        btn_add.setStyleSheet("background-color: #27ae60; color: white;")
        btn_add.clicked.connect(mw.add_gen_effect)
        l_gen.addWidget(btn_add)
        
        l_aud.addWidget(gb_gen)
        l_aud.addStretch()
        mw.main_tabs.addTab(t_aud, "AUDIO FX")

        # --- TAB 2: LIBRERIA ---
        t_lib = QWidget(); l_lib = QVBoxLayout(t_lib); l_lib.setSpacing(10); l_lib.setContentsMargins(5, 10, 5, 10)
        gb_live = QGroupBox("LIVE")
        l_lp = QVBoxLayout(gb_live); l_lp.setSpacing(5)
        mw.f_label = QLabel("DIMMER: 0%"); mw.f_label.setStyleSheet("color: #3498db; font-weight: bold;")
        l_lp.addWidget(mw.f_label)
        h_fad = QHBoxLayout()
        mw.f_slider = QSlider(Qt.Orientation.Horizontal); mw.f_slider.setRange(0, 255); mw.f_slider.valueChanged.connect(mw.fader_moved)
        mw.f_input = QLineEdit(); mw.f_input.setFixedWidth(40); mw.f_input.returnPressed.connect(mw.manual_fader_input)
        h_fad.addWidget(mw.f_slider); h_fad.addWidget(mw.f_input)
        l_lp.addLayout(h_fad)
        h_mid_b = QHBoxLayout()
        mw.btn_learn = QPushButton("MIDI"); mw.btn_learn.clicked.connect(lambda: mw.midi.toggle_learn("chans"))
        mw.btn_reset_map = QPushButton("RESET"); mw.btn_reset_map.setStyleSheet("color: #e74c3c; border-color: #555;")
        mw.btn_reset_map.clicked.connect(mw.reset_all_midi_channels)
        h_mid_b.addWidget(mw.btn_learn); h_mid_b.addWidget(mw.btn_reset_map)
        l_lp.addLayout(h_mid_b)
        l_lib.addWidget(gb_live)
        
        l_lib.addWidget(QLabel("SCENE"))
        h_sc = QHBoxLayout()
        btn_ss = QPushButton("SALVA"); btn_ss.clicked.connect(mw.save_scene_action)
        h_sc.addWidget(btn_ss)
        l_lib.addLayout(h_sc)
        mw.s_list = QListWidget(); mw.s_list.setFixedHeight(90)
        mw.s_list.itemClicked.connect(lambda i: mw.playback.toggle_scene(i.text()))
        mw.s_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.s_list, p, "sc"))
        mw.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        l_lib.addWidget(mw.s_list)
        
        l_lib.addWidget(QLabel("GRUPPI"))
        mw.g_list = QListWidget(); mw.g_list.setFixedHeight(90)
        mw.g_list.itemClicked.connect(lambda i: mw.select_group(i.text()))
        mw.g_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.g_list, p, "grp"))
        mw.g_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        l_lib.addWidget(mw.g_list)
        btn_grp = QPushButton("CREA GRUPPO"); btn_grp.clicked.connect(mw.create_group_action)
        l_lib.addWidget(btn_grp)
        
        l_lib.addWidget(QLabel("FIXTURES"))
        h_fx = QHBoxLayout()
        btn_nf = QPushButton("NUOVA"); btn_nf.clicked.connect(mw.create_fixture_action)
        mw.btn_color_pick = QPushButton("COLORE"); mw.btn_color_pick.setStyleSheet("background-color: #8e44ad; color: white;")
        mw.btn_color_pick.clicked.connect(mw.open_live_color_picker); mw.btn_color_pick.setEnabled(False)
        h_fx.addWidget(btn_nf); h_fx.addWidget(mw.btn_color_pick)
        l_lib.addLayout(h_fx)
        mw.f_list = QListWidget(); mw.f_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        mw.f_list.itemSelectionChanged.connect(mw.on_fixture_selection_change)
        mw.f_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.f_list, p, "fix"))
        mw.f_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        l_lib.addWidget(mw.f_list)
        mw.main_tabs.addTab(t_lib, "LIBRERIA")

        # --- TAB 3: MIDI ---
        t_mid = QWidget(); l_mid = QVBoxLayout(t_mid); l_mid.setContentsMargins(5, 10, 5, 10)
        l_mid.addWidget(QLabel("MIDI INPUT"))
        h_m = QHBoxLayout()
        mw.midi_combo = QComboBox()
        try: mw.midi_combo.addItems(mido.get_input_names())
        except: pass
        btn_mc = QPushButton("LINK"); btn_mc.clicked.connect(mw.connect_midi)
        h_m.addWidget(mw.midi_combo); h_m.addWidget(btn_mc)
        l_mid.addLayout(h_m)
        mw.lbl_midi_monitor = QLabel("DISCONNESSO"); mw.lbl_midi_monitor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mw.lbl_midi_monitor.setStyleSheet("border: 1px solid #333; padding: 10px; color: #666; font-size: 12px; background: #000;")
        l_mid.addWidget(mw.lbl_midi_monitor)
        l_mid.addStretch()
        mw.main_tabs.addTab(t_mid, "MIDI")

        # --- TAB 4: DMX ---
        t_dmx = QWidget(); l_dmx = QVBoxLayout(t_dmx); l_dmx.setSpacing(15); l_dmx.setContentsMargins(5, 10, 5, 10)
        gb_usb = QGroupBox("USB DMX")
        l_u = QVBoxLayout(gb_usb)
        h_u = QHBoxLayout()
        mw.dmx_combo = QComboBox()
        try: mw.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        except: pass
        btn_dc = QPushButton("LINK"); btn_dc.clicked.connect(mw.connect_serial)
        h_u.addWidget(mw.dmx_combo); h_u.addWidget(btn_dc)
        l_u.addLayout(h_u)
        l_dmx.addWidget(gb_usb)
        gb_art = QGroupBox("ART-NET")
        l_a = QVBoxLayout(gb_art)
        h_a = QHBoxLayout()
        mw.art_ip = QLineEdit("127.0.0.1"); mw.art_uni = QLineEdit("0"); mw.art_uni.setFixedWidth(40)
        btn_ac = QPushButton("ON"); btn_ac.clicked.connect(mw.connect_artnet)
        h_a.addWidget(QLabel("IP:")); h_a.addWidget(mw.art_ip); h_a.addWidget(QLabel("U:")); h_a.addWidget(mw.art_uni)
        l_a.addLayout(h_a); l_a.addWidget(btn_ac)
        l_dmx.addWidget(gb_art)
        l_dmx.addStretch()
        mw.main_tabs.addTab(t_dmx, "DMX")

        l_content.addWidget(mw.main_tabs)
        scroll.setWidget(content)
        left_layout.addWidget(scroll)
        parent_layout.addWidget(left_container)

    def _build_center_panel(self, mw, parent_layout):
        mw.cells = []
        grid_w = QWidget(); grid_w.setStyleSheet("background-color: #050505;")
        grid = QGridLayout(grid_w); grid.setSpacing(2); grid.setContentsMargins(2, 2, 2, 2)
        for i in range(512):
            c = DMXCell(i + 1); c.clicked.connect(mw.toggle_cell); c.right_clicked.connect(mw.cell_context_menu)
            grid.addWidget(c, i // GRID_COLUMNS, i % GRID_COLUMNS); mw.cells.append(c)
        scroll = QScrollArea(); scroll.setWidget(grid_w); scroll.setWidgetResizable(True); scroll.setStyleSheet("border: none;")
        parent_layout.addWidget(scroll, 1)

    def _build_right_panel(self, mw, parent_layout):
        panel = QWidget(); panel.setFixedWidth(280); panel.setStyleSheet("background-color: #151515; border-left: 1px solid #333;")
        right = QVBoxLayout(panel); right.setContentsMargins(5, 5, 5, 5); right.setSpacing(10)
        right.addWidget(QLabel("<b>CHASE PLAYBACK</b>"))
        mw.ch_list = QListWidget(); mw.ch_list.setFixedHeight(150)
        mw.ch_list.itemClicked.connect(lambda i: mw.playback.toggle_chase(i.text()))
        mw.ch_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.ch_list, p, "ch"))
        mw.ch_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        right.addWidget(mw.ch_list)
        h_ch = QHBoxLayout()
        b_new_ch = QPushButton("NUOVA"); b_new_ch.clicked.connect(mw.create_chase_action)
        b_wiz = QPushButton("WIZARD"); b_wiz.clicked.connect(mw.open_fx_wizard); b_wiz.setStyleSheet("background:#3498db; color:white;")
        h_ch.addWidget(b_new_ch); h_ch.addWidget(b_wiz)
        right.addLayout(h_ch)
        mw.lbl_speed = QLabel("SPEED: 100%"); right.addWidget(mw.lbl_speed)
        mw.sl_speed = QSlider(Qt.Orientation.Horizontal); mw.sl_speed.setRange(0, 255); mw.sl_speed.setValue(127)
        mw.sl_speed.valueChanged.connect(mw.on_speed_change)
        right.addWidget(mw.sl_speed)
        right.addWidget(QLabel("<b>CUES</b>"))
        mw.btn_rec = QPushButton("● REC CUE"); mw.btn_rec.clicked.connect(mw.toggle_rec); mw.btn_rec.setStyleSheet("color: #e74c3c;")
        right.addWidget(mw.btn_rec)
        mw.cue_list = QListWidget(); mw.cue_list.setFixedHeight(120)
        mw.cue_list.itemClicked.connect(lambda i: mw.playback.toggle_cue(i.text()))
        mw.cue_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.cue_list, p, "cue"))
        mw.cue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        right.addWidget(mw.cue_list)
        right.addStretch()
        mw.btn_bo = QPushButton("BLACKOUT"); mw.btn_bo.setFixedHeight(40)
        mw.btn_bo.setStyleSheet("background-color: #c0392b; font-size: 14px; border: 2px solid #e74c3c;")
        mw.btn_bo.clicked.connect(mw.action_blackout)
        right.addWidget(mw.btn_bo)
        parent_layout.addWidget(panel)