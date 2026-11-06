import hashlib
import re
import unicodedata

NORMALIZATION_VERSION = 'nfkc-casefold-apostrophe-space-v1'
APOSTROPHES = str.maketrans(dict.fromkeys('‘’ʻʼ`´ʹʽ', "'"))

def normalize(text):
    if text is None:
        return ''
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(text)).casefold().translate(APOSTROPHES)).strip()

def stable_id(prefix, value):
    return prefix + hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]

def text_id(text):
    return stable_id('txt_', normalize(text))

def quality_flags(text):
    s = normalize(text)
    flags = []
    if not s:
        flags.append('empty')
    if not any(c.isalpha() for c in s):
        flags.append('no_letters')
    if re.fullmatch(r'(?:<(?:url|user|phone)>\s*)+', s):
        flags.append('placeholder_only')
    if len(s) > 1000:
        flags.append('long_text_review')
    return flags
