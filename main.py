import sys
import serial.tools.list_ports
import mido
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QComboBox, QPushButton, QVBoxLayout, 
    QHBoxLayout, QWidget, QLabel, QScrollArea, QGridLayout, QMenu, 
    QListWidget, QInputDialog, QLineEdit, QMessageBox, QSlider, QFrame
)
from PyQt6.QtGui import QColor, QIntValidator, QFont, QAction
from PyQt6.QtCore import QTimer, Qt

# IMPORT DAI MODULI ESISTENTI
from dmx_engine import DMXController
from playback_engine import PlaybackEngine
from midi_manager import MidiManager
import data_manager
from gui_components import DMXCell, ChaseCreatorDialog, GRID_COLUMNS

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Dati
        self.data_store = {
            "scenes": {}, "chases": {}, "cues": {}, 
            "show": [], "rem": {}, "map": {}
        }
        self.selected_ch = set()

        # 2. Motori
        self.dmx = DMXController()
        self.playback = PlaybackEngine(self.dmx, self.data_store)
        self.midi = MidiManager(self.playback, self.dmx, self.data_store)
        
        # Collegamenti
        self.midi.selected_channels = self.selected_ch
        self.playback.state_changed.connect(self._update_list_visual_selection)
        self.midi.learn_status_changed.connect(self.on_learn_status_change)
        self.midi.request_ui_refresh.connect(lambda: None) 

        # 3. UI
        self.init_interface()
        self.load_data()

        # 4. Timers
        self.timer_ui = QTimer()
        self.timer_ui.timeout.connect(self.update_ui_frame)
        self.timer_ui.start(33) 
        
        self.timer_engine = QTimer()
        self.timer_engine.timeout.connect(self.playback.tick)
        self.timer_engine.start(40)

    def init_interface(self):
        self.setWindowTitle("MIDI-DMX Pro v.6.0 - Show Manager Restored")
        self.resize(1650, 950)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; }
            QLabel { color: #888; }
            QListWidget { 
                background-color: #141414; border: 1px solid #2a2a2a; color: #ddd; outline: none;
            }
            QListWidget::item:selected { 
                background-color: #1a1a1a; border: 2px solid #f1c40f; color: white; 
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
        """)
        
        central = QWidget()
        main_layout = QHBoxLayout(central)
        self.setCentralWidget(central)
        
        # --- LEFT PANEL (HARDWARE & LIVE) ---
        left = QVBoxLayout()
        panel_l = QWidget(); panel_l.setFixedWidth(230); panel_l.setLayout(left)
        
        # Hardware
        left.addWidget(QLabel("<b>1. HARDWARE</b>"))
        self.midi_combo = QComboBox(); self.midi_combo.addItems(mido.get_input_names())
        self.dmx_combo = QComboBox(); self.dmx_combo.addItems([p.device for p in serial.tools.list_ports.comports()])
        btn_conn = QPushButton("CONNETTI SISTEMA"); btn_conn.setFixedHeight(35)
        btn_conn.clicked.connect(self.connect_hardware)
        left.addWidget(QLabel("MIDI Input:")); left.addWidget(self.midi_combo)
        left.addWidget(QLabel("DMX Port:")); left.addWidget(self.dmx_combo)
        left.addWidget(btn_conn); left.addSpacing(15)
        
        # Live Control (MODIFICATO: Fader e Input affiancati)
        left.addWidget(QLabel("<b>2. LIVE CONTROL</b>"))
        self.f_label = QLabel("LIVE: 0 | 0%")
        self.f_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        left.addWidget(self.f_label)
        
        # Layout orizzontale per Slider + Casellina
        fader_layout = QHBoxLayout()
        
        self.f_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_slider.setRange(0, 255); self.f_slider.setFixedHeight(25)
        self.f_slider.valueChanged.connect(self.fader_moved)
        fader_layout.addWidget(self.f_slider)
        
        self.f_input = QLineEdit()
        self.f_input.setFixedWidth(40) # Casella piccola
        self.f_input.setPlaceholderText("0")
        self.f_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.f_input.setValidator(QIntValidator(0, 255))
        self.f_input.returnPressed.connect(self.manual_fader_input)
        fader_layout.addWidget(self.f_input)
        
        left.addLayout(fader_layout)
        
        self.btn_learn = QPushButton("LEARN MIDI CHANNELS")
        self.btn_learn.setFixedHeight(35)
        self.btn_learn.clicked.connect(lambda: self.midi.toggle_learn("chans"))
        left.addWidget(self.btn_learn); left.addSpacing(15)

        # Scene Statiche
        left.addWidget(QLabel("<b>3. SCENE STATICHE</b>"))
        btn_save_sc = QPushButton("SALVA SCENA"); btn_save_sc.setFixedHeight(30)
        btn_save_sc.clicked.connect(self.save_scene_action)
        btn_save_sc.setStyleSheet("background-color: #1e3d24; border-color: #2ecc71; color: #ccc;")
        left.addWidget(btn_save_sc)
        
        self.s_list = QListWidget()
        self.s_list.itemClicked.connect(lambda i: self.playback.toggle_scene(i.text()))
        self.s_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.s_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.s_list, p, "sc"))
        left.addWidget(self.s_list)
        
        # --- CENTER PANEL (GRID) ---
        self.cells = []
        grid_w = QWidget(); grid_w.setStyleSheet("background-color: #050505;")
        grid = QGridLayout(grid_w); grid.setSpacing(2); grid.setContentsMargins(5, 5, 5, 5)
        
        for i in range(512):
            c = DMXCell(i + 1)
            c.clicked.connect(self.toggle_cell)
            grid.addWidget(c, i // GRID_COLUMNS, i % GRID_COLUMNS)
            self.cells.append(c)
            
        scroll = QScrollArea(); scroll.setWidget(grid_w); scroll.setWidgetResizable(True); scroll.setStyleSheet("border: none;")
        
        # --- RIGHT PANEL (CHASE, CUE, SHOW) ---
        right = QVBoxLayout()
        panel_r = QWidget(); panel_r.setFixedWidth(280); panel_r.setLayout(right)
        
        # Chase
        right.addWidget(QLabel("<b>4. CHASE (SEQUENZE)</b>"))
        btn_mk_ch = QPushButton("CREA CHASE STEP"); btn_mk_ch.setFixedHeight(30)
        btn_mk_ch.clicked.connect(self.create_chase_action)
        right.addWidget(btn_mk_ch)
        
        self.ch_list = QListWidget()
        self.ch_list.setFixedHeight(120)
        self.ch_list.itemClicked.connect(lambda i: self.playback.toggle_chase(i.text()))
        self.ch_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ch_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.ch_list, p, "ch"))
        right.addWidget(self.ch_list)

        # Cue
        right.addWidget(QLabel("<b>5. CUES (LIVE)</b>"))
        self.btn_rec = QPushButton("● REGISTRA CUE"); self.btn_rec.setFixedHeight(35)
        self.btn_rec.setStyleSheet("color: #e74c3c; font-weight: bold; background-color: #222;")
        self.btn_rec.clicked.connect(self.toggle_rec)
        right.addWidget(self.btn_rec)
        
        self.cue_list = QListWidget()
        self.cue_list.setFixedHeight(120)
        self.cue_list.itemClicked.connect(lambda i: self.playback.toggle_cue(i.text()))
        self.cue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cue_list.customContextMenuRequested.connect(lambda p: self.show_context_menu(self.cue_list, p, "cue"))
        right.addWidget(self.cue_list)
        
        # Separatore
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setStyleSheet("color: #444;")
        right.addWidget(line)

        # SHOW MANAGER (RIPRISTINATO)
        right.addWidget(QLabel("<b>6. SHOW MANAGER</b>"))
        self.show_list_widget = QListWidget()
        self.show_list_widget.itemDoubleClicked.connect(self.play_show_item)
        # Context menu anche per la lista show (per rimuovere voci)
        self.show_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.show_list_widget.customContextMenuRequested.connect(self.show_manager_context_menu)
        right.addWidget(self.show_list_widget)
        
        self.btn_go = QPushButton("GO / NEXT")
        self.btn_go.setFixedHeight(45)
        self.btn_go.clicked.connect(self.go_next_step)
        self.btn_go.setStyleSheet("background-color: #8c4a00; color: white; font-weight: bold; font-size: 14px;")
        right.addWidget(self.btn_go)

        # Blackout
        self.btn_bo = QPushButton("MASTER BLACKOUT"); self.btn_bo.setFixedHeight(40)
        self.btn_bo.setStyleSheet("background-color: #6d0000; color: white; border: 1px solid #a00; font-weight: bold;")
        self.btn_bo.clicked.connect(self.action_blackout)
        right.addWidget(self.btn_bo)

        main_layout.addWidget(panel_l); main_layout.addWidget(scroll); main_layout.addWidget(panel_r)

    # --- SHOW MANAGER LOGIC ---
    def play_show_item(self, item):
        """Esegue l'elemento selezionato nella lista show."""
        row_idx = self.show_list_widget.row(item)
        
        # Parsa la stringa "tipo:nome"
        entry_string = self.data_store["show"][row_idx]
        try:
            type_prefix, item_name = entry_string.split(":", 1)
            
            # Ferma tutto prima di cambiare (opzionale, per pulizia)
            # self.playback.stop_all() 
            
            if type_prefix == "sc":
                self.playback.toggle_scene(item_name)
            elif type_prefix == "ch":
                self.playback.toggle_chase(item_name)
            elif type_prefix == "cue":
                self.playback.toggle_cue(item_name)
                
            # Evidenzia nelle liste laterali
            self._update_list_visual_selection()
            
        except ValueError:
            pass

    def go_next_step(self):
        """Passa al prossimo elemento nella lista Show."""
        if not self.data_store["show"]:
            return
            
        curr_row = self.show_list_widget.currentRow()
        next_row = (curr_row + 1) % len(self.data_store["show"])
        
        self.show_list_widget.setCurrentRow(next_row)
        self.play_show_item(self.show_list_widget.item(next_row))

    def refresh_show_list_widget(self):
        """Ridisegna la lista dello Show Manager basandosi sui dati."""
        self.show_list_widget.clear()
        for i, entry in enumerate(self.data_store["show"]):
            if ":" in entry:
                t, n = entry.split(":", 1)
                label = f"{i+1}. [{t.upper()}] {n}"
                self.show_list_widget.addItem(label)

    # --- RENDER LOOP ---
    def update_ui_frame(self):
        mapped_ids = {ch for ids in self.data_store["map"].values() for ch in ids}
        mapped_remote_names = []
        for val in self.data_store["rem"].values():
            if ":" in val: mapped_remote_names.append(val.split(":", 1)[1])

        for i, cell in enumerate(self.cells):
            ch_num = i + 1
            val = self.dmx.output_frame[ch_num]
            is_sel = ch_num in self.selected_ch
            is_map = ch_num in mapped_ids
            cell.update_view(val, is_sel, is_map)

        for lst in [self.s_list, self.ch_list, self.cue_list]:
            for row in range(lst.count()):
                item = lst.item(row)
                target_color = QColor("#e67e22") if item.text() in mapped_remote_names else QColor("#ddd")
                if item.foreground().color() != target_color:
                    item.setForeground(target_color)

    # --- ACTIONS ---
    def action_blackout(self):
        self.playback.stop_all()
        self.f_slider.blockSignals(True)
        self.f_slider.setValue(0)
        self.f_slider.blockSignals(False)
        self.f_input.setText("0")
        self.f_label.setText("LIVE: 0 | 0%")

    def toggle_cell(self, ch):
        if ch in self.selected_ch: self.selected_ch.remove(ch)
        else: self.selected_ch.add(ch)
        self.cells[ch-1].update_view(self.dmx.output_frame[ch], ch in self.selected_ch, False, force=True)

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

    def on_learn_status_change(self, is_learning, target):
        if is_learning:
            self.btn_learn.setText("WAITING MIDI...")
            self.btn_learn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        else:
            self.btn_learn.setText("LEARN MIDI CHANNELS")
            self.btn_learn.setStyleSheet("background-color: #2c3e50; color: #ccc;")
            self.save_data()

    def connect_hardware(self):
        self.midi.open_port(self.midi_combo.currentText())
        if self.dmx.connect(self.dmx_combo.currentText()):
            QMessageBox.information(self, "Info", "Hardware Connesso!")
        else:
            QMessageBox.critical(self, "Errore", "Impossibile aprire porta DMX")

    def toggle_rec(self):
        if self.playback.is_recording_cue:
            self.playback.is_recording_cue = False
            self.btn_rec.setText("● REGISTRA CUE")
            self.btn_rec.setStyleSheet("color: #e74c3c; background-color: #222; font-weight: bold;")
            name, ok = QInputDialog.getText(self, "Salva", "Nome Cue:")
            if ok and name:
                self.data_store["cues"][name] = {"data": self.playback.recorded_stream}
                self.cue_list.addItem(name)
                self.save_data()
        else:
            self.playback.recorded_stream = []
            self.playback.is_recording_cue = True
            self.btn_rec.setText("STOP REC")
            self.btn_rec.setStyleSheet("background-color: #c0392b; color: #fff; font-weight: bold;")

    def _update_list_visual_selection(self):
        for i in range(self.s_list.count()):
            self.s_list.item(i).setSelected(self.s_list.item(i).text() == self.playback.active_sc)
        for i in range(self.ch_list.count()):
            self.ch_list.item(i).setSelected(self.ch_list.item(i).text() == self.playback.active_ch)
        for i in range(self.cue_list.count()):
            self.cue_list.item(i).setSelected(self.cue_list.item(i).text() == self.playback.active_cue)

    # --- CONTEXT MENUS ---
    def show_context_menu(self, widget, pos, type_key):
        item = widget.itemAt(pos)
        if not item: return
        menu = QMenu()
        act_learn = menu.addAction("Mappa a Pulsante MIDI")
        act_show = menu.addAction("Aggiungi a Show Manager") # NUOVO
        act_del = menu.addAction("Elimina Elemento")
        
        res = menu.exec(widget.mapToGlobal(pos))
        
        if res == act_learn:
            self.midi.toggle_learn(f"{type_key}:{item.text()}")
        elif res == act_show:
            entry = f"{type_key}:{item.text()}"
            self.data_store["show"].append(entry)
            self.refresh_show_list_widget()
            self.save_data()
        elif res == act_del: 
            widget.takeItem(widget.row(item))
            key_map = {"sc": "scenes", "ch": "chases", "cue": "cues"}
            self.data_store[key_map[type_key]].pop(item.text(), None)
            self.save_data()

    def show_manager_context_menu(self, pos):
        """Menu per rimuovere elementi dalla lista Show."""
        item = self.show_list_widget.itemAt(pos)
        if not item: return
        menu = QMenu()
        act_del = menu.addAction("Rimuovi da Show")
        if menu.exec(self.show_list_widget.mapToGlobal(pos)) == act_del:
            row = self.show_list_widget.row(item)
            self.data_store["show"].pop(row)
            self.refresh_show_list_widget()
            self.save_data()

    def save_scene_action(self):
        snap = {str(i): self.dmx.output_frame[i] for i in range(1, 513) if self.dmx.output_frame[i] > 0}
        name, ok = QInputDialog.getText(self, "Salva", "Nome Scena:")
        if ok and name:
            self.data_store["scenes"][name] = snap
            if not self.s_list.findItems(name, Qt.MatchFlag.MatchExactly): self.s_list.addItem(name)
            self.save_data()

    def create_chase_action(self):
        if not self.data_store["scenes"]:
            QMessageBox.warning(self, "Attenzione", "Crea prima delle scene!")
            return
        dlg = ChaseCreatorDialog(self.data_store["scenes"], self)
        if dlg.exec():
            steps = [i.text() for i in dlg.list.selectedItems()]
            if steps:
                name, ok = QInputDialog.getText(self, "Nuovo Chase", "Nome Sequenza:")
                if ok and name:
                    self.data_store["chases"][name] = {"steps": steps, "h": int(dlg.t_hold.text()), "f": int(dlg.t_fade.text())}
                    self.ch_list.addItem(name)
                    self.save_data()

    def save_data(self): data_manager.save_studio_data(self.data_store)
    
    def load_data(self):
        d = data_manager.load_studio_data()
        if d:
            self.data_store.update(d)
            self.s_list.clear(); self.ch_list.clear(); self.cue_list.clear()
            self.s_list.addItems(self.data_store.get("scenes", {}).keys())
            self.ch_list.addItems(self.data_store.get("chases", {}).keys())
            self.cue_list.addItems(self.data_store.get("cues", {}).keys())
            # Carica la lista Show
            self.refresh_show_list_widget()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())