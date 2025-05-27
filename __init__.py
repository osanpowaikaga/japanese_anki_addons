# -*- coding: utf-8 -*-
import os
import sys
import csv
import json
import xml.etree.ElementTree as ET
from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo
from anki.notes import Note
from anki.hooks import addHook
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QWidget
import re
import unicodedata
import sqlite3
from .kanji_lookup import KanjiLookupDialog
from . import update_pitch_accents
from .pitch_svg import hira_to_mora, create_svg_pitch_pattern, create_html_pitch_pattern
# Add-on paths
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
JM_DICT_PATH = os.path.join(ADDON_DIR, 'JMdict_e_examp.XML')
PITCH_DB_PATH = os.path.join(ADDON_DIR, 'wadoku_pitchdb.csv')
KANJI_INFO_PATH = os.path.join(ADDON_DIR, '常用漢字の書き取り.json')

# --- Load Kanji Info JSON ---
try:
    with open(KANJI_INFO_PATH, 'r', encoding='utf-8') as f:
        KANJI_INFO_DB = json.load(f)
except Exception:
    KANJI_INFO_DB = []

# --- Pitch Accent SQLite Database Path ---
PITCH_DB_SQLITE_PATH = os.path.join(ADDON_DIR, 'wadoku_pitchdb.sqlite')

# --- Convert CSV to SQLite if needed ---
def ensure_pitchdb_sqlite():
    if os.path.exists(PITCH_DB_SQLITE_PATH):
        return
    if not os.path.exists(PITCH_DB_PATH):
        return
    import sqlite3
    import re
    try:
        conn = sqlite3.connect(PITCH_DB_SQLITE_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS pitch_accents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji TEXT,
            kana TEXT,
            accented_kana TEXT,
            pitch_number TEXT,
            pattern TEXT
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_pitch_kanji ON pitch_accents(kanji)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_pitch_kana ON pitch_accents(kana)')
        with open(PITCH_DB_PATH, 'r', encoding='utf-8') as f:
            next(f, None)
            for line in f:
                parts = line.strip().split('␞')
                if len(parts) < 5:
                    continue
                kanji_column = parts[0]
                kana_column = parts[1]
                accented_kana = parts[2]
                pitch_number = parts[3]
                pitch_pattern = parts[4]
                # Split by ␟ and remove special chars
                kanji_list = [re.sub(r'[△×…]', '', k) for k in kanji_column.split('␟') if k]
                kana_list = [re.sub(r'[△×…]', '', k) for k in kana_column.split('␟') if k]
                for kanji in kanji_list or ['']:
                    for kana in kana_list or ['']:
                        c.execute('INSERT INTO pitch_accents (kanji, kana, accented_kana, pitch_number, pattern) VALUES (?, ?, ?, ?, ?)',
                                  (kanji, kana, accented_kana, pitch_number, pitch_pattern))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

# --- On-demand Pitch Accent Lookup (no global index) ---
_pitch_accent_cache = {}

def lookup_pitch_accent(word):
    """Lookup pitch accent for a word from wadoku_pitchdb.sqlite, with in-memory cache."""
    if word in _pitch_accent_cache:
        return _pitch_accent_cache[word]
    ensure_pitchdb_sqlite()
    if not os.path.exists(PITCH_DB_SQLITE_PATH):
        return [], '', [], ''
    import sqlite3
    entries = []
    try:
        conn = sqlite3.connect(PITCH_DB_SQLITE_PATH)
        c = conn.cursor()
        # If input is a single kanji, fetch all readings for that kanji
        if len(word) == 1 and '\u4e00' <= word <= '\u9fff':
            c.execute('SELECT kana, accented_kana, pitch_number, pattern FROM pitch_accents WHERE kanji=?', (word,))
        else:
            # Otherwise, search both kanji and kana columns as before
            c.execute('SELECT kana, accented_kana, pitch_number, pattern FROM pitch_accents WHERE kanji=? OR kana=?', (word, word))
        for row in c.fetchall():
            kana, accented_kana, pitch_number, pattern = row
            pitch_entry = {
                "kana": kana,
                "accented_kana": accented_kana,
                "pitch_number": pitch_number,
                "pattern": pattern
            }
            entries.append(pitch_entry)
        conn.close()
    except Exception:
        pass
    if not entries:
        result = ([], '', [], '')
    else:
        # Collect all unique accented_kanas readings
        accented_kanas = list({e["accented_kana"] for e in entries if e["accented_kana"]})
        pitch_patterns = [e["pattern"] for e in entries]
        normal_kanas = list({e["kana"] for e in entries if e["kana"]})
        result = (accented_kanas, accented_kanas[0] if accented_kanas else '', pitch_patterns, normal_kanas[0] if normal_kanas else '')
    _pitch_accent_cache[word] = result
    return result

# --- JMdict JSON Database Path ---
JMDICT_JSON_PATH = os.path.join(ADDON_DIR, 'JMdict_e_examp.json')

# --- JMdict SQLite Database Path ---
JMDICT_SQLITE_PATH = os.path.join(ADDON_DIR, 'JMdict_e_examp.sqlite')

# --- SQLite-based JMdict Lookup ---
def ensure_jmdict_sqlite():
    """Create SQLite DB from JSON if not present."""
    if os.path.exists(JMDICT_SQLITE_PATH):
        return
    if not os.path.exists(JMDICT_JSON_PATH):
        return
    try:
        with open(JMDICT_JSON_PATH, 'r', encoding='utf-8') as f:
            jmdict_data = json.load(f)
        conn = sqlite3.connect(JMDICT_SQLITE_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS entries (
            word TEXT PRIMARY KEY,
            data TEXT
        )''')
        for word, entries in jmdict_data.items():
            c.execute('INSERT OR REPLACE INTO entries (word, data) VALUES (?, ?)', (word, json.dumps(entries, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

_ensure_sqlite_ran = False

def lookup_jmdict(word):
    global _JMDICT_JSON_CACHE, _ensure_sqlite_ran
    if not _ensure_sqlite_ran:
        ensure_jmdict_sqlite()
        _ensure_sqlite_ran = True
    # Try SQLite lookup first
    if os.path.exists(JMDICT_SQLITE_PATH):
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
    # Fallback to JSON cache
    if _JMDICT_JSON_CACHE is None:
        if os.path.exists(JMDICT_JSON_PATH):
            try:
                with open(JMDICT_JSON_PATH, 'r', encoding='utf-8') as f:
                    _JMDICT_JSON_CACHE = json.load(f)
            except Exception:
                _JMDICT_JSON_CACHE = {}
        else:
            _JMDICT_JSON_CACHE = {}
    return _JMDICT_JSON_CACHE.get(word, [])

# Ensure SQLite DB is created at startup if possible
ensure_jmdict_sqlite()

# --- Build JMdict Index (legacy, only if JSON not present) ---
JMDICT_INDEX = {}
if not os.path.exists(JMDICT_JSON_PATH) and os.path.exists(JM_DICT_PATH):
    tree = ET.parse(JM_DICT_PATH)
    root = tree.getroot()
    for entry in root.findall('entry'):
        kanjis = [keb.text for k_ele in entry.findall('k_ele') for keb in k_ele.findall('keb') if keb.text]
        kanas = [reb.text for r_ele in entry.findall('r_ele') for reb in r_ele.findall('reb') if reb.text]
        meanings = []
        for sense in entry.findall('sense'):
            glosses = [g.text for g in sense.findall('gloss') if g.text]
            if glosses:
                meanings.append('; '.join(glosses))
        for key in kanjis + kanas:
            JMDICT_INDEX.setdefault(key, []).append({'kanjis': kanjis, 'kanas': kanas, 'meanings': meanings})
    # Save as JSON for future fast loading
    try:
        with open(JMDICT_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(JMDICT_INDEX, f, ensure_ascii=False)
    except Exception:
        pass

# --- Sentence Lookup ---
import importlib.util
SENTENCE_LOOKUP_PATH = os.path.join(ADDON_DIR, 'sentence_lookup.py')
lookup_sentences_and_related = None
if os.path.exists(SENTENCE_LOOKUP_PATH):
    spec = importlib.util.spec_from_file_location('sentence_lookup', SENTENCE_LOOKUP_PATH)
    sentence_lookup = importlib.util.module_from_spec(spec)
    sys.modules['sentence_lookup'] = sentence_lookup
    spec.loader.exec_module(sentence_lookup)
    lookup_sentences_and_related = sentence_lookup.lookup_sentences_and_related
else:
    def lookup_sentences_and_related(word):
        return [], []

def get_example_sentences(word):
    examples, _ = lookup_sentences_and_related(word)
    return examples

# --- Kanji Info Lookup ---
def get_kanji_info_blocks(word):
    blocks = []
    for ch in word:
        if ord(ch) < 0x4e00 or ord(ch) > 0x9fff:
            continue
        for entry in KANJI_INFO_DB:
            # Use the kanji as the key for matching
            if entry.get('kanji') == ch:
                block = {
                    'kanji': ch,
                    'reading_on': entry.get('reading_on', ''),
                    'reading_kun': entry.get('reading_kun', ''),
                    'strokes': entry.get('number_of_strokes', ''),
                    'radical': entry.get('radical', ''),
                    'meaning': entry.get('meaning', ''),
                    'kanken_level': entry.get('kanken_level', ''),
                    'stroke_order': entry.get('stroke_order', ''),
                    'radical_reading': entry.get('radical_reading', ''),
                    'radical_information': entry.get('radical_information', ''),
                    'related_words': [w.strip() for w in entry.get('related_words', '').split(',') if w.strip()][:20]
                }
                blocks.append(block)
                break
    return blocks

class JapaneseWordCardCreator(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Japanese Word Card Creator")
        self.setMinimumWidth(800)
        self.setMinimumHeight(400)
        layout = QHBoxLayout(self)

        # Left: Controls
        left = QVBoxLayout()
        left.addWidget(QLabel("Deck:"))
        self.deck_combo = QComboBox()
        deck_names = [d['name'] for d in mw.col.decks.all()]
        self.deck_combo.addItems(deck_names)
        # Set default deck to 小説 if it exists
        if "小説" in deck_names:
            self.deck_combo.setCurrentIndex(deck_names.index("小説"))
        left.addWidget(self.deck_combo)
        left.addWidget(QLabel("Word:"))
        self.word_input = QLineEdit()
        left.addWidget(self.word_input)
        self.create_btn = QPushButton("Create Card")
        left.addWidget(self.create_btn)
        left.addStretch(1)
        layout.addLayout(left)

        # Right: Card preview
        right = QVBoxLayout()
        right.addWidget(QLabel("Card Preview:"))
        self.card_preview = QTextEdit()
        self.card_preview.setReadOnly(True)
        right.addWidget(self.card_preview)
        layout.addLayout(right)

        self.create_btn.clicked.connect(self.on_create)

    def on_create(self):
        word = self.word_input.text().strip()
        if not word:
            self.card_preview.setPlainText("Please enter a word.")
            return
        deck_name = self.deck_combo.currentText()
        deck_id = mw.col.decks.id(deck_name)
        # Create card and get preview, and actually add the card
        card_html = create_japanese_word_card(word, deck_id, preview_only=False)
        self.card_preview.setHtml(card_html)
        # Indicate card creation
        self.card_preview.append("<div style='color:green; font-weight:bold; margin-top:10px;'>Card created in deck: {}</div>".format(deck_name))

# --- Modified card creation logic to support deck and preview ---
def create_japanese_word_card(word, deck_id=None, preview_only=False):
    # Reading: try to get from wadoku_pitchdb accented kana (column 3)
    readings, accented_kana, pitch_patterns, normal_kana = lookup_pitch_accent(word)
    # Join all readings for display
    reading = '、'.join(readings) if readings else ''
    # Fallback: try to get from JMdict entry (kana)
    jmdict_entries = lookup_jmdict(word)
    if not reading and jmdict_entries:
        kanas = jmdict_entries[0].get('kanas', [])
        if kanas:
            reading = kanas[0]
    # Meanings
    meanings = []
    if jmdict_entries:
        for entry in jmdict_entries:
            for m in entry['meanings']:
                for part in m.split(';'):
                    part = part.strip()
                    if part:
                        meanings.append(part)
    # Example sentences
    examples = get_example_sentences(word)
    # Render each example as a jp-en-pair block, Japanese and English on separate lines, extra margin between blocks
    examples_str = ''.join(
        f'<div class="jp-en-pair" style="margin-bottom: 18px;">'
        f'<span class="japanese">{jp}</span><br>'
        f'<span class="english">{en}</span>'
        f'</div>'
        for jp, en in examples
    )
    # Meanings (add more space between blocks)
    meanings_str = ''.join(f'<div class="meaning-block" style="margin-bottom: 14px;">{m}</div>' for m in meanings)
    # Pitch accent SVG: use each unique (kana, pattern) pair
    pitch_html = ''
    if jmdict_entries or pitch_patterns:
        unique_pitch = set()
        entries = []
        ensure_pitchdb_sqlite()
        try:
            if os.path.exists(PITCH_DB_SQLITE_PATH):
                import sqlite3
                conn = sqlite3.connect(PITCH_DB_SQLITE_PATH)
                c = conn.cursor()
                c.execute('SELECT kana, pattern FROM pitch_accents WHERE kanji=? OR kana=?', (word, word))
                for row in c.fetchall():
                    kana, pattern = row
                    if (kana, pattern) not in unique_pitch:
                        unique_pitch.add((kana, pattern))
                        entries.append({'kana': kana, 'pattern': pattern})
                conn.close()
        except Exception:
            pass
        for entry in entries:
            formatted_pattern = format_pitch_pattern(entry['pattern'])
            # Use shared SVG logic from pitch_svg.py
            svg = create_html_pitch_pattern(entry['kana'], formatted_pattern)
            pitch_html += f'<div class="pitch-accent-block">{svg}</div>'
    # Kanji info
    kanji_blocks = get_kanji_info_blocks(word)
    kanji_info_str = ''
    for block in kanji_blocks:
        kanji_info_str += f"""
        <div class='kanji-block'>
            <div class='kanji-char'>{block['kanji']}</div>
            <div class='kanji-attr'><b>音読み:</b> {block['reading_on']}</div>
            <div class='kanji-attr'><b>訓読み:</b> {block['reading_kun']}</div>
            <div class='kanji-attr'><b>画数:</b> {block['strokes']}</div>
            <div class='kanji-attr'><b>部首:</b> {block['radical']}</div>
            <div class='kanji-attr'><b>部首読み:</b> {block['radical_reading']}</div>
            <div class='kanji-attr'><b>部首情報:</b> {block['radical_information']}</div>
            <div class='kanji-attr'><b>意味:</b> {block['meaning']}</div>
            <div class='kanji-attr'><b>漢検レベル:</b> {block['kanken_level']}</div>
            <div class='kanji-attr'><b>書き順:</b> {block['stroke_order']}</div>
            <div class='kanji-attr'><b>関連語:</b> {', '.join(block['related_words'])}</div>
        </div>
        """
    # --- Removed baked-in CSS and card_template variable ---
    # The card_template and inline CSS have been removed. Card rendering will use external template and CSS files.
    if preview_only:
        # For preview, use the actual values, not field names
        return front_template.replace('{{word}}', word).replace('{{reading}}', reading).replace('{{meanings}}', meanings_str).replace('{{example sentences}}', examples_str).replace('{{pitch_accent}}', pitch_html).replace('{{kanji_info}}', kanji_info_str)
    # Create note in Anki
    model_name = 'JapaneseWordAuto'
    mm = mw.col.models
    model = mm.byName(model_name)
    if not model:
        model = mm.new(model_name)
        for fld in ['word', 'reading', 'meanings', 'example sentences', 'pitch_accent', 'kanji_info']:
            mm.addField(model, mm.newField(fld))
        # Use external template and CSS
        tmpl = mm.newTemplate('Card 1')
        tmpl['qfmt'] = front_template
        tmpl['afmt'] = back_template
        model['css'] = card_css
        mm.addTemplate(model, tmpl)
        mm.add(model)
    note = Note(mw.col, model)
    note['word'] = word
    note['reading'] = reading
    note['meanings'] = meanings_str.replace('<br>', '\n')
    note['example sentences'] = examples_str.replace('<br>', '\n')
    note['pitch_accent'] = pitch_html
    note['kanji_info'] = kanji_info_str
    if deck_id:
        note.model()['did'] = deck_id
    mw.col.addNote(note)
    mw.reset()
    # Removed showInfo popup
    # showInfo(f"Japanese word card created for: {word}")
    return front_template.replace('{{word}}', word).replace('{{reading}}', reading).replace('{{meanings}}', meanings_str).replace('{{example sentences}}', examples_str).replace('{{pitch_accent}}', pitch_html).replace('{{kanji_info}}', kanji_info_str)

def format_pitch_pattern(pattern):
    """Convert a pitch pattern (e.g., 'LHHLL') into a standardized pattern."""
    if not pattern:
        return ""
    result = ""
    for char in pattern:
        if char == '0':
            result += 'L'
        elif char in ['1', '2']:
            result += 'H'
        else:
            result += char
    return result if result else pattern

# --- Pitch Accent SVG Generation ---
# Legacy SVG pitch accent functions removed. All SVG logic is now in pitch_svg.py.

# --- Context Menu Integration ---
def on_context_menu(webview, menu):
    selected = webview.selectedText()
    if selected and any(ord(c) > 0x3000 for c in selected):
        act = QAction('Create Japanese Word Card', menu)
        def handler():
            dlg = JapaneseWordCardCreator(mw)
            dlg.word_input.setText(selected)
            dlg.exec()
        act.triggered.connect(handler)
        menu.addAction(act)

try:
    from aqt.gui_hooks import webview_will_show_context_menu
    webview_will_show_context_menu.append(on_context_menu)
except ImportError:
    pass

# --- Add menu entry to launch the UI ---
_menu_entry_added = False  # Guard to prevent duplicate menu entries

def show_japanese_word_card_creator():
    dlg = JapaneseWordCardCreator(mw)
    dlg.exec()

def on_main_menu_add():
    global _menu_entry_added
    if _menu_entry_added:
        return
    action = QAction("Japanese Word Card Creator", mw)
    action.triggered.connect(show_japanese_word_card_creator)
    mw.form.menuTools.addAction(action)
    _menu_entry_added = True

addHook("profileLoaded", on_main_menu_add)

# --- Utility to load external template and CSS files ---
def load_file_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ''

FRONT_TEMPLATE_PATH = os.path.join(ADDON_DIR, 'front_card.html')
BACK_TEMPLATE_PATH = os.path.join(ADDON_DIR, 'back_card.html')
CSS_PATH = os.path.join(ADDON_DIR, 'css_card.css')

front_template = load_file_text(FRONT_TEMPLATE_PATH)
back_template = load_file_text(BACK_TEMPLATE_PATH)
card_css = load_file_text(CSS_PATH)

# --- Runtime Diagnostics: Measure timings for major functions ---
if __name__ == "__main__":
    import time
    timings = {}
    test_word = '可愛い'

    start = time.perf_counter()
    pitch_result = lookup_pitch_accent(test_word)
    timings['Pitch Accent Lookup'] = time.perf_counter() - start

    start = time.perf_counter()
    jmdict_result = lookup_jmdict(test_word)
    timings['JMdict Lookup'] = time.perf_counter() - start

    start = time.perf_counter()
    kanji_result = get_kanji_info_blocks(test_word)
    timings['Kanji Info Lookup'] = time.perf_counter() - start

    start = time.perf_counter()
    example_result = get_example_sentences(test_word)
    timings['Example Sentences Lookup'] = time.perf_counter() - start

    start = time.perf_counter()
    card_html = create_japanese_word_card(test_word, preview_only=True)
    timings['Card Render'] = time.perf_counter() - start

    print("\n--- Japanese Word Creator: Runtime Diagnostics ---")
    for k, v in timings.items():
        print(f"{k:28}: {v*1000:.2f} ms")
    print("--- End Diagnostics ---\n")

# --- Test case for pitch accent lookup for 生 ---
def _test_lookup_pitch_accent_for_kanji():
    print("\n--- Pitch Accent Lookup Test for '生' ---")
    results = []
    ensure_pitchdb_sqlite()
    import sqlite3
    if not os.path.exists(PITCH_DB_SQLITE_PATH):
        print("Pitch DB not found.")
        return
    conn = sqlite3.connect(PITCH_DB_SQLITE_PATH)
    c = conn.cursor()
    c.execute('SELECT kana, accented_kana, pitch_number, pattern FROM pitch_accents WHERE kanji=?', ('生',))
    for row in c.fetchall():
        kana, accented_kana, pitch_number, pattern = row
        results.append((kana, accented_kana, pitch_number, pattern))
    conn.close()
    if not results:
        print("No results found for '生'.")
    else:
        for r in results:
            print(f"kana: {r[0]}, accented_kana: {r[1]}, pitch_number: {r[2]}, pattern: {r[3]}")
    print("--- End Test ---\n")

if __name__ == "__main__":
    # ...existing code...
    _test_lookup_pitch_accent_for_kanji()
