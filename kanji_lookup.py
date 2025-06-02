from PyQt6.QtGui import QAction, QTextCursor, QPalette, QColor, QTextCharFormat, QTextObjectInterface, QImage, QPainter, QTextFormat
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSizeF, QObject, QRectF
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget, QSizePolicy
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWebEngineWidgets import QWebEngineView
import xml.etree.ElementTree as ET
import importlib.util
import os
import sys
import json
import sqlite3
import re
from aqt import gui_hooks, mw
from .pitch_svg import hira_to_mora, create_svg_pitch_pattern, create_html_pitch_pattern
from .pitch_svg import pattern_to_mora_pitch, text, circle, path, extract_unique_pitch_patterns

# --- Helper: JMdict XML lookup ---
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ADDON_DIR, 'data')
JM_DICT_XML = os.path.join(DATA_DIR, 'JMdict_e_examp.XML')
WADOKU_CSV = os.path.join(DATA_DIR, 'wadoku_pitchdb.csv')
SENTENCE_LOOKUP_PATH = os.path.join(ADDON_DIR, 'sentence_lookup.py')

# --- Load sentence_lookup.py dynamically ---
sentence_lookup = None
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

# --- JSON/SQLite DB paths ---
JMDICT_JSON_PATH = os.path.join(DATA_DIR, 'JMdict_e_examp.json')
JMDICT_SQLITE_PATH = os.path.join(DATA_DIR, 'JMdict_e_examp.sqlite')
WADOKU_JSON_PATH = os.path.join(DATA_DIR, 'wadoku_pitchdb.json')
KANJI_INFO_PATH = os.path.join(DATA_DIR, '常用漢字の書き取り.json')

# --- Kanji Info JSON ---
try:
    with open(KANJI_INFO_PATH, 'r', encoding='utf-8') as f:
        KANJI_INFO_DB = json.load(f)
except Exception:
    KANJI_INFO_DB = []

# --- JMdict XML to JSON conversion (run once) ---
def convert_jmdict_xml_to_json():
    if os.path.exists(JMDICT_JSON_PATH):
        return
    if not os.path.exists(JM_DICT_XML):
        return
    tree = ET.parse(JM_DICT_XML)
    root = tree.getroot()
    jmdict = {}
    for entry in root.findall('entry'):
        kanjis = [keb.text for k_ele in entry.findall('k_ele') for keb in k_ele.findall('keb') if keb.text]
        kanas = [reb.text for r_ele in entry.findall('r_ele') for reb in r_ele.findall('reb') if reb.text]
        meanings = []
        for sense in entry.findall('sense'):
            glosses = [g.text for g in sense.findall('gloss') if g.text]
            if glosses:
                meanings.append('; '.join(glosses))
        for key in kanjis + kanas:
            jmdict.setdefault(key, []).append({'kanjis': kanjis, 'kanas': kanas, 'meanings': meanings})
    with open(JMDICT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(jmdict, f, ensure_ascii=False)

# --- Wadoku CSV to JSON conversion (run once) ---
def convert_wadoku_csv_to_json():
    if os.path.exists(WADOKU_JSON_PATH):
        return
    if not os.path.exists(WADOKU_CSV):
        return
    entries = []
    try:
        with open(WADOKU_CSV, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip() or '\uFEFF' in line:
                    continue
                parts = line.strip().split('␞')
                if len(parts) < 5:
                    continue
                kanji_column = parts[0]
                kana_column = parts[1]
                accented_kana = parts[2]
                pitch_number = parts[3]
                pitch_pattern = parts[4]
                kanji_list = [re.sub(r'[△×…]', '', k) for k in kanji_column.split('␟') if k]
                kana_list = [re.sub(r'[△×…]', '', k) for k in kana_column.split('␟') if k]
                entries.append({
                    'kanji_list': kanji_list,
                    'kana_list': kana_list,
                    'accented_kana': accented_kana,
                    'pitch_number': pitch_number,
                    'pitch_pattern': pitch_pattern
                })
        with open(WADOKU_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# --- Ensure JSONs exist at startup ---
convert_jmdict_xml_to_json()
convert_wadoku_csv_to_json()

# --- JMdict JSON/SQLite lookup ---
_JMDICT_JSON_CACHE = None
_ensure_sqlite_ran = False

def ensure_jmdict_sqlite():
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
    except Exception:
        pass

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

# --- Wadoku Pitch Accent SQLite DB Path ---
WADOKU_SQLITE_PATH = os.path.join(DATA_DIR, 'wadoku_pitchdb.sqlite')

def ensure_wadoku_sqlite():
    """Convert wadoku_pitchdb.csv to SQLite if not present."""
    if os.path.exists(WADOKU_SQLITE_PATH):
        return
    if not os.path.exists(WADOKU_CSV):
        return
    import sqlite3
    import re
    try:
        conn = sqlite3.connect(WADOKU_SQLITE_PATH)
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
        with open(WADOKU_CSV, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip() or '\uFEFF' in line:
                    continue
                parts = line.strip().split('␞')
                if len(parts) < 5:
                    continue
                kanji_column = parts[0]
                kana_column = parts[1]
                accented_kana = parts[2]
                pitch_number = parts[3]
                pitch_pattern = parts[4]
                kanji_list = [re.sub(r'[△×…]', '', k) for k in kanji_column.split('␟') if k]
                kana_list = [re.sub(r'[△×…]', '', k) for k in kana_column.split('␟') if k]
                for kanji in kanji_list or ['']:
                    for kana in kana_list or ['']:
                        c.execute('INSERT INTO pitch_accents (kanji, kana, accented_kana, pitch_number, pattern) VALUES (?, ?, ?, ?, ?)',
                                  (kanji, kana, accented_kana, pitch_number, pitch_pattern))
        conn.commit()
        conn.close()
    except Exception:
        pass

# --- Wadoku JSON lookup (cached) ---
_WADOKU_JSON_CACHE = None
_pitch_accent_cache = {}

# --- Optimized Wadoku Pitch Accent Lookup (SQLite) ---
def lookup_pitch_accent(word):
    global _pitch_accent_cache
    if word in _pitch_accent_cache:
        return _pitch_accent_cache[word]
    ensure_wadoku_sqlite()
    entries = []
    seen = set()
    # Only use SQLite for lookup, no JSON fallback
    if os.path.exists(WADOKU_SQLITE_PATH):
        try:
            import sqlite3
            conn = sqlite3.connect(WADOKU_SQLITE_PATH)
            c = conn.cursor()
            c.execute('SELECT kana, accented_kana, pitch_number, pattern FROM pitch_accents WHERE kanji=? OR kana=?', (word, word))
            for row in c.fetchall():
                kana = row[0]
                accented_kana = row[1]
                pattern = row[3]
                dedup_key = (kana, pattern)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                entries.append({
                    'kana': kana,
                    'accented_kana': accented_kana,
                    'pattern': pattern
                })
            conn.close()
        except Exception:
            pass
    if not entries:
        result = ('', '', [], '')
    else:
        reading = entries[0]['accented_kana']
        accented_kana = entries[0]['accented_kana']
        pitch_patterns = [e['pattern'] for e in entries]
        normal_kana = entries[0]['kana']
        result = (reading, accented_kana, pitch_patterns, normal_kana)
    _pitch_accent_cache[word] = result
    return result

# --- Ensure SQLite DB is created at startup if possible ---
ensure_jmdict_sqlite()

# --- SentenceLookupThread implementation ---
class SentenceLookupThread(QThread):
    result_ready = pyqtSignal(list, list)
    def __init__(self, word):
        super().__init__()
        self.word = word
    def run(self):
        examples, related_words = lookup_sentences_and_related(self.word)
        self.result_ready.emit(examples, related_words)

# --- KanjiLookupDialog implementation ---
class PitchAccentSvgWidget(QWidget):
    def __init__(self, pitch_entries, parent=None):
        super().__init__(parent)
        self.pitch_entries = pitch_entries or []
        self.setMinimumHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)
        self.bg_color = QColor("#151618")
        self.border_color = QColor("#333")
        self.padding = 14  # px, match QTextEdit padding
        self.gap = 8  # px, gap between SVGs (reduced from 8)
        self.row_gap = 8  # px, gap between rows
        self.scroll_offset = 0  # vertical scroll offset in px
        self._update_svgs()

    def _update_svgs(self):
        self.svg_renderers = []
        self.sizes = []
        # Always use the shared SVG logic and pattern formatting
        from .__init__ import format_pitch_pattern
        unique_pitch = extract_unique_pitch_patterns(self.pitch_entries)
        for entry in unique_pitch:
            formatted_pattern = format_pitch_pattern(entry['pattern'])
            svg = create_svg_pitch_pattern(entry['kana'], formatted_pattern)
            renderer = QSvgRenderer(bytearray(svg, encoding='utf-8'))
            self.svg_renderers.append(renderer)
            size = renderer.defaultSize()
            self.sizes.append(size)
        self.scroll_offset = 0  # reset scroll on update
        self.updateGeometry()
        self.update()

    def set_pitch_entries(self, pitch_entries):
        self.pitch_entries = pitch_entries or []
        self._update_svgs()

    def sizeHint(self):
        # Responsive: estimate height based on available width and SVG sizes
        if not self.sizes:
            return super().sizeHint()
        # Use parent's width if possible, else default
        parent_width = self.parent().width() if self.parent() else 300
        w = max(200, parent_width - 2*self.padding)
        svg_widths = [s.width() for s in self.sizes]
        max_height = max((s.height() for s in self.sizes), default=90)
        # Calculate how many SVGs fit per row given available width
        if svg_widths:
            avg_svg_width = sum(svg_widths) / len(svg_widths)
        else:
            avg_svg_width = 80
        per_row = max(1, int((w + self.gap) // (avg_svg_width + self.gap)))
        n = len(self.sizes)
        rows = (n + per_row - 1) // per_row
        total_height = rows * max_height + (rows-1)*self.row_gap + 2*self.padding
        return QSizeF(parent_width, total_height).toSize()

    def minimumSizeHint(self):
        # Allow the block to shrink vertically
        return QSizeF(100, 60).toSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        # Draw background and border with padding
        bg_rect = QRectF(rect.left(), rect.top(), rect.width(), rect.height())
        painter.setBrush(self.bg_color)
        painter.setPen(QColor(self.border_color))
        painter.drawRoundedRect(bg_rect, 8, 8)
        # Content area
        x0 = rect.left() + self.padding
        y0 = rect.top() + self.padding
        w = rect.width() - 2*self.padding
        h = rect.height() - 2*self.padding
        # Responsive: fill as many SVGs per row as fit
        svg_widths = [s.width() for s in self.sizes]
        if svg_widths:
            avg_svg_width = sum(svg_widths) / len(svg_widths)
        else:
            avg_svg_width = 80
        per_row = max(1, int((w + self.gap) // (avg_svg_width + self.gap)))
        n = len(self.svg_renderers)
        x = x0
        y = y0 - self.scroll_offset  # apply scroll offset
        row_max_height = 0
        count = 0
        for i, renderer in enumerate(self.svg_renderers):
            size = self.sizes[i]
            if count == per_row:
                x = x0
                y += row_max_height + self.row_gap
                row_max_height = 0
                count = 0
            svg_rect = QRectF(x, y, size.width(), size.height())
            # Only draw if visible (for perf, optional)
            if svg_rect.bottom() >= y0 and svg_rect.top() <= y0 + h:
                renderer.render(painter, svg_rect)
            x += size.width() + self.gap
            row_max_height = max(row_max_height, size.height())
            count += 1

    def resizeEvent(self, event):
        self.updateGeometry()
        self.update()

    def wheelEvent(self, event):
        # Scroll by 3 lines per wheel step, like QTextEdit (usually 20 px per line)
        lines_per_step = 3
        px_per_line = 20
        delta = event.angleDelta().y()  # 120 per step
        scroll_amount = int((delta / 120) * lines_per_step * px_per_line)
        # Compute max scroll
        content_height = self._content_height()
        viewport_height = self.height() - 2*self.padding
        max_scroll = max(0, content_height - viewport_height)
        self.scroll_offset = min(max(self.scroll_offset - scroll_amount, 0), max_scroll)
        self.update()
        event.accept()

    def _content_height(self):
        # Calculate total content height (like sizeHint, but for scrolling)
        if not self.sizes:
            return 0
        rect = self.rect()
        w = rect.width() - 2*self.padding
        svg_widths = [s.width() for s in self.sizes]
        max_height = max((s.height() for s in self.sizes), default=90)
        if svg_widths:
            avg_svg_width = sum(svg_widths) / len(svg_widths)
        else:
            avg_svg_width = 80
        per_row = max(1, int((w + self.gap) // (avg_svg_width + self.gap)))
        n = len(self.sizes)
        rows = (n + per_row - 1) // per_row
        total_height = rows * max_height + (rows-1)*self.row_gap
        return total_height

class KanjiLookupDialog(QDialog):
    def __init__(self, word, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dictionary Lookup")
        self.resize(850, 600)
        self.setStyleSheet("""
            QDialog { background: #202124; }
            QLabel#head { font-size: 28px; font-weight: bold; }
            QLabel#reading { font-size: 20px; color: #bcd; }
            QLabel.section { font-size: 20px; font-weight: bold; }
        """)
        self.setModal(True)
        outer_layout = QVBoxLayout(self)
        self.head = QLabel(word)
        self.head.setObjectName("head")
        entries = lookup_jmdict(word)
        reading, accented_kana, pitch_patterns, normal_kana = lookup_pitch_accent(word)
        if not reading:
            entries = lookup_jmdict(word)
            readings = ", ".join([k for entry in entries for k in entry['kanas']])
        else:
            readings = reading
        # Collect all unique accented kana readings for display
        pitch_entries = []
        seen = set()
        accented_kana_list = []
        if os.path.exists(WADOKU_SQLITE_PATH):
            try:
                conn = sqlite3.connect(WADOKU_SQLITE_PATH)
                c = conn.cursor()
                c.execute('SELECT kana, accented_kana, pattern FROM pitch_accents WHERE kanji=? OR kana=?', (word, word))
                for row in c.fetchall():
                    kana = row[0]
                    accented_kana = row[1]
                    pattern = row[2]
                    dedup_key = (kana, pattern)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    pitch_entries.append({'kana': kana, 'pattern': pattern, 'accented_kana': accented_kana})
                    if accented_kana and accented_kana not in accented_kana_list:
                        accented_kana_list.append(accented_kana)
                conn.close()
            except Exception:
                pass
        if not pitch_entries:
            for i, pattern in enumerate(pitch_patterns):
                dedup_key = (normal_kana, pattern)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                pitch_entries.append({'kana': normal_kana, 'pattern': pattern, 'accented_kana': accented_kana})
                if accented_kana and accented_kana not in accented_kana_list:
                    accented_kana_list.append(accented_kana)
        # Final deduplication in case of any remaining duplicates
        unique_entries = []
        seen_final = set()
        for entry in pitch_entries:
            dedup_key = (entry['kana'], entry['pattern'])
            if dedup_key in seen_final:
                continue
            seen_final.add(dedup_key)
            unique_entries.append(entry)
        # --- Return accented kana list ---
        if accented_kana_list:
            readings = ', '.join(accented_kana_list)
        else:
            readings = reading
        self.reading = QLabel(readings)
        self.reading.setObjectName("reading")
        mid_layout = QHBoxLayout()
        meanings_label = QLabel("Meanings")
        meanings_label.setProperty("class", "section")
        meanings_te = QTextEdit()
        meanings_te.setReadOnly(True)
        meanings_te.setStyleSheet("""
            QTextEdit {
                background: #151618;
                color: #dadada;
                border: 1px solid #333;
                font-size: 18px;
                padding: 14px 16px 14px 16px;
                border-radius: 8px;
            }
            QTextEdit QScrollBar:vertical, QTextEdit QScrollBar:horizontal {
                width: 0px;
                height: 0px;
                background: transparent;
            }
        """)
        meanings = []
        for entry in entries:
            for m in entry["meanings"]:
                meanings.append(m)
        meanings_te.setHtml('<br>'.join(f"<div>{m}</div>" for m in meanings))
        pitch_label = QLabel("Pitch Accent")
        pitch_label.setProperty("class", "section")
        # --- Replace QWebEngineView with PitchAccentSvgWidget ---
        pitch_entries = []
        seen = set()
        if os.path.exists(WADOKU_SQLITE_PATH):
            try:
                conn = sqlite3.connect(WADOKU_SQLITE_PATH)
                c = conn.cursor()
                c.execute('SELECT kana, accented_kana, pattern FROM pitch_accents WHERE kanji=? OR kana=?', (word, word))
                for row in c.fetchall():
                    kana = row[0]
                    accented_kana = row[1]
                    pattern = row[2]
                    dedup_key = (kana, pattern)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    pitch_entries.append({'kana': kana, 'pattern': pattern, 'accented_kana': accented_kana})
                conn.close()
            except Exception:
                pass
        if not pitch_entries:
            for i, pattern in enumerate(pitch_patterns):
                dedup_key = (normal_kana, pattern)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                pitch_entries.append({'kana': normal_kana, 'pattern': pattern, 'accented_kana': accented_kana})
        # Final deduplication in case of any remaining duplicates
        unique_entries = []
        seen_final = set()
        for entry in pitch_entries:
            dedup_key = (entry['kana'], entry['pattern'])
            if dedup_key in seen_final:
                continue
            seen_final.add(dedup_key)
            unique_entries.append(entry)
        self.pitch_svg_widget = PitchAccentSvgWidget(unique_entries)
        examples_label = QLabel("Examples")
        examples_label.setProperty("class", "section")
        self.examples_te = QTextEdit()
        self.examples_te.setReadOnly(True)
        self.examples_te.setStyleSheet("""
            QTextEdit {
                background: #151618;
                color: #dadada;
                border: 1px solid #333;
                font-size: 18px;
                padding: 14px 16px 14px 16px;
                border-radius: 8px;
            }
            QTextEdit QScrollBar:vertical, QTextEdit QScrollBar:horizontal {
                width: 0px;
                height: 0px;
                background: transparent;
            }
        """)
        related_label = QLabel("Related Words")
        related_label.setProperty("class", "section")
        self.related_te = QTextEdit()
        self.related_te.setReadOnly(True)
        self.related_te.setStyleSheet("""
            QTextEdit {
                background: #151618;
                color: #dadada;
                border: 1px solid #333;
                font-size: 18px;
                padding: 14px 16px 14px 16px;
                border-radius: 8px;
            }
            QTextEdit QScrollBar:vertical, QTextEdit QScrollBar:horizontal {
                width: 0px;
                height: 0px;
                background: transparent;
            }
        """)
        examples, related_words = self._load_examples_from_json(word)
        if examples or related_words:
            self.examples_te.setHtml('<br><br>'.join(f"<div>{jp}<br>{en}</div>" for jp, en in examples))
            self.related_te.setHtml('<br>'.join(f"<div>{w} {t}</div>" for w, t in related_words))
        else:
            self.examples_te.setHtml('<i>Loading...</i>')
            self.related_te.setHtml('<i>Loading...</i>')
            self._start_sentence_lookup(word)
        left_layout = QVBoxLayout()
        left_layout.addWidget(meanings_label)
        left_layout.addWidget(meanings_te)
        left_layout.addWidget(pitch_label)
        left_layout.addWidget(self.pitch_svg_widget)
        right_layout = QVBoxLayout()
        right_layout.addWidget(examples_label)
        right_layout.addWidget(self.examples_te)
        right_layout.addWidget(related_label)
        right_layout.addWidget(self.related_te)
        left_layout.setStretch(0, 0)
        left_layout.setStretch(1, 1)
        left_layout.setStretch(2, 0)
        left_layout.setStretch(3, 1)
        right_layout.setStretch(0, 0)
        right_layout.setStretch(1, 1)
        right_layout.setStretch(2, 0)
        right_layout.setStretch(3, 1)
        mid_layout.addLayout(left_layout, 1)
        mid_layout.addLayout(right_layout, 1)
        outer_layout.addWidget(self.head)
        outer_layout.addWidget(self.reading)
        outer_layout.addLayout(mid_layout)
        # --- Enable text selection and re-lookup ---
        for box in [meanings_te, self.examples_te, self.related_te]:
            box.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            box.customContextMenuRequested.connect(self._show_context_menu)

    def _register_svg_text_object(self):
        # Register SvgTextObject handler for pitch_te
        handler = SvgTextObject(self.pitch_te)
        self.pitch_te.document().documentLayout().registerHandler(9, handler)

    def _set_pitch_svgs(self, pitch_entries):
        self.pitch_te.clear()
        cursor = self.pitch_te.textCursor()
        if not pitch_entries:
            self.pitch_te.setHtml('<div class="pitch-block" style="color:#dadada;">No pitch accent found.</div>')
            return
        # Add background block
        cursor.insertHtml('<div class="pitch-block" style="background:#151618;padding:14px 16px 14px 16px;">')
        # --- Inline SVG rendering for comparison (displays above the current QImage pitch accents) ---
        if pitch_entries:
            svg_block = ''
            for p in pitch_entries:
                kana = p['kana']
                pattern = p['pattern']
                if kana and pattern and len(kana) > 0 and len(pattern) > 0:
                    svg = create_svg_pitch_pattern(kana, pattern)
                    svg_block += f'<div style="display:inline-block;vertical-align:middle;">{svg}</div>'
            # Compose a full HTML document for SVG rendering
            svg_html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ background: #151618; color: #dadada; margin: 0; }}
.pitch-block {{ background:#151618;padding:14px 16px 14px 16px; }}
</style>
</head>
<body><div class="pitch-block">{svg_block}</div></body>
</html>'''
            self.pitch_te.setHtml(svg_html)
            cursor = self.pitch_te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        for idx, p in enumerate(pitch_entries):
            kana = p['kana']
            pattern = p['pattern']
            if kana and pattern and len(kana) > 0 and len(pattern) > 0:
                try:
                    svg = create_svg_pitch_pattern(kana, pattern)
                    renderer = QSvgRenderer(bytearray(svg, encoding='utf-8'))
                    size = renderer.defaultSize() * 2
                    image = QImage(size, QImage.Format.Format_ARGB32)
                    # Fill with SVG background color instead of transparent
                    image.fill(QColor("#20242b"))
                    painter = QPainter(image)
                    # Ensure SVG fills the entire QImage so background is visible
                    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
                    painter.end()
                    fmt = QTextCharFormat()
                    fmt.setObjectType(9)
                    fmt.setProperty(1, image)  # SvgData
                    cursor.insertText(chr(0xfffc), fmt)
                except Exception:
                    pass
        cursor.insertHtml('</div>')
        self.pitch_te.setTextCursor(cursor)
        # Always scroll to the top after rendering pitch accents
        self.pitch_te.moveCursor(QTextCursor.MoveOperation.Start)
        self.pitch_te.verticalScrollBar().setValue(0)

    def _load_examples_from_json(self, word):
        json_path = os.path.join(ADDON_DIR, 'kanji_examples.json')
        if not os.path.exists(json_path):
            return [], []
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            entry = data.get(word)
            if entry:
                examples = entry.get('examples', [])
                related = entry.get('related_words', [])
                return examples, related
        except Exception:
            pass
        return [], []

    def _start_sentence_lookup(self, word):
        self.sentence_thread = SentenceLookupThread(word)
        self.sentence_thread.result_ready.connect(self._on_sentence_lookup_done)
        self.sentence_thread.start()

    def _on_sentence_lookup_done(self, examples, related_words):
        self.examples_te.setHtml('<br><br>'.join(f"<div>{jp}<br>{en}</div>" for jp, en in examples))
        self.related_te.setHtml('<br>'.join(f"<div>{w} {t}</div>" for w, t in related_words))
        # --- Context menu integration for Anki browser ---
    def _show_context_menu(self, pos):
        box = self.sender()
        cursor = box.cursorForPosition(pos)
        selected_text = box.textCursor().selectedText()
        menu = box.createStandardContextMenu()
        if selected_text and any(ord(c) > 0x3000 for c in selected_text):
            menu.addSeparator()
            lookup_action = menu.addAction('Kanji Lookup')
            def do_lookup():
                KanjiLookupDialog(selected_text, parent=self).exec()
            lookup_action.triggered.connect(do_lookup)
        menu.exec(box.mapToGlobal(pos))

class SvgTextObject(QObject, QTextObjectInterface):
    def intrinsicSize(self, doc, posInDocument, format):
        image = format.property(1)  # SvgData
        if isinstance(image, QImage):
            size = image.size() * 0.45
            # if size.height() > 75:
            #     size = size * (75.0 / float(size.height()))
            return QSizeF(size)
        return QSizeF(0, 0)

    def drawObject(self, painter, rect, doc, posInDocument, format):
        image = format.property(1)  # SvgData
        if isinstance(image, QImage):
            painter.drawImage(rect, image)

def on_browser_context_menu(browser, menu):
    selected_text = browser.editor.web.selectedText() if hasattr(browser, 'editor') and browser.editor else None
    if not selected_text:
        # fallback: try first field of first selected note
        selected = browser.selectedNotes()
        if not selected:
            return
        note = browser.mw.col.getNote(selected[0])
        if not note:
            return
        fields = list(note.values())
        if not fields:
            return
        selected_text = fields[0]
    action = menu.addAction('Kanji Lookup')
    def handler():
        KanjiLookupDialog(selected_text, parent=browser).exec()
    action.triggered.connect(handler)

gui_hooks.browser_will_show_context_menu.append(on_browser_context_menu)

# --- Context menu integration for Kanji Lookup in webviews ---
def on_webview_context_menu(webview, menu):
    selected = webview.selectedText()
    if selected and any(ord(c) > 0x3000 for c in selected):
        action = menu.addAction('Kanji Lookup')
        def handler():
            KanjiLookupDialog(selected, parent=webview.window()).exec()
        action.triggered.connect(handler)

gui_hooks.webview_will_show_context_menu.append(on_webview_context_menu)

def show_kanji_lookup_dialog():
    # Get selected text from the current webview (browser/editor/reviewer)
    webview = mw.web if hasattr(mw, 'web') else None
    if webview is None:
        # Try to get the active window's webview
        try:
            webview = mw.app.activeWindow().findChild(QWidget, 'web')
        except Exception:
            webview = None
    selected = None
    if webview and hasattr(webview, 'selectedText'):
        selected = webview.selectedText()
    if not selected:
        # fallback: try first field of first selected note in browser
        try:
            browser = mw.form.browser
            selected_notes = browser.selectedNotes()
            if selected_notes:
                note = mw.col.getNote(selected_notes[0])
                if note:
                    fields = list(note.values())
                    if fields:
                        selected = fields[0]
        except Exception:
            pass
    if selected:
        dlg = KanjiLookupDialog(selected, parent=mw)
        dlg.exec()
    else:
        from aqt.utils import showInfo
        showInfo("No Japanese word selected.")

_menu_entry_added = False

def on_main_menu_add():
    global _menu_entry_added
    if _menu_entry_added:
        return
    action = QAction("Kanji Lookup (Selected Word)", mw)
    action.triggered.connect(show_kanji_lookup_dialog)
    mw.form.menuTools.addAction(action)
    _menu_entry_added = True

# --- Accented Kana Normalization and Frequency Lookup ---
def accented_kana_to_katakana(accented_kana):
    # Remove pitch accent marks (e.g., '＼', '／', etc.) and convert to katakana
    hira = accented_kana
    # Remove pitch accent marks (common: '＼', '／', 'ˉ', 'ˊ', 'ˋ', etc.)
    hira = re.sub(r'[＼／ˉˊˋ˘˙]', '', hira)
    # Convert hiragana to katakana
    hira = hira.replace('ゔ', 'う゛')  # handle voiced u
    kata = ''
    for ch in hira:
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:  # hiragana
            kata += chr(code + 0x60)
        else:
            kata += ch
    return kata

def create_svg_pitch_pattern(word, patt):
    # If multiple patterns are present, use only the first
    if ',' in str(patt):
        patt = str(patt).split(',')[0].strip()
    mora = hira_to_mora(word)
    pitch_groups = pattern_to_mora_pitch(patt, mora)
    if not pitch_groups or len(pitch_groups) != len(mora) + 1:
        # fallback to old logic
        if len(patt) < len(mora) + 1:
            last_char = patt[-1]
            patt = patt + (last_char * (len(mora) + 1 - len(patt)))
        elif len(patt) > len(mora) + 1:
            patt = patt[:len(mora) + 1]
        pitch_groups = list(patt)
    positions = len(pitch_groups)
    step_width = 35
    margin_lr = 16
    padding = 12  # px, space between SVG edge and background rect
    pattern_gap = 2  # px, right padding
    vertical_gap = 2  # px, bottom badding
    content_width = max(0, ((positions-1) * step_width) + (margin_lr*2))
    content_height = 65
    svg_width = content_width + padding*2 + pattern_gap
    svg_height = content_height + padding*2 + vertical_gap
    # Add a background rect to ensure background is always visible, with padding
    svg = ('<svg class="pitch" width="{0}px" height="{1}px" viewBox="0 0 {0} {1}">'.format(svg_width, svg_height))
    svg += '<rect x="0" y="0" width="{0}" height="{1}" rx="8" fill="#20242b"/>'.format(svg_width, svg_height)
    # Add mora characters
    chars = ''
    for pos, mor in enumerate(mora):
        x_center = padding + margin_lr + (pos * step_width)
        chars += text(x_center-11, mor)
    # Add circles and connecting paths
    circles = ''
    paths = ''
    prev_center = (None, None)
    for pos, accent in enumerate(pitch_groups):
        x_center = padding + margin_lr + (pos * step_width)
        a = accent[0] if accent else 'L'
        if a in ['H', 'h', '1', '2']:
            y_center = padding + 5
        elif a in ['L', 'l', '0']:
            y_center = padding + 30
        else:
            y_center = padding + 30
        circles += circle(x_center, y_center, pos >= len(mora))
        if pos > 0:
            if prev_center[1] == y_center:
                path_typ = 's'
            elif prev_center[1] < y_center:
                path_typ = 'd'
            elif prev_center[1] > y_center:
                path_typ = 'u'
            paths += path(prev_center[0], prev_center[1], path_typ, step_width)
        prev_center = (x_center, y_center)
    svg += chars
    svg += paths
    svg += circles
    svg += '</svg>'
    return svg
