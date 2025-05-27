# Test case for pitch accent lookup for 表情
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pitch_svg import create_svg_pitch_pattern
from __init__ import lookup_pitch_accent

def test_pitch_accent_hyoujou():
    word = '表情'
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
