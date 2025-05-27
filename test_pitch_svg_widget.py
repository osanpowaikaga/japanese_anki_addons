import unittest
from unittest.mock import patch
from PyQt6.QtSvg import QSvgRenderer
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kanji_lookup import PitchAccentSvgWidget
import pitch_svg

class TestPitchAccentSvgWidget(unittest.TestCase):
    def setUp(self):
        from PyQt6.QtWidgets import QApplication
        self._app = QApplication.instance() or QApplication([])

    def test_svg_data_passed_to_renderer(self):
        # Patch QSvgRenderer to log the SVG data it receives
        orig_init = QSvgRenderer.__init__
        svg_data_log = []

        def logging_init(self, data, *args, **kwargs):
            # data is a QByteArray or bytes
            if hasattr(data, 'data'):
                svg_bytes = data.data()
            else:
                svg_bytes = data
            try:
                svg_str = svg_bytes.decode('utf-8')
            except Exception:
                svg_str = str(svg_bytes)
            svg_data_log.append(svg_str)
            print("QSvgRenderer received SVG:", svg_str)
            return orig_init(self, data, *args, **kwargs)

        with patch('PyQt6.QtSvg.QSvgRenderer.__init__', new=logging_init):
            pitch_entries = [
                {'kana': 'ひょうじょう', 'pattern': '0-1-2'},
                {'kana': 'かんじ', 'pattern': '1-0'}
            ]
            widget = PitchAccentSvgWidget(pitch_entries)
            # Compare widget SVG to pitch_svg.py SVG
            for i, entry in enumerate(pitch_entries):
                kana = entry['kana']
                pattern = entry['pattern']
                svg_expected = pitch_svg.create_svg_pitch_pattern(kana, pattern)
                svg_actual = svg_data_log[i]
                print(f"\nKana: {kana}  Pattern: {pattern}")
                print("SVG from widget:")
                print(svg_actual)
                print("SVG from pitch_svg.py:")
                print(svg_expected)
                if svg_actual.strip() != svg_expected.strip():
                    print("[DIFFERS]")
                else:
                    print("[MATCHES]")
            print("Widget svg_renderers:", widget.svg_renderers)
            print("Widget sizes:", getattr(widget, 'sizes', None))

        # You can also assert or inspect svg_data_log here
        self.assertEqual(len(svg_data_log), 2)
        for svg in svg_data_log:
            self.assertIn('<svg', svg)  # crude check for SVG content

if __name__ == '__main__':
    unittest.main()