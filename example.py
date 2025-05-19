# -*- coding: utf-8 -*-
import os
import xml.etree.ElementTree as ET
import re
import csv
from aqt.qt import *
from aqt import mw
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QThread, pyqtSignal
import sys
import os
from PyQt6.QtCore import Qt as QtCoreQt
from PyQt6.QtGui import QTextCursor

# Ensure the add-on directory is in sys.path for module import
addon_dir = os.path.dirname(os.path.abspath(__file__))
if addon_dir not in sys.path:
    sys.path.insert(0, addon_dir)

from sentence_lookup import lookup_sentences_and_related

# Path to your JMdict_e_examp.xml file (edit as needed)
JM_DICT_PATH = r"C:\Users\kouda\AppData\Roaming\Anki2\addons21\kanji_lookup\JMdict_e_examp.xml"
# Path to your pitch accent database
PITCH_DB_PATH = r"C:\Users\kouda\AppData\Roaming\Anki2\addons21\kanji_lookup\wadoku_pitchdb.csv"

# --- 1. Build the in-memory index at load time for fast lookups ---

# We'll index by both kanji and kana
_JMDICT_INDEX = {}
# Pitch accent dictionary mapping kana to pitch pattern
_PITCH_ACCENT_INDEX = {}

def build_jmdict_index():
    print("Building JMdict index for fast lookup...")
    tree = ET.parse(JM_DICT_PATH)
    root = tree.getroot()
    count = 0
    for entry in root.findall("entry"):
        kanjis = [keb.text for k_ele in entry.findall("k_ele") for keb in k_ele.findall("keb") if keb.text]
        kanas = [reb.text for r_ele in entry.findall("r_ele") for reb in r_ele.findall("reb") if reb.text]

        entry_obj = {
            "kanjis": kanjis,
            "kanas": kanas,
            "meanings": [],
            "examples": []
        }

        for sense in entry.findall("sense"):
            entry_obj["meanings"].extend([gloss.text for gloss in sense.findall("gloss") if gloss.text])
            for example in sense.findall("example"):
                jp = ""
                en = ""
                for ex_sent in example.findall("ex_sent"):
                    lang = ex_sent.attrib.get('{http://www.w3.org/XML/1998/namespace}lang', '')
                    if lang == "jpn":
                        jp = ex_sent.text
                    elif lang == "eng":
                        en = ex_sent.text
                if jp or en:
                    entry_obj["examples"].append((jp, en))

        for key in kanjis + kanas:
            if key not in _JMDICT_INDEX:
                _JMDICT_INDEX[key] = []
            _JMDICT_INDEX[key].append(entry_obj)
        count += 1
    print(f"JMdict index built. Indexed entries: {count}")
    
def build_pitch_accent_index():
    """Build an in-memory index of pitch accent patterns from the wadoku_pitchdb.csv file."""
    print("Building pitch accent index...")
    if not os.path.exists(PITCH_DB_PATH):
        print(f"Warning: Pitch accent database not found at {PITCH_DB_PATH}")
        return

    try:
        with open(PITCH_DB_PATH, 'r', encoding='utf-8') as f:
            # Skip the first line (header/comment)
            next(f, None)

            for line in f:
                try:
                    # Parse line using split on ␞ delimiter
                    parts = line.strip().split('␞')
                    if len(parts) < 5:
                        continue

                    # Extract all columns
                    kanji_column = parts[0]
                    kana_column = parts[1]
                    accented_kana = parts[2]
                    pitch_number = parts[3]
                    pitch_pattern = parts[4]

                    # Split kanji and kana columns by ␟ and clean up marks (△, ×, …)
                    kanji_list = [re.sub(r'[△×…]', '', k) for k in kanji_column.split('␟') if k]
                    kana_list = [re.sub(r'[△×…]', '', k) for k in kana_column.split('␟') if k]

                    for kanji in kanji_list:
                        if kanji not in _PITCH_ACCENT_INDEX:
                            _PITCH_ACCENT_INDEX[kanji] = []
                        for kana in kana_list:
                            pitch_entry = {
                                "kana": kana,
                                "accented_kana": accented_kana,
                                "pitch_number": pitch_number,
                                "pattern": pitch_pattern
                            }
                            if pitch_entry not in _PITCH_ACCENT_INDEX[kanji]:
                                _PITCH_ACCENT_INDEX[kanji].append(pitch_entry)

                except Exception as e:
                    print(f"Error parsing pitch accent line: {e}")
    except Exception as e:
        print(f"Error reading pitch accent database: {e}")

    print(f"Pitch accent index built. Indexed entries: {len(_PITCH_ACCENT_INDEX)}")

def format_pitch_pattern(pattern):
    """Convert a pitch pattern (e.g., 'LHHLL') into a standardized pattern.
    Some patterns might use numbers (0, 1, 2) instead of letters.
    """
    if not pattern:
        return ""
    
    # Standardize pattern format if numbers are used
    result = ""
    for char in pattern:
        if char == '0':
            result += 'L'  # 0 = Low
        elif char in ['1', '2']:
            result += 'H'  # 1, 2 = High
        else:
            result += char
    
    return result if result else pattern

def get_pitch_accent(reading):
    """Get the pitch accent pattern for a reading."""
    patterns = _PITCH_ACCENT_INDEX.get(reading, [])
    return patterns  # Patterns are already formatted when added to the index

def fast_lookup(word):
    "Get list of entries for a word from the index."
    return _JMDICT_INDEX.get(word, [])

if not os.path.exists(JM_DICT_PATH):
    print(f"Warning: Dictionary file not found at {JM_DICT_PATH}. Lookup will fail.")
else:
    build_jmdict_index()
    # Build the pitch accent index after building the jmdict index
    build_pitch_accent_index()

# --- 2. Better UI with QTextEdit for Padding, No Selection, Perfect Readability ---

class GooLookupThread(QThread):
    result_ready = pyqtSignal(list, list)
    def __init__(self, word):
        super().__init__()
        self.word = word
    def run(self):
        from sentence_lookup import lookup_sentences_and_related
        examples, related = lookup_sentences_and_related(self.word)
        self.result_ready.emit(examples, related)

class KanjiLookupDialog(QDialog):
    def __init__(self, word, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dictionary Lookup")
        self.setMinimumWidth(900)
        self.setMinimumHeight(400)
        self.setStyleSheet("""
            QLabel#head { font-size: 28px; font-weight: bold; }
            QLabel#reading { font-size: 20px; color: #bcd; }
            QLabel.section { font-size: 20px; font-weight: bold; }
        """)
        self.setModal(True)
        outer_layout = QVBoxLayout(self)

        # Headings
        self.head = QLabel(word)
        self.head.setObjectName("head")
        entries = fast_lookup(word)
        readings = ", ".join([k for entry in entries for k in entry['kanas']])
        self.reading = QLabel(readings)
        self.reading.setObjectName("reading")

        # --- UI widgets for meanings/examples/related ---
        meanings_label = QLabel("Meanings")
        meanings_label.setProperty("class", "section")
        examples_label = QLabel("Examples")
        examples_label.setProperty("class", "section")
        related_label = QLabel("Related Words")
        related_label.setProperty("class", "section")

        meanings_te = QTextEdit()
        meanings_te.setReadOnly(True)
        meanings_te.setCursorWidth(0)
        meanings_te.setStyleSheet("""
            QTextEdit {
                background: #18191a;
                color: #dadada;
                border: 1px solid #444;
                font-size: 18px;
                padding: 14px 16px 14px 16px;
                min-height: 200px;
            }
        """)
        examples_te = QTextEdit()
        examples_te.setReadOnly(True)
        examples_te.setCursorWidth(0)
        examples_te.setStyleSheet("""
            QTextEdit {
                background: #18191a;
                color: #dadada;
                border: 1px solid #444;
                font-size: 18px;
                padding: 14px 16px 14px 16px;
                min-height: 200px;
            }
        """)
        related_te = QTextEdit()
        related_te.setReadOnly(True)
        related_te.setCursorWidth(0)
        related_te.setStyleSheet("""
            QTextEdit {
                background: #18191a;
                color: #dadada;
                border: 1px solid #444;
                font-size: 18px;
                padding: 14px 16px 14px 16px;
                min-height: 200px;
            }
        """)

        # Populate meanings (from JMdict)
        meanings = []
        for entry in entries:
            for m in entry["meanings"]:
                meanings.append(m)
        meanings_te.setHtml('<br>'.join(f"<div>{m}</div>" for m in meanings))

        # Populate examples/related with loading message
        examples_te.setHtml("<div style='color:#888'>Loading...</div>")
        related_te.setHtml("<div style='color:#888'>Loading...</div>")

        # Create pitch accent section
        pitch_label = QLabel("Pitch Accent")
        pitch_label.setProperty("class", "section")
        pitch_web_view = QWebEngineView()
        pitch_web_view.setStyleSheet("""
                QWebEngineView {
                    background: #18191a;
                    border: 1px solid #444;
                    padding: 14px 16px 14px 16px;
                    min-height: 100px;
                }
            """)

        pitch_blocks = []
        for entry in entries:
            for reading in entry["kanas"]:
                for kanji, pitch_data_list in _PITCH_ACCENT_INDEX.items():
                    if kanji == word:
                        for pitch_data in pitch_data_list:
                            if pitch_data["kana"] == reading:
                                svg = create_html_pitch_pattern(reading, pitch_data["pattern"])
                                pitch_blocks.append(svg)

        if pitch_blocks:
            pitch_html = f"""
            <!DOCTYPE html>
            <html lang=\"en\">
            <head>
                <meta charset=\"UTF-8\">
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
                <title>Pitch Accent</title>
            </head>
            <body style=\"background-color:#18191a; color:#fff; display: flex; flex-wrap: wrap; gap: 10px;\">
                {''.join(pitch_blocks)}
            </body>
            </html>
            """
            pitch_web_view.setHtml(pitch_html)
        else:
            pitch_web_view.setHtml("""
            <!DOCTYPE html>
            <html lang=\"en\">
            <head>
                <meta charset=\"UTF-8\">
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
                <title>Pitch Accent</title>
            </head>
            <body style=\"background-color:#18191a; color:#fff; display: flex; flex-wrap: wrap; gap: 10px;\">
            </body>
            </html>
            """)

        # Layouts
        mlayout = QVBoxLayout()
        mlayout.addWidget(meanings_label)
        mlayout.addWidget(meanings_te)
        elayout = QVBoxLayout()
        elayout.addWidget(examples_label)
        elayout.addWidget(examples_te)
        playout = QVBoxLayout()
        playout.addWidget(pitch_label)
        playout.addWidget(pitch_web_view)
        rlayout = QVBoxLayout()
        rlayout.addWidget(related_label)
        rlayout.addWidget(related_te)

        # Set stretch factors for equal sizing
        mid_layout = QHBoxLayout()
        mid_layout.addLayout(mlayout, 1)
        mid_layout.addLayout(elayout, 1)

        bottom_layout = QHBoxLayout()
        bottom_layout.addLayout(playout, 1)
        bottom_layout.addLayout(rlayout, 1)

        outer_layout.addWidget(self.head)
        outer_layout.addWidget(self.reading)
        outer_layout.addLayout(mid_layout)
        outer_layout.addLayout(bottom_layout)
        # No close button

        # Start background thread for goo lookup
        self.goo_thread = GooLookupThread(word)
        self.goo_thread.result_ready.connect(lambda examples, related: self.update_goo_results(examples_te, related_te, examples, related))
        self.goo_thread.start()

        # Enable context menu for meanings_te, examples_te, related_te
        for te in [meanings_te, examples_te, related_te]:
            te.setContextMenuPolicy(QtCoreQt.ContextMenuPolicy.CustomContextMenu)
            te.customContextMenuRequested.connect(lambda pos, te=te: self.show_custom_context_menu(te, pos))
            te.setTextInteractionFlags(QtCoreQt.TextInteractionFlag.TextSelectableByMouse | QtCoreQt.TextInteractionFlag.TextSelectableByKeyboard | QtCoreQt.TextInteractionFlag.TextEditable)

    def show_custom_context_menu(self, te, pos):
        cursor = te.cursorForPosition(pos)
        te.setFocus()
        if not te.textCursor().hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            te.setTextCursor(cursor)
        selected_text = te.textCursor().selectedText()
        menu = te.createStandardContextMenu()
        if selected_text and any(ord(c) > 0x3000 for c in selected_text):
            action = menu.addAction("Lookup Japanese Word")
            action.triggered.connect(lambda: self.lookup_selected_word(selected_text))
        menu.exec(te.mapToGlobal(pos))

    def lookup_selected_word(self, word):
        dialog = KanjiLookupDialog(word, self)
        dialog.exec()

    def update_goo_results(self, examples_te, related_te, goo_examples, goo_related):
        # Populate examples (from goo)
        if goo_examples:
            example_blocks = [f"<div>{jp}<br><span style='color:#bbb'>{en}</span></div>" for jp, en in goo_examples]
            examples_te.setHtml("<br>".join(example_blocks))
        else:
            examples_te.setHtml("<div style='color:#888'>No examples found.</div>")
        # Populate related words (from goo)
        if goo_related:
            related_blocks = [f"<div><b>{w}</b><br><span style='color:#bbb'>{t}</span></div>" for w, t in goo_related]
            related_te.setHtml("<br>".join(related_blocks))
        else:
            related_te.setHtml("<div style='color:#888'>No related words found.</div>")

# -- Hook into Anki webview context menu

def add_context_menu(webview, menu):
    selected_text = webview.selectedText()
    if selected_text and any(ord(c) > 0x3000 for c in selected_text):
        action = menu.addAction("Lookup Japanese Word")
        action.triggered.connect(lambda _, w=webview: on_lookup_action(w))

def on_lookup_action(webview):
    selected_text = webview.selectedText()
    if selected_text:
        parent = mw.app.activeWindow()
        dialog = KanjiLookupDialog(selected_text, parent)
        dialog.exec()

from aqt.gui_hooks import webview_will_show_context_menu
webview_will_show_context_menu.append(add_context_menu)

def hira_to_mora(hira):
    """Convert hiragana string to mora array.
    Example: 'しゅんかしゅうとう' → ['しゅ', 'ん', 'か', 'しゅ', 'う', 'と', 'う']
    """
    mora_arr = []
    combiners = ['ゃ', 'ゅ', 'ょ', 'ぁ', 'ぃ', 'ぅ', 'ぇ', 'ぉ',
                 'ャ', 'ュ', 'ョ', 'ァ', 'ィ', 'ゥ', 'ェ', 'ォ']

    i = 0
    while i < len(hira):
        if i+1 < len(hira) and hira[i+1] in combiners:
            mora_arr.append('{}{}'.format(hira[i], hira[i+1]))
            i += 2
        else:
            mora_arr.append(hira[i])
            i += 1
    return mora_arr



def circle(x, y, o=False):
    """Create an SVG circle element at (x,y), with optional center."""
    if o:
        # Final mora: white dot with black outline
        return (
            '<circle r="5" cx="{}" cy="{}" style="fill:#fff;stroke:#000;stroke-width:1.5;" />'
        ).format(x, y)
    else:
        # Regular mora: black dot
        return (
            '<circle r="5" cx="{}" cy="{}" style="fill:#000;" />'
        ).format(x, y)

def text(x, mora):
    """Create an SVG text element for a mora."""
    # letter positioning tested with Noto Sans CJK JP
    if len(mora) == 1:
        return ('<text x="{}" y="67.5" style="font-size:20px;font-family:sans-'
                'serif;fill:#fff;">{}</text>').format(x, mora)
    else:
        return ('<text x="{}" y="67.5" style="font-size:20px;font-family:sans-'
                'serif;fill:#fff;">{}</text><text x="{}" y="67.5" style="font-'
                'size:14px;font-family:sans-serif;fill:#fff;">{}</text>'
                ).format(x-5, mora[0], x+12, mora[1])

def path(x, y, typ, step_width):
    """Create an SVG path element for a pitch line."""
    if typ == 's':  # straight
        delta = '{},0'.format(step_width)
    elif typ == 'u':  # up
        delta = '{},-25'.format(step_width)
    elif typ == 'd':  # down
        delta = '{},25'.format(step_width)
    return (
        '<path d="m {},{} {}" style="fill:none;stroke:#00f;stroke-width:1.5;" />'
    ).format(x, y, delta)

def create_html_pitch_pattern(reading, pattern):
    """Create an SVG-based visualization of the pitch accent pattern."""
    # Use the SVG implementation for pitch accent visualization
    svg = create_svg_pitch_pattern(reading, pattern)

    # Wrap the SVG in a div for embedding as inline HTML
    return f'<div>{svg}</div>'

def create_svg_pitch_pattern(word, patt):
    """Draw pitch accent patterns in SVG.
    
    Examples:
        はし HLL (箸)
        はし LHL (橋)
        はし LHH (端)
    """
    mora = hira_to_mora(word)
    
    # Ensure pattern length matches mora + 1
    if len(patt) < len(mora) + 1:
        # Extend pattern if needed
        last_char = patt[-1]
        patt = patt + (last_char * (len(mora) + 1 - len(patt)))
    elif len(patt) > len(mora) + 1:
        # Truncate pattern if needed
        patt = patt[:len(mora) + 1]
    
    positions = max(len(mora), len(patt))
    step_width = 35
    margin_lr = 16
    svg_width = max(0, ((positions-1) * step_width) + (margin_lr*2))

    svg = ('<svg class="pitch" width="{0}px" height="75px" viewBox="0 0 {0} 75" '
           'style="background-color:#20242b; border-radius:4px; padding:2px;">').format(svg_width)

    # Add mora characters
    chars = ''
    for pos, mor in enumerate(mora):
        x_center = margin_lr + (pos * step_width)
        chars += text(x_center-11, mor)

    # Add circles and connecting paths
    circles = ''
    paths = ''
    prev_center = (None, None)
    
    for pos, accent in enumerate(patt):
        x_center = margin_lr + (pos * step_width)
        if accent in ['H', 'h', '1', '2']:
            y_center = 5  # High position
        elif accent in ['L', 'l', '0']:
            y_center = 30  # Low position
        else:
            # Default to low for unknown characters
            y_center = 30
            
        # Add circle, with open center for position after last mora
        circles += circle(x_center, y_center, pos >= len(mora))
        
        # Add connecting path if not the first position
        if pos > 0:
            if prev_center[1] == y_center:
                path_typ = 's'  # straight line
            elif prev_center[1] < y_center:
                path_typ = 'd'  # downward line
            elif prev_center[1] > y_center:
                path_typ = 'u'  # upward line
            paths += path(prev_center[0], prev_center[1], path_typ, step_width)
            
        prev_center = (x_center, y_center)

    # Build the SVG in the right order
    svg += chars  # Text on bottom
    svg += paths  # Connecting lines in middle
    svg += circles  # Circles on top
    svg += '</svg>'

    return svg

# Add a test case for the word '現場' (genba) to verify the pitch accent visualization
if __name__ == "__main__":
    import sys
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    # Set high-DPI scaling policy before creating the QApplication instance
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    # Test the KanjiLookupDialog with the word '現場'
    test_word = "現場"
    dialog = KanjiLookupDialog(test_word, None)
    dialog.show()

    sys.exit(app.exec())