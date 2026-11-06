import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from uzsarcasm.build import SCHEMA,add_frame,auxiliary,build
from uzsarcasm.core import normalize,text_id
from uzsarcasm.prepare import prepare,validate
from uzsarcasm.review import import_reviews
from uzsarcasm.screenshots import ingest


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/'registry.sqlite'
        self.con=sqlite3.connect(self.db);self.con.executescript(SCHEMA)

    def tearDown(self):
        self.con.close();self.temp.cleanup()

    def add(self,role,frame,name):
        sid='src_'+str(self.con.execute('SELECT count(*) FROM sources').fetchone()[0])
        self.con.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',(sid,name,'','test',sid,len(frame),role,'test'))
        add_frame(self.con,frame,sid,role,name)

    def finish(self):
        self.con.executescript('''INSERT INTO context SELECT DISTINCT video_id,'','not_fetched','','','unavailable'
          FROM occurrences WHERE resolved_platform='YouTube' AND video_id<>'';
          INSERT INTO registry_status SELECT t.text_id,
          COALESCE((SELECT group_concat(DISTINCT origin) FROM labels l WHERE l.text_id=t.text_id),'unlabeled'),
          COALESCE((SELECT group_concat(DISTINCT binary_candidate) FROM labels l WHERE l.text_id=t.text_id),''),
          (SELECT count(DISTINCT binary_candidate)>1 FROM labels l WHERE l.text_id=t.text_id),
          EXISTS(SELECT 1 FROM labels l WHERE l.text_id=t.text_id AND verification_status='auto_not_detected'),0,0,
          (SELECT count(DISTINCT video_id) FROM occurrences o WHERE o.text_id=t.text_id AND resolved_platform='YouTube' AND video_id<>''),
          NULL,'quarantine','not_assigned' FROM texts t;''')
        self.con.commit()
        return prepare(self.db,self.root/'exports')

    def populated(self):
        raw=[];legacy=[]
        for video in range(20):
            for j in range(10):
                text=f'Video {video} izoh {j} yaxshi tushunarli matn'
                raw.append({'Comment':text,'VideoID':f'video{video}'})
                legacy.append({'text':text,'ID':len(legacy)+1,'Source':'YouTube','sarcasm_label':j%2})
        raw.extend([{'Comment':'Bir xil qayta kelgan gap','VideoID':'video0'}, {'Comment':'Bir xil qayta kelgan gap','VideoID':'video1'}])
        self.add('raw',pd.DataFrame(raw),'youtube_comments.xlsx')
        self.add('legacy_verified',pd.DataFrame(legacy),'Uzbek_Sarcasm_Verified_Results.xlsx')
        self.add('synthetic',pd.DataFrame([{'Text_uz':'Suniy gap juda qiziq','Sarcasm':1}]),'synthetic_Sarcasm_10k.xlsx')

    def test_normalization_keeps_emoji_and_merges_apostrophes(self):
        self.assertEqual(text_id('  Zoʻr\nGAP 😂 '),text_id("zo'r gap 😂"))
        self.assertNotEqual(text_id('gap 😂'),text_id('gap 🙄'))
        self.assertNotEqual(text_id('зўр'),text_id("zo'r"))

    def test_original_label_provenance_not_overwritten(self):
        self.add('weak_50k',pd.DataFrame([{'Text_uz':'Bu bir xil matn','Sarcasm':0,'Label_source':'auto'}]),'Sarcasm_labeled_50k.xlsx')
        self.add('legacy_verified',pd.DataFrame([{'text':'BU bir xil matn','sarcasm_label':1}]),'Uzbek_Sarcasm_Verified_Results.xlsx')
        self.finish()
        self.assertEqual(self.con.execute('SELECT count(*) FROM texts').fetchone()[0],1)
        self.assertEqual(self.con.execute('SELECT count(*) FROM labels').fetchone()[0],2)
        self.assertEqual(self.con.execute('SELECT has_label_conflict,confirmed_negative,human_verified FROM registry_status').fetchone(),(1,0,0))
        self.assertEqual(self.con.execute("SELECT verification_status FROM labels WHERE origin='weak_50k'").fetchone()[0],'auto_not_detected')

    def test_group_split_and_synthetic_isolation(self):
        self.populated();self.finish();self.assertTrue(all(validate(self.db).values()))
        self.assertEqual(self.con.execute('SELECT split_reason FROM registry_status WHERE text_id=?',(text_id('Bir xil qayta kelgan gap'),)).fetchone()[0],'same_text_in_multiple_videos')
        self.assertEqual(self.con.execute("SELECT split FROM registry_status WHERE origins='synthetic'").fetchone()[0],'synthetic_train_only')
        self.assertEqual(self.con.execute("SELECT count(DISTINCT split) FROM legacy_experiment").fetchone()[0],3)

    def test_auto_zero_cannot_become_human_negative(self):
        self.populated();self.finish()
        self.assertEqual(self.con.execute('SELECT sum(confirmed_negative) FROM registry_status').fetchone()[0],0)
        self.assertEqual(len(pd.read_csv(self.root/'exports/confirmed_negative.csv')),0)

    def reviews(self,rows):
        p=self.root/'reviews.csv'
        pd.DataFrame(rows,columns=['text_id','annotator_id','label','is_human','needs_context','rationale']).to_csv(p,index=False)
        return p

    def test_two_humans_required_and_disagreement_stays_pending(self):
        self.populated();self.finish();tid=self.con.execute('SELECT text_id FROM legacy_experiment LIMIT 1').fetchone()[0]
        path=self.reviews([[tid,'A','0','true','false','Literal statement']])
        import_reviews(self.db,path,self.root/'human')
        self.assertEqual(self.con.execute('SELECT human_verified FROM registry_status WHERE text_id=?',(tid,)).fetchone()[0],0)
        path=self.reviews([[tid,'B','0','true','false','No implicit reversal']])
        import_reviews(self.db,path,self.root/'human')
        self.assertEqual(self.con.execute('SELECT human_verified,confirmed_negative FROM registry_status WHERE text_id=?',(tid,)).fetchone(),(1,1))
        self.assertTrue(all(validate(self.db).values()))
        path=self.reviews([[tid,'C','1','true','false','Different interpretation']])
        import_reviews(self.db,path,self.root/'human')
        self.assertEqual(self.con.execute('SELECT human_verified,confirmed_negative FROM registry_status WHERE text_id=?',(tid,)).fetchone(),(0,0))

    def test_machine_review_cannot_claim_human_attestation(self):
        self.populated();self.finish();tid=self.con.execute('SELECT text_id FROM texts LIMIT 1').fetchone()[0]
        with self.assertRaises(ValueError):
            import_reviews(self.db,self.reviews([[tid,'LLM','0','false','false','Generated']]),self.root/'human')

    def test_screenshot_transcription_does_not_verify_label(self):
        self.populated();self.finish()
        image=self.root/'screenshot.png';image.write_bytes(b'test image payload not OCR input')
        manifest=self.root/'screens.csv'
        pd.DataFrame([{'image_filename':image.name,'text':'Yangi instagram izohi','transcription_verified':'true',
                       'post_key':'post42','source_url':'','claimed_label':'1'}]).to_csv(manifest,index=False)
        ingest(self.db,manifest,self.root,self.root/'screens')
        self.assertEqual(self.con.execute('SELECT human_verified,split FROM registry_status WHERE text_id=?',(text_id('Yangi instagram izohi'),)).fetchone(),(0,'quarantine'))
        self.assertTrue(all(validate(self.db).values()))

    def test_annotation_batches_are_blind_and_disjoint_from_prior_labels(self):
        from uzsarcasm.batches import create_batches
        self.populated();self.finish()
        report=create_batches(self.db,self.root/'batches')
        a=pd.read_csv(self.root/'batches/annotation_A.csv',keep_default_na=False)
        b=pd.read_csv(self.root/'batches/annotation_B.csv',keep_default_na=False)
        self.assertEqual(list(a.text_id),list(b.text_id))
        self.assertTrue(a.label.eq('').all())
        self.assertNotIn('legacy_label',a.columns)
        self.assertNotIn('split',a.columns)
        self.assertEqual(len(a),a.text_id.nunique())
        self.assertEqual(report['human_annotations_completed'],0)

    def test_build_original_excel_and_zip_end_to_end(self):
        import zipfile
        inp=self.root/'input';inp.mkdir()
        pd.DataFrame([{'Text_uz':'Oddiy haqiqiy gap','Sarcasm':0,'Label_source':'auto'}]).to_excel(inp/'Sarcasm_labeled_50k.xlsx',sheet_name='Sarkazm',index=False)
        raw=self.root/'raw.xlsx';pd.DataFrame([{'Comment':'Oddiy haqiqiy gap','VideoID':'abc'}]).to_excel(raw,index=False)
        with zipfile.ZipFile(inp/'Comments.zip','w') as z:z.write(raw,'youtube_comments.xlsx')
        output=self.root/'rebuilt';db=build(inp,output);report=prepare(db,output)
        self.assertEqual(report['occurrences'],2)
        self.assertEqual(report['unique_texts'],1)
        self.assertFalse(report['gold_test_ready'])
        self.assertTrue(all(validate(db).values()))

if __name__=='__main__':unittest.main()
