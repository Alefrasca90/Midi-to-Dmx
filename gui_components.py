from PyQt6.QtWidgets import (QLabel, QFrame, QDialog, QVBoxLayout, 
                             QListWidget, QGridLayout, QLineEdit, QPushButton,
                             QHBoxLayout, QSpinBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QMessageBox)
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
            bg_color = "#2ecc71" 
            border = "1px solid #2ecc71"
            title_color = "#000000"
            text_color = "#000000"
        else:
            bg_color = "#0d0d0d"
            border = "1px solid #333"
            title_color = "#2ecc71" if is_map else "#666" 
            text_color = "#ffffff"
        
        self.setText(f"<b><font color='{title_color}'>CH {self.ch}:</font></b><br>"
                     f"<span style='font-size: 11px; color: {text_color};'>{val} ({pct}%)</span>")
        
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

# --- NUOVO DIALOGO AVANZATO PER FIXTURE ---
class FixtureCreatorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crea Profilo Fixture")
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout(self)
        
        # Nome e Indirizzo
        form = QHBoxLayout()
        form.addWidget(QLabel("Nome:"))
        self.name_input = QLineEdit()
        form.addWidget(self.name_input)
        
        form.addWidget(QLabel("Start Address:"))
        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(1, 512)
        form.addWidget(self.addr_spin)
        layout.addLayout(form)
        
        # Tabella Canali
        layout.addWidget(QLabel("<b>Definizione Canali:</b>"))
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Offset", "Funzione"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
        # Pulsanti gestione righe
        btns = QHBoxLayout()
        btn_add = QPushButton("+ Aggiungi Canale")
        btn_add.clicked.connect(self.add_row)
        btn_rem = QPushButton("- Rimuovi Ultimo")
        btn_rem.clicked.connect(self.remove_row)
        btns.addWidget(btn_add)
        btns.addWidget(btn_rem)
        layout.addLayout(btns)
        
        # Preset rapidi
        layout.addWidget(QLabel("Preset Rapidi:"))
        preset_box = QHBoxLayout()
        btn_rgb = QPushButton("RGB (3 ch)"); btn_rgb.clicked.connect(lambda: self.load_preset(["Red", "Green", "Blue"]))
        btn_rgbw = QPushButton("RGBW (4 ch)"); btn_rgbw.clicked.connect(lambda: self.load_preset(["Red", "Green", "Blue", "White"]))
        btn_dim = QPushButton("Dimmer (1 ch)"); btn_dim.clicked.connect(lambda: self.load_preset(["Dimmer"]))
        preset_box.addWidget(btn_rgb); preset_box.addWidget(btn_rgbw); preset_box.addWidget(btn_dim)
        layout.addLayout(preset_box)

        # OK / Cancel
        dlg_btns = QHBoxLayout()
        btn_ok = QPushButton("SALVA FIXTURE"); btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("ANNULLA"); btn_cancel.clicked.connect(self.reject)
        dlg_btns.addWidget(btn_cancel); dlg_btns.addWidget(btn_ok)
        layout.addLayout(dlg_btns)
        
        # Tipi di canali disponibili
        self.channel_types = [
            "Red", "Green", "Blue", "White", "Amber", "UV", 
            "Dimmer", "Strobe", "Pan", "Tilt", "Speed", "Macro", "Other"
        ]
        
        # Carica default RGB
        self.load_preset(["Red", "Green", "Blue"])

    def add_row(self, type_sel="Other"):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Colonna Offset (Read only)
        item_off = QTableWidgetItem(f"+ {row}")
        item_off.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(row, 0, item_off)
        
        # Colonna Funzione (ComboBox)
        combo = QComboBox()
        combo.addItems(self.channel_types)
        if type_sel in self.channel_types:
            combo.setCurrentText(type_sel)
        self.table.setCellWidget(row, 1, combo)

    def remove_row(self):
        row = self.table.rowCount()
        if row > 0: self.table.removeRow(row - 1)

    def load_preset(self, types):
        self.table.setRowCount(0)
        for t in types:
            self.add_row(t)

    def get_profile(self):
        profile = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            profile.append(combo.currentText())
        return profile