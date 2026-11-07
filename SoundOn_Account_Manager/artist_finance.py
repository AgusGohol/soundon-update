"""Artis per akun dan pemiliknya (artists[].owner) di accounts.json.

Penghasilan manual per bulan dihapus pada 3.19.0; data lama ('earnings') dibiarkan di file."""


def save_artist(account, artist_id, name, owner):
    name, owner = ' '.join(name.split()), ' '.join(owner.split())
    if not name or not owner:
        raise ValueError('Nama artis dan pemilik wajib diisi.')
    artists = account.get('artists', [])
    artist = next((x for x in artists if x['id'] == artist_id), None)
    if any(x['name'].casefold() == name.casefold() and x is not artist for x in artists):
        raise ValueError('Nama artis sudah ada pada akun ini. Pilih artis tersebut untuk mengubahnya.')
    if artist is None:
        artist = {'id': max((x['id'] for x in artists), default=0) + 1, 'name': name, 'owner': owner}
        artists.append(artist)
        account['artists'] = artists
    artist.update(name=name, owner=owner)
    return artist


def owner_groups(accounts, owners=()):
    """Group registered artists across accounts; keep undetailed accounts reachable."""
    groups = {}
    for name in owners:
        name = ' '.join(str(name).split())
        if name:
            groups.setdefault(name.casefold(), {'owner': name, 'entries': [], 'accounts': {}})
    for account in accounts:
        artists = account.get('artists', [])
        entries = artists or [None]
        for artist in entries:
            owner = ' '.join(str(artist.get('owner', '') if artist else '').split())
            key = owner.casefold() if owner else None
            group = groups.setdefault(key, {'owner': owner or 'Belum ditentukan', 'entries': [], 'accounts': {}})
            group['entries'].append({'account': account, 'artist': artist})
            group['accounts'][str(account['id'])] = account
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
                            'name': item['name'], 'owner': owner})
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
