"""Import explicit human reviews without overwriting historical machine labels."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

from .prepare import export_csv

REQUIRED={'text_id','annotator_id','label','is_human','needs_context','rationale'}

def import_reviews(db,csv_path,out):
    frame=pd.read_csv(csv_path,dtype=str,keep_default_na=False)
    if not REQUIRED.issubset(frame.columns):raise ValueError(f'Missing columns: {REQUIRED-set(frame.columns)}')
    if frame.duplicated(['text_id','annotator_id']).any():raise ValueError('Duplicate annotator/text pairs')
    con=sqlite3.connect(db)
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''CREATE TABLE IF NOT EXISTS human_reviews(
       text_id TEXT REFERENCES texts,annotator_id TEXT,label TEXT,is_human INTEGER CHECK(is_human=1),
       needs_context INTEGER,rationale TEXT,PRIMARY KEY(text_id,annotator_id));
       CREATE TABLE IF NOT EXISTS human_resolution(text_id TEXT PRIMARY KEY REFERENCES texts,
       final_label INTEGER,status TEXT,n_reviewers INTEGER);''')
    rows=[]
    for row in frame.to_dict('records'):
        if row['label'] not in ['0','1','uncertain']:raise ValueError('Labels must be 0, 1, or uncertain')
        if row['is_human'].strip().lower() not in ['true','1','yes']:raise ValueError('Explicit human attestation required')
        if row['needs_context'].strip().lower() not in ['true','false','1','0','yes','no']:raise ValueError('needs_context must be explicit')
        if not row['annotator_id'].strip() or not row['rationale'].strip():raise ValueError('Annotator ID and rationale required')
        rows.append((row['text_id'],row['annotator_id'].strip(),row['label'],1,
                     int(row['needs_context'].strip().lower() in ['true','1','yes']),row['rationale']))
    try:
        con.executemany('INSERT INTO human_reviews VALUES (?,?,?,?,?,?)',rows)
        con.execute('DELETE FROM human_resolution')
        con.execute('''INSERT INTO human_resolution
          SELECT text_id,CASE WHEN count(*)>=2 AND count(DISTINCT label)=1 AND max(needs_context)=0
            AND min(label) IN ('0','1') THEN CAST(min(label) AS INTEGER) ELSE NULL END,
            CASE WHEN count(*)>=2 AND count(DISTINCT label)=1 AND max(needs_context)=0
            AND min(label) IN ('0','1') THEN 'human_consensus' ELSE 'pending_adjudication_or_context' END,count(*)
          FROM human_reviews GROUP BY text_id''')
        con.execute('''UPDATE registry_status SET
          human_verified=EXISTS(SELECT 1 FROM human_resolution h WHERE h.text_id=registry_status.text_id AND h.status='human_consensus'),
          confirmed_negative=EXISTS(SELECT 1 FROM human_resolution h WHERE h.text_id=registry_status.text_id AND h.status='human_consensus' AND h.final_label=0)''')
        con.commit()
    except Exception:
        con.rollback();con.close();raise
    output=Path(out);output.mkdir(parents=True,exist_ok=True)
    export_csv(con,'SELECT * FROM human_resolution',output/'human_resolution.csv')
    export_csv(con,"SELECT * FROM human_resolution WHERE status<>'human_consensus'",output/'adjudication_queue.csv')
    export_csv(con,'SELECT * FROM human_resolution WHERE final_label=0',output/'confirmed_negative.csv')
    counts={}
    for split in ['provisional_train','provisional_validation','provisional_test']:
        path=output/(split.replace('provisional_','human_')+'.csv')
        export_csv(con,f'''SELECT t.text_id,t.representative_text AS text,h.final_label AS label,r.group_id AS video_id
          FROM human_resolution h JOIN texts t USING(text_id) JOIN registry_status r USING(text_id)
          WHERE h.status='human_consensus' AND r.split='{split}' AND r.origins NOT LIKE '%synthetic%' ''',path)
        counts[path.name]=0
    # Count actual records rather than physical lines (comments can contain newlines).
    counts={name:len(pd.read_csv(output/name)) for name in counts}
    result={'files':counts,'test_ready':counts.get('human_test.csv',0)>0,
            'note':'Readiness here means consensus rows exist, not sufficient size or representativeness.'}
    (output/'review_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    con.close();return result
