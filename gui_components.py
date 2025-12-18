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
        
        # --- MEMORIA DI STATO PER OTTIMIZZAZIONE ---
        self.last_val = -1
        self.last_sel = False
        self.last_map = False
        
        # Inizializzazione stile base
        self.update_view(0, False, False, force=True)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ch)

    def update_view(self, val, is_sel, is_map, force=False):
        """
        Aggiorna la grafica SOLO se i dati sono cambiati.
        Questo elimina il lag dell'interfaccia.
        """
        if not force:
            if val == self.last_val and is_sel == self.last_sel and is_map == self.last_map:
                return # Nessun cambiamento, non faccio nulla (Risparmio CPU)

        # Aggiorno la cache
        self.last_val = val
        self.last_sel = is_sel
        self.last_map = is_map
        
        # Calcoli Grafici
        pct = int(val / 2.55)
        border = "2px solid #f1c40f" if is_sel else "1px solid #333"
        color_title = "#2ecc71" if is_map else "#666"
        
        # Aggiorno HTML e CSS
        self.setText(f"<b><font color='{color_title}'>CH {self.ch}:</font></b><br><span style='font-size: 11px; color: #FFF;'>{val} ({pct}%)</span>")
        self.setStyleSheet(f"background-color: #0d0d0d; border: {border}; border-radius: 2px; color: #fff;")

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