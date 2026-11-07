import tempfile
import unittest
import sqlite3
from pathlib import Path

import pandas as pd

import test_pipeline
from uzsarcasm.screenshot_workbooks import ingest_workbooks


class ScreenshotWorkbookTests(unittest.TestCase):
    setUp=test_pipeline.PipelineTests.setUp
    tearDown=test_pipeline.PipelineTests.tearDown
    add=test_pipeline.PipelineTests.add
    finish=test_pipeline.PipelineTests.finish
    populated=test_pipeline.PipelineTests.populated

    def fixture(self,bad_subset=False):
        path=self.root/'Skrinshot_test.xlsx'
        rows=[]
        for i,label in enumerate(['kinoya','sarkazm','kinoyasiz','noaniq']):
            rows.append({'ID':f'IG-{i}','Izoh matni':f'Yangi instagram matni {i}',
              'Sinf':label,'Post konteksti':'Post haqida dastlabki xulosa',
              'Tasnif asosi':'Dastlabki izoh','Skrinshot fayli':'image.png','Post guruhi':'P1'})
        d=pd.DataFrame(rows)
        subset=d[d.Sinf.isin(['kinoya','sarkazm'])].copy()
        if bad_subset:subset.loc[subset.index[0],'Sinf']='kinoyasiz'
        with pd.ExcelWriter(path) as writer:
            d.to_excel(writer,sheet_name='Dataset',index=False)
            subset.to_excel(writer,sheet_name='Kinoya va sarkazm',index=False)
            pd.DataFrame([{'Ko‘rsatkich':'Annotatsiya','Qiymat / izoh':'Ikkinchi annotator tekshirmagan'}]).to_excel(writer,sheet_name='Pasport',index=False)
        return path

    def test_subsets_not_double_counted_and_uncertainty_preserved(self):
        self.populated();self.finish()
        before=self.con.execute('SELECT count(*) FROM occurrences').fetchone()[0]
        report=ingest_workbooks(self.db,[self.fixture()],self.root/'new')
        self.assertEqual(report['new_workbook_rows'],4)
        self.assertEqual(self.con.execute('SELECT count(*) FROM occurrences').fetchone()[0],before+4)
        self.assertEqual(self.con.execute('SELECT count(*) FROM screenshot_subset_links').fetchone()[0],2)
        uncertain=self.con.execute("SELECT binary_candidate FROM labels WHERE original_label='noaniq'").fetchone()[0]
        self.assertIsNone(uncertain)
        self.assertEqual(self.con.execute('SELECT sum(human_verified) FROM registry_status').fetchone()[0],0)
        self.assertEqual(report['workbooks'][0]['subset_rows_linked_not_recounted'],2)
        candidates=pd.read_csv(self.root/'new/screenshot_binary_candidates.csv')
        self.assertEqual(len(candidates),3)

    def test_conflicting_subset_rolls_back(self):
        self.populated();self.finish()
        before=self.con.execute('SELECT count(*) FROM occurrences').fetchone()[0]
        with self.assertRaises(ValueError):ingest_workbooks(self.db,[self.fixture(True)],self.root/'new')
        self.assertEqual(self.con.execute('SELECT count(*) FROM occurrences').fetchone()[0],before)

    def test_existing_video_splits_preserved_and_no_images_fabricated(self):
        self.populated();self.finish()
        before=self.con.execute('SELECT * FROM video_splits ORDER BY video_id').fetchall()
        ingest_workbooks(self.db,[self.fixture()],self.root/'new')
        self.assertEqual(self.con.execute('SELECT * FROM video_splits ORDER BY video_id').fetchall(),before)
        self.assertEqual(self.con.execute('SELECT DISTINCT image_status FROM screenshot_workbook_rows').fetchall(),[('original_image_not_supplied',)])
        self.assertEqual(self.con.execute("SELECT count(*) FROM registry_status WHERE origins='screenshot_workbook' AND split<>'quarantine'").fetchone()[0],0)


if __name__=='__main__':unittest.main()
