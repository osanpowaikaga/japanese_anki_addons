# Test case for pitch accent lookup for 表情
from pitch_svg import create_svg_pitch_pattern

import os
import sqlite3

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
PITCH_DB_SQLITE_PATH = os.path.join(ADDON_DIR, 'wadoku_pitchdb.sqlite')

_pitch_accent_cache = {}

def lookup_pitch_accent(word):
    """Lookup pitch accent for a word from wadoku_pitchdb.sqlite, with in-memory cache."""
    if word in _pitch_accent_cache:
        return _pitch_accent_cache[word]
    if not os.path.exists(PITCH_DB_SQLITE_PATH):
        return [], '', [], ''
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

def test_pitch_accent_hyoujou():
    word = 'アイスコーヒー'
    readings, accented_kana, pitch_patterns, normal_kana = lookup_pitch_accent(word)
    print(f"Word: {word}")
    print(f"Readings: {readings}")
    print(f"Accented Kana: {accented_kana}")
    print(f"Pitch Patterns: {pitch_patterns}")
    print(f"Normal Kana: {normal_kana}")
    # Show SVG for each pitch pattern
    for i, pattern in enumerate(pitch_patterns):
        print(f"SVG for pattern {pattern}:")
        svg = create_svg_pitch_pattern(normal_kana, pattern)
        print(svg)

if __name__ == "__main__":
    test_pitch_accent_hyoujou()
