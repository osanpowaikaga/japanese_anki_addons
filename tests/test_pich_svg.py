# test_pitch_svg.py
# Standalone test for pitch accent SVG generation for 原子力

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import json
import sqlite3
from pitch_svg import hira_to_mora, create_svg_pitch_pattern, create_html_pitch_pattern

# --- Minimal lookup_pitch_accent (copied from __init__.py, no relative imports) ---
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDON_DIR, 'data')
PITCH_DB_SQLITE_PATH = os.path.join(DATA_DIR, 'wadoku_pitchdb.sqlite')

_pitch_accent_cache = {}
def lookup_pitch_accent(word):
    if word in _pitch_accent_cache:
        return _pitch_accent_cache[word]
    if not os.path.exists(PITCH_DB_SQLITE_PATH):
        return [], '', [], ''
    entries = []
    try:
        conn = sqlite3.connect(PITCH_DB_SQLITE_PATH)
        c = conn.cursor()
        if len(word) == 1 and '\u4e00' <= word <= '\u9fff':
            c.execute('SELECT kana, accented_kana, pitch_number, pattern FROM pitch_accents WHERE kanji=?', (word,))
        else:
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
        accented_kanas = list({e["accented_kana"] for e in entries if e["accented_kana"]})
        pitch_patterns = [e["pattern"] for e in entries]
        normal_kanas = list({e["kana"] for e in entries if e["kana"]})
        result = (accented_kanas, accented_kanas[0] if accented_kanas else '', pitch_patterns, normal_kanas[0] if normal_kanas else '')
    _pitch_accent_cache[word] = result
    return result

# --- Test logic ---
def test_pitch_svg_for_genshiryoku():
    word = '盆'
    print(f"Word: {word}")

    # 1. Lookup pitch accent data
    readings, accented_kana, pitch_patterns, normal_kana = lookup_pitch_accent(word)
    print(f"Readings: {readings}")
    print(f"Accented kana: {accented_kana}")
    print(f"Pitch patterns: {pitch_patterns}")
    print(f"Normal kana: {normal_kana}")

    # 2. Use kana for mora splitting
    kana = accented_kana if accented_kana else (normal_kana if normal_kana else word)
    mora = hira_to_mora(kana)
    print(f"Mora: {mora}")

    # 3. Generate SVG for each pitch pattern
    for pattern in pitch_patterns:
        print(f"Pattern: {pattern}")
        svg = create_svg_pitch_pattern(kana, pattern)
        print(f"SVG:\n{svg}\n")
        html = create_html_pitch_pattern(kana, pattern)
        print(f"HTML:\n{html}\n")

if __name__ == "__main__":
    test_pitch_svg_for_genshiryoku()
