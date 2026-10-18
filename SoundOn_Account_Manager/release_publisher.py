"""Menerbitkan rilis ke GitHub Releases (dipakai tools/terbitkan_rilis.py dan Penerbit Otomatis).

Penerbit Otomatis hanya aktif di komputer admin yang menyimpan token GitHub
(~/.soundon_github_token). Paket rilis yang diletakkan di ~/SoundOnRilis/masuk
(SoundOn_Update_<versi>.zip + manifest.json) diperiksa lalu diterbitkan sebagai
rilis "Latest"; semua aplikasi klien kemudian memperbarui dirinya otomatis.
"""
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

API = 'https://api.github.com'
UPLOADS = 'https://uploads.github.com'
LATEST_URL = 'https://github.com/%s/releases/latest/download/manifest.json'
TOKEN_FILE = Path.home() / '.soundon_github_token'
RELEASE_DIR = Path.home() / 'SoundOnRilis'
INBOX = RELEASE_DIR / 'masuk'
DONE = RELEASE_DIR / 'terbit'
FAILED = RELEASE_DIR / 'gagal'
LOG = RELEASE_DIR / 'log_terbit.txt'


class PublishError(Exception):
    pass


# ---------------------------------------------------------------- token
def load_token():
    env = os.environ.get('SOUNDON_GITHUB_TOKEN', '').strip()
    if env:
        return env
    try:
        return TOKEN_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def save_token(token):
    token = (token or '').strip()
    if not token:
        try:
            TOKEN_FILE.unlink()
        except OSError:
            pass
        return
    if not re.fullmatch(r'(github_pat_|ghp_)[A-Za-z0-9_]{20,255}', token):
        raise PublishError('Format token tidak dikenal. Token GitHub diawali "github_pat_" atau "ghp_".')
    TOKEN_FILE.write_text(token, encoding='utf-8')
    ensure_folders()


def ensure_folders():
    for d in (INBOX, DONE, FAILED):
        d.mkdir(parents=True, exist_ok=True)


def log(text):
    try:
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '  ' + text + '\n')
    except OSError:
        pass


# ---------------------------------------------------------------- GitHub API
def _call(method, url, token, data=None, content_type='application/json'):
    body = data
    if data is not None and not isinstance(data, bytes):
        body = json.dumps(data).encode()
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'SoundOn-Release-Publisher'}
    if body is not None:
        headers['Content-Type'] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        if e.code == 404 and method == 'GET':
            return 404, None
        hint = {401: 'Token salah atau sudah kedaluwarsa.',
                403: 'Token tidak punya izin "Contents: Read and write" untuk repo ini.',
                404: 'Repo tidak ditemukan atau token tidak diberi akses ke repo ini.',
                422: 'Data rilis ditolak GitHub.'}.get(e.code, '')
        if 'empty' in raw.lower():
            hint = 'Repo masih kosong. Buat satu file (mis. README) di repo dulu.'
        raise PublishError('GitHub menolak (%s): %s %s' % (e.code, hint, raw[:200]))
    except urllib.error.URLError as e:
        raise PublishError('Tidak bisa terhubung ke GitHub: %s' % e.reason)


def check_token(token, repo):
    """Pastikan token bisa menulis ke repo. Mengembalikan pesan singkat."""
    status, info = _call('GET', '%s/repos/%s' % (API, repo), token)
    if status == 404 or not info:
        raise PublishError('Repo %s tidak terlihat dengan token ini.' % repo)
    perms = info.get('permissions') or {}
    if perms and not perms.get('push'):
        raise PublishError('Token hanya bisa membaca %s, belum bisa menerbitkan (butuh Contents: Read and write).' % repo)
    return 'Token valid untuk %s.' % repo


# ---------------------------------------------------------------- validasi paket
def validate_package(folder):
    """Periksa manifest + ZIP di folder. Mengembalikan (manifest, zip_path)."""
    import updater  # aturan isi paket sama persis dengan yang dipakai klien
    folder = Path(folder)
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise PublishError('manifest.json tidak terbaca: %s' % exc)
    version = str(manifest.get('version', ''))
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise PublishError('Versi di manifest tidak valid.')
    name = str(manifest.get('zip_name', ''))
    if not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', name):
        raise PublishError('zip_name di manifest tidak valid.')
    manifest.setdefault('tag', 'v' + version)
    zpath = folder / name
    if not zpath.exists():
        raise PublishError('%s belum ada di folder.' % name)
    if hashlib.sha256(zpath.read_bytes()).hexdigest().lower() != str(manifest.get('sha256', '')).lower():
        raise PublishError('SHA-256 %s tidak cocok dengan manifest (file belum lengkap/rusak).' % name)
    try:
        with zipfile.ZipFile(zpath) as z:
            members = updater._zip_members(z)
            for rel, item in members.items():
                if rel.endswith('.py'):
                    compile(z.read(item).decode('utf-8-sig'), rel, 'exec')
            dash = z.read(members['soundon_dashboard.py']).decode('utf-8-sig')
    except PublishError:
        raise
    except Exception as exc:
        raise PublishError('Isi ZIP ditolak: %s' % exc)
    if "APP_VERSION='%s'" % version not in dash:
        raise PublishError('APP_VERSION di ZIP tidak sama dengan versi manifest %s.' % version)
    return manifest, zpath


# ---------------------------------------------------------------- terbitkan
def publish(folder, token, repo, replace=False, say=print):
    manifest, zpath = validate_package(folder)
    version, tag = manifest['version'], manifest['tag']
    status, rel = _call('GET', '%s/repos/%s/releases/tags/%s' % (API, repo, tag), token)
    if status == 200 and rel:
        if not replace:
            raise PublishError('Rilis %s sudah ada di %s.' % (tag, repo))
        for asset in rel.get('assets', []):
            _call('DELETE', '%s/repos/%s/releases/assets/%d' % (API, repo, asset['id']), token)
        _call('PATCH', '%s/repos/%s/releases/%d' % (API, repo, rel['id']), token,
              {'make_latest': 'true', 'draft': False, 'prerelease': False})
    else:
        _, rel = _call('POST', '%s/repos/%s/releases' % (API, repo), token, {
            'tag_name': tag, 'name': 'SoundOn %s' % version,
            'body': manifest.get('notes') or ('Pembaruan SoundOn Account Manager %s' % version),
            'draft': False, 'prerelease': False, 'make_latest': 'true'})
    say('Rilis dibuat: %s' % rel.get('html_url', tag))
    for path, ctype in ((zpath, 'application/zip'), (Path(folder) / 'manifest.json', 'application/json')):
        url = '%s/repos/%s/releases/%d/assets?name=%s' % (UPLOADS, repo, rel['id'], path.name)
        _call('POST', url, token, path.read_bytes(), content_type=ctype)
        say('Terunggah: %s (%d KB)' % (path.name, path.stat().st_size // 1024))
    check = LATEST_URL % repo
    for _ in range(12):
        try:
            req = urllib.request.Request(check + '?t=%d' % time.time(),
                                         headers={'User-Agent': 'SoundOn-Release-Publisher', 'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=30) as r:
                live = json.loads(r.read())
            if live.get('version') == version and live.get('sha256') == manifest['sha256']:
                say('Terverifikasi: versi terbaru di GitHub = %s.' % version)
                return version
        except Exception:
            pass
        time.sleep(5)
    say('Rilis %s terunggah, tetapi "latest" belum menunjukkan versi ini. Periksa halaman Releases.' % version)
    return version


def process_inbox(repo, say=log):
    """Terbitkan paket di ~/SoundOnRilis/masuk bila ada. Dipanggil berkala dari aplikasi admin.
    Mengembalikan versi yang diterbitkan, atau None."""
    token = load_token()
    if not token or not (INBOX / 'manifest.json').exists():
        return None
    try:
        manifest = json.loads((INBOX / 'manifest.json').read_text(encoding='utf-8-sig'))
        zip_name = str(manifest.get('zip_name', ''))
    except (OSError, ValueError):
        return None
    # Tunggu sampai file selesai disalin (ZIP ada dan ukurannya tidak berubah).
    zpath = INBOX / zip_name
    if not zip_name or not zpath.exists():
        return None
    size = zpath.stat().st_size
    time.sleep(3)
    if not zpath.exists() or zpath.stat().st_size != size:
        return None
    version = str(manifest.get('version', '?'))
    say('Menerbitkan %s ke %s…' % (version, repo))
    try:
        publish(INBOX, token, repo, say=say)
        dest, ok = DONE / version, True
    except PublishError as exc:
        say('GAGAL %s: %s' % (version, exc))
        dest, ok = FAILED / ('%s_%s' % (version, datetime.now().strftime('%H%M%S'))), False
    dest.mkdir(parents=True, exist_ok=True)
    for f in list(INBOX.iterdir()):
        if f.is_file():
            target = dest / f.name
            if target.exists():
                target.unlink()
            shutil.move(str(f), str(target))
    if ok:
        say('Selesai: %s diterbitkan. Semua aplikasi akan memperbarui otomatis.' % version)
        return version
    raise PublishError('Penerbitan %s gagal, lihat %s' % (version, LOG))
