"""Tabel akun Dashboard yang digambar langsung di satu Canvas.

Tabel lama memakai ratusan widget kecil (tombol, avatar, grafik) per baris.
Di Windows, menggulir ratusan widget membuat layar berbayang/rusak dan lambat.
Di sini semua baris digambar sebagai item Canvas, sehingga gulir mulus dan
ringan; header kolom tetap di atas saat digulir.
"""
import tkinter as tk
from tkinter import ttk

import ui_theme as UI
from ui_theme import (rounded_points, RED, INK, TINT, THEME, PANEL, CARD, CARD_HI, LINE, WHITE, DIM, MUTED, PURPLE, GREEN, FONT, FONT_SEMI,
                      mix, rounded_rect, draw_icon, text_width)

# (judul, lebar minimum, bobot, kunci)
COLUMNS = [('', 40, 0, 'sel'), ('AKUN', 190, 1, 'name'), ('STATUS', 100, 0, 'status'),
           ('STREAMS', 100, 0, 'streams'), ('PENDENGAR', 100, 0, 'listeners'), ('HP', 46, 0, 'hp'),
           ('ARTIS', 56, 0, 'artists'), ('LAGU', 52, 0, 'songs'), ('SALDO TERSEDIA', 160, 0, 'balance'),
           ('DIPERBARUI', 104, 0, 'updated'), ('', 385, 0, 'actions')]
COMPACT_HIDE = {'updated'}
COMPACT_WIDTH = 1360
ROW_H = 50
HEAD_H = 36

F_TEXT = (FONT, 10, 'normal')
F_BOLD = (FONT, 10, 'bold')
F_SMALL = (FONT, 8, 'normal')
F_HEAD = (FONT, 8, 'bold')
F_BTN = (FONT, 9, 'normal')
F_BTN_BOLD = (FONT, 9, 'bold')


def _fit(text, font, width):
    text = str(text)
    if width <= 10:
        return ''
    if text_width(font, text) <= width:
        return text
    lo, hi = 0, len(text)          # pencarian biner: sedikit pengukuran font
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(font, text[:mid] + '…') <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + '…' if lo else ''


class AccountTable(tk.Frame):
    """rows: list of dict. actions: dict kunci -> fungsi(row)."""

    def __init__(self, parent, actions, menu_items):
        super().__init__(parent, bg=PANEL)
        self.actions = actions
        self.menu_items = menu_items      # fungsi(row) -> [(label, fungsi)]
        self.rows = []
        self.empty_text = ''
        self.hover_row = None
        self.hover_btn = None
        self._draw_job = None
        self.compact = None
        self.selected = set()            # ID akun yang dicentang
        self.on_selection = None         # fungsi(jumlah) saat pilihan berubah
        self.head = tk.Canvas(self, height=HEAD_H, bg=CARD_HI, highlightthickness=0, bd=0, cursor='hand2')
        self.head.bind('<ButtonRelease-1>', self._head_click)
        self.head.pack(fill='x', padx=(0, 14))
        body_wrap = tk.Frame(self, bg=PANEL)
        body_wrap.pack(fill='both', expand=True)
        self.body = tk.Canvas(body_wrap, bg=PANEL, highlightthickness=0, bd=0, yscrollincrement=1)
        self.bar = ttk.Scrollbar(body_wrap, orient='vertical', command=self.body.yview, style='Dark.Vertical.TScrollbar')
        self.body.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side='right', fill='y', padx=(4, 2))
        self.body.pack(side='left', fill='both', expand=True)
        self.body.bind('<Configure>', self._on_resize)
        self.body.bind('<Motion>', self._on_motion)
        self.body.bind('<Leave>', lambda e: self._set_hover(None, None))
        self.body.bind('<ButtonRelease-1>', self._on_click)
        self.on_compact_change = None

    # ------------------------------------------------------------ data
    def set_rows(self, rows, empty_text='Belum ada akun.'):
        self.rows = rows
        ids = {str(r['account']['id']) for r in rows}
        before = len(self.selected)
        self.selected &= ids
        if len(self.selected) != before and self.on_selection:
            self.on_selection(len(self.selected))
        self.empty_text = empty_text
        self.hover_row = self.hover_btn = None
        self._draw()

    def _on_resize(self, event):
        if self._draw_job:
            self.after_cancel(self._draw_job)
        self._draw_job = self.after(40, self._draw)

    # ------------------------------------------------------------ layout
    def _layout(self, width):
        compact = width < COMPACT_WIDTH
        self.compact = compact
        cols = [c for c in COLUMNS if not (compact and c[3] in COMPACT_HIDE)]
        fixed = sum(c[1] for c in cols)
        extra = max(0, width - fixed)
        weights = sum(c[2] for c in cols) or 1
        xs = {}
        x = 0
        for title, minw, weight, key in cols:
            w = minw + extra * weight / weights
            xs[key] = (x, w, title)
            x += w
        return xs

    def _draw(self):
        self._draw_job = None
        b, h = self.body, self.head
        width = max(400, b.winfo_width())
        xs = self._layout(width)
        # header
        h.delete('all')
        for key, (x, w, title) in xs.items():
            if title:
                h.create_text(x + 12, HEAD_H / 2, text=title, anchor='w', fill=MUTED, font=F_HEAD)
        if self.rows:
            all_on = all(str(r['account']['id']) in self.selected for r in self.rows)
            self._checkbox(h, xs['sel'][0] + 12, HEAD_H / 2, all_on, CARD_HI, ('headsel',))
        b.delete('all')
        if not self.rows:
            b.create_text(width / 2, 60, text=self.empty_text, fill=DIM, font=(FONT, 11))
            b.configure(scrollregion=(0, 0, width, 120))
            return
        for i, r in enumerate(self.rows):
            self._draw_row(i, r, xs, width)
        b.configure(scrollregion=(0, 0, width, len(self.rows) * ROW_H + 8))

    def _checkbox(self, c, x, cy, on, bg, tags):
        size = 16
        if on:
            c.create_polygon(rounded_points(x, cy - size / 2, x + size, cy + size / 2, 4), smooth=True,
                             fill=PURPLE, outline=PURPLE, tags=tags)
            c.create_line(x + 4, cy, x + 7, cy + 3.5, x + 12.5, cy - 3.5, fill='#ffffff', width=2,
                          capstyle='round', joinstyle='round', tags=tags)
        else:
            c.create_polygon(rounded_points(x, cy - size / 2, x + size, cy + size / 2, 4), smooth=True,
                             fill=bg, outline=mix(bg, INK, 0.35), tags=tags)

    def _draw_row(self, i, r, xs, width):
        c = self.body
        y0 = i * ROW_H
        cy = y0 + ROW_H / 2
        tag = 'row%d' % i
        c.create_rectangle(0, y0, width, y0 + ROW_H, fill=PANEL, outline='', tags=(tag, 'rowbg', 'rowbg%d' % i))
        c.create_line(8, y0 + ROW_H - 0.5, width - 8, y0 + ROW_H - 0.5, fill=LINE, tags=tag)

        def text(key, value, color=WHITE, font=F_TEXT, dy=0, pad=12):
            x, w, _ = xs[key]
            c.create_text(x + pad, cy + dy, text=_fit(value, font, w - pad - 6), anchor='w', fill=color, font=font, tags=tag)

        sel_on = str(r['account']['id']) in self.selected
        if sel_on:
            c.itemconfigure('rowbg%d' % i, fill=mix(PANEL, PURPLE, 0.08))
        x, w, _ = xs['sel']
        c.create_rectangle(x, y0, x + w, y0 + ROW_H, fill='', outline='', tags=(tag, 'btn:%d:sel' % i))
        self._checkbox(c, x + 12, cy, sel_on, PANEL, (tag, 'btn:%d:sel' % i))
        # avatar + nama
        x, w, _ = xs['name']
        ax = x + 12
        accent = r.get('accent', PURPLE)
        c.create_oval(ax, cy - 16, ax + 32, cy + 16, fill=mix(PANEL, accent, 0.24), outline=mix(PANEL, accent, 0.45), tags=tag)
        c.create_text(ax + 16, cy, text=(r['name'][:1] or '?').upper(), fill=mix(accent, TINT, 0.35 if THEME == 'dark' else 0.15),
                      font=(FONT, 11, 'bold'), tags=tag)
        nx = ax + 42
        avail = w - (nx - x) - 8
        c.create_text(nx, cy - 8, text=_fit(r['name'], F_BOLD, avail), anchor='w', fill=WHITE, font=F_BOLD, tags=tag)
        c.create_text(nx, cy + 10, text=_fit(r.get('sub', ''), F_SMALL, avail), anchor='w', fill=MUTED, font=F_SMALL, tags=tag)
        # status pill
        x, w, _ = xs['status']
        online = r.get('online')
        color = GREEN if online else MUTED
        label = 'Aktif' if online else 'Tertutup'
        pw = text_width(F_SMALL, label) + 28
        pid = rounded_rect(c, x + 10, cy - 10, x + 10 + pw, cy + 10, 10, mix(PANEL, color, 0.14))
        c.addtag_withtag(tag, pid)
        c.create_oval(x + 19, cy - 3, x + 25, cy + 3, fill=color, outline='', tags=tag)
        c.create_text(x + 30, cy, text=label, anchor='w', fill=mix(color, TINT, 0.3 if THEME == 'dark' else 0.25), font=F_SMALL, tags=tag)
        # angka
        has = r.get('has_period')
        text('streams', r['streams'], GREEN if has else MUTED, F_BOLD if has else F_TEXT)
        text('listeners', r['listeners'], WHITE if has else MUTED)
        text('hp', r['hp']); text('artists', r['artists']); text('songs', r['songs'])
        text('balance', r['balance'], WHITE if r.get('balance_known') else MUTED)
        if 'updated' in xs:
            text('updated', r.get('updated', '—'), DIM, (FONT, 9))
        # tombol aksi (rata kanan)
        x, w, _ = xs['actions']
        buttons = [('open', 'Buka', None, 'primary'), ('upload', 'Unggah', 'music', 'secondary'),
                   ('read', 'Baca  ▾', 'sync', 'secondary'),
                   ('data', 'Data', None, 'secondary'), ('more', '', 'more', 'secondary'),
                   ('delete', '', 'trash', 'danger')]
        bh = 30
        right = x + w - 10
        specs = []
        for key, label, icon_name, variant in reversed(buttons):
            font = F_BTN_BOLD if variant == 'primary' else F_BTN
            tw = text_width(font, label) if label else 0
            bw = (tw + 22 + (20 if icon_name and label else 0)) if label else 30
            specs.append((right - bw, bw, key, label, icon_name, variant, font))
            right -= bw + 5
        for bx, bw, key, label, icon_name, variant, font in specs:
            btag = 'btn:%d:%s' % (i, key)
            if variant == 'danger':
                fill, outline = mix(PANEL, RED, 0.12), ''
            else:
                fill = PURPLE if variant == 'primary' else mix(PANEL, INK, 0.055 if THEME == 'dark' else 0.04)
                outline = '' if variant == 'primary' else mix(PANEL, INK, 0.13)
            rid = rounded_rect(c, bx, cy - bh / 2, bx + bw, cy + bh / 2, 8, fill, outline)
            c.itemconfigure(rid, tags=(tag, btag, 'btn', 'btnbg:%d:%s' % (i, key)))
            fg = '#ffffff' if variant == 'primary' else (RED if variant == 'danger' else WHITE)
            tx = bx + bw / 2
            if icon_name and label:
                draw_icon(c, icon_name, bx + 9, cy - 7, 14, fg, tag=(tag, btag, 'btn'))
                tx = bx + 23 + (bw - 23 - 9) / 2
            elif icon_name:
                draw_icon(c, icon_name, bx + (bw - 16) / 2, cy - 8, 16, fg, tag=(tag, btag, 'btn'))
            if label:
                c.create_text(tx, cy, text=label, fill=fg, font=font, tags=(tag, btag, 'btn'))

    # ------------------------------------------------------------ interaksi
    def _hit(self, event):
        c = self.body
        x, y = c.canvasx(event.x), c.canvasy(event.y)
        row = int(y // ROW_H) if y >= 0 else None
        if row is not None and row >= len(self.rows):
            row = None
        btn = None
        for item in c.find_overlapping(x, y, x, y):
            for t in c.gettags(item):
                if t.startswith('btn:'):
                    btn = t
        return row, btn

    def _set_hover(self, row, btn):
        c = self.body
        if row != self.hover_row:
            if self.hover_row is not None and self.hover_row < len(self.rows):
                on = str(self.rows[self.hover_row]['account']['id']) in self.selected
                c.itemconfigure('rowbg%d' % self.hover_row, fill=mix(PANEL, PURPLE, 0.08) if on else PANEL)
            if row is not None:
                c.itemconfigure('rowbg%d' % row, fill=mix(PANEL, INK, 0.025))
            self.hover_row = row
        if btn != self.hover_btn:
            if self.hover_btn:
                self._paint_btn(self.hover_btn, False)
            if btn:
                self._paint_btn(btn, True)
            self.hover_btn = btn
            c.configure(cursor='hand2' if btn else '')

    def _paint_btn(self, btn, hover):
        _, i, key = btn.split(':')
        if key == 'sel':
            return
        primary = key == 'open'
        if key == 'delete':
            fill = mix(PANEL, RED, 0.24 if hover else 0.12)
        elif primary:
            fill = mix(PURPLE, '#ffffff', 0.12) if hover else PURPLE
        else:
            fill = mix(PANEL, INK, (0.11 if hover else 0.055) if THEME == 'dark' else (0.08 if hover else 0.04))
        try:
            self.body.itemconfigure('btnbg:%s:%s' % (i, key), fill=fill)
        except tk.TclError:
            pass

    def _on_motion(self, event):
        row, btn = self._hit(event)
        self._set_hover(row, btn)

    def _on_click(self, event):
        row, btn = self._hit(event)
        if not btn or row is None:
            return
        _, i, key = btn.split(':')
        r = self.rows[int(i)]
        if key == 'sel':
            self.toggle(str(r['account']['id']))
            return
        if key == 'read':
            m = tk.Menu(self, tearoff=False)
            for label, fn in self.menu_items(r):
                m.add_command(label=label, command=fn)
            m.tk_popup(event.x_root, event.y_root + 8)
            return
        fn = self.actions.get(key)
        if fn:
            fn(r)

    def toggle(self, account_id):
        if account_id in self.selected:
            self.selected.discard(account_id)
        else:
            self.selected.add(account_id)
        self._redraw_keep()
        if self.on_selection:
            self.on_selection(len(self.selected))

    def set_all(self, on):
        ids = {str(r['account']['id']) for r in self.rows}
        self.selected = (self.selected | ids) if on else (self.selected - ids)
        self._redraw_keep()
        if self.on_selection:
            self.on_selection(len(self.selected))

    def clear_selection(self):
        self.set_all(False)
        self.selected.clear()

    def selected_rows(self):
        return [r for r in self.rows if str(r['account']['id']) in self.selected]

    def _redraw_keep(self):
        pos = self.body.yview()[0]
        self._draw()
        self.body.yview_moveto(pos)

    def _head_click(self, event):
        if not self.rows:
            return
        xs = self._layout(max(400, self.body.winfo_width()))
        x, w, _ = xs['sel']
        if x <= event.x <= x + w:
            all_on = all(str(r['account']['id']) in self.selected for r in self.rows)
            self.set_all(not all_on)

    def scroll_top(self):
        self.body.yview_moveto(0)
