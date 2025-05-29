from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo
from anki.notes import Note
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QProgressBar
import os
import sqlite3
import json
import re

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ADDON_DIR, 'data')
JMDICT_SQLITE_PATH = os.path.join(DATA_DIR, 'JMdict_e_examp.sqlite')

# --- JMdict lookup (copied from __init__.py) ---
def lookup_jmdict(word):
    if not os.path.exists(JMDICT_SQLITE_PATH):
        return []
    try:
        conn = sqlite3.connect(JMDICT_SQLITE_PATH)
        c = conn.cursor()
        c.execute('SELECT data FROM entries WHERE word=?', (word,))
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return []

class WordsWithTranslationsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Populate Words Fields with Translations")
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

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # OK/Cancel
        btns = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def accept(self):
        deck_name = self.deck_combo.currentText()
        deck_id = self.deck_map.get(deck_name)
        if not deck_id:
            showInfo("Please select a deck.")
            return
        nids = mw.col.db.list("select nid from cards where did=?", deck_id)
        total = len(set(nids))
        updated = 0
        for i, nid in enumerate(set(nids)):
            note = mw.col.getNote(nid)
            # Required fields: kanji, related_words, words, words_blank
            if not all(f in note for f in ("kanji", "related_words", "words", "words_blank")):
                continue
            kanji = note["kanji"].strip()
            related = note["related_words"]
            words = [w.strip() for w in related.replace('\n', ',').replace('、', ',').replace(';', ',').split(',') if w.strip()]
            if not words:
                continue
            selected_words = words[:4]
            words_lines = []
            words_blank_lines = []
            for w in selected_words:
                # Get furigana (if present in original field)
                furigana = self.get_furigana(w)
                # If not present, try to get from JMdict
                if not furigana:
                    furigana = self.get_first_reading(w)
                translations = self.get_translations(w)
                translations_str = '; '.join(translations) if translations else ''
                # For words: show as 漢字[かな] - translations, each in a styled block
                if furigana:
                    word_with_furi = f"{self.strip_furigana(w)}[{furigana}]"
                else:
                    word_with_furi = self.strip_furigana(w)
                words_lines.append(f'<div class="word-translation"><span class="word-jp">{word_with_furi}</span> - <span class="word-en">{translations_str}</span></div>')
                blanked = self.blank_kanji(self.strip_furigana(w), kanji)
                if furigana:
                    blanked_with_furi = f"{blanked}[{furigana}]"
                else:
                    blanked_with_furi = blanked
                words_blank_lines.append(f'<div class="word-translation"><span class="word-jp">{blanked_with_furi}</span> - <span class="word-en">{translations_str}</span></div>')
            note["words"] = '\n'.join(words_lines)
            note["words_blank"] = '\n'.join(words_blank_lines)
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

    def get_furigana(self, word):
        # Extract furigana from word if present (e.g., 名前[なまえ])
        m = re.match(r"(.+?)\[(.+?)\]", word)
        if m:
            return m.group(2)
        return ''

    def blank_kanji(self, word, kanji):
        # Replace all occurrences of the kanji with 〇
        return word.replace(kanji, '〇')

    def get_translations(self, word):
        entries = lookup_jmdict(self.strip_furigana(word))
        translations = []
        for entry in entries:
            for m in entry.get('meanings', []):
                for part in m.split(';'):
                    part = part.strip()
                    if part:
                        translations.append(part)
        return translations[:3]  # Limit to 3 translations

    def strip_furigana(self, word):
        # Remove [furigana] from word
        return re.sub(r"\[.+?\]", "", word)

    def get_first_reading(self, word):
        # Try to get the first kana reading from JMdict
        entries = lookup_jmdict(self.strip_furigana(word))
        for entry in entries:
            kanas = entry.get('kanas', [])
            if kanas:
                return kanas[0]
        return ''

_menu_entry_added_words_trans = False

def on_main_menu_add_words_trans():
    global _menu_entry_added_words_trans
    if _menu_entry_added_words_trans:
        return
    action = QAction("Populate Words Fields with Translations", mw)
    def show_dialog():
        dlg = WordsWithTranslationsDialog(mw)
        dlg.exec()
    action.triggered.connect(show_dialog)
    mw.form.menuTools.addAction(action)
    _menu_entry_added_words_trans = True

from anki.hooks import addHook
addHook("profileLoaded", on_main_menu_add_words_trans)
