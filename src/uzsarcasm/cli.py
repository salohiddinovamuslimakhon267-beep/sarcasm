import argparse
import json
from pathlib import Path

from .build import build
from .prepare import prepare,validate


def main():
    parser=argparse.ArgumentParser(description='Uzbek sarcasm dataset preparation')
    commands=parser.add_subparsers(dest='command',required=True)
    b=commands.add_parser('build');b.add_argument('--input',required=True);b.add_argument('--output',required=True)
    v=commands.add_parser('validate');v.add_argument('--db',required=True)
    e=commands.add_parser('experiment');e.add_argument('--db',required=True);e.add_argument('--output',required=True)
    c=commands.add_parser('fetch-titles');c.add_argument('--db',required=True);c.add_argument('--output',required=True);c.add_argument('--limit',type=int)
    r=commands.add_parser('import-reviews');r.add_argument('--db',required=True);r.add_argument('--csv',required=True);r.add_argument('--output',required=True)
    sh=commands.add_parser('ingest-screenshots');sh.add_argument('--db',required=True);sh.add_argument('--csv',required=True);sh.add_argument('--images',required=True);sh.add_argument('--output',required=True)
    ba=commands.add_parser('annotation-batches');ba.add_argument('--db',required=True);ba.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='build':result=prepare(build(args.input,args.output),args.output)
    elif args.command=='validate':result=validate(args.db)
    elif args.command=='experiment':
        from .experiment import run
        result=run(args.db,args.output)
    elif args.command=='fetch-titles':
        from .context import fetch_titles
        result=fetch_titles(args.db,args.output,args.limit)
    elif args.command=='annotation-batches':
        from .batches import create_batches
        result=create_batches(args.db,args.output)
    elif args.command=='ingest-screenshots':
        from .screenshots import ingest
        result=ingest(args.db,args.csv,args.images,args.output)
    else:
        from .review import import_reviews
        result=import_reviews(args.db,args.csv,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
