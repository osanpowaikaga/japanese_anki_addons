import csv
import os
import re
from tqdm import tqdm

def parse_accents_file(filepath):
    """Parse accents.txt and return a dict with (word, reading) as key and pitch numbers as value."""
    accents = {}
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('//'):  # skip comments
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                word, reading, pitch = parts[:3]
                if not reading:
                    reading = word  # If reading is empty, use word as reading
            elif len(parts) == 2:
                word, pitch = parts
                reading = word  # Use word as reading if reading is missing
            else:
                continue
            accents[(word, reading)] = pitch
    return accents

def generate_lh(reading, pitch_numbers):
    """Generate LH representation for a reading and pitch numbers (comma separated), always len(reading)+1, handling small kana as lowercase l/h, replacing the position for small kana with the lowercase version, and the trailing L/H is always uppercase."""
    combiners = ['ゃ', 'ゅ', 'ょ', 'ぁ', 'ぃ', 'ぅ', 'ぇ', 'ぉ',
                 'ャ', 'ュ', 'ョ', 'ァ', 'ィ', 'ゥ', 'ェ', 'ォ']
    pitch_numbers = pitch_numbers.strip(',')
    readings = [reading] * len(pitch_numbers.split(',')) if pitch_numbers else []
    lh_list = []
    for r, p in zip(readings, pitch_numbers.split(',')):
        try:
            p = int(p)
        except ValueError:
            lh_list.append('')
            continue
        chars = list(r)
        n = len(chars)
        # Build base LH pattern for each kana position (not mora)
        base_lh = []
        for idx in range(n+1):
            if idx == 0:
                base_lh.append('H' if p == 1 else 'L')
            elif p == 0:
                base_lh.append('H')
            elif p == 1:
                base_lh.append('L')
            elif 1 < p <= n:
                base_lh.append('H' if idx <= p-1 else 'L')
            else:
                base_lh.append('H')
        kana_lh = []
        mora_idx = 0
        for i, c in enumerate(chars):
            if c in combiners and i > 0:
                # Small kana: use previous mora's L/H, in lowercase
                kana_lh.append(base_lh[mora_idx-1].lower())
            else:
                kana_lh.append(base_lh[mora_idx])
                mora_idx += 1
        lh = ''.join(kana_lh) + base_lh[-1]
        lh_list.append(lh)
    return ','.join(lh_list)

def main():
    accents_path = os.path.join(os.path.dirname(__file__), '../data/accents.txt')
    wadoku_path = os.path.join(os.path.dirname(__file__), '../data/wadoku_pitchdb.csv')
    output_path = os.path.join(os.path.dirname(__file__), '../data/wadoku_pitchdb_corrected.csv')

    accents = parse_accents_file(accents_path)

    def clean_word(word):
        return re.sub(r'[△×…]', '', word)

    # Count total lines for progress bar
    with open(wadoku_path, encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)

    changed_words = []
    all_changed = []  # Store all changed lines for accurate stats
    changed_count = 0
    # Track which (kanji, reading) pairs from accents.txt were matched
    matched_keys = set()
    new_words = []
    total_new_words = 0
    with open(wadoku_path, encoding='utf-8') as fin, open(output_path, 'w', encoding='utf-8', newline='') as fout:
        for line in tqdm(fin, total=total_lines, desc='Processing'):
            if not line.strip() or line.startswith('//'):
                fout.write(line)
                continue
            parts = line.strip().split('␞')
            if len(parts) < 5:
                fout.write(line)
                continue
            kanji_column = parts[0]
            reading = parts[1]
            kanji_list = [clean_word(k) for k in kanji_column.split('␟') if k]
            matched = False
            for kanji in kanji_list:
                key = (kanji, reading)
                if key in accents:
                    pitch_numbers = accents[key].strip(',')  # Remove trailing comma if present
                    old_pitch = parts[3].strip(',')  # Also strip from old pitch for comparison/output
                    old_lh = parts[4]
                    parts[3] = pitch_numbers
                    parts[4] = generate_lh(reading, pitch_numbers)
                    fout.write('␞'.join(parts) + '\n')
                    matched = True
                    changed_count += 1
                    matched_keys.add(key)
                    all_changed.append({
                        'kanji': kanji,
                        'reading': reading,
                        'old_pitch': old_pitch,
                        'new_pitch': pitch_numbers,
                        'old_lh': old_lh,
                        'new_lh': parts[4]
                    })
                    if len(changed_words) < 20:
                        changed_words.append({
                            'kanji': kanji,
                            'reading': reading,
                            'old_pitch': old_pitch,
                            'new_pitch': pitch_numbers,
                            'old_lh': old_lh,
                            'new_lh': parts[4]
                        })
                    break
            if not matched:
                fout.write(line)
        # After processing, add missing entries from accents.txt
        for (word, reading), pitch_numbers in accents.items():
            pitch_numbers = pitch_numbers.strip(',')  # Remove trailing comma if present
            if (word, reading) not in matched_keys:
                pitch_lh = generate_lh(reading, pitch_numbers)
                # Use reading for both reading and accented reading
                new_line = f"{word}␞{reading}␞{reading}␞{pitch_numbers}␞{pitch_lh}\n"
                fout.write(new_line)
                if len(new_words) < 5:
                    new_words.append({'word': word, 'reading': reading, 'pitch': pitch_numbers, 'lh': pitch_lh})
                total_new_words += 1

    print(f"Total words changed: {changed_count}")
    print("Sample of changed words:")
    for w in changed_words:
        print(f"Kanji: {w['kanji']}, Reading: {w['reading']}, Old Pitch: {w['old_pitch']} -> New Pitch: {w['new_pitch']}, Old LH: {w['old_lh']} -> New LH: {w['new_lh']}")

    # Prepare output cases
    same_pitch = []
    diff_pitch = []
    perfect_matches = []
    total_same_pitch = 0
    total_diff_pitch = 0
    total_perfect_matches = 0
    for w in all_changed:
        if w['old_pitch'] == w['new_pitch']:
            if len(same_pitch) < 5:
                same_pitch.append({'word': w['kanji'], 'reading': w['reading'], 'old_pitch': w['old_pitch'], 'new_pitch': w['new_pitch'], 'lh': w['new_lh']})
            total_same_pitch += 1
        else:
            if len(diff_pitch) < 5:
                diff_pitch.append({'word': w['kanji'], 'reading': w['reading'], 'old_pitch': w['old_pitch'], 'new_pitch': w['new_pitch'], 'lh': w['new_lh']})
            total_diff_pitch += 1
        if w['old_lh'] == w['new_lh']:
            if len(perfect_matches) < 5:
                perfect_matches.append({'word': w['kanji'], 'reading': w['reading'], 'pitch': w['old_pitch'], 'lh': w['old_lh']})
            total_perfect_matches += 1

    print(f"\n--- 5 cases where old pitch number matches new pitch number ---")
    for w in same_pitch:
        print(f"Word: {w['word']}, Reading: {w['reading']}, Pitch: {w['old_pitch']} -> {w['new_pitch']}, LH: {w['lh']}")
    print(f"Total: {total_same_pitch}")
    print(f"\n--- 5 cases of perfect matches (pitch and LH) ---")
    for w in perfect_matches:
        print(f"Word: {w['word']}, Reading: {w['reading']}, Pitch: {w['pitch']}, LH: {w['lh']}")
    print(f"Total: {total_perfect_matches}")

    print(f"\n--- 5 cases where old pitch number doesn't match new pitch number ---")
    for w in diff_pitch:
        print(f"Word: {w['word']}, Reading: {w['reading']}, Pitch: {w['old_pitch']} -> {w['new_pitch']}, LH: {w['lh']}")
    print(f"Total: {total_diff_pitch}")

    print(f"\n--- 5 cases where it's a new word ---")
    for w in new_words:
        print(f"Word: {w['word']}, Reading: {w['reading']}, Pitch: {w['pitch']}, LH: {w['lh']}")
    print(f"Total: {total_new_words}")

    for w in all_changed:
        # Diagnostic: If pitch matches but LH does not, print a sample
        if w['old_pitch'] == w['new_pitch'] and w['old_lh'] != w['new_lh']:
            if 'diagnosed' not in locals():
                print("\n--- Diagnostic: Pitch matches but LH does not (showing up to 10 cases) ---")
                diagnosed = 0
            if diagnosed < 10:
                print(f"Word: {w['kanji']}, Reading: {w['reading']}, Pitch: {w['old_pitch']}, Old LH: {w['old_lh']} -> New LH: {w['new_lh']}")
                diagnosed += 1

if __name__ == '__main__':
    main()
