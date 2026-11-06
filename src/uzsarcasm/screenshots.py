"""Import transcribed screenshot manifests; transcription is separate from label verification."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

from .core import NORMALIZATION_VERSION,normalize,quality_flags,stable_id,text_id
from .prepare import export_csv


def ingest(db,manifest,image_root,output):
    frame=pd.read_csv(manifest,dtype=str,keep_default_na=False)
    required={'image_filename','text','transcription_verified','post_key','source_url','claimed_label'}
    if not required.issubset(frame.columns):raise ValueError('Screenshot manifest columns missing')
    root=Path(image_root).resolve()
    sid=stable_id('src_screenshot_',hashlib.sha256(Path(manifest).read_bytes()).hexdigest())
    con=sqlite3.connect(db);con.execute('PRAGMA foreign_keys=ON')
    con.execute('''CREATE TABLE IF NOT EXISTS screenshot_evidence(occurrence_id TEXT PRIMARY KEY REFERENCES occurrences,
      image_filename TEXT,image_sha256 TEXT,transcription_verified INTEGER,post_key TEXT,source_url TEXT,
      collection_bias TEXT)''')
    try:
        con.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
          (sid,Path(manifest).name,'','screenshots',hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),len(frame),'screenshots',NORMALIZATION_VERSION))
        for num,row in enumerate(frame.to_dict('records'),2):
            image=(root/row['image_filename']).resolve()
            if not image.is_relative_to(root) or not image.is_file():raise ValueError('Image must exist inside --images directory')
            if not normalize(row['text']):raise ValueError('Screenshot text is empty')
            if row['transcription_verified'].lower() not in ['true','false','1','0']:raise ValueError('Explicit transcription_verified required')
            if row['claimed_label'] not in ['','0','1','uncertain']:raise ValueError('Invalid claimed label')
            tid=text_id(row['text']);oid=stable_id('occ_',sid+':'+str(num))
            con.execute('INSERT OR IGNORE INTO texts VALUES (?,?,?,?)',(tid,row['text'],normalize(row['text']),json.dumps(quality_flags(row['text']))))
            con.execute('INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (oid,tid,sid,num,'',row['text'],'Instagram','Instagram','screenshot_claim','',row['post_key'],'',None))
            con.execute('INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?)',
              (stable_id('lab_',oid),oid,tid,row['claimed_label'],int(row['claimed_label']) if row['claimed_label'] in ['0','1'] else None,
               'screenshot_collection','screenshot_label_unverified','screenshot',json.dumps({'transcription_verified':row['transcription_verified']},ensure_ascii=False)))
            con.execute('INSERT INTO screenshot_evidence VALUES (?,?,?,?,?,?,?)',
              (oid,row['image_filename'],hashlib.sha256(image.read_bytes()).hexdigest(),int(row['transcription_verified'].lower() in ['true','1']),
               row['post_key'],row['source_url'],'selected_for_sarcasm_not_random_sample'))
            con.execute("INSERT OR IGNORE INTO registry_status VALUES (?, 'screenshot','',0,0,0,0,0,NULL,'quarantine','screenshot_pending_transcription_label_and_group_review')",(tid,))
            con.execute('''UPDATE registry_status SET origins=(SELECT group_concat(DISTINCT origin) FROM labels WHERE text_id=?),
             binary_labels=COALESCE((SELECT group_concat(DISTINCT binary_candidate) FROM labels WHERE text_id=?),''),
             has_label_conflict=(SELECT count(DISTINCT binary_candidate)>1 FROM labels WHERE text_id=?) WHERE text_id=?''',(tid,tid,tid,tid))
            con.execute("UPDATE registry_status SET split='quarantine',split_reason='synthetic_real_collision' WHERE text_id=? AND origins LIKE '%synthetic%'",(tid,))
        con.commit()
    except Exception:
        con.rollback();con.close();raise
    Path(output).mkdir(parents=True,exist_ok=True)
    export_csv(con,'''SELECT t.text_id,t.representative_text AS text,e.image_filename,e.image_sha256,e.transcription_verified,
      e.post_key,e.source_url,l.original_label AS claimed_label,l.verification_status,r.split
      FROM screenshot_evidence e JOIN occurrences o USING(occurrence_id) JOIN texts t USING(text_id)
      JOIN labels l USING(occurrence_id) JOIN registry_status r ON r.text_id=t.text_id''',Path(output)/'screenshot_review.csv')
    con.close();return {'imported':len(frame),'label_verification':'not_human_verified','new_screenshots_split':'quarantine'}
