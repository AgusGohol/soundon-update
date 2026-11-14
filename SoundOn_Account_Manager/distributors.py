"""Daftar distributor musik untuk Dashboard Distributor.

SoundOn memakai otomatisasi penuh (sinkron, Asal Streams, Riwayat Transaksi, Studio unggah).
Distributor lain: akun & profil Chrome terpisah, data diisi manual (dialog Data), sampai
pembacaan otomatisnya dipetakan dari tangkapan layar situs masing-masing.
Tidak ada distributor di daftar ini yang menyediakan API publik untuk artis (dicek 2026-11).
Pilihan pengguna (distributor aktif, tambahan, alamat) disimpan di ui_settings.json.
"""
import ui_theme as UI

DEFAULT = 'SoundOn'
SOUNDON_LOGIN = 'https://www.soundon.global/library/login-after?lang=id&region=ID'

# (nama, alamat awal). Alamat kosong = ditanyakan saat akun pertama kali dibuka.
BUILTIN = [
    ('SoundOn', SOUNDON_LOGIN),
    ('DistroKid', 'https://distrokid.com/'),
    ('TuneCore', 'https://www.tunecore.com/'),
    ('CD Baby', 'https://cdbaby.com/'),
    ('Amuse', 'https://www.amuse.io/'),
    ('UnitedMasters', 'https://unitedmasters.com/'),
    ('Ditto Music', 'https://dittomusic.com/'),
    ('LANDR', 'https://www.landr.com/'),
    ('Symphonic', ''),
    ('ONErpm', 'https://onerpm.com/'),
    ('Stem', ''),
    ('Level', ''),
    ('RouteNote', 'https://routenote.com/'),
    ('Soundrop', 'https://soundrop.com/'),
    ('Believe', 'https://www.believe.com/'),
    ('The Orchard', 'https://www.theorchard.com/'),
    ('Virgin Music Group', ''),
    ('Musicblast', ''),
]


def is_auto(name):
    """Distributor dengan sinkron & unggah otomatis."""
    return name == DEFAULT


def names():
    extra = [n for n in UI.load_settings().get('distributors_extra', []) if isinstance(n, str) and n.strip()]
    base = [n for n, _ in BUILTIN]
    return base + [n for n in extra if n not in base]


def url_for(name):
    custom = UI.load_settings().get('distributor_urls', {})
    if isinstance(custom, dict) and custom.get(name):
        return custom[name]
    return dict(BUILTIN).get(name, '')


def set_url(name, url):
    custom = dict(UI.load_settings().get('distributor_urls', {}) or {})
    custom[name] = (url or '').strip()
    UI.save_settings(distributor_urls=custom)


def add(name, url=''):
    name = ' '.join(str(name).split())
    if not name:
        raise ValueError('Nama distributor wajib diisi.')
    if name.casefold() in {n.casefold() for n in names()}:
        raise ValueError('Distributor itu sudah ada.')
    extra = list(UI.load_settings().get('distributors_extra', []) or []) + [name]
    UI.save_settings(distributors_extra=extra)
    if url:
        set_url(name, url)
    return name


def active():
    name = UI.load_settings().get('active_distributor') or DEFAULT
    return name if name in names() else DEFAULT


def set_active(name):
    UI.save_settings(active_distributor=name)


def of(account):
    return account.get('distributor') or DEFAULT
