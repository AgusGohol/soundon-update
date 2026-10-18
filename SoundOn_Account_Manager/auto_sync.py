"""Sinkron otomatis Streams & Pendengar dari halaman Analytics SoundOn.

Untuk setiap akun (berurutan, satu per satu):
  1. Pakai Chrome akun yang sedang terbuka, atau buka Chrome profil akun itu
     (diperkecil) bila tertutup dan pengaturan mengizinkan.
  2. Buka https://www.soundon.global/library/analytics?startTime=..&endTime=..[&store=..]
  3. Pastikan rentang tanggal yang tampil di SoundOn sesuai permintaan.
  4. Baca kartu Streams dan Listeners/Pendengar (hanya membaca halaman yang tampil;
     tidak memakai API privat, tidak mengubah apa pun di SoundOn).
  5. Tutup tab yang dibuka, dan tutup Chrome bila Chrome itu dibuka oleh sinkron.

Modul ini tidak menyentuh Tkinter. Hasil dikirim lewat callback; aplikasi
menyimpannya di thread utama.
"""
import os
import re
import subprocess
import time
import urllib.parse
from datetime import date, datetime

ANALYTICS_URL = 'https://www.soundon.global/library/analytics'
ROYALTY_URL = 'https://www.soundon.global/library/royalty'
MAX_ARTISTS = 12          # batas artis per akun agar satu putaran tidak terlalu lama
REGION_WAIT = 15          # detik maksimum menunggu grafik wilayah satu artis yang punya Streams

# Baris artis di tab "Artists" Analytics: nama + tombol/tautan "View Insights".
ARTIST_ROWS_JS = r"""() => {
  const label = /^(view insights|lihat insights?|lihat wawasan|lihat analitik)$/i;
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const rows = [...document.querySelectorAll('tbody tr, [role=row]')].filter(visible);
  const out = [];
  rows.forEach((r, i) => {
    const btn = [...r.querySelectorAll('a,button,span,div')].find(e => label.test((e.textContent || '').trim()));
    if (!btn) return;
    const cell = r.querySelector('td,[role=cell]');
    const lines = ((cell ? cell.innerText : r.innerText) || '').split('\n').map(t => t.trim()).filter(Boolean);
    const link = btn.closest('a');
    // Nilai kolom "Streams" baris ini (bila tabel punya judul kolom itu) agar artis
    // yang 0 Streams bisa dilewati tanpa membuka halaman insights-nya.
    let streams = null;
    const table = r.closest('table');
    const heads = table ? [...table.querySelectorAll('thead th')]
                        : [...document.querySelectorAll('[role=columnheader]')];
    const col = heads.findIndex(h => /^streams?\b/i.test((h.innerText || '').trim()));
    const cells = [...r.querySelectorAll(':scope > td, [role=cell]')];
    if (col >= 0 && cells[col]) streams = (cells[col].innerText || '').trim().split('\n')[0] || null;
    out.push({index: out.length, name: lines[0] || '', href: link ? link.href : null, streams});
  });
  return out;
}"""
# Tabel tanpa isi ("No data") — dipakai agar tab Artists yang kosong tidak ditunggu lama.
NO_DATA_JS = r"""() => {
  const re = /^(no data|tidak ada data|belum ada data|data tidak tersedia)$/i;
  return [...document.querySelectorAll('body *')].some(el => {
    if (el.children.length > 1 || !re.test((el.innerText || '').trim())) return false;
    const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0;
  });
}"""

# ID "store" SoundOn untuk filter platform. "Semua Platform" = tanpa parameter store.
STORE_IDS = {'Spotify': '1026'}
SUPPORTED_PLATFORMS = ('Semua Platform',) + tuple(STORE_IDS)

RANGE_JS = r"""() => {
  const re = /(\d{4}-\d{2}-\d{2})\s*[~–-]\s*(\d{4}-\d{2}-\d{2})/;
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  for (const el of document.querySelectorAll('input')) {
    if (visible(el) && re.test(el.value || '')) { const m = (el.value).match(re); return [m[1], m[2]]; }
  }
  const nodes = [...document.querySelectorAll('div,span,p,button')].filter(el => el.children.length <= 3);
  for (const el of nodes) {
    const t = (el.innerText || '').trim();
    if (t.length < 40 && re.test(t) && visible(el)) { const m = t.match(re); return [m[1], m[2]]; }
  }
  return null;
}"""

# Jumlah harian dari grafik (bila ECharts tersedia di halaman) untuk angka Streams yang persis.
CHART_SUM_JS = r"""() => {
  try {
    const ec = window.echarts;
    if (!ec || !ec.getInstanceByDom) return null;
    for (const el of document.querySelectorAll('[_echarts_instance_]')) {
      const inst = ec.getInstanceByDom(el);
      if (!inst) continue;
      const bars = (inst.getOption().series || []).filter(s => s.type === 'bar');
      if (!bars.length) continue;
      let sum = 0;
      for (const s of bars) for (const d of (s.data || [])) {
        let v = (d !== null && typeof d === 'object') ? (Array.isArray(d) ? d[d.length - 1] : d.value) : d;
        if (Array.isArray(v)) v = v[v.length - 1];
        const n = Number(v);
        if (isFinite(n)) sum += n;
      }
      return sum;
    }
  } catch (e) {}
  return null;
}"""


CARD_JS = r"""(labels) => {
  // Cadangan bila struktur kartu SoundOn berubah: cari label persis (mis. "Streams")
  // lalu angka di kartu yang sama. Kartu ringkasan muncul sebelum tabel lagu.
  const num = /^[\d.,]+\s*(K|M|B|rb|jt|ribu|juta)?$/i;
  const leaves = el => [...el.querySelectorAll('*')].filter(x => x.children.length === 0);
  for (const lab of labels) {
    for (const el of leaves(document.body)) {
      if (el.textContent.trim() !== lab || el.closest('th,thead,table')) continue;
      let card = el.parentElement;
      for (let k = 0; k < 2 && card; k++, card = card.parentElement) {
        const hit = leaves(card).map(x => x.textContent.trim()).find(t => num.test(t));
        if (hit) return hit;
      }
    }
  }
  return null;
}"""
CARD_LABELS = {'streams': ['Streams'], 'listeners': ['Listeners', 'Pendengar']}


def read_card_fallback(page, kind):
    try:
        return page.evaluate(CARD_JS, CARD_LABELS[kind])
    except Exception:
        return None


def analytics_url(start, end, platform):
    params = {'startTime': start.isoformat(), 'endTime': end.isoformat()}
    store = STORE_IDS.get(platform)
    if store:
        params['store'] = store
    return ANALYTICS_URL + '?' + urllib.parse.urlencode(params)


class SyncStopped(Exception):
    pass


class Syncer:
    """Jalankan di thread latar belakang: Syncer(...).run(accounts)."""

    def __init__(self, *, start, end, platform, open_closed, chrome_path, profile_dir, port_for, ready,
                 read_card, parse_number, on_progress, on_result, should_stop, busy_account=None, log=None,
                 read_balance=None, on_balance=None, read_regions=None, on_region=None, periods=None):
        self.start, self.end = start, end
        # Beberapa periode sekaligus (mis. bulan ini + bulan lalu). Periode pertama juga dipakai
        # untuk Asal Streams.
        self.periods = list(periods) if periods else [(start, end)]
        self.start, self.end = self.periods[0]
        self.platform = platform if platform in SUPPORTED_PLATFORMS else 'Semua Platform'
        self.open_closed = open_closed
        self.chrome_path, self.profile_dir, self.port_for, self.ready = chrome_path, profile_dir, port_for, ready
        self.read_card, self.parse_number = read_card, parse_number
        self.on_progress, self.on_result, self.should_stop = on_progress, on_result, should_stop
        self.busy_account = busy_account or (lambda a: False)
        self.log = log or (lambda text: None)
        self.read_balance, self.on_balance = read_balance, on_balance      # saldo (My Earnings)
        self.read_regions, self.on_region = read_regions, on_region        # asal Streams per artis

    # ------------------------------------------------------------ helpers
    def _sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.should_stop():
                raise SyncStopped()
            time.sleep(0.25)

    def _launch(self, a):
        chrome = self.chrome_path()
        if not chrome:
            raise RuntimeError('Google Chrome tidak ditemukan.')
        os.makedirs(self.profile_dir(a), exist_ok=True)
        subprocess.Popen([chrome, '--user-data-dir=' + self.profile_dir(a), '--remote-debugging-address=127.0.0.1',
                          '--remote-debugging-port=' + str(self.port_for(a)), '--start-minimized',
                          '--no-first-run', '--no-default-browser-check', 'about:blank'])
        for _ in range(80):
            self._sleep(0.5)
            if self.ready(a):
                return
        raise RuntimeError('Chrome akun tidak siap dalam 40 detik.')

    def _balance(self, page, a):
        page.goto(ROYALTY_URL, wait_until='domcontentloaded', timeout=60000)
        for _ in range(50):
            self._sleep(0.5)
            if 'login' in page.url.lower():
                return 'saldo: perlu login'
            try:
                result = self.read_balance(page)
            except Exception:
                result = None
            if result:
                amount, currency, raw = result
                self.on_balance(a, amount, currency)
                return 'saldo ' + str(raw).strip()
        return 'saldo tidak terbaca'

    def _open_artists_tab(self, page):
        url = analytics_url(self.start, self.end, self.platform)
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        for _ in range(40):
            self._sleep(0.5)
            if self.read_card(page, 'streams'):
                break
        for label in ('Artists', 'Artis', 'Artist'):
            tab = page.get_by_text(label, exact=True)
            if tab.count():
                tab.first.scroll_into_view_if_needed(timeout=5000)
                tab.first.click(timeout=5000)
                break
        else:
            raise RuntimeError('tab Artists tidak ditemukan')
        rows, empty_hits = [], 0
        for _ in range(30):
            self._sleep(0.5)
            rows = page.evaluate(ARTIST_ROWS_JS) or []
            if rows:
                break
            # "No data" terlihat dua kali berturut-turut (±1 detik) → tidak ada artis.
            try:
                empty_hits = empty_hits + 1 if page.evaluate(NO_DATA_JS) else 0
            except Exception:
                empty_hits = 0
            if empty_hits >= 2:
                break
        return rows

    def _ensure_range(self, page):
        shown = None
        for _ in range(20):
            shown = page.evaluate(RANGE_JS)
            if shown:
                break
            self._sleep(0.5)
        if shown and date.fromisoformat(shown[0]) == self.start and date.fromisoformat(shown[1]) <= self.end:
            return shown
        # Coba tambahkan tanggal ke alamat halaman insights.
        parts = urllib.parse.urlsplit(page.url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        q.update(startTime=self.start.isoformat(), endTime=self.end.isoformat())
        if STORE_IDS.get(self.platform):
            q['store'] = STORE_IDS[self.platform]
        page.goto(urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q))),
                  wait_until='domcontentloaded', timeout=60000)
        for _ in range(20):
            self._sleep(0.5)
            shown = page.evaluate(RANGE_JS)
            if shown:
                break
        if shown and date.fromisoformat(shown[0]) == self.start and date.fromisoformat(shown[1]) <= self.end:
            return shown
        return None

    def _number(self, text):
        """Angka dari teks kartu/tabel; None bila tidak terbaca."""
        if text is None or str(text).strip() in ('', '-', '--', '—'):
            return None
        try:
            value = self.parse_number(text)
        except Exception:
            return None
        return value[0] if isinstance(value, tuple) else value

    def _with_range(self, url):
        """Tambahkan periode (dan platform) ke alamat insights agar tidak perlu dimuat ulang."""
        parts = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        q.update(startTime=self.start.isoformat(), endTime=self.end.isoformat())
        if STORE_IDS.get(self.platform):
            q['store'] = STORE_IDS[self.platform]
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))

    def _wait_regions(self, page):
        """Tunggu grafik "Streams berdasarkan wilayah".

        Mengembalikan (regions, kosong). Artis yang Streams-nya 0 langsung dianggap kosong
        setelah angka 0 terlihat stabil ±1,5 detik — tidak lagi menunggu grafik sampai habis waktu.
        """
        heading_re = re.compile(r'^(streams by region|stream(s)? (berdasarkan|menurut) wilayah)$', re.I)
        started, zeros, scrolled = time.time(), 0, False
        while time.time() - started < REGION_WAIT:
            self._sleep(0.5)
            if not scrolled:
                try:
                    heading = page.get_by_text(heading_re)
                    if heading.count():
                        heading.first.scroll_into_view_if_needed(timeout=2000)
                        scrolled = True
                except Exception:
                    pass
            try:
                result = self.read_regions(page)
            except Exception:
                result = None
            if result and result.get('regions'):
                return result['regions'], False
            try:
                value = self._number(self.read_card(page, 'streams'))
            except Exception:
                value = None
            zeros = zeros + 1 if value == 0 else 0
            # 0 stabil + judul grafik sudah tampil (halaman selesai dimuat) → kosong.
            if (zeros >= 3 and scrolled) or zeros >= 8:
                return None, True
        return None, False

    def _regions(self, page, a):
        rows = self._open_artists_tab(page)
        if not rows:
            return 'asal Streams: tidak ada artis'
        done, failed, empty = 0, 0, 0
        need_tab = False           # tab Artists hanya dibuka ulang bila harus menekan tombol
        for row in rows[:MAX_ARTISTS]:
            if self.should_stop():
                raise SyncStopped()
            # Kolom Streams di tabel Artists = 0 → lewati tanpa membuka insights.
            if self._number(row.get('streams')) == 0:
                empty += 1
                self.log('  %s · %s: 0 Streams, dilewati' % (a.get('name', ''), row['name']))
                continue
            if row.get('href'):
                page.goto(self._with_range(row['href']), wait_until='domcontentloaded', timeout=60000)
            else:
                if need_tab:
                    rows_now = self._open_artists_tab(page)
                    row = next((r for r in rows_now if r['name'] == row['name']), row)
                buttons = page.get_by_text(re.compile(r'^(view insights|lihat insights?|lihat wawasan|lihat analitik)$', re.I))
                if buttons.count() <= row['index']:
                    failed += 1
                    continue
                buttons.nth(row['index']).click(timeout=8000)
            need_tab = True
            for _ in range(40):
                if '/analytics/artist' in page.url:
                    break
                self._sleep(0.5)
            if '/analytics/artist' not in page.url:
                failed += 1
                continue
            artist_id = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query).get('id', [''])[0]
            shown = self._ensure_range(page)
            if not artist_id or not shown:
                failed += 1
                self.log('  %s · %s: periode/ID artis tidak cocok, dilewati' % (a.get('name', ''), row['name']))
                continue
            regions, is_empty = self._wait_regions(page)
            if is_empty:
                empty += 1
                self.log('  %s · %s: 0 Streams pada periode ini, dilewati' % (a.get('name', ''), row['name']))
                continue
            if not regions:
                failed += 1
                continue
            self.on_region(a, {'start': self.start.isoformat(), 'end': self.end.isoformat(), 'platform': self.platform,
                               'artist_id': artist_id, 'artist_name': row['name'] or ('Artis ' + artist_id),
                               'regions': regions, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                               'source': 'sinkron otomatis (%s ~ %s)' % (shown[0], shown[1])})
            done += 1
        extra = ' (maks. %d artis)' % MAX_ARTISTS if len(rows) > MAX_ARTISTS else ''
        return ('asal Streams %d artis%s' % (done, extra) + (', %d kosong' % empty if empty else '')
                + (', %d gagal' % failed if failed else ''))

    # ------------------------------------------------------------ satu akun
    def _read_streams(self, page, a):
        """Baca Streams & Pendengar untuk periode self.start..self.end di tab ini."""
        url = analytics_url(self.start, self.end, self.platform)
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        # Tunggu sampai kartu Streams tampil, atau terdeteksi halaman login.
        text = None
        for _ in range(60):
            self._sleep(0.5)
            low = page.url.lower()
            if 'login' in low or 'signin' in low or 'sign-in' in low:
                return 'login', 'Belum login. Buka akun ini dan login sekali.'
            try:
                text = self.read_card(page, 'streams')
            except Exception:
                text = None
            if text:
                break
        if not text:
            return 'gagal', 'Kartu Streams tidak muncul (halaman lambat atau tampilan SoundOn berubah).'
        # Rentang tanggal yang benar-benar dipakai SoundOn.
        shown = None
        for _ in range(20):
            shown = page.evaluate(RANGE_JS)
            if shown:
                break
            self._sleep(0.5)
        if not shown:
            return 'gagal', 'Rentang tanggal di SoundOn tidak terbaca; data tidak disimpan.'
        s_shown, e_shown = date.fromisoformat(shown[0]), date.fromisoformat(shown[1])
        if s_shown != self.start or e_shown > self.end:
            return 'gagal', 'SoundOn menampilkan %s ~ %s, bukan %s ~ %s; data tidak disimpan.' % (
                shown[0], shown[1], self.start, self.end)
        # Beri waktu angka diperbarui, lalu baca dua kali sampai stabil.
        self._sleep(2.5)
        values = None
        for _ in range(6):
            s1 = self.read_card(page, 'streams')
            l1 = self.read_card(page, 'listeners')
            self._sleep(1.2)
            s2 = self.read_card(page, 'streams')
            l2 = self.read_card(page, 'listeners')
            if s1 and s1 == s2 and l1 == l2:
                values = (s1, l1)
                break
        if not values:
            return 'gagal', 'Angka belum stabil; coba lagi nanti.'
        streams, s_approx = self.parse_number(values[0])
        listeners, l_approx = self.parse_number(values[1]) if values[1] else (0, False)
        if s_approx:
            try:
                exact = page.evaluate(CHART_SUM_JS)
            except Exception:
                exact = None
            if exact is not None and streams and abs(exact - streams) <= max(1, streams * 0.06):
                streams, s_approx = int(round(exact)), False
        record = {'start': self.start.isoformat(), 'end': self.end.isoformat(), 'platform': self.platform,
                  'streams': int(streams), 'listeners': int(listeners),
                  'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'source': 'sinkron otomatis',
                  'streams_display': values[0], 'streams_approx': bool(s_approx),
                  'listeners_display': values[1] or '', 'listeners_approx': bool(l_approx),
                  'soundon_range': '%s ~ %s' % (shown[0], shown[1])}
        self.on_result(a, record)
        self._last_streams = int(streams)
        note = values[0] + ' streams'
        if e_shown < self.end:
            note += ' (data SoundOn s.d. %s)' % shown[1]
        return 'ok', note

    def sync_one(self, pw, a):
        opened_by_us = False
        if self.busy_account(a):
            return 'lewati', 'Sedang dipakai Studio unggah.'
        if not self.ready(a):
            if not self.open_closed:
                return 'lewati', 'Chrome akun tertutup.'
            self._launch(a)
            opened_by_us = True
        browser = page = None
        try:
            browser = pw.chromium.connect_over_cdp('http://127.0.0.1:%d' % self.port_for(a), timeout=15000)
            ctx = browser.contexts[0] if browser.contexts else None
            if ctx is None:
                raise RuntimeError('Profil Chrome belum siap.')
            if opened_by_us and ctx.pages:
                page = ctx.pages[0]
            else:
                page = ctx.new_page()
            notes, oks, first_streams = [], [], None
            periods = self.periods
            for i, (p_start, p_end) in enumerate(periods):
                self.start, self.end = p_start, p_end
                self._last_streams = None
                status, note = self._read_streams(page, a)
                if i == 0:
                    first_streams = self._last_streams
                if status == 'login':
                    return status, note
                label = ('%s: ' % p_start.strftime('%m/%Y')) if len(periods) > 1 else ''
                notes.append(label + note)
                oks.append(status == 'ok')
            self.start, self.end = periods[0]
            note = ' · '.join(notes)
            if not any(oks):
                return 'gagal', note
            if self.read_regions and self.on_region and first_streams == 0:
                # Akun tanpa Streams pada periode ini: tidak ada artis yang perlu dibuka.
                note += ' · asal Streams: 0 Streams, dilewati'
            elif self.read_regions and self.on_region:
                try:
                    note += ' · ' + self._regions(page, a)
                except SyncStopped:
                    raise
                except Exception as exc:
                    note += ' · asal Streams gagal: ' + str(exc).split('\n')[0][:120]
            if self.read_balance and self.on_balance:
                try:
                    note += ' · ' + self._balance(page, a)
                except SyncStopped:
                    raise
                except Exception as exc:
                    note += ' · saldo gagal: ' + str(exc).split('\n')[0][:120]
            return 'ok', note
        finally:
            try:
                if page is not None and not opened_by_us:
                    page.close()
            except Exception:
                pass
            if opened_by_us and browser is not None:
                try:
                    browser.new_browser_cdp_session().send('Browser.close')
                except Exception:
                    pass
            try:
                if browser is not None:
                    browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------ semua akun
    def run(self, accounts):
        from playwright.sync_api import sync_playwright
        summary = {'ok': [], 'login': [], 'lewati': [], 'gagal': []}
        total = len(accounts)
        self.log('Mulai sinkron %d akun · %s · %s' % (total, ', '.join('%s s.d. %s' % p for p in self.periods), self.platform))
        with sync_playwright() as pw:
            for i, a in enumerate(accounts, 1):
                if self.should_stop():
                    self.log('Dihentikan pengguna.')
                    break
                self.on_progress(i, total, a)
                try:
                    status, note = self.sync_one(pw, a)
                except SyncStopped:
                    self.log('Dihentikan pengguna.')
                    break
                except Exception as exc:
                    status, note = 'gagal', str(exc).split('\n')[0][:200]
                summary[status].append((a, note))
                self.log('[%s] %s (#%s): %s' % (status.upper(), a.get('name', ''), a.get('id'), note))
                try:
                    self._sleep(3)        # jeda sopan antarakun
                except SyncStopped:
                    self.log('Dihentikan pengguna.')
                    break
        return summary
