"""Komponen grafik Dashboard (Tkinter Canvas murni, tanpa library tambahan).

StatCard   kartu angka (ikon, nilai besar, chip persen, grafik kecil)
AddCard    kartu bergaris putus untuk aksi "Tambah akun"
LineChart  grafik garis beberapa seri per bulan, keterangan saat disorot
BarChart   grafik batang (akun teratas), batang tertinggi disorot warna aksen
BarList    daftar nilai dengan batang horizontal (saldo per akun)
Activity   daftar aktivitas sinkron terakhir
StatusGrid kotak status sinkron per akun
Semua komponen menggambar ulang sendiri saat ukurannya berubah.
"""
import tkinter as tk

from ui_theme import (PANEL, CARD, WHITE, DIM, MUTED, PURPLE, GREEN, RED, INK, THEME, FONT,
                      mix, rounded_rect, draw_icon, text_width)

ACCENT = PURPLE                     # aksen utama (merah-oranye pada mode gelap)
# Batas peringatan Asal Streams per artis (persen, "lebih dari").
WARN_US = 80
WARN_ID = 30


def region_warnings(id_pct, us_pct):
    """Daftar peringatan untuk satu artis, mis. ['AS > 80%']."""
    out = []
    if us_pct is not None and us_pct > WARN_US:
        out.append('AS > %d%%' % WARN_US)
    if id_pct is not None and id_pct > WARN_ID:
        out.append('ID > %d%%' % WARN_ID)
    return out
SECOND = WHITE if THEME == 'dark' else '#3f3f46'


def _font(size, bold=False):
    return (FONT, size, 'bold' if bold else 'normal')


def chip(canvas, x, y, text, color, bg, anchor='w', size=8):
    """Kapsul kecil berwarna (mis. "+12%"). Mengembalikan lebar."""
    f = _font(size, True)
    w = text_width(f, text) + 14
    h = size * 2 + 6
    x0 = x if anchor == 'w' else x - w
    rounded_rect(canvas, x0, y - h / 2, x0 + w, y + h / 2, h / 2, mix(bg, color, 0.18))
    canvas.create_text(x0 + w / 2, y, text=text, fill=color, font=f)
    return w


def tooltip(canvas, x, y, lines, bg=None):
    """Kotak keterangan kecil di dekat (x, y). lines = [(teks, warna, tebal)]."""
    canvas.delete('tip')
    bg = bg or mix(PANEL, INK, 0.1)
    f = [_font(9, b) for _, _, b in lines]
    w = max(text_width(fo, t) for (t, _, _), fo in zip(lines, f)) + 20
    h = 10 + 17 * len(lines)
    cw, ch = canvas.winfo_width(), canvas.winfo_height()
    x0 = min(max(4, x + 12), cw - w - 4)
    y0 = min(max(4, y - h - 10), ch - h - 4)
    items = [rounded_rect(canvas, x0, y0, x0 + w, y0 + h, 8, bg, mix(bg, INK, 0.12))]
    for i, ((t, col, _), fo) in enumerate(zip(lines, f)):
        items.append(canvas.create_text(x0 + 10, y0 + 13 + 17 * i, text=t, fill=col, font=fo, anchor='w'))
    for it in items:
        canvas.addtag_withtag('tip', it)


class _Surface(tk.Canvas):
    """Kanvas dengan panel bulat sebagai latar; subkelas menggambar di _paint(w, h)."""

    def __init__(self, parent, height, color=PANEL, radius=16, width=160):
        outer = parent.cget('bg')
        # Lebar awal kecil: grid/pack yang menentukan lebar sebenarnya.
        super().__init__(parent, height=height, width=width, bg=outer, highlightthickness=0, bd=0)
        self._color, self._radius = color, radius
        self.bind('<Configure>', lambda e: self.redraw())

    def redraw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, self._radius, self._color)
        self._paint(w, h)

    def _paint(self, w, h):
        pass

    def _title(self, title, value=None, x=20, y=22, sub=None):
        self.create_text(x, y, text=title, fill=DIM, font=_font(10), anchor='w')
        if value is not None:
            self.create_text(x, y + 30, text=value, fill=WHITE, font=_font(19, True), anchor='w')
        if sub:
            self.create_text(x, y + 56, text=sub, fill=MUTED, font=_font(8), anchor='w')


# ---------------------------------------------------------------- kartu angka
class StatCard(_Surface):
    def __init__(self, parent, title, icon, accent=ACCENT, height=136):
        super().__init__(parent, height, CARD, 16)
        self.title, self.icon, self.accent = title, icon, accent
        self.value, self.sub, self.chip, self.chip_color, self.series = '—', '', '', GREEN, []
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))

    def _hover(self, on):
        self._color = mix(CARD, INK, 0.05) if on else CARD
        self.redraw()

    def set(self, value, sub='', chip_text='', chip_color=GREEN, series=None):
        self.value, self.sub, self.chip, self.chip_color = value, sub, chip_text, chip_color
        self.series = list(series or [])
        self.redraw()

    def _paint(self, w, h):
        c = self._color
        # Kilau lembut di kanan atas (pengganti tekstur pada contoh).
        for i in range(10):
            t = 0.012 * (10 - i)
            r = 40 + i * 9
            self.create_oval(w - 30 - r, -30 - r, w - 30 + r, -30 + r, fill=mix(c, INK, t), outline='')
        rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, 16, '', mix(c, INK, 0.07))
        # ikon dalam lingkaran bergaris + judul
        self.create_oval(16, 14, 44, 42, outline=mix(c, INK, 0.25), width=1.2)
        draw_icon(self, self.icon, 22, 20, 16, mix(self.accent, INK, 0.1))
        self.create_text(54, 28, text=self.title, fill=WHITE, font=_font(10, True), anchor='w')
        size = 18                         # kecilkan huruf bila angka panjang (mis. saldo Rupiah)
        while size > 11 and text_width(_font(size, True), self.value) > w - 36:
            size -= 1
        self.create_text(18, h - 52, text=self.value, fill=WHITE, font=_font(size, True), anchor='w')
        x = 18
        if self.chip:
            x += chip(self, 18, h - 22, self.chip, self.chip_color, c) + 8
        if self.sub:
            self.create_text(x, h - 22, text=self.sub, fill=MUTED, font=_font(8), anchor='w')
        pts = [(i, v) for i, v in enumerate(self.series) if v is not None]
        if len(pts) >= 2:
            sw, sh = min(110, w * 0.42), 26        # di kanan, di antara judul dan angka
            x0, y0 = w - sw - 16, 50
            lo, hi = min(v for _, v in pts), max(v for _, v in pts)
            span = (hi - lo) or 1
            last = max(len(self.series) - 1, 1)
            xy = [(x0 + sw * i / last, y0 + sh - sh * (v - lo) / span) for i, v in pts]
            col = self.chip_color if self.chip else self.accent
            self.create_line(*[q for p in xy for q in p], fill=col, width=2, smooth=True, capstyle='round')
            ex, ey = xy[-1]
            self.create_oval(ex - 3, ey - 3, ex + 3, ey + 3, fill=col, outline=c)


class AddCard(_Surface):
    def __init__(self, parent, text, command, height=136):
        super().__init__(parent, height, parent.cget('bg'), 16, width=150)
        self.text, self.command = text, command
        self.configure(cursor='hand2')
        self.bind('<ButtonRelease-1>', lambda e: command())
        self._on = False
        self.bind('<Enter>', lambda e: self._set(True))
        self.bind('<Leave>', lambda e: self._set(False))

    def _set(self, on):
        self._on = on
        self.redraw()

    def _paint(self, w, h):
        col = mix(self._color, INK, 0.35 if self._on else 0.2)
        self.create_rectangle(1, 1, w - 1, h - 1, outline=col, dash=(6, 5), width=1.2)
        self.create_oval(18, 16, 46, 44, outline=col, width=1.2)
        self.create_text(32, 30, text='+', fill=DIM, font=_font(14))
        self.create_text(18, h - 34, text=self.text, fill=DIM, font=_font(9), anchor='w', width=w - 36)


# ---------------------------------------------------------------- grafik garis
class LineChart(_Surface):
    def __init__(self, parent, title, height=280):
        super().__init__(parent, height, PANEL, 18)
        self.title, self.value, self.labels, self.series = title, '', [], []
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self.delete('tip') or self.delete('cursor'))
        self._pts = []

    def set(self, value, labels, series):
        """series = [(nama, warna, [nilai/None per label])]."""
        self.value, self.labels, self.series = value, list(labels), list(series)
        self.redraw()

    def _area(self, w, h):
        return 24, 96, w - 24, h - 44

    def _paint(self, w, h):
        self._title(self.title, self.value)
        # keterangan seri (kanan atas)
        x = w - 20
        for name, col, _ in reversed(self.series):
            tw = text_width(_font(9), name)
            self.create_text(x, 24, text=name, fill=DIM, font=_font(9), anchor='e')
            self.create_oval(x - tw - 16, 20, x - tw - 8, 28, fill=col, outline='')
            x -= tw + 34
        x0, y0, x1, y1 = self._area(w, h)
        for i in range(4):
            y = y0 + (y1 - y0) * i / 3
            self.create_line(x0, y, x1, y, fill=mix(PANEL, INK, 0.07), dash=(2, 4))
        n = len(self.labels)
        if n == 0:
            return
        step = (x1 - x0) / max(n - 1, 1)
        for i, lab in enumerate(self.labels):
            bx = x0 + step * i
            rounded_rect(self, bx - 20, y1 + 14, bx + 20, y1 + 34, 10, mix(PANEL, INK, 0.06))
            self.create_text(bx, y1 + 24, text=lab, fill=MUTED, font=_font(8))
        vals = [v for _, _, s in self.series for v in s if v is not None]
        if not vals:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text='Grafik muncul setelah ada data sinkron bulanan',
                             fill=MUTED, font=_font(9))
            return
        hi = max(vals) or 1
        self._pts = []
        for name, col, s in self.series:
            pts = [(x0 + step * i, y1 - (y1 - y0) * v / hi, v) for i, v in enumerate(s) if v is not None]
            self._pts.append((name, col, {round(p[0]): p for p in pts}))
            if len(pts) >= 2:
                self.create_line(*[q for p in pts for q in p[:2]], fill=col, width=2.5, smooth=True, capstyle='round')
            for px, py, _ in pts[-1:]:
                self.create_oval(px - 5, py - 5, px + 5, py + 5, fill=col, outline=PANEL, width=2)

    def _motion(self, e):
        w, h = self.winfo_width(), self.winfo_height()
        x0, y0, x1, y1 = self._area(w, h)
        n = len(self.labels)
        if not n or not self._pts or not (x0 - 10 <= e.x <= x1 + 10):
            self.delete('tip', 'cursor')
            return
        step = (x1 - x0) / max(n - 1, 1)
        i = min(n - 1, max(0, round((e.x - x0) / step)))
        bx = x0 + step * i
        self.delete('cursor')
        self.create_line(bx, y0, bx, y1, fill=mix(PANEL, INK, 0.25), dash=(3, 3), tags='cursor')
        lines = [(self.labels[i], WHITE, True)]
        for name, col, pts in self._pts:
            p = pts.get(round(bx))
            lines.append(('%s: %s' % (name, _num(p[2]) if p else '—'), col, False))
            if p:
                self.create_oval(p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4, fill=col, outline=PANEL, width=2, tags='cursor')
        tooltip(self, bx, min(e.y, y1), lines)


# ---------------------------------------------------------------- grafik batang
class BarChart(_Surface):
    def __init__(self, parent, title, height=280):
        super().__init__(parent, height, PANEL, 18)
        self.title, self.value, self.items = title, '', []
        self._bars = []
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self.delete('tip'))

    def set(self, value, items):
        """items = [(label pendek, nama lengkap, nilai)]."""
        self.value, self.items = value, list(items)
        self.redraw()

    def _paint(self, w, h):
        self._title(self.title, self.value)
        self._bars = []
        if not self.items:
            self.create_text(w / 2, h / 2 + 20, text='Belum ada data periode ini', fill=MUTED, font=_font(9))
            return
        x0, y0, x1, y1 = 20, 96, w - 20, h - 40
        n = len(self.items)
        slot = (x1 - x0) / n
        bw = max(10, min(34, slot * 0.55))
        hi = max(v for _, _, v in self.items) or 1
        top = max(range(n), key=lambda i: self.items[i][2])
        for i, (lab, name, v) in enumerate(self.items):
            cx = x0 + slot * (i + 0.5)
            rounded_rect(self, cx - bw / 2, y0, cx + bw / 2, y1, 6, mix(PANEL, INK, 0.05))
            bh = max(6, (y1 - y0) * v / hi)
            col = ACCENT if i == top else mix(PANEL, INK, 0.26)
            rounded_rect(self, cx - bw / 2, y1 - bh, cx + bw / 2, y1, 6, col)
            if i == top:
                for k in range(int(y1 - bh) + 6, int(y1) - 4, 7):    # garis tipis pada batang tertinggi
                    self.create_line(cx - bw / 2 + 3, k, cx + bw / 2 - 3, k, fill=mix(ACCENT, INK, 0.2))
            self.create_text(cx, y1 + 18, text=lab, fill=WHITE if i == top else MUTED, font=_font(8, i == top))
            self._bars.append((cx - slot / 2, cx + slot / 2, name, v))

    def _motion(self, e):
        for a, b, name, v in self._bars:
            if a <= e.x <= b:
                tooltip(self, e.x, e.y, [(name, WHITE, True), (_num(v) + ' streams', DIM, False)])
                return
        self.delete('tip')


class BarList(_Surface):
    """Judul + nilai besar + daftar (nama, teks nilai, porsi 0..1, warna)."""

    def __init__(self, parent, title, height=250):
        super().__init__(parent, height, PANEL, 18)
        self.title, self.value, self.sub, self.rows = title, '', '', []

    def set(self, value, rows, sub=''):
        self.value, self.rows, self.sub = value, list(rows), sub
        self.redraw()

    def _paint(self, w, h):
        self._title(self.title, self.value, sub=self.sub)
        y = 104
        if not self.rows:
            self.create_text(20, y + 10, text='Belum ada saldo tersinkron', fill=MUTED, font=_font(9), anchor='w')
            return
        for name, text, part, col in self.rows:
            if y > h - 26:
                break
            self.create_text(20, y, text=name, fill=WHITE, font=_font(9), anchor='w', width=w * 0.55)
            self.create_text(w - 20, y, text=text, fill=DIM, font=_font(9, True), anchor='e')
            rounded_rect(self, 20, y + 12, w - 20, y + 18, 3, mix(PANEL, INK, 0.07))
            rounded_rect(self, 20, y + 12, 20 + max(6, (w - 40) * min(1, part)), y + 18, 3, col)
            y += 36


# ---------------------------------------------------------------- aktivitas & status
STATUS_STYLE = {
    'OK': ('Berhasil', GREEN, 'check'),
    'LOGIN': ('Perlu login', ACCENT, 'key'),
    'GAGAL': ('Gagal', RED, 'alert'),
    'LEWATI': ('Dilewati', MUTED, 'circle'),
}


class Activity(_Surface):
    def __init__(self, parent, title, on_link=None, height=250):
        super().__init__(parent, height, PANEL, 18)
        self.title, self.rows, self.on_link = title, [], on_link
        self.bind('<ButtonRelease-1>', self._click)

    def set(self, rows):
        """rows = [(status, nama akun, keterangan, waktu 'dd/mm HH:MM')] terbaru dulu."""
        self.rows = list(rows)
        self.redraw()

    def _paint(self, w, h):
        self.create_text(20, 24, text=self.title, fill=DIM, font=_font(10), anchor='w')
        if self.on_link:
            rounded_rect(self, w - 108, 12, w - 16, 36, 12, mix(PANEL, INK, 0.08))
            self.create_text(w - 62, 24, text='Lihat laporan', fill=WHITE, font=_font(8))
        if not self.rows:
            self.create_text(20, 70, text='Belum ada sinkron.', fill=MUTED, font=_font(9), anchor='w')
            return
        y = 64
        for status, name, note, when in self.rows:
            if y > h - 24:
                break
            label, col, icon = STATUS_STYLE.get(status, ('', DIM, 'circle'))
            self.create_oval(20, y - 15, 50, y + 15, outline=mix(PANEL, INK, 0.2), width=1.2)
            draw_icon(self, icon, 28, y - 7, 14, col)
            self.create_text(62, y - 7, text=name, fill=WHITE, font=_font(9, True), anchor='w', width=w * 0.5)
            self.create_text(62, y + 9, text=label + ('  ·  ' + when if when else ''), fill=MUTED, font=_font(8), anchor='w')
            note = note if len(note) <= 26 else note[:25] + '…'
            self.create_text(w - 20, y, text=note, fill=col if status != 'OK' else WHITE, font=_font(9, True), anchor='e')
            y += 44

    def _click(self, e):
        if self.on_link and e.x > self.winfo_width() - 110 and e.y < 40:
            self.on_link()


class StatusGrid(_Surface):
    def __init__(self, parent, title, height=250):
        super().__init__(parent, height, PANEL, 18)
        self.title, self.value, self.cells = title, '', []
        self._boxes = []
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self.delete('tip'))

    def set(self, value, cells):
        """cells = [(nama akun, status 'OK'/'LOGIN'/'GAGAL'/'LEWATI'/None)]."""
        self.value, self.cells = value, list(cells)
        self.redraw()

    def _paint(self, w, h):
        self._title(self.title, self.value)
        x = 20
        for key in ('OK', 'LOGIN', 'GAGAL'):
            label, col, _ = STATUS_STYLE[key]
            self.create_rectangle(x, h - 22, x + 8, h - 14, fill=self._color_of(key), outline='')
            self.create_text(x + 13, h - 18, text=label, fill=MUTED, font=_font(8), anchor='w')
            x += text_width(_font(8), label) + 30
        self._boxes = []
        n = len(self.cells)
        if not n:
            return
        x0, y0, x1, y1 = 20, 92, w - 20, h - 34
        size = 28
        gap = 6
        while size > 6:
            cols = max(1, int((x1 - x0 + gap) // (size + gap)))
            if ((n + cols - 1) // cols) * (size + gap) <= y1 - y0:
                break
            size -= 1
        cols = max(1, int((x1 - x0 + gap) // (size + gap)))
        for i, (name, status) in enumerate(self.cells):
            cx = x0 + (i % cols) * (size + gap)
            cy = y0 + (i // cols) * (size + gap)
            self.create_rectangle(cx, cy, cx + size, cy + size, fill=self._color_of(status), outline='')
            self._boxes.append((cx, cy, cx + size, cy + size, name, status))

    @staticmethod
    def _color_of(status):
        return {'OK': mix(PANEL, WHITE, 0.85), 'LOGIN': ACCENT, 'GAGAL': RED,
                'LEWATI': mix(PANEL, INK, 0.3)}.get(status, mix(PANEL, INK, 0.1))

    def _motion(self, e):
        for a, b, c, d, name, status in self._boxes:
            if a <= e.x <= c and b <= e.y <= d:
                label = STATUS_STYLE.get(status, ('Belum disinkron',))[0]
                tooltip(self, e.x, e.y, [(name, WHITE, True), (label, DIM, False)])
                return
        self.delete('tip')


class RegionTable(tk.Canvas):
    """Tabel Asal Streams: satu baris per artis (atau per akun yang belum dibaca).

    rows = [dict(account, name, sub, artist, id_pct, us_pct, streams, updated, accent, first)]
    first=False: baris artis berikutnya dari akun yang sama (nama akun tidak diulang)."""
    HEAD, ROW = 38, 54

    def __init__(self, parent, on_open, on_read):
        self._bg = parent.cget('bg')
        super().__init__(parent, height=self.HEAD + self.ROW, bg=self._bg, highlightthickness=0, bd=0)
        self.on_open, self.on_read = on_open, on_read
        self.rows, self._hits, self._hover, self._base = [], [], None, {}
        self.bind('<Configure>', lambda e: self.redraw())
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self._set_hover(None))
        self.bind('<ButtonRelease-1>', self._click)

    def set(self, rows):
        self.rows = list(rows)
        self.configure(height=self.HEAD + max(1, len(self.rows)) * self.ROW + 8)
        self.redraw()

    def _cols(self, w):
        act = 176
        rest = max(400, w - act)
        spec = [('akun', 'AKUN', 0.24), ('artis', 'ARTIS', 0.17), ('id', 'INDONESIA', 0.2), ('us', 'AMERIKA SERIKAT', 0.2),
                ('streams', 'STREAMS AKUN', 0.1), ('dibaca', 'DIBACA', 0.09)]
        x, cols = 0, {}
        for key, title, part in spec:
            cols[key] = (x, rest * part, title)
            x += rest * part
        cols['aksi'] = (x, act, '')
        return cols

    def redraw(self):
        self.delete('all')
        w = self.winfo_width()
        if w < 50:
            return
        cols = self._cols(w)
        rounded_rect(self, 0, 0, w, self.HEAD, 10, mix(self._bg, INK, 0.06))
        for key, (x, cw, title) in cols.items():
            if title:
                self.create_text(x + 14, self.HEAD / 2, text=title, fill=MUTED, font=_font(8, True), anchor='w')
        self._hits = []
        if not self.rows:
            self.create_text(w / 2, self.HEAD + 26, text='Tidak ada data yang cocok dengan filter.', fill=MUTED, font=_font(10))
            return
        for i, r in enumerate(self.rows):
            self._row(i, r, cols, w)

    def _row(self, i, r, cols, w):
        y0 = self.HEAD + i * self.ROW
        cy = y0 + self.ROW / 2
        warn = region_warnings(r.get('id_pct'), r.get('us_pct')) if r.get('artist') else []
        self._base[i] = mix(self._bg, RED, 0.07) if warn else self._bg
        bg = mix(self._base[i], INK, 0.05) if i == self._hover else self._base[i]
        self.create_rectangle(0, y0, w, y0 + self.ROW, fill=bg, outline='', tags=('rowbg', 'rowbg%d' % i))
        if r.get('first', True):
            self.create_line(8, y0, w - 8, y0, fill=mix(self._bg, INK, 0.08))
            x = cols['akun'][0] + 14
            acc = r.get('accent', ACCENT)
            self.create_oval(x, cy - 15, x + 30, cy + 15, fill=mix(self._bg, acc, 0.22), outline='')
            self.create_text(x + 15, cy, text=(r['name'][:1] or '?').upper(), fill=mix(acc, INK, 0.3), font=_font(10, True))
            avail = cols['akun'][1] - 60
            self.create_text(x + 40, cy - 8, text=_fit(r['name'], _font(10, True), avail), fill=WHITE, font=_font(10, True), anchor='w')
            self.create_text(x + 40, cy + 10, text=_fit(r.get('sub', ''), _font(8), avail), fill=MUTED, font=_font(8), anchor='w')
            sx, sw, _ = cols['streams']
            self.create_text(sx + 14, cy, text=r.get('streams', '—'), fill=DIM, font=_font(9), anchor='w')
        ax, aw, _ = cols['artis']
        if r.get('artist'):
            self.create_text(ax + 14, cy - (8 if warn else 0), text=_fit(r['artist'], _font(10), aw - 20), fill=WHITE,
                             font=_font(10), anchor='w')
            if warn:
                self.create_text(ax + 14, cy + 10, text='⚠ ' + ' · '.join(warn), fill=RED, font=_font(8, True), anchor='w')
            for key, col in (('id', GREEN), ('us', ACCENT)):
                x, cw, _ = cols[key]
                v = r.get(key + '_pct')
                if v is not None and v > (WARN_ID if key == 'id' else WARN_US):
                    col = RED
                bx0, bx1 = x + 14, x + cw - 70
                rounded_rect(self, bx0, cy - 3, bx1, cy + 3, 3, mix(self._bg, INK, 0.09))
                if v is not None and bx1 > bx0:
                    rounded_rect(self, bx0, cy - 3, bx0 + max(6, (bx1 - bx0) * min(100, max(0, v)) / 100), cy + 3, 3, col)
                txt = '—' if v is None else ('%.1f%%' % v).replace('.', ',')
                self.create_text(x + cw - 14, cy, text=txt, fill=col if v is not None else MUTED, font=_font(10, True), anchor='e')
            dx, dw, _ = cols['dibaca']
            self.create_text(dx + 14, cy, text=r.get('updated', '—'), fill=MUTED, font=_font(8), anchor='w')
        else:
            self.create_text(ax + 14, cy, text='Belum dibaca untuk periode ini', fill=MUTED, font=_font(9), anchor='w')
        if r.get('first', True):
            x, aw, _ = cols['aksi']
            right = x + aw - 10
            for key, text, primary in (('read', 'Baca', True), ('open', 'Buka', False)):
                bw = text_width(_font(9, True), text) + 26
                fill = ACCENT if primary else mix(self._bg, INK, 0.1)
                rounded_rect(self, right - bw, cy - 14, right, cy + 14, 14, fill)
                self.create_text(right - bw / 2, cy, text=text, fill='#ffffff' if primary else WHITE, font=_font(9, True))
                self._hits.append((right - bw, cy - 14, right, cy + 14, key, r['account']))
                right -= bw + 8

    def _index(self, y):
        i = int((y - self.HEAD) // self.ROW)
        return i if y >= self.HEAD and 0 <= i < len(self.rows) else None

    def _set_hover(self, i):
        if i != self._hover:
            for j in (self._hover, i):
                if j is not None:
                    base = self._base.get(j, self._bg)
                    self.itemconfigure('rowbg%d' % j, fill=mix(base, INK, 0.05) if j == i else base)
            self._hover = i

    def _motion(self, e):
        self._set_hover(self._index(e.y))
        over = any(a <= e.x <= c and b <= e.y <= d for a, b, c, d, _, _ in self._hits)
        self.configure(cursor='hand2' if over else '')

    def _click(self, e):
        for a, b, c, d, key, account in self._hits:
            if a <= e.x <= c and b <= e.y <= d:
                (self.on_read if key == 'read' else self.on_open)(account)
                return


def _fit(text, font, width):
    text = str(text)
    if width <= 10 or text_width(font, text) <= width:
        return text
    while text and text_width(font, text + '…') > width:
        text = text[:-1]
    return text + '…'


class Segmented(tk.Canvas):
    """Tombol tab berbentuk kapsul (mis. Ringkasan | Daftar Akun)."""

    def __init__(self, parent, options, value, command):
        self._outer = parent.cget('bg')
        super().__init__(parent, height=38, bg=self._outer, highlightthickness=0, bd=0, cursor='hand2')
        self.options, self.value, self.command = list(options), value, command
        self._spans = []
        widths = [text_width(_font(10, True), o) + 36 for o in self.options]
        self.configure(width=sum(widths) + 8)
        self.bind('<Configure>', lambda e: self.redraw())
        self.bind('<ButtonRelease-1>', self._click)

    def set(self, value):
        self.value = value
        self.redraw()

    def redraw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, h / 2, mix(self._outer, INK, 0.07))
        x = 4
        self._spans = []
        for o in self.options:
            ow = text_width(_font(10, True), o) + 36
            if o == self.value:
                rounded_rect(self, x, 4, x + ow, h - 4, (h - 8) / 2, WHITE if THEME == 'dark' else PURPLE)
            self.create_text(x + ow / 2, h / 2, text=o, font=_font(10, o == self.value),
                             fill=('#111113' if THEME == 'dark' else '#ffffff') if o == self.value else DIM)
            self._spans.append((x, x + ow, o))
            x += ow

    def _click(self, e):
        for a, b, o in self._spans:
            if a <= e.x <= b and o != self.value:
                self.set(o)
                self.command(o)


def _num(x):
    try:
        return f'{int(round(x)):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return '—'
