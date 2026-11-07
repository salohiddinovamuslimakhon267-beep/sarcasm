"""Package CSV/XLSX plus an xz-compressed registry below GitHub's file limit."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import zipfile


def sha_file(path):
    digest=hashlib.sha256()
    with open(path,'rb') as src:
        for chunk in iter(lambda:src.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def package(prepared,registry_xz,output):
    prepared=Path(prepared);registry_xz=Path(registry_xz);output=Path(output)
    original_hash=sha_file(prepared/'registry.sqlite')
    restored=hashlib.sha256()
    with lzma.open(registry_xz,'rb') as src:
        for chunk in iter(lambda:src.read(1024*1024),b''):restored.update(chunk)
    if restored.hexdigest()!=original_hash:raise ValueError('Compressed registry does not match source')
    prefix='prepared_v1_1/'
    hashes={}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for src in sorted(prepared.rglob('*')):
            if not src.is_file() or src.name=='registry.sqlite':continue
            rel=str(src.relative_to(prepared))
            if rel=='checksums.json':rel='checksums_original_uncompressed.json'
            archive.write(src,prefix+rel);hashes[rel]=sha_file(src)
        archive.write(registry_xz,prefix+'registry.sqlite.xz',compress_type=zipfile.ZIP_STORED)
        hashes['registry.sqlite.xz']=sha_file(registry_xz)
        note='''YUKLAB OLINGAN DATASET V1.1

CSV va Excel fayllari tayyor: ularni to‘g‘ridan-to‘g‘ri ochish mumkin.
SQLite reyestri registry.sqlite.xz ichida qo‘shimcha siqilgan.
Uni ochish uchun shu katalogda Python buyrug‘ini bajaring:

python -c "import lzma,shutil; s=lzma.open('registry.sqlite.xz','rb'); d=open('registry.sqlite','wb'); shutil.copyfileobj(s,d); s.close(); d.close()"

registry_restore.json ochilgan bazaning SHA256 hashini beradi.
checksums.json arxiv ichidagi fayllarni tekshiradi.
checksums_original_uncompressed.json tayyorlash bosqichidagi asl manifestdir.

Bu dastlabki yorliqlari saqlangan tayyorlash korpusi, inson-gold test emas.
'''
        extra={'DOWNLOAD_README_UZ.txt':note.encode('utf-8'),
          'registry_restore.json':json.dumps({'uncompressed_filename':'registry.sqlite','uncompressed_sha256':original_hash,
            'uncompressed_bytes':(prepared/'registry.sqlite').stat().st_size},indent=2).encode('utf-8')}
        for name,data in extra.items():
            archive.writestr(prefix+name,data);hashes[name]=hashlib.sha256(data).hexdigest()
        archive.writestr(prefix+'checksums.json',json.dumps(hashes,indent=2))
    if output.stat().st_size>=100*1024*1024:raise ValueError('Archive exceeds GitHub 100 MiB file limit')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP CRC check failed')
        for name,expected in hashes.items():
            if hashlib.sha256(archive.read(prefix+name)).hexdigest()!=expected:raise ValueError('ZIP SHA256 mismatch: '+name)
    return {'file':str(output),'bytes':output.stat().st_size,'sha256':sha_file(output),'verified_files':len(hashes),
            'registry_uncompressed_sha256':original_hash}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',required=True);p.add_argument('--registry-xz',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(package(a.prepared,a.registry_xz,a.output),indent=2))
