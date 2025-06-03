import os
import sys
import sqlite3
import json
import re

# Set up paths for test
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDON_DIR, 'data')
JMDICT_SQLITE_PATH = os.path.join(DATA_DIR, 'JMdict_e_examp.sqlite')
FREQ_SQLITE_PATH = os.path.join(DATA_DIR, 'japanese_word_frequencies.sqlite')

# --- JMdict lookup (copied from main script) ---
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
    except Exception as e:
        print('JMdict lookup error:', e)
    return []

def strip_furigana(word):
    return re.sub(r"\[.+?\]", "", word)

def kana_to_katakana(text):
    return text.translate(str.maketrans(
        'ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをんゔゕゖ',
        'ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヵヶ'))

def get_highest_frequency_entry(word):
    entries = lookup_jmdict(strip_furigana(word))
    print(f"JMdict entries for '{word}':\n{json.dumps(entries, ensure_ascii=False, indent=2)}\n")
    if not entries:
        print('No JMdict entries found.')
        return None, None
    best_entry = None
    best_reading = None
    best_freq = -1
    try:
        conn = sqlite3.connect(FREQ_SQLITE_PATH)
        c = conn.cursor()
        for entry in entries:
            kanas = entry.get('kanas', [])
            for kana in kanas:
                katakana_kana = kana_to_katakana(kana)
                c.execute('SELECT frequency FROM word_readings WHERE word=? AND reading=?', (strip_furigana(word), katakana_kana))
                row = c.fetchone()
                freq = row[0] if row else -1
                print(f"Frequency for (word='{strip_furigana(word)}', reading='{katakana_kana}'): {freq}")
                if freq > best_freq:
                    best_freq = freq
                    best_entry = entry
                    best_reading = kana
        conn.close()
    except Exception as e:
        print('Frequency DB error:', e)
    if best_entry:
        print(f"\nChosen entry: {json.dumps(best_entry, ensure_ascii=False, indent=2)}")
        print(f"Chosen reading: {best_reading}")
        print(f"Chosen frequency: {best_freq}")
        return best_entry, best_reading
    # fallback: just return first entry/reading
    entry = entries[0]
    kanas = entry.get('kanas', [])
    print(f"\nFallback entry: {json.dumps(entry, ensure_ascii=False, indent=2)}")
    print(f"Fallback reading: {kanas[0] if kanas else ''}")
    return entry, kanas[0] if kanas else ''

if __name__ == "__main__":
    word = "秋"
    print(f"\n--- Test for word: {word} ---\n")
    get_highest_frequency_entry(word)
