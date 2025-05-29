import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
GOO_BASE_URL = "https://dictionary.goo.ne.jp"
GOO_SEARCH_URL = "https://dictionary.goo.ne.jp/en/"
GOO_SEARCH_ACTION = "/freewordsearcher.html"
KANJI_EXAMPLES_PATH = os.path.join(DATA_DIR, 'kanji_examples.json')


def load_kanji_examples():
    if os.path.exists(KANJI_EXAMPLES_PATH):
        try:
            with open(KANJI_EXAMPLES_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_kanji_examples(db):
    try:
        with open(KANJI_EXAMPLES_PATH, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


KANJI_EXAMPLES_DB = load_kanji_examples()


def lookup_sentences_and_related(word):
    # Check local DB first
    if word in KANJI_EXAMPLES_DB:
        entry = KANJI_EXAMPLES_DB[word]
        return entry.get('examples', []), entry.get('related_words', [])

    session = requests.Session()
    params = {
        'MT': word,
        'mode': '1',  # exact match
        'kind': 'en',
    }
    search_url = urljoin(GOO_BASE_URL, GOO_SEARCH_ACTION)
    try:
        resp = session.get(search_url, params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return [], []
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Check for 'no results' message
    contents_div = soup.find('div', class_='contents')
    if contents_div and '一致する情報は見つかりませんでした' in contents_div.text:
        return [], []

    # Step 2: Check if we are on a results page or direct word page
    example_sentence_div = soup.find('div', class_='example_sentence')
    if example_sentence_div:
        first_link = example_sentence_div.find('a', href=True)
        if first_link:
            word_url = urljoin(GOO_BASE_URL, first_link['href'])
            try:
                resp = session.get(word_url, timeout=10)
                resp.raise_for_status()
            except Exception as e:
                return [], []
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Check again for 'no results' message on the redirected page
            contents_div = soup.find('div', class_='contents')
            if contents_div and '一致する情報は見つかりませんでした' in contents_div.text:
                return [], []

    examples = []
    related_words = []

    for content_box in soup.find_all('div', class_='content-box-ej'):
        ols = content_box.find_all('ol', class_='list-data-b')
        for ol in ols:
            examples_block = ol.find('div', class_='examples-block')
            if examples_block:
                for ul in examples_block.find_all('ul', class_='list-data-b-in'):
                    jp = None
                    en = None
                    for li in ul.find_all('li'):
                        if 'text-jejp' in li.get('class', []):
                            ex_span = li.find('span', class_='ex')
                            jp = ex_span.text.strip() if ex_span else li.text.strip()
                        elif 'text-jeen' in li.get('class', []):
                            en = li.text.strip()
                    if jp and en:
                        examples.append((jp, en))
            for li in ol.find_all('li', class_='in-ttl-b'):
                strongs = li.find_all('strong')
                if strongs:
                    word_text = ''.join(s.text for s in strongs)
                    translation = li.get_text(separator=' ', strip=True)
                    for s in strongs:
                        translation = translation.replace(s.text, '').strip()
                    if translation:
                        related_words.append((word_text, translation))
    # Save to local DB
    KANJI_EXAMPLES_DB[word] = {'examples': examples, 'related_words': related_words}
    save_kanji_examples(KANJI_EXAMPLES_DB)
    return examples, related_words
