from PyQt6.QtWidgets import (QLabel, QFrame, QDialog, QVBoxLayout, 
                             QListWidget, QGridLayout, QLineEdit, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator

CELL_WIDTH = 75
CELL_HEIGHT = 42
GRID_COLUMNS = 12

class DMXCell(QLabel):
    clicked = pyqtSignal(int)
    
    def __init__(self, ch, parent=None):
        super().__init__(parent)
        self.ch = ch
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Plain)
        
        # Cache per ottimizzazione
        self.last_val = -1
        self.last_sel = None
        self.last_map = None
        
        # Inizializzazione forzata
        self.update_view(0, False, False, force=True)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ch)

    def update_view(self, val, is_sel, is_map, force=False):
        """
        Aggiorna la grafica.
        MODIFICA: Se selezionato -> Sfondo Verde (#2ecc71), Testo Nero.
        """
        if not force:
            if val == self.last_val and is_sel == self.last_sel and is_map == self.last_map:
                return

        self.last_val = val
        self.last_sel = is_sel
        self.last_map = is_map
        
        pct = int(val / 2.55)
        
        # --- LOGICA COLORI ---
        if is_sel:
            # STILE SELEZIONATO (Verde sfondo, Nero testo)
            bg_color = "#2ecc71" 
            border = "1px solid #2ecc71"
            title_color = "#000000" # Nero
            text_color = "#000000"  # Nero
        else:
            # STILE NORMALE (Nero sfondo, Bianco testo)
            bg_color = "#0d0d0d"
            border = "1px solid #333"
            # Se mappato è verde, altrimenti grigio scuro
            title_color = "#2ecc71" if is_map else "#666" 
            text_color = "#ffffff"  # Bianco
        
        # HTML per il testo
        self.setText(f"<b><font color='{title_color}'>CH {self.ch}:</font></b><br>"
                     f"<span style='font-size: 11px; color: {text_color};'>{val} ({pct}%)</span>")
        
        # CSS per il box
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