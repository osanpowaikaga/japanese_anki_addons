from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo
from anki.notes import Note
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox

class PitchAccentDeckFieldSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pitch Accent Deck/Field Selector")
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)
        layout = QVBoxLayout(self)

        # Deck selection
        layout.addWidget(QLabel("Select Deck:"))
        self.deck_combo = QComboBox()
        decks = sorted(mw.col.decks.all(), key=lambda d: d['name'])
        self.deck_map = {d['name']: d['id'] for d in decks}
        self.deck_combo.addItems([d['name'] for d in decks])
        layout.addWidget(self.deck_combo)

        # Field selection (populated after deck selection)
        layout.addWidget(QLabel("Select Field 1:"))
        self.field1_combo = QComboBox()
        layout.addWidget(self.field1_combo)
        layout.addWidget(QLabel("Select Field 2:"))
        self.field2_combo = QComboBox()
        layout.addWidget(self.field2_combo)

        # Update fields when deck changes
        self.deck_combo.currentIndexChanged.connect(self.update_fields)
        self.update_fields()

        # OK/Cancel
        btns = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def update_fields(self):
        deck_name = self.deck_combo.currentText()
        deck_id = self.deck_map.get(deck_name)
        # Get first note in deck to get model/fields
        nids = mw.col.db.list("select id from notes where id in (select nid from cards where did=?) limit 1", deck_id)
        if nids:
            note = mw.col.getNote(nids[0])
            fields = list(note.keys())
        else:
            fields = []
        self.field1_combo.clear()
        self.field2_combo.clear()
        self.field1_combo.addItems(fields)
        self.field2_combo.addItems(fields)

# Add menu entry to Tools menu
_menu_entry_added_pitch = False

def on_main_menu_add_pitch():
    global _menu_entry_added_pitch
    if _menu_entry_added_pitch:
        return
    action = QAction("Pitch Accent Deck/Field Selector", mw)
    def show_dialog():
        dlg = PitchAccentDeckFieldSelector(mw)
        dlg.exec()
    action.triggered.connect(show_dialog)
    mw.form.menuTools.addAction(action)
    _menu_entry_added_pitch = True

from anki.hooks import addHook
addHook("profileLoaded", on_main_menu_add_pitch)