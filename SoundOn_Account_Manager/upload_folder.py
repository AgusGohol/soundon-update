"""Folder pantau Studio unggah: lagu yang ditaruh di folder otomatis masuk antrean.

Struktur (dibuat otomatis):
    ~/SoundOnUnggah/
        masuk/<nama akun atau ID akun>/
            data.txt                 opsional: data untuk SEMUA lagu di folder akun ini
            Judul Lagu.wav           satu file audio = satu lagu (judul = nama file)
            Judul Lagu.jpg           cover (opsional bila cover AI SoundOn)
            Judul Lagu.txt           opsional: data khusus lagu ini (format sama dengan data.txt)
            Judul Lagu.lirik.txt     opsional: lirik
        diproses/   file lagu yang sudah masuk antrean (dipakai saat unggah)
        gagal/      lagu yang datanya belum lengkap, dengan file ALASAN.txt
"""
import os
import re
import shutil
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path.home() / 'SoundOnUnggah'
INBOX = ROOT / 'masuk'
PROCESSED = ROOT / 'diproses'
FAILED = ROOT / 'gagal'

AUDIO_EXT = {'.wav', '.flac', '.mp3', '.aiff', '.aif'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png'}
STABLE_SECONDS = 8          # file dianggap selesai disalin bila ukurannya tidak berubah selama ini

# Kunci data.txt (bahasa Indonesia) -> kunci antrean.
KEYS = {
    'judul': 'title', 'artis': 'artist', 'artis_utama': 'artist', 'bahasa': 'language', 'bahasa_judul': 'language',
    'genre': 'genre', 'subgenre': 'subgenre', 'tanggal_rilis': 'release_date', 'tanggal': 'release_date',
    'penulis_lagu': 'songwriter', 'songwriter': 'songwriter', 'penulis_lirik': 'lyricist', 'bahasa_lirik': 'lyrics_language',
    'kontributor': 'contributor', 'peran_kontributor': 'contributor_role', 'produser': 'producer',
    'peran_produser': 'producer_role', 'eksplisit': 'explicit', 'instrumental': 'instrumental',
    'judul_inggris': 'english_title', 'versi': 'version', 'label': 'record_label', 'label_rekaman': 'record_label',
    'cover': 'cover_mode', 'gaya_cover': 'cover_style', 'klip': 'clip_mode', 'iswc': 'iswc',
    'kepemilikan': 'ownership', 'penerbit': 'publisher', 'pro': 'pro', 'cml': 'cml', 'capcut': 'capcut',
    'waktu': 'time_mode', 'pernah_dirilis': 'previously_released',
}
YES = {'ya', 'yes', 'y', 'on', 'aktif', '1', 'true'}
NO = {'tidak', 'no', 'n', 'off', 'mati', '0', 'false'}

SAMPLE = """# Contoh data.txt — taruh di folder akun (berlaku untuk semua lagu di folder itu),
# atau beri nama sama dengan file lagu (Judul Lagu.txt) untuk satu lagu saja.
# Baris yang diawali # diabaikan. Kolom kosong memakai data lagu terakhir akun ini di antrean.
artis: Nama Artis
genre: Pop
bahasa: Indonesian
penulis_lagu: Nama Lengkap Penulis
penulis_lirik: Nama Lengkap Penulis
bahasa_lirik: Indonesian
kontributor: Nama Penyanyi
peran_kontributor: Vocalist
produser: Nama Produser
peran_produser: Producer
eksplisit: Non-Explicit
instrumental: tidak
cover: file            # file = pakai gambar dengan nama sama, ai = cover AI SoundOn
# cml: ya / capcut: ya   (monetisasi; bawaan aktif)
# tanggal_rilis: 2026-12-01   (kosong = hari ini + jumlah hari di Studio)
"""

GUIDE = """FOLDER PANTAU — STUDIO UNGGAH SOUNDON

1. Buat folder di dalam "masuk" dengan nama akun persis seperti di aplikasi (atau ID akunnya).
2. Taruh file lagu di folder akun itu: Judul Lagu.wav (+ Judul Lagu.jpg untuk cover).
   Judul lagu diambil dari nama file.
3. Data lain (artis, genre, penulis, kredit) diambil dari data.txt di folder akun, atau dari
   lagu terakhir akun itu di antrean. Lihat CONTOH_data.txt.
4. Selama aplikasi terbuka dan "Folder pantau" aktif di Studio, lagu langsung masuk antrean
   dan diunggah satu per satu. Bila "Submit otomatis" aktif, rilis langsung dikirim setelah
   Review; bila tidak, bot berhenti di Review.
5. File yang sudah masuk antrean dipindah ke "diproses". Data yang belum lengkap dipindah ke
   "gagal" beserta ALASAN.txt — perbaiki lalu pindahkan kembali ke "masuk".
"""


def ensure_folders():
    for d in (INBOX, PROCESSED, FAILED):
        d.mkdir(parents=True, exist_ok=True)
    try:
        if not (ROOT / 'CARA_PAKAI.txt').exists():
            (ROOT / 'CARA_PAKAI.txt').write_text(GUIDE, encoding='utf-8')
        if not (ROOT / 'CONTOH_data.txt').exists():
            (ROOT / 'CONTOH_data.txt').write_text(SAMPLE, encoding='utf-8')
    except OSError:
        pass


def parse_data(path):
    """Baca file 'kunci: nilai'. Kunci tidak dikenal diabaikan."""
    out = {}
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except (OSError, UnicodeDecodeError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, value = line.split(':', 1)
        value = re.split(r'\s+#', value, 1)[0].strip()
        key = key.strip().lower().replace(' ', '_')
        key = KEYS.get(key, key)
        if value:
            out[key] = value
    return normalize(out)


def normalize(data):
    d = dict(data)
    if 'instrumental' in d:
        v = d['instrumental'].lower()
        d['instrumental'] = 'Yes' if v in YES else 'No' if v in NO else d['instrumental']
    for key in ('cml', 'capcut'):
        if key in d:
            v = d[key].lower()
            d[key] = 'On' if v in YES else 'Off' if v in NO else d[key]
    for key in ('publisher', 'pro'):
        if key in d:
            v = d[key].lower()
            d[key] = 'Yes' if v in YES else 'No' if v in NO else d[key]
    if 'cover_mode' in d:
        d['cover_mode'] = 'AI SoundOn' if d['cover_mode'].lower() in ('ai', 'ai soundon', 'otomatis') else 'File'
    if 'explicit' in d:
        v = d['explicit'].lower().replace(' ', '-')
        d['explicit'] = {'eksplisit': 'Explicit', 'explicit': 'Explicit', 'tidak-eksplisit': 'Non-Explicit',
                         'non-explicit': 'Non-Explicit', 'non-eksplisit': 'Non-Explicit', 'clean': 'Clean'}.get(v, d['explicit'])
    if 'clip_mode' in d and d['clip_mode'].lower() in ('otomatis', 'soundon', 'auto'):
        d['clip_mode'] = 'SoundOn selected segment'
    return d


def find_account(folder_name, accounts):
    name = folder_name.strip().lower()
    for a in accounts:
        if str(a.get('id')) == folder_name.strip() or str(a.get('name', '')).strip().lower() == name:
            return a
    m = re.match(r'^\s*(\d+)\s*[·\-_ ]', folder_name)
    if m:
        return next((a for a in accounts if str(a.get('id')) == m.group(1)), None)
    return None


def _stable(path, seen):
    """True bila ukuran & waktu ubah file tidak berubah selama STABLE_SECONDS."""
    try:
        st = path.stat()
    except OSError:
        return False
    sig = (st.st_size, int(st.st_mtime))
    old = seen.get(str(path))
    now = time.time()
    if not old or old[0] != sig:
        seen[str(path)] = (sig, now)
        return False
    return now - old[1] >= STABLE_SECONDS and st.st_size > 0


def _unique(dest):
    dest = Path(dest)
    if not dest.exists():
        return dest
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return dest.with_name('%s_%s%s' % (dest.stem, stamp, dest.suffix))


def _move(src, folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique(folder / src.name)
    shutil.move(str(src), str(target))
    return target


def _fail(files, account_folder, reason):
    dest = FAILED / account_folder
    moved = []
    for f in files:
        if f and Path(f).exists():
            moved.append(_move(Path(f), dest).name)
    try:
        with open(dest / 'ALASAN.txt', 'a', encoding='utf-8') as fh:
            fh.write('%s  %s: %s\n' % (datetime.now().strftime('%Y-%m-%d %H:%M'), ', '.join(moved), reason))
    except OSError:
        pass


def scan(accounts, template_for, validators, seen, date_offset=7):
    """Periksa folder masuk. Mengembalikan (jobs_baru, pesan_log).

    template_for(account_id) -> dict data lagu terakhir akun itu (tanpa id/status).
    validators: daftar fungsi(job) yang melempar ValueError bila data belum lengkap.
    seen: dict yang dipertahankan pemanggil antar-pemanggilan (cek file selesai disalin).
    """
    ensure_folders()
    jobs, logs = [], []
    for acc_dir in sorted(p for p in INBOX.iterdir() if p.is_dir()):
        audio_files = sorted(p for p in acc_dir.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXT)
        if not audio_files:
            continue
        account = find_account(acc_dir.name, accounts)
        for audio in audio_files:
            stem = audio.stem
            cover = next((acc_dir / (stem + e) for e in ('.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG')
                          if (acc_dir / (stem + e)).exists()), None)
            song_data = acc_dir / (stem + '.txt')
            lyrics = acc_dir / (stem + '.lirik.txt')
            related = [audio, cover, song_data if song_data.exists() else None, lyrics if lyrics.exists() else None]
            if not all([_stable(f, seen) for f in related if f]):   # list: semua file dicatat sekaligus
                continue                                  # masih disalin; cek lagi nanti
            if account is None:
                _fail(related, acc_dir.name, 'Folder "%s" tidak cocok dengan nama/ID akun mana pun.' % acc_dir.name)
                logs.append('Folder pantau: akun "%s" tidak ditemukan; %s dipindah ke gagal.' % (acc_dir.name, audio.name))
                continue
            job = dict(template_for(account['id']) or {})
            job.update(parse_data(acc_dir / 'data.txt'))
            if song_data.exists():
                job.update(parse_data(song_data))
            job.setdefault('cover_mode', 'File')
            job.setdefault('clip_mode', 'SoundOn selected segment')
            job.setdefault('previously_released', 'No, I want to distribute a new release')
            job.setdefault('time_mode', 'Local release')
            job.setdefault('ownership', '100%')
            job.setdefault('publisher', 'No')
            job.setdefault('pro', 'No')
            job.setdefault('cml', 'On')
            job.setdefault('capcut', 'On')
            job.setdefault('cover_style', '3D Animation')
            job.setdefault('cover_prompt', '')
            if not (song_data.exists() and 'title' in parse_data(song_data)):
                job['title'] = stem
            explicit_date = 'release_date' in parse_data(acc_dir / 'data.txt') or (
                song_data.exists() and 'release_date' in parse_data(song_data))
            if not explicit_date:
                job['release_date'] = (date.today() + timedelta(days=int(date_offset))).isoformat()
            # Lirik lagu lain tidak pernah ikut terbawa dari templat.
            job['lyrics'] = lyrics.read_text(encoding='utf-8-sig', errors='replace').strip() if lyrics.exists() else ''
            for k in ('upc', 'isrc'):
                job[k] = ''
            job.update(account_id=account['id'], id=uuid.uuid4().hex, status='Menunggu', report='', source='folder',
                       draft_url='', added=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            job.pop('submit_clicked', None)
            job.pop('submitted_at', None)
            if job['cover_mode'] != 'AI SoundOn' and cover is None:
                _fail(related, acc_dir.name, 'Cover tidak ada. Tambahkan %s.jpg/.png atau tulis "cover: ai" di data.txt.' % stem)
                logs.append('Folder pantau: %s tanpa cover; dipindah ke gagal.' % audio.name)
                continue
            # Pindahkan dulu ke "diproses" agar jalur file di antrean tetap.
            dest = PROCESSED / acc_dir.name
            job['audio'] = str(_move(audio, dest))
            job['cover'] = str(_move(cover, dest)) if cover is not None else ''
            extras = [str(_move(extra, dest)) for extra in (song_data, lyrics) if extra.exists()]
            try:
                for check in validators:
                    check(job)
            except (ValueError, OSError) as exc:
                _fail([job['audio'], job['cover'] or None] + extras, acc_dir.name, str(exc) + ' — isi di data.txt akun ini.')
                logs.append('Folder pantau: %s belum lengkap (%s); dipindah ke gagal.' % (audio.name, exc))
                continue
            jobs.append(job)
            logs.append('Folder pantau: "%s" → antrean %s.' % (job['title'], account.get('name', account['id'])))
    return jobs, logs
