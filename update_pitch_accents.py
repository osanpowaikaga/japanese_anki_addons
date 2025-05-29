from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo
from anki.notes import Note
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QProgressBar
from .pitch_svg import hira_to_mora, create_svg_pitch_pattern, create_html_pitch_pattern
import os
import sys
import sqlite3

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ADDON_DIR, 'data')

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

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

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

    def accept(self):
        # On OK, process all notes in the selected deck
        deck_name = self.deck_combo.currentText()
        deck_id = self.deck_map.get(deck_name)
        field1 = self.field1_combo.currentText()
        field2 = self.field2_combo.currentText()
        if not (deck_id and field1 and field2):
            showInfo("Please select a deck and two fields.")
            return
        # Get all note ids in the selected deck
        nids = mw.col.db.list("select nid from cards where did=?", deck_id)
        total = len(set(nids))
        updated = 0
        addon_init = sys.modules.get('japanese_word_creator')
        if not addon_init or not hasattr(addon_init, "lookup_pitch_accent"):
            showInfo("Could not import pitch accent functions from __init__.py. Aborting.")
            return
        for i, nid in enumerate(set(nids)):
            note = mw.col.getNote(nid)
            if field1 in note and field2 in note:
                input_value = note[field1]
                # --- Use the same logic as in __init__.py: fetch all (kana, pattern) pairs from DB ---
                pitch_html = ''
                unique_pitch = set()
                entries = []
                # Use the same DB path as in __init__.py
                PITCH_DB_SQLITE_PATH = addon_init.PITCH_DB_SQLITE_PATH
                addon_init.ensure_pitchdb_sqlite()
                try:
                    if os.path.exists(PITCH_DB_SQLITE_PATH):
                        conn = sqlite3.connect(PITCH_DB_SQLITE_PATH)
                        c = conn.cursor()
                        c.execute('SELECT kana, pattern FROM pitch_accents WHERE kanji=? OR kana=?', (input_value, input_value))
                        for row in c.fetchall():
                            kana, pattern = row
                            if (kana, pattern) not in unique_pitch:
                                unique_pitch.add((kana, pattern))
                                entries.append({'kana': kana, 'pattern': pattern})
                        conn.close()
                except Exception:
                    pass
                for entry in entries:
                    formatted_pattern = addon_init.format_pitch_pattern(entry['pattern'])
                    svg = create_html_pitch_pattern(entry['kana'], formatted_pattern)
                    pitch_html += f'<div class="pitch-accent-block">{svg}</div>'
                note[field2] = pitch_html
                note.flush()
                updated += 1
            # Update progress bar
            if total > 0:
                percent = int((i + 1) / total * 100)
                self.progress.setValue(percent)
                QApplication.processEvents()
        mw.col.reset()
        showInfo(f"Updated {updated} notes in deck '{deck_name}'.")
        super().accept()

# In get_reading_frequencies and any other place, update the path:
freq_db_path = os.path.join(DATA_DIR, 'japanese_word_frequencies.sqlite')

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