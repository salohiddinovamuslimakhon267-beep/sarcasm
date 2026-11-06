import concurrent.futures
import datetime
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request

from .prepare import export_csv


def fetch_one(video):
    url='https://www.youtube.com/oembed?'+urllib.parse.urlencode({'url':'https://www.youtube.com/watch?v='+video,'format':'json'})
    try:
        with urllib.request.urlopen(url,timeout=15) as response:
            data=json.load(response)
        title=data.get('title','')
        return video,title,'fetched' if title else 'missing_title',url,datetime.datetime.now(datetime.timezone.utc).isoformat()
    except (urllib.error.URLError,TimeoutError,ValueError,OSError) as exc:
        reason=('http_'+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else 'proxy_403' if '403 Forbidden' in str(exc) else type(exc).__name__)
        return video,'','unavailable_'+reason,url,datetime.datetime.now(datetime.timezone.utc).isoformat()


def fetch_titles(db,output,limit=None):
    con=sqlite3.connect(db)
    query="SELECT video_id FROM context WHERE title_status<>'fetched' ORDER BY video_id"
    videos=[r[0] for r in con.execute(query)]
    if limit is not None: videos=videos[:limit]
    # oEmbed provides title only; it cannot restore comment/reply parents.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(fetch_one,videos):
            video,title,status,url,stamp=row
            con.execute('UPDATE context SET title=?,title_status=?,title_source=?,fetched_at=? WHERE video_id=?',
                        (title,status,url,stamp,video))
            print(video,status,flush=True)
    con.commit()
    export_csv(con,'SELECT * FROM context ORDER BY video_id',output)
    counts=dict(con.execute('SELECT title_status,count(*) FROM context GROUP BY title_status'))
    con.close();return counts
