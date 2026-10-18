"""Membuat paket rilis untuk pembaruan otomatis (GitHub Releases).

Pemakaian (dari folder aplikasi):
    python tools/buat_rilis.py --notes "Ringkasan perubahan"

Hasil di folder dist/:
    SoundOn_Update_<versi>.zip   -> unggah ke GitHub Release dengan tag v<versi>
    manifest.json                -> unggah ke rilis yang sama

Versi dibaca dari APP_VERSION di soundon_dashboard.py.
soundon.license dan update_config.json tidak pernah dimasukkan ke paket.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from updater import allowed_relpath, PROTECTED  # noqa: E402

TOP = 'SoundOn_Account_Manager'


def app_version():
    text = (APP / 'soundon_dashboard.py').read_text(encoding='utf-8')
    m = re.search(r"^APP_VERSION='(\d+\.\d+\.\d+)'", text, re.M)
    if not m:
        sys.exit('APP_VERSION tidak ditemukan di soundon_dashboard.py')
    return m.group(1)


def changelog_notes(version):
    """Judul entri versi ini di docs/Riwayat_Perbaikan.txt (dipakai bila --notes kosong)."""
    try:
        text = (APP / 'docs' / 'Riwayat_Perbaikan.txt').read_text(encoding='utf-8')
    except OSError:
        return ''
    m = re.search(r'^' + re.escape(version) + r':\s*(.+)$', text, re.M)
    return m.group(1).strip()[:200] if m else ''


def collect():
    files = []
    for p in sorted(APP.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(APP).as_posix()
        if '/' not in rel and p.name in PROTECTED:
            continue
        if allowed_relpath(rel):
            files.append((p, rel))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--notes', default='')
    ap.add_argument('--out', default=str(APP / 'dist'))
    args = ap.parse_args()
    version = app_version()
    for f in ('upload_manager.py',):
        if version not in (APP / f).read_text(encoding='utf-8'):
            print('PERINGATAN: versi %s tidak ditemukan di %s' % (version, f))
    for p, rel in collect():
        if p.suffix == '.py':
            compile(p.read_text(encoding='utf-8-sig'), rel, 'exec')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    zip_name = 'SoundOn_Update_%s.zip' % version
    zpath = out / zip_name
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for p, rel in collect():
            z.write(p, TOP + '/' + rel)
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    manifest = {'version': version, 'tag': 'v' + version, 'zip_name': zip_name, 'sha256': sha,
                'notes': args.notes or changelog_notes(version), 'published': datetime.now().strftime('%Y-%m-%d %H:%M')}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Versi      :', version)
    print('Tag rilis  : v' + version)
    print('ZIP        :', zpath)
    print('Manifest   :', out / 'manifest.json')
    print('SHA-256    :', sha)
    print('Catatan    :', manifest['notes'])
    print('\nTerbitkan otomatis: python tools/terbitkan_rilis.py')
    print('atau unggah KEDUA file ke GitHub > Releases > Draft a new release, tag v%s, lalu Publish.' % version)


if __name__ == '__main__':
    main()
