"""Import labeled screenshot workbooks, preserving subtype, uncertainty and lineage."""
import hashlib
import json
import io
import sqlite3
from pathlib import Path

import pandas as pd

from .core import NORMALIZATION_VERSION,normalize,quality_flags,stable_id,text_id
from .prepare import export_csv,validate

LABELS={'kinoya':1,'sarkazm':1,'kinoyasiz':0,'noaniq':None}
REQUIRED={'ID','Izoh matni','Sinf','Post konteksti','Tasnif asosi','Skrinshot fayli','Post guruhi'}


def ingest_workbooks(db,paths,output):
    con=sqlite3.connect(db);con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''CREATE TABLE IF NOT EXISTS screenshot_workbook_rows(
      occurrence_id TEXT PRIMARY KEY REFERENCES occurrences,comment_id TEXT,label_subtype TEXT,
      language_original TEXT,confidence_original TEXT,context_summary TEXT,rationale TEXT,
      screenshot_filename TEXT,post_group_original TEXT,post_group_key TEXT,
      image_status TEXT,context_status TEXT);
      CREATE TABLE IF NOT EXISTS screenshot_subset_links(source_id TEXT REFERENCES sources,
        excel_row INTEGER,occurrence_id TEXT REFERENCES occurrences,PRIMARY KEY(source_id,excel_row));
      CREATE TABLE IF NOT EXISTS workbook_notes(source_id TEXT PRIMARY KEY REFERENCES sources,notes_json TEXT);
    ''')
    reports=[]
    try:
        for path in sorted(map(Path,paths),key=lambda p:p.name):
            content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
            book=pd.ExcelFile(io.BytesIO(content))
            if 'Dataset' not in book.sheet_names:raise ValueError('Expected Dataset sheet')
            frame=pd.read_excel(book,'Dataset').fillna('')
            if not REQUIRED.issubset(frame.columns):raise ValueError('Workbook columns missing')
            if frame.ID.duplicated().any():raise ValueError('Repeated source comment ID')
            frame['label_key']=frame.Sinf.map(normalize)
            if not frame.label_key.isin(LABELS).all():raise ValueError('Unknown label; do not silently map it to 0')
            if not frame['Izoh matni'].map(normalize).ne('').all():raise ValueError('Empty comment')
            sid=stable_id('src_',digest+':Dataset')
            con.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
              (sid,path.name,'','Dataset',digest,len(frame),'screenshot_workbook',NORMALIZATION_VERSION))
            existing=0;lookup={}
            for i,row in enumerate(frame.to_dict('records'),2):
                tid=text_id(row['Izoh matni']);oid=stable_id('occ_',sid+':'+str(i))
                existing+=bool(con.execute('SELECT 1 FROM texts WHERE text_id=?',(tid,)).fetchone())
                con.execute('INSERT OR IGNORE INTO texts VALUES (?,?,?,?)',
                  (tid,row['Izoh matni'],normalize(row['Izoh matni']),json.dumps(quality_flags(row['Izoh matni']))))
                # Codes such as P1/T1 are local to each workbook, not globally unique post IDs.
                group=stable_id('ig_group_',digest+':'+str(row['Post guruhi'])) if str(row['Post guruhi']).strip() else ''
                con.execute('INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (oid,tid,sid,i,str(row['ID']),row['Izoh matni'],'Instagram','Instagram',
                   'screenshot_workbook_claim_images_not_supplied','',group,'',None))
                attrs={str(k):str(v) for k,v in row.items() if k not in ['label_key','Izoh matni']}
                key=row['label_key'];candidate=LABELS[key]
                con.execute('INSERT INTO labels VALUES (?,?,?,?,?,?,?,?,?)',
                  (stable_id('lab_',oid),oid,tid,row['Sinf'],candidate,
                   'workbook_claimed_manual_initial_classification','single_annotation_claim_unconfirmed',
                   'screenshot_workbook',json.dumps(attrs,ensure_ascii=False)))
                con.execute('INSERT INTO screenshot_workbook_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                  (oid,str(row['ID']),key,str(row.get('Til','')),str(row.get('Ishonch','')),
                   row['Post konteksti'],row['Tasnif asosi'],row['Skrinshot fayli'],str(row['Post guruhi']),
                   group,'original_image_not_supplied','annotator_summary_not_checked_against_image'))
                con.execute("INSERT OR IGNORE INTO registry_status VALUES (?,'screenshot_workbook','',0,0,0,0,0,NULL,'quarantine','screenshot_pending_independent_review_and_source_check')",(tid,))
                con.execute('''UPDATE registry_status SET
                  origins=(SELECT group_concat(DISTINCT origin) FROM labels WHERE text_id=?),
                  binary_labels=COALESCE((SELECT group_concat(DISTINCT binary_candidate) FROM labels WHERE text_id=?),''),
                  has_label_conflict=(SELECT count(DISTINCT binary_candidate)>1 FROM labels WHERE text_id=?) WHERE text_id=?''',(tid,tid,tid,tid))
                con.execute("UPDATE registry_status SET split='quarantine',split_reason='synthetic_real_collision' WHERE text_id=? AND origins LIKE '%synthetic%'",(tid,))
                lookup[str(row['ID'])]=(oid,row)
            subset_rows=0
            for sheet in book.sheet_names:
                if sheet=='Dataset':continue
                sub=pd.read_excel(book,sheet).fillna('')
                subid=stable_id('src_',digest+':'+sheet)
                role='screenshot_subset_view' if sheet=='Kinoya va sarkazm' else 'screenshot_metadata'
                con.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                  (subid,path.name,'',sheet,digest,len(sub),role,NORMALIZATION_VERSION))
                if role=='screenshot_subset_view':
                    for i,row in enumerate(sub.to_dict('records'),2):
                        if str(row['ID']) not in lookup:raise ValueError('Subset ID absent from main sheet')
                        oid,parent=lookup[str(row['ID'])]
                        if any(str(row[k])!=str(parent[k]) for k in REQUIRED):raise ValueError('Subset row differs from main sheet')
                        if normalize(row['Sinf']) not in ['kinoya','sarkazm']:raise ValueError('Unexpected subset class')
                        con.execute('INSERT INTO screenshot_subset_links VALUES (?,?,?)',(subid,i,oid))
                    subset_rows+=len(sub)
                else:
                    con.execute('INSERT INTO workbook_notes VALUES (?,?)',
                      (subid,json.dumps({'columns':list(sub.columns),'rows':sub.astype(str).to_dict('records')},ensure_ascii=False)))
            reports.append({'filename':path.name,'sha256':digest,'rows':len(frame),
              'labels':frame.label_key.value_counts().to_dict(),'post_groups':frame['Post guruhi'].nunique(),
              'screenshot_filenames':frame['Skrinshot fayli'].nunique(),'existing_registry_matches':existing,
              'subset_rows_linked_not_recounted':subset_rows})
        con.commit()
    except Exception:
        con.rollback();con.close();raise
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    query='''SELECT t.text_id,s.filename,w.comment_id,t.representative_text AS text,
      w.label_subtype,l.binary_candidate AS binary_label,l.verification_status,w.language_original,
      w.confidence_original,w.context_summary,w.context_status,w.rationale,w.screenshot_filename,
      w.post_group_original,w.post_group_key,w.image_status,r.split,r.split_reason
      FROM screenshot_workbook_rows w JOIN occurrences o USING(occurrence_id)
      JOIN sources s ON s.source_id=o.source_id JOIN texts t ON t.text_id=o.text_id
      JOIN labels l ON l.occurrence_id=o.occurrence_id JOIN registry_status r ON r.text_id=o.text_id'''
    combined=pd.read_sql_query(query,con).sort_values(['filename','comment_id'])
    combined.to_csv(out/'screenshot_comments_combined.csv',index=False,encoding='utf-8-sig')
    combined[combined.label_subtype.eq('noaniq')].to_csv(out/'screenshot_uncertain.csv',index=False,encoding='utf-8-sig')
    combined[combined.binary_label.notna()].to_csv(out/'screenshot_binary_candidates.csv',index=False,encoding='utf-8-sig')
    with pd.ExcelWriter(out/'screenshot_comments_combined.xlsx',engine='openpyxl') as writer:
        combined.to_excel(writer,sheet_name='Barcha_izohlar',index=False)
        combined.label_subtype.value_counts().rename_axis('class').reset_index(name='n').to_excel(writer,sheet_name='Taqsimot',index=False)
        ws=writer.sheets['Barcha_izohlar'];ws.freeze_panes='E2';ws.auto_filter.ref=ws.dimensions
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value,str):cell.data_type='s'
    # A second reviewer must not see initial subtype or rationale.
    blind=combined[['text_id','text','context_summary','context_status','screenshot_filename','image_status']].copy()
    for col in ['annotator_id','label','is_human','needs_context','rationale']:blind[col]=''
    blind.to_csv(out/'screenshot_second_review_blind.csv',index=False,encoding='utf-8-sig')
    export_csv(con,'SELECT * FROM registry_status ORDER BY text_id',out/'registry_status_updated.csv')
    report={'workbooks':reports,'new_workbook_rows':sum(r['rows'] for r in reports),
      'combined_rows':len(combined),'combined_unique_texts':combined.text_id.nunique(),
      'label_counts':combined.label_subtype.value_counts().to_dict(),
      'binary_candidates':int(combined.binary_label.notna().sum()),
      'uncertain_not_mapped_to_zero':int(combined.binary_label.isna().sum()),
      'registry_unique_texts':con.execute('SELECT count(*) FROM texts').fetchone()[0],
      'registry_occurrences':con.execute('SELECT count(*) FROM occurrences').fetchone()[0],
      'human_gold_ready':False,'new_ig_train_val_test_assigned':False,
      'reason':'Initial single annotation; image evidence and globally verified post/thread keys unavailable. Existing video splits preserved.'}
    con.close();report['checks']=validate(db)
    (out/'screenshot_workbook_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
