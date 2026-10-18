"""Pembaruan otomatis SoundOn Account Manager melalui GitHub Releases.

Alur:
  1. Saat aplikasi dibuka, manifest.json rilis terbaru dibaca dari
     https://github.com/<repo>/releases/latest/download/manifest.json
  2. Jika versinya lebih baru, ZIP diunduh, SHA-256 dicocokkan, isi ZIP diperiksa.
  3. Aplikasi ditutup, installer terpisah mencadangkan file lama ke
     ~/SoundOnAccounts/update_backups, mengganti file aplikasi, lalu membuka
     aplikasi kembali.

Yang TIDAK pernah disentuh: soundon.license, update_config.json, dan seluruh
folder data pengguna ~/SoundOnAccounts (akun, antrean, profil Chrome).
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime

# Isi dengan "username/nama-repo" GitHub agar setiap salinan aplikasi langsung
# tahu ke mana mencari pembaruan. update_config.json dapat menimpanya.
DEFAULT_GITHUB_REPO = 'AgusGohol/soundon-update'

MAX_MANIFEST = 100_000
MAX_ARCHIVE = 30_000_000
MAX_FILES = 300
STARTUP_TIMEOUT = 6
MAX_AUTO_ATTEMPTS = 2

# File milik pengguna/perangkat: tidak pernah ditimpa oleh pembaruan.
PROTECTED = {'soundon.license', 'update_config.json'}
ALLOWED_EXT = {'.py', '.bat', '.txt', '.csv', '.json', '.md'}
ALLOWED_SUBDIRS = {'docs', 'tools'}
SKIP_PARTS = {'__pycache__', '.git', 'dist'}

REPO_RE = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}')
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
DETACHED = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
NEW_CONSOLE = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)

# Kode keluar khusus: run_app.bat menutup jendela konsol lama tanpa "pause".
EXIT_FOR_UPDATE = 75


# ---------------------------------------------------------------- konfigurasi
def config_path(app_dir):
    return os.path.join(app_dir, 'update_config.json')


def load_config(app_dir):
    cfg = {'github_repo': DEFAULT_GITHUB_REPO, 'auto_update': True, 'manifest_url': ''}
    try:
        with open(config_path(app_dir), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in cfg:
                if key in data and data[key] not in (None, ''):
                    cfg[key] = data[key]
    except (OSError, ValueError):
        pass
    try:
        cfg['github_repo'] = normalize_repo(cfg.get('github_repo', ''))
    except ValueError:
        cfg['github_repo'] = ''
    cfg['auto_update'] = bool(cfg.get('auto_update', True))
    return cfg


def save_config(app_dir, cfg):
    data = {'github_repo': normalize_repo(cfg.get('github_repo', '')),
            'auto_update': bool(cfg.get('auto_update', True)),
            'manifest_url': (cfg.get('manifest_url') or '').strip()}
    with open(config_path(app_dir), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def normalize_repo(text):
    """Terima 'user/repo' atau URL github.com/user/repo; kembalikan 'user/repo' atau ''."""
    text = (text or '').strip().strip('/')
    if not text:
        return ''
    if '://' in text or text.lower().startswith('github.com/'):
        if '://' not in text:
            text = 'https://' + text
        p = urllib.parse.urlsplit(text)
        if p.netloc.lower() not in ('github.com', 'www.github.com'):
            raise ValueError('Gunakan alamat repo github.com.')
        parts = [x for x in p.path.split('/') if x][:2]
        text = '/'.join(parts)
    if text.endswith('.git'):
        text = text[:-4]
    if not REPO_RE.fullmatch(text):
        raise ValueError('Format repo GitHub harus username/nama-repo.')
    return text


def manifest_url_for(cfg):
    if cfg.get('github_repo'):
        return 'https://github.com/%s/releases/latest/download/manifest.json' % cfg['github_repo']
    return (cfg.get('manifest_url') or '').strip()


# ---------------------------------------------------------------- unduhan
def https_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or not p.netloc or p.username or p.password:
        raise ValueError('Sumber pembaruan harus menggunakan HTTPS tanpa kredensial pada URL.')
    return url


def download(url, limit, timeout=25):
    https_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'SoundOnAccountManagerUpdater/2.0',
                                               'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if urllib.parse.urlsplit(resp.geturl()).scheme != 'https':
            raise ValueError('Pengalihan ke HTTP tidak diizinkan.')
        result = resp.read(limit + 1)
    if len(result) > limit:
        raise ValueError('Ukuran pembaruan melebihi batas.')
    return result


def read_manifest(url, repo='', timeout=25):
    data = json.loads(download(url, MAX_MANIFEST, timeout).decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Format manifest tidak valid.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(data.get('version', ''))):
        raise ValueError('Versi harus menggunakan format 1.2.3.')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', str(data.get('sha256', ''))):
        raise ValueError('SHA-256 manifest tidak valid.')
    if not data.get('zip_url'):
        name = str(data.get('zip_name', ''))
        tag = str(data.get('tag') or 'v' + data['version'])
        if not repo or not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', name) or not re.fullmatch(r'[A-Za-z0-9._-]+', tag):
            raise ValueError('Manifest tidak memiliki zip_url/zip_name yang valid.')
        data['zip_url'] = 'https://github.com/%s/releases/download/%s/%s' % (repo, tag, name)
    https_url(data['zip_url'])
    if repo:
        prefix = ('https://github.com/%s/releases/download/' % repo).lower()
        if not data['zip_url'].lower().startswith(prefix):
            raise ValueError('ZIP pembaruan harus berasal dari rilis repo ' + repo + '.')
    return data


def version_newer(remote, local):
    return tuple(map(int, remote.split('.'))) > tuple(map(int, local.split('.')))


# ---------------------------------------------------------------- isi paket
def allowed_relpath(rel):
    """Jalur relatif (pakai /) yang boleh dipasang ke folder aplikasi."""
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts or any(x in ('', '.', '..') for x in p.parts):
        return False
    if ':' in rel or any(x in SKIP_PARTS for x in p.parts):
        return False
    if p.suffix.lower() not in ALLOWED_EXT:
        return False
    if len(p.parts) > 1 and (p.parts[0] not in ALLOWED_SUBDIRS or len(p.parts) > 4):
        return False
    return True


def _zip_members(z):
    names = []
    for item in z.infolist():
        if item.is_dir():
            continue
        name = item.filename.replace('\\', '/')
        names.append((name, item))
    # Buang satu folder induk bersama, mis. SoundOn_Account_Manager/...
    tops = {n.split('/', 1)[0] for n, _ in names}
    strip = len(tops) == 1 and all('/' in n for n, _ in names)
    out = {}
    for name, item in names:
        rel = name.split('/', 1)[1] if strip else name
        if PurePosixPath(rel).name in PROTECTED and len(PurePosixPath(rel).parts) == 1:
            continue  # tidak pernah menimpa izin/konfigurasi pengguna
        if not allowed_relpath(rel):
            raise ValueError('ZIP mengandung file yang tidak diizinkan: ' + item.filename)
        if rel.lower() in {k.lower() for k in out}:
            raise ValueError('File ganda di ZIP: ' + rel)
        if item.file_size > MAX_ARCHIVE:
            raise ValueError('File di ZIP terlalu besar: ' + rel)
        out[rel] = item
    if len(out) > MAX_FILES:
        raise ValueError('ZIP berisi terlalu banyak file.')
    if 'soundon_dashboard.py' not in out:
        raise ValueError('ZIP tidak berisi soundon_dashboard.py')
    return out


def prepare_update(manifest):
    """Unduh + verifikasi + ekstrak ke folder sementara. Kembalikan (staging, extract)."""
    blob = download(manifest['zip_url'], MAX_ARCHIVE, timeout=60)
    digest = hashlib.sha256(blob).hexdigest()
    if digest.lower() != manifest['sha256'].lower():
        raise ValueError('SHA-256 ZIP tidak cocok. Pembaruan dibatalkan.')
    staging = Path(tempfile.mkdtemp(prefix='soundon_update_'))
    archive = staging / 'update.zip'
    archive.write_bytes(blob)
    extract = staging / 'new'
    extract.mkdir()
    with zipfile.ZipFile(archive) as z:
        members = _zip_members(z)
        for rel, item in members.items():
            dst = extract.joinpath(*PurePosixPath(rel).parts)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(z.read(item))
    # Pastikan kode Python baru setidaknya bisa dikompilasi sebelum memasang.
    for py in extract.rglob('*.py'):
        compile(py.read_text(encoding='utf-8-sig'), str(py), 'exec')
    return staging, extract


def launch_installer(staging, extract, app_dir, python_executable, data_dir, version=''):
    """Jalankan installer dari salinan sementara agar updater.py ikut bisa diganti."""
    helper = Path(staging) / 'installer.py'
    shutil.copy2(Path(__file__), helper)
    pyw = Path(python_executable).with_name('pythonw.exe')
    exe = str(pyw) if os.name == 'nt' and pyw.exists() else python_executable
    subprocess.Popen([exe, str(helper), '--install', str(extract), str(Path(app_dir).resolve()),
                      str(staging), str(data_dir), str(os.getpid()), version],
                     cwd=str(staging), creationflags=DETACHED | CREATE_NO_WINDOW,
                     close_fds=True)


def begin_update(manifest, app_dir, python_executable, data_dir=None):
    data_dir = data_dir or os.path.join(os.path.expanduser('~'), 'SoundOnAccounts')
    staging, extract = prepare_update(manifest)
    launch_installer(staging, extract, app_dir, python_executable, data_dir, manifest.get('version', ''))


# ---------------------------------------------------------------- installer
def _log(data_dir, text):
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, 'update_log.txt'), 'a', encoding='utf-8') as f:
            f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '  ' + text + '\n')
    except OSError:
        pass


def _wait_for_exit(pid, timeout=40):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        time.sleep(2)
        return
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if h:
                k.WaitForSingleObject(h, int(timeout * 1000))
                k.CloseHandle(h)
        except Exception:
            time.sleep(2)
        time.sleep(0.8)
        return
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.3)


def _relaunch(app):
    bat = app / 'run_app.bat'
    if os.name == 'nt' and bat.exists():
        subprocess.Popen(['cmd', '/c', str(bat)], cwd=str(app), creationflags=NEW_CONSOLE, close_fds=True)
    else:
        subprocess.Popen([sys.executable, str(app / 'soundon_dashboard.py')], cwd=str(app))


def _prune_backups(root, keep=5):
    try:
        olds = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)
        for p in olds[:-keep]:
            shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def install(extract, app_dir, staging, data_dir, parent_pid, version=''):
    app = Path(app_dir)
    source = Path(extract)
    _wait_for_exit(parent_pid)
    files = []
    for p in sorted(source.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(source).as_posix()
        if not allowed_relpath(rel) or (PurePosixPath(rel).name in PROTECTED and '/' not in rel):
            continue
        dst = app.joinpath(*PurePosixPath(rel).parts)
        if dst.exists() and dst.read_bytes() == p.read_bytes():
            continue  # sama persis: jangan sentuh (aman untuk run_app.bat yang sedang berjalan)
        files.append((p, dst, rel))
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_root = Path(data_dir) / 'update_backups'
    backup = backup_root / ('%s_sebelum_%s' % (stamp, version or 'update'))
    created = []
    for attempt in range(40):
        try:
            for p, dst, rel in files:
                b = backup.joinpath(*PurePosixPath(rel).parts)
                if dst.exists() and not b.exists():
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, b)
            for p, dst, rel in files:
                existed = dst.exists()
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
                if not existed:
                    created.append(dst)
            break
        except (PermissionError, OSError) as exc:
            if attempt == 39:
                # Kembalikan semua file lama.
                if backup.exists():
                    for b in backup.rglob('*'):
                        if b.is_file():
                            shutil.copy2(b, app / b.relative_to(backup))
                for c in created:
                    try:
                        c.unlink()
                    except OSError:
                        pass
                _log(data_dir, 'GAGAL memasang %s, file lama dikembalikan: %s' % (version, exc))
                _relaunch(app)
                return False
            time.sleep(0.5)
    _prune_backups(backup_root)
    _log(data_dir, 'Berhasil memasang versi %s (%d file diganti). Cadangan: %s' % (version, len(files), backup))
    shutil.rmtree(Path(staging) / 'new', ignore_errors=True)
    _relaunch(app)
    return True


# ---------------------------------------------------------------- otomatis saat dibuka
def _state_path(data_dir):
    return os.path.join(data_dir, 'update_state.json')


def _load_state(data_dir):
    try:
        with open(_state_path(data_dir), encoding='utf-8') as f:
            s = json.load(f)
            return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(data_dir, state):
    try:
        with open(_state_path(data_dir), 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass


def auto_update_on_start(app_dir, current_version, data_dir):
    """Dipanggil sebelum jendela utama dibuat. True = installer sudah berjalan,
    aplikasi harus keluar dengan EXIT_FOR_UPDATE. Semua kegagalan diabaikan agar
    aplikasi tetap bisa dibuka (offline, GitHub belum siap, dll)."""
    try:
        cfg = load_config(app_dir)
    except Exception:
        return False
    url = manifest_url_for(cfg)
    if not cfg.get('auto_update') or not url:
        return False
    try:
        manifest = read_manifest(url, cfg.get('github_repo', ''), timeout=STARTUP_TIMEOUT)
    except Exception as exc:
        _log(data_dir, 'Cek pembaruan dilewati: %s' % exc)
        return False
    remote = manifest['version']
    if not version_newer(remote, current_version):
        return False
    if not register_attempt(data_dir, remote, current_version):
        return False
    return _run_with_splash(manifest, app_dir, current_version, data_dir)


def register_attempt(data_dir, remote, current_version):
    """Catat satu percobaan pasang otomatis. False bila versi ini sudah gagal MAX_AUTO_ATTEMPTS kali
    (mencegah aplikasi terus-menerus mencoba memasang pembaruan yang rusak)."""
    state = _load_state(data_dir)
    if state.get('version') == remote and int(state.get('attempts', 0)) >= MAX_AUTO_ATTEMPTS:
        _log(data_dir, 'Pembaruan otomatis %s dilewati setelah %d percobaan. Pasang manual dari Pengaturan.'
             % (remote, MAX_AUTO_ATTEMPTS))
        return False
    state = {'version': remote, 'attempts': (int(state.get('attempts', 0)) + 1) if state.get('version') == remote else 1,
             'from': current_version, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    _save_state(data_dir, state)
    return True


def attempts_exhausted(data_dir, remote):
    state = _load_state(data_dir)
    return state.get('version') == remote and int(state.get('attempts', 0)) >= MAX_AUTO_ATTEMPTS


def check_while_running(app_dir, current_version, data_dir, timeout=20):
    """Untuk pemeriksaan berkala saat aplikasi terbuka (dipanggil dari thread latar).
    Mengembalikan (manifest, (staging, extract)) bila ada versi baru yang sudah diunduh
    dan terverifikasi; None bila tidak ada / dimatikan / offline."""
    try:
        cfg = load_config(app_dir)
    except Exception:
        return None
    url = manifest_url_for(cfg)
    if not cfg.get('auto_update') or not url:
        return None
    try:
        manifest = read_manifest(url, cfg.get('github_repo', ''), timeout=timeout)
    except Exception as exc:
        _log(data_dir, 'Cek pembaruan berkala dilewati: %s' % exc)
        return None
    if not version_newer(manifest['version'], current_version) or attempts_exhausted(data_dir, manifest['version']):
        return None
    try:
        return manifest, prepare_update(manifest)
    except Exception as exc:
        _log(data_dir, 'Unduhan pembaruan %s gagal: %s' % (manifest['version'], exc))
        return None


def _run_with_splash(manifest, app_dir, current_version, data_dir):
    import threading
    import tkinter as tk
    result = {'done': False, 'error': None, 'prepared': None}

    def work():
        try:
            result['prepared'] = prepare_update(manifest)
        except Exception as exc:
            result['error'] = exc
        result['done'] = True

    win = tk.Tk()
    win.title('Pembaruan SoundOn')
    win.configure(bg='#09111f')
    win.resizable(False, False)
    w, h = 460, 170
    win.geometry('%dx%d+%d+%d' % (w, h, (win.winfo_screenwidth() - w) // 2, (win.winfo_screenheight() - h) // 2))
    tk.Label(win, text='Memperbarui SoundOn Account Manager', bg='#09111f', fg='#f5f8ff',
             font=('Segoe UI', 13, 'bold')).pack(anchor='w', padx=22, pady=(22, 4))
    tk.Label(win, text='Versi %s  →  %s' % (current_version, manifest['version']), bg='#09111f', fg='#24d6a0',
             font=('Segoe UI', 10)).pack(anchor='w', padx=22)
    status = tk.StringVar(value='Mengunduh pembaruan...')
    tk.Label(win, textvariable=status, bg='#09111f', fg='#9fb0c8', font=('Segoe UI', 9),
             wraplength=410, justify='left').pack(anchor='w', padx=22, pady=(14, 0))
    notes = str(manifest.get('notes', ''))[:160]
    if notes:
        tk.Label(win, text=notes, bg='#09111f', fg='#9fb0c8', font=('Segoe UI', 9),
                 wraplength=410, justify='left').pack(anchor='w', padx=22, pady=(4, 0))
    outcome = {'launched': False}

    def poll():
        if not result['done']:
            win.after(200, poll)
            return
        if result['error'] is not None:
            _log(data_dir, 'Pembaruan otomatis %s gagal: %s' % (manifest['version'], result['error']))
            status.set('Pembaruan gagal, aplikasi dibuka dengan versi saat ini.')
            win.after(1800, win.destroy)
            return
        try:
            staging, extract = result['prepared']
            launch_installer(staging, extract, app_dir, sys.executable, data_dir, manifest['version'])
            outcome['launched'] = True
            status.set('Memasang dan membuka ulang aplikasi...')
            win.after(900, win.destroy)
        except Exception as exc:
            _log(data_dir, 'Gagal menjalankan installer: %s' % exc)
            win.after(0, win.destroy)

    win.protocol('WM_DELETE_WINDOW', lambda: None)  # jangan ditutup di tengah unduhan
    threading.Thread(target=work, daemon=True).start()
    win.after(200, poll)
    win.mainloop()
    return outcome['launched']


if __name__ == '__main__' and len(sys.argv) >= 7 and sys.argv[1] == '--install':
    args = sys.argv[2:]
    try:
        install(args[0], args[1], args[2], args[3], args[4], args[5] if len(args) > 5 else '')
    except Exception as exc:
        _log(args[3], 'Installer error: %s' % exc)
        try:
            (Path(args[2]) / 'UPDATE_ERROR.txt').write_text(str(exc), encoding='utf-8')
        except OSError:
            pass
        try:
            _relaunch(Path(args[1]))
        except Exception:
            pass
