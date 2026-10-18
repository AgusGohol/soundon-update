"""Pemilih periode & bulan yang sederhana dan rapi (Tkinter murni).

PeriodButton: tombol "1 Okt – 18 Okt 2026" yang membuka panel berisi pilihan
cepat (Hari ini, 7 hari, Bulan ini, ...) dan kalender untuk memilih rentang.
MonthButton: tombol "Oktober 2026" yang membuka kisi 12 bulan.
"""
import calendar
import tkinter as tk
from datetime import date, timedelta

import ui_theme as UI
from ui_theme import (BG, PANEL, CARD, CARD_HI, LINE, WHITE, DIM, MUTED, PURPLE, FONT, INK, TINT, THEME,
                      mix, rounded_rect, draw_icon, text_width)

MONTHS = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September',
          'Oktober', 'November', 'Desember']
MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
DAYS = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']


def _parse(text, fallback):
    try:
        return date.fromisoformat(str(text).strip())
    except ValueError:
        return fallback


def format_period(start, end):
    if start == end:
        return '%d %s %d' % (start.day, MONTHS_SHORT[start.month - 1], start.year)
    if start.year == end.year:
        return '%d %s – %d %s %d' % (start.day, MONTHS_SHORT[start.month - 1], end.day,
                                     MONTHS_SHORT[end.month - 1], end.year)
    return '%d %s %d – %d %s %d' % (start.day, MONTHS_SHORT[start.month - 1], start.year,
                                     end.day, MONTHS_SHORT[end.month - 1], end.year)


def presets(today=None):
    t = today or date.today()
    first = t.replace(day=1)
    last_month_end = first - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return [('Hari ini', t, t), ('Kemarin', t - timedelta(days=1), t - timedelta(days=1)),
            ('7 hari terakhir', t - timedelta(days=6), t), ('30 hari terakhir', t - timedelta(days=29), t),
            ('Bulan ini', first, t), ('Bulan lalu', last_month_start, last_month_end),
            ('Tahun ini', date(t.year, 1, 1), t)]


class _Popup(tk.Toplevel):
    """Panel mengambang tanpa bingkai; tertutup bila klik di luar atau Esc."""

    def __init__(self, anchor):
        super().__init__(anchor)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=LINE)
        self.inner = tk.Frame(self, bg=PANEL)
        self.inner.pack(fill='both', expand=True, padx=1, pady=1)
        self.anchor = anchor
        self.bind('<Escape>', lambda e: self.close())

    def show(self):
        self.update_idletasks()
        x = self.anchor.winfo_rootx()
        y = self.anchor.winfo_rooty() + self.anchor.winfo_height() + 6
        sw = self.winfo_screenwidth()
        w = self.winfo_reqwidth()
        if x + w > sw - 10:
            x = max(10, sw - w - 10)
        self.geometry('+%d+%d' % (x, y))
        self.deiconify()
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()
        self.bind('<ButtonPress-1>', self._outside, add='+')

    def _outside(self, event):
        x, y = event.x_root, event.y_root
        x1, y1 = self.winfo_rootx(), self.winfo_rooty()
        if not (x1 <= x <= x1 + self.winfo_width() and y1 <= y <= y1 + self.winfo_height()):
            self.close()

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class _Trigger(tk.Canvas):
    """Tombol bergaya kolom input dengan ikon kalender dan panah."""

    def __init__(self, parent, text_fn, on_click, width=230, height=36):
        self._bg = UI.bg_of(parent)
        super().__init__(parent, width=width, height=height, bg=self._bg, highlightthickness=0, bd=0, cursor='hand2')
        self.text_fn, self.on_click = text_fn, on_click
        self._h, self._hover = height, False
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self._set(True))
        self.bind('<Leave>', lambda e: self._set(False))
        self.bind('<ButtonRelease-1>', lambda e: self.on_click())
        self.draw()

    def _set(self, hover):
        self._hover = hover
        self.draw()

    def draw(self):
        self.delete('all')
        w = max(int(self.cget('width')), self.winfo_width())
        h = self._h
        rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, 8, CARD, PURPLE if self._hover else LINE)
        draw_icon(self, 'calendar', 11, (h - 16) / 2, 16, PURPLE)
        f = (FONT, 10, 'normal')
        text = self.text_fn()
        self.create_text(36, h / 2, text=text, anchor='w', fill=WHITE, font=f)
        draw_icon(self, 'chevron-down', w - 26, (h - 14) / 2, 14, DIM)

    def fit(self):
        w = text_width((FONT, 10, 'normal'), self.text_fn()) + 70
        self.configure(width=max(150, w))
        self.draw()


class PeriodButton(tk.Frame):
    """Pemilih rentang tanggal. start_var/end_var berisi teks YYYY-MM-DD."""

    def __init__(self, parent, start_var, end_var, on_change=None):
        super().__init__(parent, bg=UI.bg_of(parent))
        self.start_var, self.end_var, self.on_change = start_var, end_var, on_change
        self.trigger = _Trigger(self, self.label, self.open)
        self.trigger.pack()
        self.trigger.fit()
        for v in (start_var, end_var):
            v.trace_add('write', lambda *_: self.trigger.fit())

    def period(self):
        t = date.today()
        s = _parse(self.start_var.get(), t.replace(day=1))
        e = _parse(self.end_var.get(), t)
        return (s, e) if s <= e else (e, s)

    def label(self):
        s, e = self.period()
        name = next((n for n, ps, pe in presets() if ps == s and pe == e), None)
        if name is None and s.day == 1 and s.year == e.year and s.month == e.month and (
                e.day == calendar.monthrange(e.year, e.month)[1] or e == date.today()):
            name = '%s %d' % (MONTHS[s.month - 1], s.year)
        return (name + '  ·  ' if name else '') + format_period(s, e)

    def open(self):
        s, e = self.period()
        pop = _Popup(self.trigger)
        state = {'start': s, 'end': e, 'pick': None, 'month': date(e.year, e.month, 1), 'hover': None}
        body = tk.Frame(pop.inner, bg=PANEL)
        body.pack(fill='both', expand=True, padx=14, pady=14)
        left = tk.Frame(body, bg=PANEL)
        left.pack(side='left', fill='y', padx=(0, 14))
        tk.Label(left, text='PILIHAN CEPAT', bg=PANEL, fg=MUTED, font=(FONT, 8, 'bold')).pack(anchor='w', pady=(0, 6))
        tk.Frame(body, bg=LINE, width=1).pack(side='left', fill='y', padx=(0, 14))
        # Pilih per bulan (12 bulan terakhir): satu klik = satu bulan penuh.
        months_col = tk.Frame(body, bg=PANEL)
        months_col.pack(side='left', fill='y', padx=(0, 14))
        tk.Label(months_col, text='PER BULAN', bg=PANEL, fg=MUTED, font=(FONT, 8, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
        today = date.today()
        for k in range(12):
            idx = today.year * 12 + today.month - 1 - k
            y, m = idx // 12, idx % 12 + 1
            ms = date(y, m, 1)
            me = min(date(y, m, calendar.monthrange(y, m)[1]), today)
            active = (ms, me) == (s, e)
            UI.RoundButton(months_col, '%s %d' % (MONTHS_SHORT[m - 1], y), lambda ms=ms, me=me: apply(ms, me),
                           variant='subtle' if active else 'ghost', width=78, height=28, font_size=9,
                           bold=active).grid(row=1 + k // 2, column=k % 2, padx=1, pady=1)
        tk.Frame(body, bg=LINE, width=1).pack(side='left', fill='y', padx=(0, 14))
        right = tk.Frame(body, bg=PANEL)
        right.pack(side='left')
        summary = tk.StringVar()

        def apply(start, end):
            self.start_var.set(start.isoformat())
            self.end_var.set(end.isoformat())
            pop.close()
            if self.on_change:
                self.on_change()

        for name, ps, pe in presets():
            active = (ps, pe) == (s, e)
            UI.RoundButton(left, name, lambda ps=ps, pe=pe: apply(ps, pe), variant='subtle' if active else 'ghost',
                           width=150, height=30, font_size=9, bold=active).pack(anchor='w', pady=1)

        head = tk.Frame(right, bg=PANEL)
        head.pack(fill='x')
        title = tk.Label(head, bg=PANEL, fg=WHITE, font=(FONT, 11, 'bold'))
        UI.RoundButton(head, '', lambda: move(-1), icon='chevron-left', variant='ghost', height=28, padx=6).pack(side='left')
        title.pack(side='left', expand=True)
        UI.RoundButton(head, '', lambda: move(1), icon='chevron-right', variant='ghost', height=28, padx=6).pack(side='right')
        cell = 38
        cal = tk.Canvas(right, width=cell * 7, height=cell * 7 + 4, bg=PANEL, highlightthickness=0, cursor='hand2')
        cal.pack(pady=(8, 4))
        tk.Label(right, textvariable=summary, bg=PANEL, fg=DIM, font=(FONT, 9)).pack(anchor='w', pady=(4, 8))
        foot = tk.Frame(right, bg=PANEL)
        foot.pack(fill='x')
        UI.RoundButton(foot, 'Terapkan', lambda: apply(*ordered()), variant='primary', height=32).pack(side='right')
        UI.RoundButton(foot, 'Batal', pop.close, variant='ghost', height=32).pack(side='right', padx=6)

        def ordered():
            a, b = state['start'], state['end']
            if state['pick'] is not None:
                a = b = state['pick']
            return (a, b) if a <= b else (b, a)

        def move(delta):
            m = state['month']
            idx = m.year * 12 + m.month - 1 + delta
            state['month'] = date(idx // 12, idx % 12 + 1, 1)
            draw()

        def day_at(x, y):
            col, row = int(x // cell), int((y - 26) // cell)
            if y < 26 or not (0 <= col < 7 and 0 <= row < 6):
                return None
            weeks = calendar.Calendar().monthdayscalendar(state['month'].year, state['month'].month)
            if row >= len(weeks) or not weeks[row][col]:
                return None
            return date(state['month'].year, state['month'].month, weeks[row][col])

        def draw():
            cal.delete('all')
            m = state['month']
            title.configure(text='%s %d' % (MONTHS[m.month - 1], m.year))
            for i, d in enumerate(DAYS):
                cal.create_text(i * cell + cell / 2, 12, text=d, fill=MUTED, font=(FONT, 8, 'bold'))
            a, b = ordered()
            if state['pick'] is not None and state['hover'] is not None:
                a, b = sorted([state['pick'], state['hover']])
            today = date.today()
            weeks = calendar.Calendar().monthdayscalendar(m.year, m.month)
            for r, week in enumerate(weeks):
                for c, day in enumerate(week):
                    if not day:
                        continue
                    d = date(m.year, m.month, day)
                    x0, y0 = c * cell, 26 + r * cell
                    in_range = a <= d <= b
                    edge = d in (a, b)
                    if in_range and not edge:
                        cal.create_rectangle(x0, y0 + 4, x0 + cell, y0 + cell - 4, fill=mix(PANEL, PURPLE, 0.16), outline='')
                    if in_range and edge and a != b:
                        # sambungan halus antara ujung dan isi rentang
                        if d == a:
                            cal.create_rectangle(x0 + cell / 2, y0 + 4, x0 + cell, y0 + cell - 4, fill=mix(PANEL, PURPLE, 0.16), outline='')
                        else:
                            cal.create_rectangle(x0, y0 + 4, x0 + cell / 2, y0 + cell - 4, fill=mix(PANEL, PURPLE, 0.16), outline='')
                    if edge:
                        cal.create_oval(x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4, fill=PURPLE, outline='')
                    elif d == today:
                        cal.create_oval(x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4, outline=PURPLE, width=1)
                    future = d > today
                    color = '#ffffff' if edge else (MUTED if future else WHITE)
                    cal.create_text(x0 + cell / 2, y0 + cell / 2, text=str(day), fill=color,
                                    font=(FONT, 9, 'bold' if edge else 'normal'))
            if state['pick'] is not None:
                summary.set('Pilih tanggal akhir…')
            else:
                summary.set('Periode: ' + format_period(*ordered()))

        def click(event):
            d = day_at(event.x, event.y)
            if d is None:
                return
            if state['pick'] is None:
                state['pick'] = d
            else:
                state['start'], state['end'] = sorted([state['pick'], d])
                state['pick'] = None
            draw()

        def motion(event):
            if state['pick'] is None:
                return
            d = day_at(event.x, event.y)
            if d != state['hover']:
                state['hover'] = d
                draw()

        cal.bind('<ButtonRelease-1>', click)
        cal.bind('<Motion>', motion)
        draw()
        pop.show()


class MonthButton(tk.Frame):
    """Pemilih bulan. variable berisi YYYY-MM."""

    def __init__(self, parent, variable, on_change=None):
        super().__init__(parent, bg=UI.bg_of(parent))
        self.var, self.on_change = variable, on_change
        self.trigger = _Trigger(self, self.label, self.open, width=170)
        self.trigger.pack()
        self.trigger.fit()
        variable.trace_add('write', lambda *_: self.trigger.fit())

    def value(self):
        try:
            y, m = map(int, self.var.get().split('-'))
            return y, m
        except ValueError:
            t = date.today()
            return t.year, t.month

    def label(self):
        y, m = self.value()
        return '%s %d' % (MONTHS[m - 1], y)

    def open(self):
        y, m = self.value()
        pop = _Popup(self.trigger)
        state = {'year': y}
        body = tk.Frame(pop.inner, bg=PANEL)
        body.pack(padx=14, pady=14)
        head = tk.Frame(body, bg=PANEL)
        head.pack(fill='x', pady=(0, 8))
        title = tk.Label(head, bg=PANEL, fg=WHITE, font=(FONT, 11, 'bold'))
        UI.RoundButton(head, '', lambda: move(-1), icon='chevron-left', variant='ghost', height=28, padx=6).pack(side='left')
        title.pack(side='left', expand=True)
        UI.RoundButton(head, '', lambda: move(1), icon='chevron-right', variant='ghost', height=28, padx=6).pack(side='right')
        grid = tk.Frame(body, bg=PANEL)
        grid.pack()

        def choose(month):
            self.var.set('%04d-%02d' % (state['year'], month))
            pop.close()
            if self.on_change:
                self.on_change()

        def draw():
            for c in grid.winfo_children():
                c.destroy()
            title.configure(text=str(state['year']))
            for i in range(12):
                active = (state['year'], i + 1) == (y, m)
                UI.RoundButton(grid, MONTHS_SHORT[i], lambda k=i + 1: choose(k),
                               variant='primary' if active else 'ghost', width=64, height=34,
                               font_size=10).grid(row=i // 4, column=i % 4, padx=2, pady=2)

        def move(delta):
            state['year'] += delta
            draw()

        draw()
        pop.show()
