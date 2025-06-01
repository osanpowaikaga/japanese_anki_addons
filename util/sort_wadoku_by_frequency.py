import sqlite3
import re
import os
from tqdm import tqdm

# Paths
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '../data'))
WADOKU_PATH = os.path.join(DATA_DIR, 'wadoku_pitchdb.csv')
FREQ_DB_PATH = os.path.join(DATA_DIR, 'japanese_word_frequencies.sqlite')
OUTPUT_PATH = os.path.join(DATA_DIR, 'wadoku_pitchdb_sorted.csv')

# Regex for cleaning special characters
SPECIAL_CHAR_PATTERN = re.compile(r'[△×…]')

# Hiragana to Katakana conversion table
HIRAGANA_START = ord('ぁ')
HIRAGANA_END = ord('ゖ')
KATAKANA_START = ord('ァ')

def hiragana_to_katakana(text):
    # Convert all hiragana chars to katakana
    return ''.join(
        chr(ord(ch) + (KATAKANA_START - HIRAGANA_START)) if HIRAGANA_START <= ord(ch) <= HIRAGANA_END else ch
        for ch in text
    )

def clean_word(word):
    # Remove special characters and parenthesis content
    word = SPECIAL_CHAR_PATTERN.sub('', word)
    word = re.sub(r'\([^)]*\)', '', word)  # Remove anything in parenthesis
    return word

def get_highest_frequency(conn, words, reading):
    """
    For a list of words and a reading, return the highest frequency found in the DB.
    If none found, return 0.
    """
    max_freq = 0
    for word in words:
        cursor = conn.execute(
            'SELECT frequency FROM word_readings WHERE word=? AND reading=?',
            (word, reading)
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            freq = row[0]
            if freq > max_freq:
                max_freq = freq
    return max_freq

def main():
    # Read all lines from wadoku csv (process all lines, not just 1000)
    with open(WADOKU_PATH, encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f if line.strip() and not line.startswith('//')]

    # Connect to frequency DB
    conn = sqlite3.connect(FREQ_DB_PATH)

    # For diagnostics: count how many kanji_list/reading pairs are actually in the DB
    freq_db_words = set()
    cursor = conn.execute('SELECT word, reading FROM word_readings')
    for row in cursor:
        freq_db_words.add((row[0], row[1]))
    print(f"Loaded {len(freq_db_words)} (word, reading) pairs from frequency DB.")

    # Parse and score lines with progress bar
    scored_lines = []
    changed_lines = 0
    found_words = []
    print("\n--- Diagnostic: Showing original line and search words for first 2 lines ---")
    for idx, line in enumerate(tqdm(lines, desc='Scoring by frequency')):
        parts = line.split('␞')
        if len(parts) < 2:
            scored_lines.append((0, line))
            continue
        kanji_column = parts[0]
        reading = parts[1]
        reading_kata = hiragana_to_katakana(reading)
        kanji_list = [clean_word(k) for k in kanji_column.split('␟') if k]
        # Filter: if any entry in kanji_list contains a non-kana character, remove all entries that are only kana
        has_non_kana = any(re.search(r'[^ぁ-ゖァ-ヺー]', w) for w in kanji_list)
        if has_non_kana:
            kanji_list = [w for w in kanji_list if re.search(r'[^ぁ-ゖァ-ヺー]', w)]
        if idx < 2:
            print(f"\nLine {idx+1}: {line}")
            print(f"  Search words: {kanji_list} | Reading: {reading} | Katakana: {reading_kata}")
        # For diagnostics: count how many of these are in the DB
        found_any = False
        max_freq = 0
        for word in kanji_list:
            if (word, reading_kata) in freq_db_words:
                found_any = True
            cursor = conn.execute(
                'SELECT frequency FROM word_readings WHERE word=? AND reading=?',
                (word, reading_kata)
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                freq = row[0]
                if freq > max_freq:
                    max_freq = freq
        scored_lines.append((max_freq, line))
        if max_freq > 0:
            changed_lines += 1
            if len(found_words) < 100:
                found_words.append({'words': kanji_list, 'reading': reading, 'katakana': reading_kata, 'freq': max_freq})
    conn.close()

    # Sort by frequency descending
    scored_lines.sort(key=lambda x: x[0], reverse=True)

    # Write to output
    with open(OUTPUT_PATH, 'w', encoding='utf-8', newline='') as f:
        for freq, line in scored_lines:
            f.write(line + '\n')

    print(f"Sorted {len(scored_lines)} lines by frequency. Output: {OUTPUT_PATH}")
    print(f"Lines with frequency found in DB: {changed_lines}")
    # Collect up to 100 random samples from all lines (including those without frequency)
    import random
    sample_lines = random.sample(scored_lines, min(100, len(scored_lines)))
    print("Sample of words (random, including those without frequency found):")
    for freq, line in sample_lines:
        parts = line.split('␞')
        if len(parts) < 2:
            continue
        kanji_column = parts[0]
        reading = parts[1]
        reading_kata = hiragana_to_katakana(reading)
        kanji_list = [clean_word(k) for k in kanji_column.split('␟') if k]
        print(f"Words: {kanji_list}, Reading: {reading}, Frequency: {freq}")

    # Diagnostic: how many kanji/reading pairs in wadoku are in the DB at all?
    total_pairs = 0
    found_pairs = 0
    for line in lines:
        parts = line.split('␞')
        if len(parts) < 2:
            continue
        kanji_column = parts[0]
        reading = parts[1]
        reading_kata = hiragana_to_katakana(reading)
        kanji_list = [clean_word(k) for k in kanji_column.split('␟') if k]
        for word in kanji_list:
            total_pairs += 1
            if (word, reading_kata) in freq_db_words:
                found_pairs += 1
    print(f"\nTotal (word, reading) pairs in wadoku: {total_pairs}")
    print(f"Pairs found in frequency DB: {found_pairs}")
    print(f"Coverage: {found_pairs/total_pairs:.4%}")

    # Custom test for two specific lines
    test_lines = [
        '△飯␟いい␟飯␞いい␞いい␞1␞HLL',
        '飯␟飯␟めし␟メシ␞めし␞めし␞2␞LHL'
    ]
    print("\n--- Custom Test: Frequency for two specific lines ---")
    for line in test_lines:
        parts = line.split('␞')
        if len(parts) < 2:
            print(f"Line: {line} | Frequency: 0 (invalid line)")
            continue
        kanji_column = parts[0]
        reading = parts[1]
        reading_kata = hiragana_to_katakana(reading)
        kanji_list = [clean_word(k) for k in kanji_column.split('␟') if k]
        # Apply the same filter as above
        has_non_kana = any(re.search(r'[^ぁ-ゖァ-ヺー]', w) for w in kanji_list)
        if has_non_kana:
            kanji_list = [w for w in kanji_list if re.search(r'[^ぁ-ゖァ-ヺー]', w)]
        max_freq = 0
        for word in kanji_list:
            cursor = sqlite3.connect(FREQ_DB_PATH).execute(
                'SELECT frequency FROM word_readings WHERE word=? AND reading=?',
                (word, reading_kata)
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                freq = int(row[0])
                if freq > max_freq:
                    max_freq = freq
        print(f"Line: {line}\n  Words: {kanji_list} | Reading: {reading} | Katakana: {reading_kata} | Frequency in DB: {max_freq}")

if __name__ == '__main__':
    main()
