import csv
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from .core import normalize, quality_flags


def export_csv(con, sql, path):
    cursor = con.execute(sql)
    with Path(path).open('w',encoding='utf-8-sig',newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([col[0] for col in cursor.description])
        writer.writerows(cursor)


def assign_splits(con):
    """Partition videos, quarantine texts spanning videos, never create a gold label."""
    legacy = pd.read_sql_query('''SELECT DISTINCT l.text_id, l.binary_candidate AS label,
      min(o.video_id) AS video_id FROM labels l JOIN registry_status r USING(text_id)
      JOIN occurrences o USING(text_id)
      WHERE l.origin='legacy_verified' AND r.raw_video_count=1
        AND o.resolved_platform='YouTube' AND o.video_id<>''
      GROUP BY l.text_id,l.binary_candidate''', con)
    if len(legacy) and legacy.label.nunique()==2 and legacy.video_id.nunique()>=10 and legacy.label.value_counts().min()>=5:
        splitter = StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=42)
        rest, test = next(splitter.split(legacy,legacy.label,groups=legacy.video_id))
        remaining = legacy.iloc[rest]
        tr, va = next(splitter.split(remaining,remaining.label,groups=remaining.video_id))
        assignment = {v:'provisional_train' for v in remaining.iloc[tr].video_id}
        assignment.update({v:'provisional_validation' for v in remaining.iloc[va].video_id})
        assignment.update({v:'provisional_test' for v in legacy.iloc[test].video_id})
    else:
        assignment = {}
    all_videos = [r[0] for r in con.execute('SELECT video_id FROM context ORDER BY video_id')]
    # Extra videos have no legacy evaluation rows and can supply unlabeled training data.
    for video in all_videos: assignment.setdefault(video,'provisional_train')
    con.execute('CREATE TABLE video_splits(video_id TEXT PRIMARY KEY, split TEXT, seed INTEGER)')
    con.executemany('INSERT INTO video_splits VALUES (?,?,42)',sorted(assignment.items()))
    con.execute('''UPDATE registry_status SET group_id=(SELECT min(video_id) FROM occurrences o
      WHERE o.text_id=registry_status.text_id AND resolved_platform='YouTube' AND video_id<>'')
      WHERE raw_video_count=1''')
    con.execute('''UPDATE registry_status SET split=COALESCE((SELECT split FROM video_splits v
      WHERE v.video_id=registry_status.group_id),'quarantine'), split_reason='single_youtube_video'
      WHERE raw_video_count=1''')
    con.execute("UPDATE registry_status SET split_reason='same_text_in_multiple_videos' WHERE raw_video_count>1")
    con.execute("UPDATE registry_status SET split_reason='no_trustworthy_video_group' WHERE raw_video_count=0")
    con.execute('''UPDATE registry_status SET split='synthetic_train_only', split_reason='synthetic_never_evaluation'
      WHERE origins='synthetic' ''')
    # Synthetic/real collision must be quarantined even if future inputs introduce it.
    con.execute("UPDATE registry_status SET split='quarantine',split_reason='synthetic_real_collision' WHERE origins LIKE '%synthetic%' AND origins<>'synthetic'")
    bad = [r[0] for r in con.execute('SELECT text_id,quality_flags FROM texts')
           if any(x in json.loads(r[1]) for x in ['empty','no_letters','placeholder_only'])]
    con.executemany("UPDATE registry_status SET split='quarantine',split_reason='text_quality_review' WHERE text_id=?",[(x,) for x in bad])
    return legacy


def prepare(db, output_dir):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(db)
    if con.execute("SELECT name FROM sqlite_master WHERE name='video_splits'").fetchone():
        raise ValueError('Splits already assigned; rebuild in a new directory to create a new dataset version')
    assign_splits(con)
    con.commit()
    con.executescript('''CREATE VIEW review_items AS
      SELECT t.text_id,t.representative_text,t.quality_flags,r.origins,r.binary_labels,
       r.has_label_conflict,r.has_unverified_auto_zero,r.raw_video_count,r.group_id,r.split,r.split_reason,
       CASE WHEN r.has_label_conflict=1 THEN 'P1_label_disagreement'
         WHEN EXISTS(SELECT 1 FROM labels l WHERE l.text_id=t.text_id AND l.origin='legacy_verified') THEN 'P2_legacy_verified_audit'
         WHEN EXISTS(SELECT 1 FROM labels l WHERE l.text_id=t.text_id AND l.binary_candidate=1 AND l.origin='weak_50k') THEN 'P2_rare_positive'
         WHEN r.origins LIKE '%legacy_annotations%' THEN 'P3_uniform_neutral_audit'
         WHEN r.origins='unlabeled' THEN 'P4_unlabeled'
         ELSE 'P3_unverified_labels' END AS priority,
       (SELECT json_group_array(json_object('origin',l.origin,'value',l.original_label,'status',l.verification_status)) FROM labels l WHERE l.text_id=t.text_id) AS label_history
      FROM texts t JOIN registry_status r USING(text_id);
    CREATE VIEW legacy_experiment AS
      SELECT DISTINCT l.text_id,t.representative_text AS text,l.binary_candidate AS legacy_label,
       r.group_id AS video_id,r.split,r.has_label_conflict,
       'unconfirmed_legacy_labels_not_gold' AS label_status
      FROM labels l JOIN texts t USING(text_id) JOIN registry_status r USING(text_id)
      WHERE l.origin='legacy_verified' AND r.split IN ('provisional_train','provisional_validation','provisional_test');
    ''')
    export_csv(con,'SELECT * FROM registry_status ORDER BY text_id',out/'registry_status.csv')
    export_csv(con,'SELECT * FROM video_splits ORDER BY video_id',out/'video_splits.csv')
    export_csv(con,'SELECT * FROM review_items WHERE origins<>\'synthetic\' AND origins<>\'unlabeled\' ORDER BY priority,text_id',out/'review_queue.csv')
    export_csv(con,'SELECT * FROM review_items WHERE has_label_conflict=1 ORDER BY text_id',out/'label_disagreements.csv')
    export_csv(con,"SELECT * FROM labels WHERE verification_status='auto_not_detected' ORDER BY text_id",out/'unverified_auto_zero.csv')
    # Explicitly empty until independent human annotations have been adjudicated.
    export_csv(con,'SELECT l.* FROM labels l JOIN registry_status r USING(text_id) WHERE r.confirmed_negative=1',out/'confirmed_negative.csv')
    export_csv(con,'''SELECT o.occurrence_id,o.source_id,o.excel_row,o.source_record_id,o.text_id,o.declared_platform,
      o.resolved_platform,o.platform_status,o.video_id AS original_video_id,r.group_id AS recovered_unique_video_id,
      r.raw_video_count,c.title,c.title_status,c.parent_context_status
      FROM occurrences o JOIN registry_status r USING(text_id) LEFT JOIN context c ON c.video_id=r.group_id
      WHERE o.source_id IN (SELECT source_id FROM sources WHERE role IN ('legacy_verified','weak_50k','posts','curated_unlabeled'))
      ORDER BY o.source_id,o.excel_row''',out/'context_links.csv')
    for split in ['provisional_train','provisional_validation','provisional_test']:
        export_csv(con,f"SELECT * FROM legacy_experiment WHERE split='{split}' ORDER BY text_id",out/(split+'.csv'))
    export_csv(con,"SELECT DISTINCT l.text_id,t.representative_text AS text,l.binary_candidate AS label,l.verification_status FROM labels l JOIN texts t USING(text_id) JOIN registry_status r USING(text_id) WHERE l.origin='synthetic' AND r.split='synthetic_train_only' ORDER BY text_id",out/'synthetic_train_only.csv')
    # No previous machine/legacy decisions shown to independent annotators.
    blind=pd.read_sql_query("SELECT text_id,representative_text AS text FROM review_items WHERE origins<>'synthetic' AND origins<>'unlabeled' ORDER BY priority,text_id LIMIT 3000",con)
    for col in ['annotator_id','label','is_human','confidence','needs_context','rationale']: blind[col]=''
    blind.to_csv(out/'human_review_blind.csv',index=False,encoding='utf-8-sig')
    report={
      'normalization':'NFKC + casefold + apostrophe normalization + whitespace; emoji preserved; no transliteration',
      'occurrences':con.execute('SELECT count(*) FROM occurrences').fetchone()[0],
      'unique_texts':con.execute('SELECT count(*) FROM texts').fetchone()[0],
      'label_rows':con.execute('SELECT count(*) FROM labels').fetchone()[0],
      'sources':pd.read_sql_query('SELECT filename,member,sheet,rows,role FROM sources',con).to_dict('records'),
      'splits':dict(con.execute('SELECT split,count(*) FROM registry_status GROUP BY split').fetchall()),
      'quarantine_reasons':dict(con.execute("SELECT split_reason,count(*) FROM registry_status WHERE split='quarantine' GROUP BY split_reason").fetchall()),
      'legacy_experiment_split_labels':pd.read_sql_query('SELECT split,legacy_label,count(*) AS n FROM legacy_experiment GROUP BY split,legacy_label',con).to_dict('records'),
      'candidate_label_disagreements':con.execute('SELECT count(*) FROM registry_status WHERE has_label_conflict=1').fetchone()[0],
      'confirmed_negative':0,'human_verified':0,'gold_test_ready':False,
      'context':{'youtube_videos':con.execute('SELECT count(*) FROM context').fetchone()[0],
                 'legacy_verified_unique_video':con.execute("SELECT count(DISTINCT l.text_id) FROM labels l JOIN registry_status r USING(text_id) WHERE l.origin='legacy_verified' AND r.raw_video_count=1").fetchone()[0],
                 'legacy_verified_any_youtube_video':con.execute("SELECT count(DISTINCT l.text_id) FROM labels l JOIN registry_status r USING(text_id) WHERE l.origin='legacy_verified' AND r.raw_video_count>0").fetchone()[0]},
      'warnings':['All existing labels remain unconfirmed by independent humans.',
        'Neutral legacy annotations are not mapped to binary negatives.',
        'Instagram-named workbook is quarantined as an uncertain platform, not evidence of Instagram coverage.',
        'Multi-video texts are quarantined across ALL roles, preventing cross-video duplicate leakage.',
        'Parent comments are unavailable; no parent or title content is invented.',
        'Exact normalization cannot guarantee removal of paraphrases or all near duplicates.'],
    }
    (out/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    con.commit();con.close()
    validate(db)
    return report


def validate(db):
    con=sqlite3.connect(db)
    checks={
      'foreign_keys':not con.execute('PRAGMA foreign_key_check').fetchall(),
      'one_registry_row_per_text':con.execute('SELECT count(*) FROM texts').fetchone()[0]==con.execute('SELECT count(*) FROM registry_status').fetchone()[0],
      'no_multivideo_assigned':con.execute("SELECT count(*) FROM registry_status WHERE raw_video_count>1 AND split<>'quarantine'").fetchone()[0]==0,
      'no_synthetic_in_evaluation':con.execute("SELECT count(*) FROM registry_status WHERE origins LIKE '%synthetic%' AND split IN ('provisional_test','provisional_validation')").fetchone()[0]==0,
      'no_video_cross_split':con.execute('''SELECT count(*) FROM (SELECT o.video_id FROM occurrences o
        JOIN registry_status r USING(text_id) WHERE o.resolved_platform='YouTube' AND o.video_id<>'' AND r.split LIKE 'provisional_%'
        GROUP BY o.video_id HAVING count(DISTINCT r.split)>1)''').fetchone()[0]==0,
      'no_unsubstantiated_gold':True,
      'confirmed_negative_requires_human':con.execute('SELECT count(*) FROM registry_status WHERE confirmed_negative=1 AND human_verified<>1').fetchone()[0]==0,
      'legacy_no_duplicate_rows':con.execute('SELECT count(*)-count(DISTINCT text_id) FROM legacy_experiment').fetchone()[0]==0,
    }
    resolutions=con.execute("SELECT name FROM sqlite_master WHERE name='human_resolution'").fetchone()
    if resolutions:
        checks['no_unsubstantiated_gold']=con.execute("SELECT count(*) FROM registry_status r WHERE r.human_verified=1 AND NOT EXISTS (SELECT 1 FROM human_resolution h WHERE h.text_id=r.text_id AND h.status='human_consensus' AND h.n_reviewers>=2)").fetchone()[0]==0
    else:
        checks['no_unsubstantiated_gold']=con.execute('SELECT count(*) FROM registry_status WHERE human_verified<>0 OR confirmed_negative<>0').fetchone()[0]==0
    con.close()
    if not all(checks.values()):raise AssertionError(checks)
    return checks
