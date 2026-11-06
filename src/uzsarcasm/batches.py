import json
import sqlite3
from pathlib import Path

import pandas as pd

from .core import stable_id


def create_batches(db,output):
    """Blend priority audits and seeded random raw examples; keep annotators blind."""
    con=sqlite3.connect(db)
    priority=pd.read_sql_query('''SELECT DISTINCT t.text_id,t.representative_text AS text,r.split,r.group_id AS video_id
      FROM texts t JOIN registry_status r USING(text_id) JOIN occurrences o USING(text_id)
      JOIN sources s USING(source_id) WHERE s.role IN ('legacy_verified','curated_unlabeled') OR
      EXISTS(SELECT 1 FROM labels l WHERE l.text_id=t.text_id AND l.origin='weak_50k' AND l.binary_candidate=1)''',con)
    selected=set(priority.text_id);parts=[priority]
    for split,n in [('provisional_test',500),('provisional_validation',250),('provisional_train',1000)]:
        frame=pd.read_sql_query('''SELECT t.text_id,t.representative_text AS text,r.split,r.group_id AS video_id
          FROM texts t JOIN registry_status r USING(text_id) WHERE r.split=? AND r.origins='unlabeled' ''',con,params=[split])
        frame=frame[~frame.text_id.isin(selected)].copy()
        frame['sample_key']=frame.text_id.map(lambda t:stable_id('sample_', '42:'+t))
        frame=frame.sort_values('sample_key').head(n).drop(columns='sample_key')
        parts.append(frame);selected.update(frame.text_id)
    tasks=pd.concat(parts,ignore_index=True).drop_duplicates('text_id')
    # The private coordinator map carries split/video; annotators see only text and available context.
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    tasks.to_csv(out/'annotation_coordinator_map.csv',index=False,encoding='utf-8-sig')
    blind=tasks[['text_id','text']].sample(frac=1,random_state=42).reset_index(drop=True)
    blind['context_text']='';blind['context_status']='original_post_or_parent_not_available'
    for name in ['annotator_id','label','is_human','needs_context','confidence','rationale']:blind[name]=''
    for reviewer in ['A','B']:
        reviewer_frame=blind.copy();reviewer_frame['annotator_id']='reviewer_'+reviewer
        reviewer_frame.to_csv(out/f'annotation_{reviewer}.csv',index=False,encoding='utf-8-sig')
        with pd.ExcelWriter(out/f'annotation_{reviewer}.xlsx',engine='openpyxl') as writer:
            reviewer_frame.to_excel(writer,index=False,sheet_name='Mustaqil_baholash')
            ws=writer.sheets['Mustaqil_baholash'];ws.freeze_panes='C2';ws.auto_filter.ref=ws.dimensions
            ws.column_dimensions['A'].width=32;ws.column_dimensions['B'].width=85
            for cell in ws['B'][1:]:cell.alignment=__import__('openpyxl').styles.Alignment(wrap_text=True,vertical='top')
    report={'priority_rows':len(priority),'total_unique_tasks':len(tasks),
      'split_counts':tasks.split.value_counts().to_dict(),'random_raw_added':len(tasks)-len(priority),
      'seed':42,'human_annotations_completed':0,'instructions':'Two separate people; no prior labels; uncertain and needs_context are allowed. Do not infer 0 from missing context.'}
    (out/'annotation_batch_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    con.close();return report
