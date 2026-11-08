"""Riwayat Transaksi SoundOn (Penghasilan > Riwayat Transaksi) untuk rekap pendapatan bulanan.

Halaman: https://www.soundon.global/library/royalty/transaction-history
Kolom tabel: Tanggal Transaksi | Jenis transaksi | Jumlah | Saldo | Status | Keterangan
  "Transfer masuk" / "Transfer in" (+, keterangan ROYALTY) = pendapatan
  "Tarik" / "Withdraw" (-)                                  = penarikan
Modul ini hanya mengolah teks yang tampil; tidak memakai API privat. Disimpan di akun sebagai
a['transactions'] = [{date, kind 'in'/'out', amount, currency, balance, status, remark, type}].
"""
import re
from datetime import date

TRANSACTIONS_URL = 'https://www.soundon.global/library/royalty/transaction-history'
MAX_PAGES = 6            # 10 baris per halaman; ±2,5 tahun riwayat bulanan
KEEP_MONTHS = 25         # riwayat yang disimpan per akun
SUCCESS = re.compile(r'berhasil|success', re.I)

# Baris tabel yang terlihat + teks "Menampilkan 1-10 dari 41" / "Showing 1 to 10 of 17".
READ_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let rows = [...document.querySelectorAll('tr')].filter(vis)
      .map(tr => [...tr.querySelectorAll('td')].map(td => (td.innerText || '').trim()));
  if (!rows.some(c => c.length >= 4))
    rows = [...document.querySelectorAll('[role=row]')].filter(vis)
      .map(r => [...r.querySelectorAll('[role=cell],[role=gridcell]')].map(td => (td.innerText || '').trim()));
  rows = rows.filter(c => c.length >= 4 && /^\d{4}-\d{2}-\d{2}/.test(c[0]));
  const info = [...document.querySelectorAll('body *')]
      .filter(e => vis(e) && e.children.length === 0 && /(Menampilkan|Showing)\s+\d+/i.test(e.textContent || ''))
      .map(e => e.textContent.trim())[0] || '';
  return {rows, info};
}"""

# Tandai tombol halaman berikutnya pada pager (angka halaman, atau panah "next").
NEXT_JS = r"""(target) => {
  document.querySelectorAll('[data-soundon-next]').forEach(e => e.removeAttribute('data-soundon-next'));
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const info = [...document.querySelectorAll('body *')]
      .find(e => vis(e) && e.children.length === 0 && /(Menampilkan|Showing)\s+\d+/i.test(e.textContent || ''));
  let scope = info;
  for (let i = 0; scope && i < 6; i++, scope = scope.parentElement) {
    if ([...scope.querySelectorAll('li,button,a,span,div')].some(e => vis(e) && (e.textContent || '').trim() === String(target))) break;
  }
  scope = scope || document.body;
  const disabled = e => e.closest('[aria-disabled=true],[disabled],[class*=disabled]');
  let el = [...scope.querySelectorAll('li,button,a,span,div')]
      .filter(e => vis(e) && !disabled(e) && (e.textContent || '').trim() === String(target)
                && ![...e.children].some(c => (c.textContent || '').trim() === String(target)))[0];
  if (!el) el = [...scope.querySelectorAll('li,button,a')]
      .filter(e => vis(e) && !disabled(e) && /next/i.test((e.className || '') + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.title || '')))[0];
  if (!el) return false;
  el.setAttribute('data-soundon-next', '1');
  return true;
}"""


def parse_amount(text):
    """'+ 4.823.304,85 IDR' -> (4823304.85, 'IDR', '+'); '- 247.00 USD' -> (247.0, 'USD', '-')."""
    raw = str(text).replace(' ', ' ').strip()
    m = re.search(r'([+\-−])?\s*([0-9][0-9.,]*)\s*([A-Z]{3})?', raw)
    if not m:
        raise ValueError('Jumlah tidak dikenal: ' + raw)
    sign = '-' if m.group(1) in ('-', '−') else '+'
    num, cur = m.group(2), (m.group(3) or '').upper()
    if not cur:
        cur = 'IDR' if re.search(r'\bRp\b|IDR', raw, re.I) else ('USD' if '$' in raw or 'USD' in raw.upper() else '')
    if ',' in num and '.' in num:
        dec = ',' if num.rfind(',') > num.rfind('.') else '.'
        num = num.replace('.' if dec == ',' else ',', '').replace(dec, '.')
    elif ',' in num or '.' in num:
        sep = ',' if ',' in num else '.'
        parts = num.split(sep)
        # Pemisah terakhir dengan bukan 3 angka di belakangnya = desimal (474,42 / 247.182752).
        if len(parts) == 2 and len(parts[1]) != 3:
            num = parts[0] + '.' + parts[1]
        else:
            num = ''.join(parts)
    return float(num), cur, sign


def parse_rows(rows):
    """Baris tabel (list teks per kolom) -> transaksi. Baris yang tidak dikenal dilewati."""
    out = []
    for cells in rows:
        try:
            when = re.match(r'(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?', cells[0])
            if not when:
                continue
            amount, cur, sign = parse_amount(cells[2])
            balance = None
            try:
                balance = parse_amount(cells[3])[0]
            except (ValueError, IndexError):
                pass
            out.append({'date': when.group(1) + (' ' + when.group(2) if when.group(2) else ''),
                        'kind': 'in' if sign == '+' else 'out', 'amount': amount, 'currency': cur,
                        'balance': balance, 'type': cells[1],
                        'status': cells[4] if len(cells) > 4 else '', 'remark': cells[5] if len(cells) > 5 else ''})
        except (ValueError, IndexError):
            continue
    return out


def total_from_info(info):
    m = re.search(r'(?:dari|of)\s+(\d+)', info or '', re.I)
    return int(m.group(1)) if m else None


def merge(existing, fresh, today=None):
    """Gabung tanpa duplikat (tanggal+jenis+jumlah+mata uang), terbaru dulu, simpan KEEP_MONTHS bulan."""
    keyf = lambda t: (t.get('date'), t.get('kind'), round(float(t.get('amount', 0)), 6), t.get('currency'))
    seen = {}
    for t in list(existing or []) + list(fresh or []):
        seen[keyf(t)] = t
    today = today or date.today()
    y, m = today.year, today.month - KEEP_MONTHS
    while m <= 0:
        y, m = y - 1, m + 12
    cutoff = '%04d-%02d' % (y, m)
    return sorted((t for t in seen.values() if str(t.get('date', ''))[:7] >= cutoff), key=lambda t: t['date'], reverse=True)


def month_summary(transactions, month):
    """Ringkasan satu bulan ('YYYY-MM') untuk satu akun:
    {currency: {'income', 'out', 'count'}} — hanya transaksi berstatus berhasil."""
    out = {}
    for t in transactions or []:
        if str(t.get('date', ''))[:7] != month:
            continue
        if t.get('status') and not SUCCESS.search(str(t['status'])):
            continue
        s = out.setdefault(t.get('currency') or '?', {'income': 0.0, 'out': 0.0, 'count': 0})
        s['income' if t.get('kind') == 'in' else 'out'] += float(t.get('amount', 0))
        s['count'] += 1
    return out
