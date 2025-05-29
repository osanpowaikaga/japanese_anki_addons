from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo
from anki.notes import Note
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QProgressBar
import os
import sys
import sqlite3
import re

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ADDON_DIR, 'data')
FREQ_DB_PATH = os.path.join(DATA_DIR, 'japanese_word_frequencies.sqlite')

class RelatedWordsFrequencySorter(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sort Related Words by Frequency")
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

        # Field selection
        layout.addWidget(QLabel("Select Related Words Field:"))
        self.field_combo = QComboBox()
        layout.addWidget(self.field_combo)

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
        nids = mw.col.db.list("select id from notes where id in (select nid from cards where did=?) limit 1", deck_id)
        if nids:
            note = mw.col.getNote(nids[0])
            fields = list(note.keys())
        else:
            fields = []
        self.field_combo.clear()
        self.field_combo.addItems(fields)

    def accented_kana_to_katakana(self, accented_kana):
        # Remove pitch accent marks (e.g., '＼', '／', etc.) and convert to katakana
        hira = accented_kana
        hira = re.sub(r'[＼／ˉˊˋ˘˙]', '', hira)
        hira = hira.replace('ゔ', 'う゛')  # handle voiced u
        kata = ''
        for ch in hira:
            code = ord(ch)
            # Hiragana to Katakana
            if 0x3041 <= code <= 0x3096:
                kata += chr(code + 0x60)
            else:
                kata += ch
        return kata

    def get_word_frequency(self, word, conn):
        # Query all readings for the word and use the max frequency (kanji_lookup logic)
        try:
            c = conn.cursor()
            c.execute('SELECT reading, frequency FROM word_readings WHERE word=?', (word,))
            rows = c.fetchall()
            if rows:
                return max(row[1] for row in rows if row[1] is not None)
        except Exception:
            pass
        return 0

    def accept(self):
        deck_name = self.deck_combo.currentText()
        deck_id = self.deck_map.get(deck_name)
        field = self.field_combo.currentText()
        if not (deck_id and field):
            showInfo("Please select a deck and a field.")
            return
        nids = mw.col.db.list("select nid from cards where did=?", deck_id)
        total = len(set(nids))
        updated = 0
        if not os.path.exists(FREQ_DB_PATH):
            showInfo("Frequency database not found: {}".format(FREQ_DB_PATH))
            return
        try:
            conn = sqlite3.connect(FREQ_DB_PATH)
        except Exception:
            showInfo("Could not open frequency database.")
            return
        for i, nid in enumerate(set(nids)):
            note = mw.col.getNote(nid)
            if field in note:
                related = note[field]
                words = [w.strip() for w in related.replace('\n', ',').replace('、', ',').replace(';', ',').split(',') if w.strip()]
                if not words:
                    continue
                # Get frequency for each word
                freq_pairs = [(w, self.get_word_frequency(w, conn)) for w in words]
                # Sort by frequency descending, then by word
                freq_pairs.sort(key=lambda x: (-x[1], x[0]))
                sorted_words = [w for w, _ in freq_pairs]
                new_value = ', '.join(sorted_words)
                note[field] = new_value
                note.flush()
                updated += 1
            # Update progress bar
            if total > 0:
                percent = int((i + 1) / total * 100)
                self.progress.setValue(percent)
                QApplication.processEvents()
        conn.close()
        mw.col.reset()
        showInfo(f"Updated {updated} notes in deck '{deck_name}'.")
        super().accept()

_menu_entry_added_related = False

def on_main_menu_add_related():
    global _menu_entry_added_related
    if _menu_entry_added_related:
        return
    action = QAction("Sort Related Words by Frequency", mw)
    def show_dialog():
        dlg = RelatedWordsFrequencySorter(mw)
        dlg.exec()
    action.triggered.connect(show_dialog)
    mw.form.menuTools.addAction(action)
    _menu_entry_added_related = True

from anki.hooks import addHook
addHook("profileLoaded", on_main_menu_add_related)

def get_word_frequency_standalone(word, db_path=FREQ_DB_PATH):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('SELECT reading, frequency FROM word_readings WHERE word=?', (word,))
        rows = c.fetchall()
        conn.close()
        if rows:
            return max(row[1] for row in rows if row[1] is not None)
    except Exception:
        pass
    return 0

def test_frequency_sorting():
    test_words = [
        "二百", "百", "八百", "三百", "一罰百戒", "百合", "百貨店", "百年", "百万円", "百人一首"
    ]
    if not os.path.exists(FREQ_DB_PATH):
        print(f"Frequency database not found: {FREQ_DB_PATH}")
        return
    freq_pairs = [(w, get_word_frequency_standalone(w)) for w in test_words]
    print("Frequencies:")
    for w, f in freq_pairs:
        print(f"{w}: {f}")
    freq_pairs.sort(key=lambda x: (-x[1], x[0]))
    print("\nSorted:")
    for w, f in freq_pairs:
        print(f"{w}: {f}")

def show_first_frequencies(n=20):
    if not os.path.exists(FREQ_DB_PATH):
        print(f"Frequency database not found: {FREQ_DB_PATH}")
        return
    try:
        conn = sqlite3.connect(FREQ_DB_PATH)
        c = conn.cursor()
        c.execute('SELECT word, frequency FROM word_readings LIMIT ?', (n,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            print("No rows found in word_readings table.")
        else:
            print("First entries in word_readings:")
            for word, freq in rows:
                print(f"{word}: {freq}")
    except Exception as e:
        print(f"Error reading database: {e}")

# Uncomment the following line to run the test in Anki's debug console or on startup:
# test_frequency_sorting()
# show_first_frequencies()
