"""Menerbitkan paket rilis di dist/ ke GitHub Releases (tanpa unggah manual).

Pemakaian (dari folder aplikasi), setelah `python tools/buat_rilis.py`:
    python tools/terbitkan_rilis.py [--token TOKEN] [--replace]

Token dibaca dari --token, variabel SOUNDON_GITHUB_TOKEN, atau ~/.soundon_github_token
(diisi dari Pengaturan > Pembaruan > Penerbit Otomatis). Gunakan fine-grained token yang
hanya punya akses ke repo rilis dengan izin "Contents: Read and write".
"""
import argparse
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from updater import DEFAULT_GITHUB_REPO, load_config  # noqa: E402
import release_publisher as rp  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token')
    ap.add_argument('--repo')
    ap.add_argument('--dist', default=str(APP / 'dist'))
    ap.add_argument('--replace', action='store_true', help='timpa file rilis bila tag sudah ada')
    args = ap.parse_args()
    token = (args.token or rp.load_token()).strip()
    if not token:
        sys.exit('Token GitHub belum diatur (Pengaturan > Pembaruan > Penerbit Otomatis, atau --token).')
    repo = args.repo or load_config(str(APP)).get('github_repo') or DEFAULT_GITHUB_REPO
    try:
        version = rp.publish(args.dist, token, repo, replace=args.replace)
    except rp.PublishError as exc:
        sys.exit('GAGAL: %s' % exc)
    print('\nBERHASIL: %s diterbitkan. Semua aplikasi akan memperbarui otomatis.' % version)


if __name__ == '__main__':
    main()
