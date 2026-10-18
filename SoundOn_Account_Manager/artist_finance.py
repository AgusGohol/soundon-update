"""Manual monthly artist earnings, stored as integer rupiah in each account."""
import re
from datetime import date


def validate_month(month):
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Pilih bulan dan tahun yang valid.')
    date.fromisoformat(month + '-01')
    return month


def parse_rupiah(raw):
    raw = str(raw).strip()
    raw = re.sub(r'^Rp\s*', '', raw, flags=re.I)
    if re.fullmatch(r'\d+', raw):
        return int(raw)
    if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', raw):
        return int(raw.replace('.', ''))
    raise ValueError('Isi rupiah bulat, misalnya 5000000 atau 5.000.000. Tanpa minus/desimal.')


def save_artist(account, artist_id, name, owner, month, amount):
    name, owner = name.strip(), owner.strip()
    if not name or not owner:
        raise ValueError('Nama artis dan pemilik wajib diisi.')
    validate_month(month)
    amount = parse_rupiah(amount)
    artists = account.get('artists', [])
    artist = next((x for x in artists if x['id'] == artist_id), None)
    if any(x['name'].casefold() == name.casefold() and x is not artist for x in artists):
        raise ValueError('Nama artis sudah ada pada akun ini. Pilih artis tersebut untuk mengubahnya.')
    if artist is None:
        artist = {'id': max((x['id'] for x in artists), default=0) + 1,
                  'name': name, 'owner': owner, 'earnings': {}}
        artists.append(artist)
        account['artists'] = artists
    artist.update(name=name, owner=owner)
    artist.setdefault('earnings', {})[month] = amount
    return artist


def month_total(account, month):
    return sum(x.get('earnings', {}).get(month, 0) for x in account.get('artists', []))


def rupiah(amount):
    return 'Rp' + f'{amount:,}'.replace(',', '.')


def owner_groups(accounts, month, owners=()):
    """Group registered artists across accounts; keep undetailed accounts reachable."""
    groups = {}
    for name in owners:
        name = ' '.join(str(name).split())
        if name:
            groups.setdefault(name.casefold(), {'owner': name, 'entries': [], 'accounts': {}, 'total': 0})
    for account in accounts:
        artists = account.get('artists', [])
        entries = artists or [None]
        for artist in entries:
            owner = ' '.join(str(artist.get('owner', '') if artist else '').split())
            key = owner.casefold() if owner else None
            group = groups.setdefault(key, {'owner': owner or 'Belum ditentukan',
                                            'entries': [], 'accounts': {}, 'total': 0})
            amount = artist.get('earnings', {}).get(month) if artist else None
            group['entries'].append({'account': account, 'artist': artist, 'amount': amount})
            group['accounts'][str(account['id'])] = account
            if amount is not None:
                group['total'] += amount
    return sorted(groups.values(), key=lambda g: (g['owner']=='Belum ditentukan', g['owner'].casefold()))


def available_artists(accounts):
    assigned = {x['name'].strip().casefold() for a in accounts for x in a.get('artists', [])
                if str(x.get('owner', '')).strip()}
    choices = []
    seen = set()
    for account in accounts:
        for artist in account.get('artists', []) or [None]:
            name = artist['name'] if artist else account['name']
            key = name.strip().casefold()
            if key in assigned or key in seen or (artist and str(artist.get('owner', '')).strip()):
                continue
            seen.add(key)
            choices.append({'account_id': account['id'], 'artist_id': artist['id'] if artist else None,
                            'name': name, 'account_name': account['name'], 'from_account': artist is None})
    return sorted(choices, key=lambda x: x['name'].casefold())


def assign_artists(accounts, choices, owner):
    owner = ' '.join(owner.split())
    if not owner or not choices:
        raise ValueError('Centang minimal satu artis dan tentukan pemiliknya.')
    current = {(x['account_id'], x['artist_id']): x for x in available_artists(accounts)}
    keys = [(x['account_id'], x['artist_id']) for x in choices]
    if len(set(keys)) != len(keys) or any(key not in current for key in keys):
        raise ValueError('Pilihan artis sudah berubah atau sudah dimiliki. Buka kembali checklist.')
    for key in keys:
        item = current[key]
        account = next(a for a in accounts if a['id'] == item['account_id'])
        if item['artist_id'] is None:
            artists = account.setdefault('artists', [])
            artists.append({'id': max((x['id'] for x in artists), default=0)+1,
                            'name': item['name'], 'owner': owner, 'earnings': {}})
        else:
            artist = next(x for x in account['artists'] if x['id'] == item['artist_id'])
            artist['owner'] = owner


def rename_owner(accounts, owners, old, new):
    new = ' '.join(new.split())
    if not new or new.casefold() == 'belum ditentukan':
        raise ValueError('Isi nama pemilik yang valid.')
    old_key = ' '.join(old.split()).casefold()
    names = owners + [x.get('owner','') for a in accounts for x in a.get('artists',[])]
    if any(' '.join(n.split()).casefold() == new.casefold() and ' '.join(n.split()).casefold() != old_key for n in names):
        raise ValueError('Nama pemilik tersebut sudah dipakai.')
    owners[:] = [n for n in owners if ' '.join(n.split()).casefold() != old_key] + [new]
    for a in accounts:
        for artist in a.get('artists',[]):
            if ' '.join(artist.get('owner','').split()).casefold() == old_key:
                artist['owner'] = new


def remove_owner(accounts, owners, owner):
    key = ' '.join(owner.split()).casefold()
    owners[:] = [n for n in owners if ' '.join(n.split()).casefold() != key]
    for a in accounts:
        for artist in a.get('artists',[]):
            if ' '.join(artist.get('owner','').split()).casefold() == key:
                artist['owner'] = ''
