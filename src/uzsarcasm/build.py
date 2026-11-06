"""Read original workbooks without trusting their labels or embedded instructions."""
import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd

from .core import NORMALIZATION_VERSION, normalize, quality_flags, stable_id, text_id

SCHEMA = '''
CREATE TABLE sources(source_id TEXT PRIMARY KEY, filename TEXT, member TEXT, sheet TEXT,
 sha256 TEXT, rows INTEGER, role TEXT, normalization_version TEXT);
CREATE TABLE texts(text_id TEXT PRIMARY KEY, representative_text TEXT, normalized_text TEXT UNIQUE,
 quality_flags TEXT);
CREATE TABLE occurrences(occurrence_id TEXT PRIMARY KEY, text_id TEXT REFERENCES texts,
 source_id TEXT REFERENCES sources, excel_row INTEGER, source_record_id TEXT, original_text TEXT,
 declared_platform TEXT, resolved_platform TEXT, platform_status TEXT, video_id TEXT,
 post_id TEXT, published_at TEXT, like_count INTEGER);
CREATE INDEX occurrence_text ON occurrences(text_id);
CREATE INDEX occurrence_video ON occurrences(video_id);
CREATE TABLE labels(label_id TEXT PRIMARY KEY, occurrence_id TEXT REFERENCES occurrences,
 text_id TEXT REFERENCES texts, original_label TEXT, binary_candidate INTEGER,
 label_source_original TEXT, verification_status TEXT, origin TEXT, attributes_json TEXT);
CREATE INDEX label_text ON labels(text_id);
CREATE TABLE post_links(post_id TEXT PRIMARY KEY, text_id TEXT REFERENCES texts);
CREATE TABLE cues(cue_id INTEGER PRIMARY KEY, cue_type TEXT, cue_text TEXT);
CREATE TABLE post_cues(post_cue_id INTEGER PRIMARY KEY, post_id TEXT, cue_id INTEGER);
CREATE TABLE tokens(token_id INTEGER PRIMARY KEY, post_id TEXT, token_text TEXT, lemma TEXT,
 pos_tag TEXT, token_index INTEGER);
CREATE TABLE legacy_annotations(annotation_id INTEGER PRIMARY KEY, post_id TEXT, label TEXT,
 annotator_id TEXT, confidence_score REAL, created_at TEXT);
CREATE TABLE context(video_id TEXT PRIMARY KEY, title TEXT, title_status TEXT,
 title_source TEXT, fetched_at TEXT, parent_context_status TEXT);
CREATE TABLE registry_status(text_id TEXT PRIMARY KEY REFERENCES texts, origins TEXT,
 binary_labels TEXT, has_label_conflict INTEGER, has_unverified_auto_zero INTEGER,
 confirmed_negative INTEGER, human_verified INTEGER, raw_video_count INTEGER,
 group_id TEXT, split TEXT, split_reason TEXT);
'''

def scalar(x):
    if pd.isna(x):
        return None
    return x.item() if hasattr(x, 'item') else x

def svalue(x):
    x = scalar(x)
    return '' if x is None else str(x)

def classify(name, sheet):
    if name.startswith('Sarcasm_labeled_50k') and sheet == 'Sarkazm': return 'weak_50k'
    if name.startswith('synthetic_Sarcasm_10k') and sheet == 'Sarkazm': return 'synthetic'
    if name == 'Uzbek_Sarcasm_Verified_Results.xlsx' and sheet == 'Labeled Dataset': return 'legacy_verified'
    if name == 'Posts.xlsx' and sheet == 'Posts': return 'posts'
    if name == 'Kinoya va sarkazm_post.xlsx' and sheet == 'Лист1': return 'curated_unlabeled'
    if name.strip() in ['youtube_comments.xlsx', 'instagram_comments .xlsx', 'telegram_pubg_comments (7).xlsx']: return 'raw'
    return 'auxiliary'

def iter_workbooks(root):
    for path in sorted(Path(root).rglob('*.xlsx')):
        yield path.name, '', path.read_bytes()
    for path in sorted(Path(root).rglob('*.zip')):
        with zipfile.ZipFile(path) as archive:
            for item in sorted(archive.infolist(), key=lambda i: i.filename):
                # Read only workbook bytes; never extract paths or execute archive contents.
                if item.filename.endswith('.xlsx'):
                    if item.file_size > 150_000_000:
                        raise ValueError('Archive workbook is unexpectedly large')
                    yield path.name, item.filename, archive.read(item)

def add_frame(con, frame, source, role, filename):
    if role == 'auxiliary':
        return
    if role in ['weak_50k', 'synthetic']: text_col = 'Text_uz'
    elif role in ['legacy_verified', 'raw']: text_col = 'Comment' if 'Comment' in frame else 'text'
    elif role == 'posts': text_col = 'text_content'
    else: text_col = 'post'
    texts, occurrences, labels = [], [], []
    for rownum, record in enumerate(frame.to_dict('records'), 2):
        original = svalue(record.get(text_col))
        if not normalize(original):
            continue
        tid = text_id(original)
        texts.append((tid, original, normalize(original), json.dumps(quality_flags(original))))
        oid = stable_id('occ_', source + ':' + str(rownum))
        declared = resolved = status = ''
        if role == 'raw':
            if filename.startswith('youtube'): declared = resolved = 'YouTube'; status = 'source_file'
            elif filename.startswith('instagram'): declared = 'Instagram'; resolved = 'unknown'; status = 'suspected_youtube_duplicate'
            else: declared = resolved = 'Telegram_PUBG'; status = 'source_file'
        elif role == 'legacy_verified': declared = resolved = svalue(record.get('Source')); status = 'legacy_claim'
        elif role == 'posts': declared = resolved = svalue(record.get('platform')); status = 'legacy_claim'
        rid = next((svalue(record.get(k)) for k in ['record_id', 'ID', '№', 'post_id', 'Post ID'] if k in record), '')
        post = svalue(record.get('post_id')) if role == 'posts' else ''
        video = svalue(record.get('VideoID')) if role == 'raw' else ''
        occurrences.append((oid, tid, source, rownum, rid, original, declared, resolved, status,
                            video, post, svalue(record.get('PublishedAt')), scalar(record.get('LikeCount'))))
        if role == 'posts':
            con.execute('INSERT INTO post_links VALUES (?,?)', (post, tid))
        if role in ['weak_50k', 'synthetic', 'legacy_verified']:
            raw_label = record['sarcasm_label' if role == 'legacy_verified' else 'Sarcasm']
            label = int(raw_label)
            if label not in [0, 1]: raise ValueError('Unexpected binary label')
            source_label = svalue(record.get('Label_source'))
            if role == 'weak_50k':
                if source_label == 'auto': verification = 'auto_not_detected' if label == 0 else 'auto_positive'
                elif source_label == "manual (to'liq)": verification = 'llm_review_not_human_verified'
                else: verification = 'review_claim_unverified'
            elif role == 'synthetic': verification = 'synthetic_generated'
            else: verification = 'legacy_verified_claim_unconfirmed'
            attrs = {k:scalar(val) for k,val in record.items() if k not in [text_col, '№', 'ID', 'record_id']}
            labels.append((stable_id('lab_', oid), oid, tid, str(raw_label), label, source_label,
                           verification, role, json.dumps(attrs, ensure_ascii=False)))
    con.executemany('INSERT OR IGNORE INTO texts VALUES (?,?,?,?)', texts)
    con.executemany('INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', occurrences)
    con.executemany('INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?)', labels)

def auxiliary(con, frame, name, sheet):
    mapping = {
        ('Cues.xlsx','Cues'): ('cues',['cue_id','cue_type','cue_text']),
        ('Post_Cues.xlsx','Post_Cues'): ('post_cues',['post_cue_id','post_id','cue_id']),
        ('Tokens.xlsx','Tokens'): ('tokens',['token_id','post_id','token_text','lemma','pos_tag','token_index']),
        ('Annotations.xlsx','Annotations'): ('legacy_annotations',['annotation_id','post_id','label','annotator_id','confidence_score','created_at'])}
    if (name,sheet) not in mapping: return
    table, cols = mapping[(name,sheet)]
    values = [tuple(scalar(r[c]) for c in cols) for r in frame.to_dict('records')]
    con.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in cols)})', values)

def build(input_dir, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    db = out / 'registry.sqlite'
    if db.exists(): raise FileExistsError(f'{db} exists; use a fresh output directory')
    con = sqlite3.connect(db)
    # Parent texts may occur later in input order; check integrity after ingestion.
    con.executescript(SCHEMA)
    metadata = []
    try:
        seen = set()
        for container, member, data in iter_workbooks(input_dir):
            name = Path(member).name if member else container
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen: continue
            seen.add(digest)
            book = pd.ExcelFile(io.BytesIO(data))
            for sheet in book.sheet_names:
                frame = pd.read_excel(book, sheet)
                role = classify(name, sheet)
                sid = stable_id('src_', digest + ':' + sheet)
                con.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                            (sid,container,member,sheet,digest,len(frame),role,NORMALIZATION_VERSION))
                add_frame(con, frame, sid, role, name)
                auxiliary(con, frame, name, sheet)
                if role == 'auxiliary' and name not in ['Tokens.xlsx','Cues.xlsx','Post_Cues.xlsx','Annotations.xlsx']:
                    metadata.append({'file':name,'sheet':sheet,'columns':[str(c) for c in frame.columns],
                                     'rows':frame.fillna('').astype(str).to_dict('records')})
                con.commit()
                print(f'{name} / {sheet}: {len(frame):,} [{role}]', flush=True)
        # Annotations carry Neutral, not a documented binary sarcasm judgment.
        con.execute('''INSERT INTO labels
          SELECT 'lab_legacy_'||a.annotation_id, o.occurrence_id, p.text_id, a.label, NULL,
          'annotator_id='||a.annotator_id, 'uniform_neutral_placeholder_unverified', 'legacy_annotations',
          json_object('confidence_score',a.confidence_score,'created_at',a.created_at)
          FROM legacy_annotations a JOIN post_links p ON CAST(a.post_id AS TEXT)=p.post_id
          JOIN occurrences o ON o.text_id=p.text_id AND o.post_id=p.post_id''')
        con.executescript('''
          INSERT INTO context SELECT DISTINCT video_id, '', 'not_fetched', '', '', 'not_available_in_uploaded_sources'
            FROM occurrences WHERE resolved_platform='YouTube' AND video_id<>'';
          INSERT INTO registry_status
          SELECT t.text_id,
            COALESCE((SELECT group_concat(DISTINCT origin) FROM labels l WHERE l.text_id=t.text_id), 'unlabeled'),
            COALESCE((SELECT group_concat(DISTINCT binary_candidate) FROM labels l WHERE l.text_id=t.text_id),''),
            (SELECT count(DISTINCT binary_candidate)>1 FROM labels l WHERE l.text_id=t.text_id),
            EXISTS(SELECT 1 FROM labels l WHERE l.text_id=t.text_id AND verification_status='auto_not_detected'),
            0, 0,
            (SELECT count(DISTINCT video_id) FROM occurrences o WHERE o.text_id=t.text_id AND resolved_platform='YouTube' AND video_id<>''),
            NULL, 'quarantine', 'not_assigned'
          FROM texts t;
        ''')
        con.commit()
        if con.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Broken foreign key')
        (out/'source_notes.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        con.close()
        db.unlink(missing_ok=True)
        raise
    con.close()
    return db
