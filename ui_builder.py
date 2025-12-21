from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QComboBox, 
    QPushButton, QLineEdit, QListWidget, QSlider, QGridLayout, QScrollArea,
    QAbstractItemView, QCheckBox, QProgressBar, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
import serial.tools.list_ports
import mido
from gui_components import DMXCell, GRID_COLUMNS

class UIBuilder:
    def setup_ui(self, mw):
        mw.setWindowTitle("MIDI-DMX Pro v.18.0 - Audio Reactive")
        mw.resize(1250, 850)
        
        mw.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; }
            QLabel { color: #888; }
            QListWidget { background-color: #141414; border: 1px solid #2a2a2a; color: #ddd; outline: none; }
            QListWidget::item:selected { background-color: #2ecc71; color: black; border: none; }
            QLineEdit { background-color: #1a1a1a; color: #ddd; border: 1px solid #333; padding: 4px; }
            QSlider::groove:horizontal { border: 1px solid #333; height: 8px; background: #1a1a1a; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #3498db; border: 1px solid #3498db; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
            QTabWidget::pane { border: 1px solid #333; }
            QTabBar::tab { background: #222; color: #888; padding: 5px; }
            QTabBar::tab:selected { background: #333; color: white; border-bottom: 2px solid #3498db; }
            QMenu { background-color: #222; color: white; border: 1px solid #555; }
            QMenu::item:selected { background-color: #3498db; }
            QProgressBar { border: 1px solid #333; background-color: #111; text-align: center; }
            QProgressBar::chunk { background-color: #e67e22; }
        """)
        
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        mw.setCentralWidget(central)
        
        self._build_left_panel(mw, layout)
        self._build_center_panel(mw, layout)
        self._build_right_panel(mw, layout)

    def _build_left_panel(self, mw, parent_layout):
        panel = QWidget(); panel.setFixedWidth(280)
        left = QVBoxLayout(panel)
        
        # 1. HARDWARE
        left.addWidget(QLabel("<b>1. OUTPUT & AUDIO</b>"))
        mw.hw_tabs = QTabWidget(); mw.hw_tabs.setFixedHeight(180)
        
        # Serial
        t_ser = QWidget(); l_ser = QVBoxLayout(t_ser)
        mw.dmx_combo = QComboBox()
        try: mw.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        except: pass
        btn_ser = QPushButton("CONNETTI SERIALE"); btn_ser.clicked.connect(mw.connect_serial)
        l_ser.addWidget(QLabel("Porta DMX:")); l_ser.addWidget(mw.dmx_combo); l_ser.addWidget(btn_ser)
        mw.hw_tabs.addTab(t_ser, "USB DMX")
        
        # ArtNet
        t_art = QWidget(); l_art = QVBoxLayout(t_art)
        row_ip = QHBoxLayout()
        mw.art_ip = QLineEdit("127.0.0.1"); mw.art_uni = QLineEdit("0"); mw.art_uni.setFixedWidth(30)
        row_ip.addWidget(QLabel("IP:")); row_ip.addWidget(mw.art_ip); row_ip.addWidget(QLabel("Uni:")); row_ip.addWidget(mw.art_uni)
        btn_art = QPushButton("ATTIVA ART-NET"); btn_art.clicked.connect(mw.connect_artnet)
        l_art.addLayout(row_ip); l_art.addWidget(btn_art)
        mw.hw_tabs.addTab(t_art, "ART-NET")

        # AUDIO TAB (NUOVO)
        t_aud = QWidget(); l_aud = QVBoxLayout(t_aud); l_aud.setContentsMargins(5,5,5,5)
        mw.audio_combo = QComboBox() # Popolato dal main
        mw.btn_audio_start = QPushButton("START LISTENING"); mw.btn_audio_start.setCheckable(True)
        mw.btn_audio_start.clicked.connect(mw.toggle_audio_engine)
        mw.btn_audio_start.setStyleSheet("background-color: #2c3e50; color: #ccc;")
        
        l_aud.addWidget(QLabel("Input Device:"))
        l_aud.addWidget(mw.audio_combo)
        l_aud.addWidget(mw.btn_audio_start)
        
        h_vis = QHBoxLayout()
        mw.prog_vol = QProgressBar(); mw.prog_vol.setRange(0, 255); mw.prog_vol.setFixedHeight(8); mw.prog_vol.setTextVisible(False)
        mw.ind_beat = QLabel("⬤"); mw.ind_beat.setStyleSheet("color:#333; font-size:18px;")
        h_vis.addWidget(QLabel("Vol:")); h_vis.addWidget(mw.prog_vol); h_vis.addWidget(mw.ind_beat)
        l_aud.addLayout(h_vis)
        
        mw.hw_tabs.addTab(t_aud, "AUDIO FX")
        left.addWidget(mw.hw_tabs)
        
        # MIDI
        midi_box = QHBoxLayout()
        mw.midi_combo = QComboBox()
        try: mw.midi_combo.addItems(mido.get_input_names())
        except: pass
        btn_m = QPushButton("OK"); btn_m.setFixedWidth(40); btn_m.clicked.connect(mw.connect_midi)
        midi_box.addWidget(QLabel("MIDI:")); midi_box.addWidget(mw.midi_combo); midi_box.addWidget(btn_m)
        left.addLayout(midi_box)
        mw.lbl_midi_monitor = QLabel("DISCONNECTED")
        mw.lbl_midi_monitor.setStyleSheet("color: #666; font-size: 11px; border: 1px solid #333; padding: 2px;")
        mw.lbl_midi_monitor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(mw.lbl_midi_monitor); left.addSpacing(10)
        
        # 2. AUDIO REACTION & LIVE
        left.addWidget(QLabel("<b>2. REAZIONI & LIVE</b>"))
        
        react_box = QGroupBox("Audio Triggers")
        react_box.setStyleSheet("QGroupBox { border: 1px solid #333; margin-top: 5px; padding-top: 10px; }")
        l_react = QVBoxLayout(react_box); l_react.setSpacing(5)
        
        l_react.addWidget(QLabel("Mic Gain:"))
        mw.sl_gain = QSlider(Qt.Orientation.Horizontal); mw.sl_gain.setRange(1, 50); mw.sl_gain.setValue(10)
        mw.sl_gain.valueChanged.connect(mw.on_gain_change)
        l_react.addWidget(mw.sl_gain)
        
        mw.chk_beat_chase = QCheckBox("BEAT -> Next Step"); mw.chk_beat_chase.setToolTip("Avanza Chase col Bass Beat")
        l_react.addWidget(mw.chk_beat_chase)
        mw.chk_vol_dimmer = QCheckBox("VOLUME -> Master Dimmer"); mw.chk_vol_dimmer.setToolTip("Volume controlla Fader Live")
        l_react.addWidget(mw.chk_vol_dimmer)
        left.addWidget(react_box)
        
        left.addSpacing(5)
        mw.f_label = QLabel("LIVE: 0 | 0%"); mw.f_label.setStyleSheet("color: #3498db; font-weight: bold;")
        left.addWidget(mw.f_label)
        f_lay = QHBoxLayout()
        mw.f_slider = QSlider(Qt.Orientation.Horizontal); mw.f_slider.setRange(0, 255); mw.f_slider.valueChanged.connect(mw.fader_moved)
        mw.f_input = QLineEdit(); mw.f_input.setFixedWidth(40); mw.f_input.returnPressed.connect(mw.manual_fader_input)
        f_lay.addWidget(mw.f_slider); f_lay.addWidget(mw.f_input)
        left.addLayout(f_lay)
        
        mw.btn_learn = QPushButton("LEARN MIDI CHANNELS"); mw.btn_learn.clicked.connect(lambda: mw.midi.toggle_learn("chans"))
        left.addWidget(mw.btn_learn)
        mw.btn_reset_map = QPushButton("ELIMINA MIDI MAP"); mw.btn_reset_map.setStyleSheet("color:#c0392b; border:1px solid #555;")
        mw.btn_reset_map.clicked.connect(mw.reset_all_midi_channels)
        left.addWidget(mw.btn_reset_map)
        left.addSpacing(10)
        
        # 3. RISORSE
        left.addWidget(QLabel("<b>3. RISORSE</b>"))
        mw.sg_tabs = QTabWidget(); mw.sg_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #333; }")
        
        t_sc = QWidget(); l_sc = QVBoxLayout(t_sc); l_sc.setContentsMargins(2,2,2,2)
        btn_ss = QPushButton("SALVA SCENA"); btn_ss.clicked.connect(mw.save_scene_action)
        mw.s_list = QListWidget(); mw.s_list.itemClicked.connect(lambda i: mw.playback.toggle_scene(i.text()))
        mw.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.s_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.s_list, p, "sc"))
        l_sc.addWidget(btn_ss); l_sc.addWidget(mw.s_list); mw.sg_tabs.addTab(t_sc, "SCENE")
        
        t_gr = QWidget(); l_gr = QVBoxLayout(t_gr); l_gr.setContentsMargins(2,2,2,2)
        btn_mg = QPushButton("CREA GRUPPO"); btn_mg.clicked.connect(mw.create_group_action)
        mw.g_list = QListWidget(); mw.g_list.itemClicked.connect(lambda i: mw.select_group(i.text()))
        mw.g_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.g_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.g_list, p, "grp"))
        l_gr.addWidget(btn_mg); l_gr.addWidget(mw.g_list); mw.sg_tabs.addTab(t_gr, "GRUPPI")
        
        t_fx = QWidget(); l_fx = QVBoxLayout(t_fx); l_fx.setContentsMargins(2,2,2,2)
        btn_nf = QPushButton("NUOVA FIXTURE"); btn_nf.clicked.connect(mw.create_fixture_action)
        mw.btn_color_pick = QPushButton("🎨 PICK COLOR"); mw.btn_color_pick.setStyleSheet("background-color: #8e44ad; color: white;")
        mw.btn_color_pick.clicked.connect(mw.open_live_color_picker); mw.btn_color_pick.setEnabled(False)
        mw.f_list = QListWidget(); mw.f_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        mw.f_list.itemSelectionChanged.connect(mw.on_fixture_selection_change)
        mw.f_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.f_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.f_list, p, "fix"))
        l_fx.addWidget(btn_nf); l_fx.addWidget(mw.btn_color_pick); l_fx.addWidget(mw.f_list)
        mw.sg_tabs.addTab(t_fx, "FIXTURES")
        
        left.addWidget(mw.sg_tabs)
        parent_layout.addWidget(panel)

    def _build_center_panel(self, mw, parent_layout):
        mw.cells = []
        grid_w = QWidget(); grid_w.setStyleSheet("background-color: #050505;")
        grid = QGridLayout(grid_w); grid.setSpacing(2); grid.setContentsMargins(5, 5, 5, 5)
        for i in range(512):
            c = DMXCell(i + 1); c.clicked.connect(mw.toggle_cell); c.right_clicked.connect(mw.cell_context_menu)
            grid.addWidget(c, i // GRID_COLUMNS, i % GRID_COLUMNS); mw.cells.append(c)
        scroll = QScrollArea(); scroll.setWidget(grid_w); scroll.setWidgetResizable(True); scroll.setStyleSheet("border: none;")
        parent_layout.addWidget(scroll)

    def _build_right_panel(self, mw, parent_layout):
        panel = QWidget(); panel.setFixedWidth(280)
        right = QVBoxLayout(panel)
        
        right.addWidget(QLabel("<b>4. CHASE</b>"))
        r_btns = QHBoxLayout()
        b_man = QPushButton("MANUALE"); b_man.clicked.connect(mw.create_chase_action)
        b_wiz = QPushButton("✨ FX WIZARD"); b_wiz.setStyleSheet("background-color: #e67e22; color: white;")
        b_wiz.clicked.connect(mw.open_fx_wizard)
        r_btns.addWidget(b_man); r_btns.addWidget(b_wiz); right.addLayout(r_btns)
        
        mw.ch_list = QListWidget(); mw.ch_list.setFixedHeight(120)
        mw.ch_list.itemClicked.connect(lambda i: mw.playback.toggle_chase(i.text()))
        mw.ch_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.ch_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.ch_list, p, "ch"))
        right.addWidget(mw.ch_list)
        
        spd_box = QWidget(); spd_box.setStyleSheet("background-color: #1a1a1a; margin-top: 5px;")
        l_spd = QVBoxLayout(spd_box); l_spd.setSpacing(2)
        mw.lbl_speed = QLabel("HOLD TIME %: 100%"); l_spd.addWidget(mw.lbl_speed)
        mw.sl_speed = QSlider(Qt.Orientation.Horizontal); mw.sl_speed.setRange(0, 255); mw.sl_speed.setValue(127)
        mw.sl_speed.valueChanged.connect(mw.on_speed_change)
        mw.sl_speed.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.sl_speed.customContextMenuRequested.connect(lambda p: mw.show_slider_context(p, "chase_speed"))
        l_spd.addWidget(mw.sl_speed)
        mw.lbl_fade = QLabel("FADE TIME %: 100%"); l_spd.addWidget(mw.lbl_fade)
        mw.sl_fade = QSlider(Qt.Orientation.Horizontal); mw.sl_fade.setRange(0, 255); mw.sl_fade.setValue(127)
        mw.sl_fade.valueChanged.connect(mw.on_fade_change)
        mw.sl_fade.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.sl_fade.customContextMenuRequested.connect(lambda p: mw.show_slider_context(p, "chase_fade"))
        l_spd.addWidget(mw.sl_fade)
        right.addWidget(spd_box)
        
        right.addWidget(QLabel("<b>5. CUES</b>"))
        mw.btn_rec = QPushButton("● REGISTRA CUE"); mw.btn_rec.clicked.connect(mw.toggle_rec)
        mw.btn_rec.setStyleSheet("color: #e74c3c; font-weight: bold; background-color: #222;")
        right.addWidget(mw.btn_rec)
        mw.cue_list = QListWidget(); mw.cue_list.setFixedHeight(120)
        mw.cue_list.itemClicked.connect(lambda i: mw.playback.toggle_cue(i.text()))
        mw.cue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.cue_list.customContextMenuRequested.connect(lambda p: mw.show_context_menu(mw.cue_list, p, "cue"))
        right.addWidget(mw.cue_list)
        
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setStyleSheet("color: #444;")
        right.addWidget(line)
        
        right.addWidget(QLabel("<b>6. SHOW MANAGER</b>"))
        mw.show_list_widget = QListWidget()
        mw.show_list_widget.itemDoubleClicked.connect(mw.play_show_item)
        mw.show_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mw.show_list_widget.customContextMenuRequested.connect(mw.show_manager_context_menu)
        right.addWidget(mw.show_list_widget)
        
        mw.btn_go = QPushButton("GO / NEXT ▶"); mw.btn_go.clicked.connect(mw.go_next_step)
        mw.btn_go.setStyleSheet("background-color: #d35400; color: white; font-weight: bold; font-size: 14px;")
        right.addWidget(mw.btn_go)
        mw.btn_bo = QPushButton("MASTER BLACKOUT"); mw.btn_bo.clicked.connect(mw.action_blackout)
        mw.btn_bo.setStyleSheet("background-color: #6d0000; color: white; font-weight: bold;")
        right.addWidget(mw.btn_bo)
        
        parent_layout.addWidget(panel)