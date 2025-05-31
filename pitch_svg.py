# pitch_svg.py
# Shared pitch accent SVG generation utilities for Japanese add-ons
import re

def normalize_hira(hira):
    """
    Remove all characters except hiragana and small kana combiners.
    This strips markup, punctuation, and non-hiragana symbols.
    """
    # Allow hiragana, small kana, and long vowel mark (ー)
    return ''.join(c for c in hira if re.match(r'[ぁ-ゖー]', c))


def hira_to_mora(hira):
    hira = normalize_hira(hira)
    mora_arr = []
    combiners = ['ゃ', 'ゅ', 'ょ', 'ぁ', 'ぃ', 'ぅ', 'ぇ', 'ぉ',
                 'ャ', 'ュ', 'ョ', 'ァ', 'ィ', 'ゥ', 'ェ', 'ォ']
    i = 0
    while i < len(hira):
        if i+1 < len(hira) and hira[i+1] in combiners:
            mora_arr.append(hira[i] + hira[i+1])
            i += 2
        else:
            mora_arr.append(hira[i])
            i += 1
    return mora_arr

def pattern_to_mora_pitch(pattern, mora_list):
    """
    Map a pitch pattern string to mora units and post-mora.
    Handles digraphs (e.g., Ll for りょ) by matching mora length to pattern length - 1.
    """
    if not pattern or not mora_list:
        return []
    n_mora = len(mora_list)
    # If pattern length == n_mora+1, just use as is
    if len(pattern) == n_mora + 1:
        return list(pattern)
    # Otherwise, try to group pattern chars to match mora count
    groups = []
    idx = 0
    for mora in mora_list:
        # If there are at least 2 pattern chars left and the next two are an upper-lower pair (e.g., Ll, Hl, etc.), treat as a digraph
        if idx + 1 < len(pattern) - 1 and pattern[idx].isalpha() and pattern[idx+1].islower() and pattern[idx].isupper():
            groups.append(pattern[idx] + pattern[idx+1])
            idx += 2
        # Special case: Wadoku uses 'Ll' for digraphs, but sometimes just 'L' or 'H' for single kana
        elif idx + 1 < len(pattern) - 1 and pattern[idx:idx+2] in ['Ll', 'Hl', 'Hl', 'Ll', 'lh', 'hl']:
            groups.append(pattern[idx:idx+2])
            idx += 2
        else:
            groups.append(pattern[idx])
            idx += 1
    # Post-mora
    groups.append(pattern[-1])
    return groups

def circle(x, y, o=False):
    if o:
        return (
            '<circle r="5" cx="{}" cy="{}" style="fill:#fff;stroke:#000;stroke-width:1.5;" />'
        ).format(x, y)
    else:
        return (
            '<circle r="5" cx="{}" cy="{}" style="fill:#000;" />'
        ).format(x, y)

def text(x, mora):
    if len(mora) == 1:
        return ('<text x="{}" y="67.5" style="font-size:20px;font-family:sans-serif;fill:#fff;">{}</text>').format(x, mora)
    else:
        return ('<text x="{}" y="67.5" style="font-size:20px;font-family:sans-serif;fill:#fff;">{}</text>'
                '<text x="{}" y="67.5" style="font-size:14px;font-family:sans-serif;fill:#fff;">{}</text>'
                ).format(x-5, mora[0], x+12, mora[1])

def path(x, y, typ, step_width):
    if typ == 's':  # straight
        delta = '{},0'.format(step_width)
    elif typ == 'u':  # up
        delta = '{},-25'.format(step_width)
    elif typ == 'd':  # down
        delta = '{},25'.format(step_width)
    return (
        '<path d="m {},{} {}" style="fill:none;stroke:#00f;stroke-width:1.5;" />'
    ).format(x, y, delta)

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
    svg_width = max(0, ((positions-1) * step_width) + (margin_lr*2))
    svg = ('<svg class="pitch" width="{0}px" height="75px" viewBox="0 0 {0} 75" '
           'style="background-color:#20242b; border-radius:4px; padding:12px;">').format(svg_width)
    # Add mora characters
    chars = ''
    for pos, mor in enumerate(mora):
        x_center = margin_lr + (pos * step_width)
        chars += text(x_center-11, mor)
    # Add circles and connecting paths
    circles = ''
    paths = ''
    prev_center = (None, None)
    for pos, accent in enumerate(pitch_groups):
        x_center = margin_lr + (pos * step_width)
        # Use first char of group for pitch height
        a = accent[0] if accent else 'L'
        if a in ['H', 'h', '1', '2']:
            y_center = 5
        elif a in ['L', 'l', '0']:
            y_center = 30
        else:
            y_center = 30
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

def create_html_pitch_pattern(reading, pattern):
    svg = create_svg_pitch_pattern(reading, pattern)
    return f'<div>{svg}</div>'

def extract_unique_pitch_patterns(entries):
    """
    Given a list of DB entries (each with 'kana' and 'pattern'),
    return a list of unique (kana, pattern) pairs, splitting comma-separated patterns and deduplicating.
    Order is preserved by first occurrence.
    """
    seen = set()
    result = []
    for entry in entries:
        kana = entry.get('kana')
        patterns = entry.get('pattern', '')
        for patt in [p.strip() for p in patterns.split(',') if p.strip()]:
            key = (kana, patt)
            if key not in seen:
                seen.add(key)
                result.append({'kana': kana, 'pattern': patt})
    return result
