from PyQt6.QtWidgets import (QLabel, QFrame, QDialog, QVBoxLayout, 
                             QListWidget, QGridLayout, QLineEdit, QPushButton,
                             QHBoxLayout, QSpinBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QMessageBox, QSlider, QColorDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator, QColor

CELL_WIDTH = 75
CELL_HEIGHT = 42
GRID_COLUMNS = 12

class DMXCell(QLabel):
    clicked = pyqtSignal(int)
    right_clicked = pyqtSignal(int)
    
    def __init__(self, ch, parent=None):
        super().__init__(parent)
        self.ch = ch
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Plain)
        
        self.last_val = -1
        self.last_sel = None
        self.last_map = None
        self.update_view(0, False, False, force=True)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ch)
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self.ch)

    def update_view(self, val, is_sel, is_map, force=False):
        if not force:
            if val == self.last_val and is_sel == self.last_sel and is_map == self.last_map:
                return
        self.last_val = val
        self.last_sel = is_sel
        self.last_map = is_map
        pct = int(val / 2.55)
        
        if is_sel:
            bg_color = "#2ecc71"; border = "1px solid #2ecc71"; title_color = "#000000"; text_color = "#000000"
        else:
            bg_color = "#0d0d0d"; border = "1px solid #333"; title_color = "#2ecc71" if is_map else "#666"; text_color = "#ffffff"
        
        self.setText(f"<b><font color='{title_color}'>CH {self.ch}:</font></b><br><span style='font-size: 11px; color: {text_color};'>{val} ({pct}%)</span>")
        self.setStyleSheet(f"background-color: {bg_color}; border: {border}; border-radius: 2px;")

class ChaseCreatorDialog(QDialog):
    def __init__(self, scenes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuratore Sequenza Chase")
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Seleziona le Scene per gli Step:</b>"))
        self.list = QListWidget()
        self.list.addItems(scenes.keys())
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list)
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

class FixtureCreatorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crea Profilo Fixture")
        self.setMinimumWidth(450); self.setMinimumHeight(400)
        layout = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(QLabel("Nome:")); self.name_input = QLineEdit(); form.addWidget(self.name_input)
        form.addWidget(QLabel("Start Address:")); self.addr_spin = QSpinBox(); self.addr_spin.setRange(1, 512); form.addWidget(self.addr_spin)
        layout.addLayout(form)
        layout.addWidget(QLabel("<b>Definizione Canali:</b>"))
        self.table = QTableWidget(); self.table.setColumnCount(2); self.table.setHorizontalHeaderLabels(["Offset", "Funzione"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        btns = QHBoxLayout()
        btn_add = QPushButton("+ Aggiungi Canale"); btn_add.clicked.connect(self.add_row)
        btn_rem = QPushButton("- Rimuovi Ultimo"); btn_rem.clicked.connect(self.remove_row)
        btns.addWidget(btn_add); btns.addWidget(btn_rem)
        layout.addLayout(btns)
        layout.addWidget(QLabel("Preset Rapidi:"))
        preset_box = QHBoxLayout()
        btn_rgb = QPushButton("RGB (3 ch)"); btn_rgb.clicked.connect(lambda: self.load_preset(["Red", "Green", "Blue"]))
        btn_rgbw = QPushButton("RGBW (4 ch)"); btn_rgbw.clicked.connect(lambda: self.load_preset(["Red", "Green", "Blue", "White"]))
        btn_dim = QPushButton("Dimmer (1 ch)"); btn_dim.clicked.connect(lambda: self.load_preset(["Dimmer"]))
        preset_box.addWidget(btn_rgb); preset_box.addWidget(btn_rgbw); preset_box.addWidget(btn_dim)
        layout.addLayout(preset_box)
        dlg_btns = QHBoxLayout()
        btn_ok = QPushButton("SALVA FIXTURE"); btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("ANNULLA"); btn_cancel.clicked.connect(self.reject)
        dlg_btns.addWidget(btn_cancel); dlg_btns.addWidget(btn_ok)
        layout.addLayout(dlg_btns)
        self.channel_types = ["Red", "Green", "Blue", "White", "Amber", "UV", "Dimmer", "Strobe", "Pan", "Tilt", "Speed", "Macro", "Other"]
        self.load_preset(["Red", "Green", "Blue"])

    def add_row(self, type_sel="Other"):
        row = self.table.rowCount(); self.table.insertRow(row)
        item_off = QTableWidgetItem(f"+ {row}"); item_off.setFlags(Qt.ItemFlag.ItemIsEnabled); self.table.setItem(row, 0, item_off)
        combo = QComboBox(); combo.addItems(self.channel_types)
        if type_sel in self.channel_types: combo.setCurrentText(type_sel)
        self.table.setCellWidget(row, 1, combo)

    def remove_row(self):
        row = self.table.rowCount()
        if row > 0: self.table.removeRow(row - 1)

    def load_preset(self, types):
        self.table.setRowCount(0)
        for t in types: self.add_row(t)

    def get_profile(self):
        profile = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1); profile.append(combo.currentText())
        return profile

# --- FX GENERATOR POTENZIATO ---
class FXGeneratorDialog(QDialog):
    def __init__(self, fixtures_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✨ FX Wizard Pro")
        self.setFixedWidth(400)
        
        layout = QVBoxLayout(self)
        self.selected_color = QColor(255, 255, 255) # Base color user choice
        
        layout.addWidget(QLabel(f"Target: <b>{fixtures_count}</b> fixtures selezionate."))
        layout.addSpacing(5)
        
        # 1. Tipo Effetto
        layout.addWidget(QLabel("1. Scegli Effetto:"))
        self.combo_fx = QComboBox()
        self.combo_fx.addItems([
            "🌊 Color Pulse (Sine Wave)", 
            "🏃 Color Chase (Scorrimento)", 
            "💥 Blinder (Flash & Fade)",  # NUOVO
            "✨ Sparkle (Scintillio Random)",
            "🔥 Fire Flicker (Fuoco)",
            "🔦 Knight Rider (Scanner)",
            "🌈 Rainbow Wave (Ignora pattern)", 
            "🚓 Police (Ignora pattern)",
            "⚡ Strobe Attack"
        ])
        layout.addWidget(self.combo_fx)
        
        # 2. Pattern Colori
        layout.addSpacing(5)
        layout.addWidget(QLabel("2. Pattern Colori:"))
        
        h_pat = QHBoxLayout()
        self.combo_pattern = QComboBox()
        self.combo_pattern.addItems([
            "Usa Colore Singolo Personalizzato",
            "🔴🔵 Rosso / Blu",
            "🟠🔵 Arancio / Teal",
            "🟡⚪ Ambra / Bianco (Warm)",
            "🟣🟢 Viola / Verde (Acid)",
            "🔴🟢 Natale (Rosso/Verde)",
            "🎲 Colori Random"
        ])
        h_pat.addWidget(self.combo_pattern)
        
        self.btn_color = QPushButton("...")
        self.btn_color.setFixedWidth(40)
        self.btn_color.setStyleSheet(f"background-color: {self.selected_color.name()}; border: 1px solid #555;")
        self.btn_color.clicked.connect(self.pick_color)
        h_pat.addWidget(self.btn_color)
        
        layout.addLayout(h_pat)

        # 3. Parametri
        layout.addSpacing(5)
        layout.addWidget(QLabel("3. Parametri:"))
        
        grid = QGridLayout()
        grid.addWidget(QLabel("Step Totali:"), 0, 0)
        self.spin_steps = QSpinBox(); self.spin_steps.setRange(2, 100); self.spin_steps.setValue(16)
        grid.addWidget(self.spin_steps, 0, 1)
        
        grid.addWidget(QLabel("Velocità (ms):"), 1, 0)
        self.spin_hold = QSpinBox(); self.spin_hold.setRange(20, 5000); self.spin_hold.setValue(100); self.spin_hold.setSingleStep(10)
        grid.addWidget(self.spin_hold, 1, 1)
        
        grid.addWidget(QLabel("Spread (Fase):"), 2, 0)
        self.slider_spread = QSlider(Qt.Orientation.Horizontal); self.slider_spread.setRange(0, 200); self.slider_spread.setValue(100)
        grid.addWidget(self.slider_spread, 2, 1)
        
        layout.addLayout(grid)
        
        layout.addSpacing(10)
        layout.addWidget(QLabel("Nome Chase:"))
        self.name_input = QLineEdit("New FX")
        layout.addWidget(self.name_input)
        
        btns = QHBoxLayout()
        btn_ok = QPushButton("GENERA CHASE"); btn_ok.clicked.connect(self.accept)
        btn_ok.setStyleSheet("background-color: #d35400; color: white; font-weight: bold; padding: 5px;")
        btn_cancel = QPushButton("ANNULLA"); btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel); btns.addWidget(btn_ok)
        layout.addLayout(btns)

        # Logica: se scelgo un preset, disabilito il bottone colore custom
        self.combo_pattern.currentIndexChanged.connect(self.check_pattern_mode)

    def pick_color(self):
        c = QColorDialog.getColor(self.selected_color, self, "Scegli Colore Base")
        if c.isValid():
            self.selected_color = c
            self.btn_color.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #ccc;")
    
    def check_pattern_mode(self):
        is_custom = (self.combo_pattern.currentIndex() == 0)
        self.btn_color.setEnabled(is_custom)
        if not is_custom:
            self.btn_color.setStyleSheet("background-color: #333; border: 1px solid #555; color: #555;")
        else:
            self.btn_color.setStyleSheet(f"background-color: {self.selected_color.name()}; border: 1px solid #ccc;")