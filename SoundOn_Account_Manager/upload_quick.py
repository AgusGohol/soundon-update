"""Unggah cepat: tombol Unggah di baris akun -> pilih file lagu -> langsung masuk antrean dan diunggah.

Data lagu yang sama untuk semua akun disimpan sekali di "Pengaturan unggah" (ui_settings.json,
kunci upload_defaults). Per lagu hanya judul (dari nama file) dan artis (dari daftar artis akun).
"""
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import ui_theme as UI
from ui_theme import PANEL, CARD, WHITE, DIM, MUTED, PURPLE, FONT

AUDIO_TYPES = [('File lagu', '*.wav *.flac *.mp3 *.aiff *.aif'), ('Semua file', '*.*')]

DEFAULTS = {
    'genre': 'Pop',
    'language': 'English',            # bahasa judul
    'instrumental': False,
    'lyrics_language': 'English',
    'explicit': 'Non-Explicit',
    'credits_artist': True,           # penulis lagu, penulis lirik, penyanyi, produser = nama artis
    'songwriter': '', 'contributor': '', 'producer': '',
    'contributor_role': 'Vocalist', 'producer_role': 'Producer',
    'days': 7,                        # tanggal rilis = hari ini + N hari
    'monetize': True,                 # Commercial Music Licensing & CapCut aktif
    'cover_style': '3D Animation',
}
LANGS = ('English', 'Indonesian')
GENRES = ('Pop', 'Dance', 'Electronic', 'Hip-Hop/Rap', 'R&B', 'Rock', 'Alternative', 'Jazz', 'Classical',
          'Country', 'Latin', 'K-Pop', 'Folk', 'Soundtrack', 'Ambient', 'Instrumental')


def load_defaults():
    data = dict(DEFAULTS)
    data.update(UI.load_settings().get('upload_defaults') or {})
    return data


def defaults_confirmed():
    return bool(UI.load_settings().get('upload_defaults_confirmed'))


def clean_title(path):
    stem = Path(path).stem
    stem = re.sub(r'^\s*\d{1,3}\s*[-._)]\s*', '', stem)      # "01 - Judul" -> "Judul"
    stem = stem.replace('_', ' ').strip()
    return re.sub(r'\s+', ' ', stem) or Path(path).stem


def build_job(account, artist, audio, d):
    name = artist.strip()
    credit = (lambda key: name) if d.get('credits_artist', True) else (lambda key: (d.get(key) or '').strip())
    lyrics_file = Path(audio).with_suffix('.txt')
    job = {
        'account_id': account['id'], 'title': clean_title(audio), 'artist': name, 'audio': str(audio),
        'cover': '', 'cover_mode': 'AI SoundOn', 'cover_style': d.get('cover_style', '3D Animation'), 'cover_prompt': '',
        'language': d['language'], 'genre': d['genre'], 'songwriter': credit('songwriter'),
        'instrumental': 'Yes' if d.get('instrumental') else 'No',
        'previously_released': 'No, I want to distribute a new release', 'time_mode': 'Local release',
        'ownership': '100%', 'publisher': 'No', 'pro': 'No', 'cml': 'On' if d.get('monetize', True) else 'Off',
        'capcut': 'On' if d.get('monetize', True) else 'Off',
        'release_date': (date.today() + timedelta(days=int(d.get('days', 7) or 7))).isoformat(),
        'contributor': credit('contributor'), 'contributor_role': d.get('contributor_role') or 'Vocalist',
        'producer': credit('producer'), 'producer_role': d.get('producer_role') or 'Producer',
        'clip_mode': 'SoundOn selected segment',
        'lyrics_language': '' if d.get('instrumental') else d['lyrics_language'],
        'explicit': '' if d.get('instrumental') else d['explicit'],
        'lyricist': '' if d.get('instrumental') else credit('songwriter'),
        'lyrics': '',
        'english_title': '', 'version': '', 'subgenre': '', 'record_label': '', 'iswc': '', 'upc': '', 'isrc': '',
        'id': uuid.uuid4().hex, 'status': 'Menunggu', 'report': '', 'source': 'cepat', 'draft_url': '',
        'added': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    if not d.get('instrumental') and lyrics_file.exists():
        try:
            job['lyrics'] = lyrics_file.read_text(encoding='utf-8-sig', errors='replace').strip()
        except OSError:
            pass
    return job


def _center(win, parent):
    win.update_idletasks()
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + max(40, (parent.winfo_height() - win.winfo_reqheight()) // 3)
        win.geometry('+%d+%d' % (max(0, x), max(0, y)))
    except tk.TclError:
        pass


def edit_defaults(parent, on_saved=None, first_time=False):
    """Satu jendela kecil berisi data yang sama untuk semua akun."""
    d = load_defaults()
    cfg = UI.load_settings()
    win = tk.Toplevel(parent)
    win.title('Pengaturan unggah')
    win.configure(bg=PANEL)
    win.resizable(False, False)
    win.transient(parent)
    body = tk.Frame(win, bg=PANEL, padx=24, pady=20)
    body.pack(fill='both')
    tk.Label(body, text='Pengaturan unggah', bg=PANEL, fg=WHITE, font=(FONT, 14, 'bold')).pack(anchor='w')
    tk.Label(body, text=('Diisi sekali, dipakai untuk semua akun. ' if first_time else '') +
             'Judul = nama file, artis = artis akun, cover = AI SoundOn.',
             bg=PANEL, fg=DIM, font=(FONT, 9)).pack(anchor='w', pady=(2, 12))
    grid = tk.Frame(body, bg=PANEL)
    grid.pack(fill='x')
    v = {
        'genre': tk.StringVar(value=d['genre']), 'language': tk.StringVar(value=d['language']),
        'kind': tk.StringVar(value='Instrumental' if d['instrumental'] else 'Ada vokal'),
        'lyrics_language': tk.StringVar(value=d['lyrics_language']),
        'explicit': tk.StringVar(value=d['explicit']), 'days': tk.StringVar(value=str(d['days'])),
        'credits_artist': tk.BooleanVar(value=d['credits_artist']),
        'songwriter': tk.StringVar(value=d['songwriter']), 'contributor': tk.StringVar(value=d['contributor']),
        'producer': tk.StringVar(value=d['producer']),
        'autosubmit': tk.BooleanVar(value=bool(cfg.get('upload_autosubmit', False))),
        'monetize': tk.BooleanVar(value=bool(d.get('monetize', True))),
    }
    rows = [('Genre', 'genre', GENRES, False), ('Bahasa judul', 'language', LANGS, True),
            ('Jenis lagu', 'kind', ('Ada vokal', 'Instrumental'), True),
            ('Bahasa lirik', 'lyrics_language', LANGS, True),
            ('Eksplisit', 'explicit', ('Non-Explicit', 'Explicit', 'Clean'), True),
            ('Rilis (hari dari sekarang)', 'days', ('1', '3', '7', '14', '30'), False)]
    for r, (caption, key, values, ro) in enumerate(rows):
        tk.Label(grid, text=caption, bg=PANEL, fg=DIM, font=(FONT, 10)).grid(row=r, column=0, sticky='w', pady=4, padx=(0, 14))
        ttk.Combobox(grid, textvariable=v[key], values=values, width=28, state='readonly' if ro else 'normal',
                     style='Dark.TCombobox').grid(row=r, column=1, sticky='w', pady=4)
    names = tk.Frame(body, bg=PANEL)

    def toggle_names():
        if v['credits_artist'].get():
            names.pack_forget()
        else:
            names.pack(fill='x', pady=(4, 0), after=credit_box)
    credit_box = UI.dark_checkbutton(body, '  Penulis lagu, penulis lirik, penyanyi & produser = nama artis akun',
                                     v['credits_artist'], PANEL, command=toggle_names)
    credit_box.pack(anchor='w', pady=(12, 0))
    for r, (caption, key) in enumerate([('Penulis lagu & lirik', 'songwriter'), ('Penyanyi', 'contributor'), ('Produser', 'producer')]):
        tk.Label(names, text=caption, bg=PANEL, fg=DIM, font=(FONT, 10)).grid(row=r, column=0, sticky='w', pady=3, padx=(0, 14))
        UI.styled_entry(names, v[key], width=32).grid(row=r, column=1, sticky='w', pady=3, ipady=3)
    toggle_names()
    UI.dark_checkbutton(body, '  Monetisasi aktif: Commercial Music Licensing & CapCut', v['monetize'], PANEL).pack(anchor='w', pady=(8, 0))
    UI.dark_checkbutton(body, '  Submit otomatis setelah Review (rilis langsung dikirim)', v['autosubmit'], PANEL).pack(anchor='w', pady=(4, 0))
    tk.Label(body, text='Nama artis/penulis harus sudah tersedia di akun SoundOn tersebut.', bg=PANEL, fg=MUTED,
             font=(FONT, 9)).pack(anchor='w', pady=(10, 0))
    result = {'saved': False}

    def save():
        try:
            days = int(v['days'].get())
            if not 0 <= days <= 365:
                raise ValueError
        except ValueError:
            messagebox.showerror('Periksa data', 'Hari rilis harus angka 0–365.', parent=win)
            return
        if not v['genre'].get().strip():
            messagebox.showerror('Periksa data', 'Genre wajib diisi.', parent=win)
            return
        if not v['credits_artist'].get() and not all(v[k].get().strip() for k in ('songwriter', 'contributor', 'producer')):
            messagebox.showerror('Periksa data', 'Isi nama penulis lagu, penyanyi, dan produser.', parent=win)
            return
        was_auto = bool(UI.load_settings().get('upload_autosubmit', False))
        if v['autosubmit'].get() and not was_auto and not messagebox.askyesno(
                'Aktifkan Submit otomatis?', 'Setelah Review, rilis langsung dikirim ke SoundOn tanpa Anda periksa. Aktifkan?', parent=win):
            v['autosubmit'].set(False)
        data = dict(d, genre=v['genre'].get().strip(), language=v['language'].get(), instrumental=v['kind'].get() == 'Instrumental',
                    lyrics_language=v['lyrics_language'].get(), explicit=v['explicit'].get(), days=days,
                    credits_artist=v['credits_artist'].get(), songwriter=v['songwriter'].get().strip(),
                    contributor=v['contributor'].get().strip(), producer=v['producer'].get().strip(),
                    monetize=v['monetize'].get())
        try:
            UI.save_settings(upload_defaults=data, upload_defaults_confirmed=True, upload_autosubmit=v['autosubmit'].get())
        except OSError as exc:
            messagebox.showerror('Gagal menyimpan', str(exc), parent=win)
            return
        result['saved'] = True
        win.destroy()
        if on_saved:
            on_saved()
    foot = tk.Frame(body, bg=PANEL)
    foot.pack(fill='x', pady=(16, 0))
    UI.RoundButton(foot, 'Simpan' + (' & lanjut' if first_time else ''), save, icon='check', variant='primary').pack(side='right')
    UI.RoundButton(foot, 'Batal', win.destroy, variant='ghost').pack(side='right', padx=8)
    _center(win, parent)
    win.grab_set()
    return result


def choose_artist(parent, account):
    """Nama artis untuk akun ini: satu artis -> langsung; beberapa -> pilih; kosong -> ketik (diingat)."""
    names = [x.get('name', '').strip() for x in account.get('artists', []) if x.get('name', '').strip()]
    names = list(dict.fromkeys(names))
    if len(names) == 1:
        return names[0]
    if not names:
        value = simpledialog.askstring('Nama artis', 'Akun %s belum punya artis tercatat.\nNama artis untuk lagu ini:' % account.get('name', ''),
                                       initialvalue=account.get('upload_artist', ''), parent=parent)
        return value.strip() if value and value.strip() else None
    win = tk.Toplevel(parent)
    win.title('Pilih artis')
    win.configure(bg=PANEL)
    win.resizable(False, False)
    win.transient(parent)
    body = tk.Frame(win, bg=PANEL, padx=22, pady=18)
    body.pack(fill='both')
    tk.Label(body, text='Artis untuk lagu ini', bg=PANEL, fg=WHITE, font=(FONT, 12, 'bold')).pack(anchor='w', pady=(0, 8))
    last = account.get('upload_artist')
    var = tk.StringVar(value=last if last in names else names[0])
    for n in names:
        tk.Radiobutton(body, text=n, variable=var, value=n, bg=PANEL, fg=WHITE, selectcolor=CARD, activebackground=PANEL,
                       activeforeground=WHITE, font=(FONT, 10), anchor='w', highlightthickness=0, bd=0).pack(fill='x', ipadx=40, pady=1)
    out = {'name': None}

    def ok():
        out['name'] = var.get()
        win.destroy()
    foot = tk.Frame(body, bg=PANEL)
    foot.pack(fill='x', pady=(12, 0))
    UI.RoundButton(foot, 'Pilih', ok, icon='check', variant='primary').pack(side='right')
    UI.RoundButton(foot, 'Batal', win.destroy, variant='ghost').pack(side='right', padx=8)
    _center(win, parent)
    win.grab_set()
    parent.wait_window(win)
    return out['name']


def pick_files(parent, account):
    return list(filedialog.askopenfilenames(parent=parent, title='Pilih lagu untuk ' + account.get('name', ''),
                                            filetypes=AUDIO_TYPES))
