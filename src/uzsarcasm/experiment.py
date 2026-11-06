"""Diagnostic validation only. Never evaluate the held-out test or claim gold results."""
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score,confusion_matrix,f1_score,precision_score,recall_score
from sklearn.pipeline import FeatureUnion,Pipeline


def model():
    return Pipeline([('features',FeatureUnion([
      ('word',TfidfVectorizer(ngram_range=(1,2),min_df=2,max_features=40000,sublinear_tf=True)),
      ('char',TfidfVectorizer(analyzer='char',ngram_range=(3,5),min_df=2,max_features=60000,sublinear_tf=True))])),
      ('lr',LogisticRegression(C=1,class_weight='balanced',max_iter=1000,solver='liblinear',random_state=42))])


def metrics(y,p):
    return {'n':len(y),'accuracy':accuracy_score(y,p),'sarcasm_precision':precision_score(y,p,zero_division=0),
      'sarcasm_recall':recall_score(y,p,zero_division=0),'sarcasm_f1':f1_score(y,p,zero_division=0),
      'macro_f1':f1_score(y,p,average='macro',zero_division=0),
      'tn_fp_fn_tp':confusion_matrix(y,p,labels=[0,1]).ravel().tolist()}


def run(db,output):
    con=sqlite3.connect(db)
    train=pd.read_sql_query("SELECT * FROM legacy_experiment WHERE split='provisional_train' ORDER BY text_id",con)
    val=pd.read_sql_query("SELECT * FROM legacy_experiment WHERE split='provisional_validation' ORDER BY text_id",con)
    synth=pd.read_sql_query("SELECT t.text_id,t.representative_text AS text,l.binary_candidate AS legacy_label FROM labels l JOIN texts t USING(text_id) JOIN registry_status r USING(text_id) WHERE l.origin='synthetic' AND r.split='synthetic_train_only' ORDER BY t.text_id",con)
    con.close()
    if train.legacy_label.nunique()<2 or val.legacy_label.nunique()<2:raise ValueError('Both classes required in training and validation')
    if set(train.video_id)&set(val.video_id) or set(train.text_id)&set(val.text_id):raise ValueError('Leakage')
    results={'majority':metrics(val.legacy_label,np.full(len(val),int(train.legacy_label.mode().iloc[0])))}
    for name, extra, synthetic_weight in [('real_only',False,1),('real_plus_synthetic',True,1),('real_plus_synthetic_equal_source_weight',True,len(train)/max(len(synth),1))]:
        data=pd.concat([train,synth],ignore_index=True) if extra else train
        weights=np.ones(len(data))
        if extra:weights[len(train):]=synthetic_weight
        m=model();m.fit(data.text,data.legacy_label,lr__sample_weight=weights)
        results[name]=metrics(val.legacy_label,m.predict(val.text))
        print(name,results[name],flush=True)
    report={'warning':'Diagnostic against UNCONFIRMED legacy labels; not human gold or final model quality.',
      'train_real':len(train),'train_synthetic':len(synth),'validation_real':len(val),
      'test_evaluated':False,'seed':42,'tuning':'none','results':results,
      'protocol':'Frozen video groups; same real validation in all runs. Vectorizers fit only on train. TFIDF word1-2 + char3-5, balanced LR C1; no metadata/label-source features. Equal-source variant gives total synthetic sample weight equal to total real sample weight before class weighting.'}
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
