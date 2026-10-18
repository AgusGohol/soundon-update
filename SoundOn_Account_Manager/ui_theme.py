"""Komponen tampilan bersama SoundOn Account Manager (Tkinter murni).

Berisi palet warna, tipografi, ikon vektor yang digambar di Canvas (tidak
bergantung pada glyph font Windows), tombol bulat, avatar, kartu, dan gaya ttk.
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- palet & tema
import json as _json
import os as _os

SETTINGS_FILE = _os.path.join(_os.path.expanduser('~'), 'SoundOnAccounts', 'ui_settings.json')


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes):
    data = load_settings()
    data.update(changes)
    _os.makedirs(_os.path.dirname(SETTINGS_FILE), exist_ok=True)
    tmp = SETTINGS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        _json.dump(data, f, indent=2)
    _os.replace(tmp, SETTINGS_FILE)


PALETTES = {
    'dark': dict(BG='#0b1220', SIDE='#09101c', PANEL='#111c2e', CARD='#172439', CARD_HI='#1d2d46',
                 LINE='#24364f', WHITE='#eef3fb', DIM='#93a4bd', MUTED='#6b7c95', PURPLE='#7357ff',
                 GREEN='#22c993', RED='#f25f7a', BLUE='#3d9bff', AMBER='#f2b544'),
    'light': dict(BG='#eef1f7', SIDE='#ffffff', PANEL='#ffffff', CARD='#f5f7fb', CARD_HI='#eaeef5',
                  LINE='#dfe4ee', WHITE='#18213a', DIM='#56647b', MUTED='#8692a6', PURPLE='#6a4df5',
                  GREEN='#109c74', RED='#dc4560', BLUE='#2b80ea', AMBER='#c98a12'),
}
THEME = 'light' if load_settings().get('theme') == 'light' else 'dark'
_P = PALETTES[THEME]
BG, SIDE, PANEL, CARD, CARD_HI, LINE = _P['BG'], _P['SIDE'], _P['PANEL'], _P['CARD'], _P['CARD_HI'], _P['LINE']
WHITE, DIM, MUTED = _P['WHITE'], _P['DIM'], _P['MUTED']   # WHITE = warna teks utama
PURPLE, GREEN, RED, BLUE, AMBER = _P['PURPLE'], _P['GREEN'], _P['RED'], _P['BLUE'], _P['AMBER']
# Arah "angkat" permukaan (hover/tombol) dan warna untuk mempertegas teks aksen.
INK = '#ffffff' if THEME == 'dark' else '#0b1220'
TINT = '#ffffff' if THEME == 'dark' else '#000000'

FONT = 'Segoe UI'
FONT_SEMI = 'Segoe UI Semibold'


def mix(a, b, t):
    a = a.lstrip('#'); b = b.lstrip('#')
    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg_, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return '#%02x%02x%02x' % (round(ar + (br - ar) * t), round(ag + (bg_ - ag) * t), round(ab + (bb - ab) * t))


def bg_of(widget):
    try:
        return widget.cget('bg')
    except tk.TclError:
        try:
            return ttk.Style().lookup(widget.winfo_class(), 'background') or BG
        except tk.TclError:
            return BG


_font_cache = {}


def font_obj(spec):
    f = _font_cache.get(spec)
    if f is None:
        f = tkfont.Font(family=spec[0], size=spec[1], weight='bold' if 'bold' in spec[2:] else 'normal')
        _font_cache[spec] = f
    return f


_width_cache = {}


def text_width(spec, text):
    key = (spec, text)
    w = _width_cache.get(key)
    if w is None:
        if len(_width_cache) > 20000:
            _width_cache.clear()
        w = _width_cache[key] = font_obj(spec).measure(text)
    return w


# ---------------------------------------------------------------- bentuk
def rounded_points(x1, y1, x2, y2, r):
    # Spline Tk memakai titik tengah sebagai ujung kurva, jadi radius titik kontrol
    # digandakan agar sudut tampak sebesar r.
    r = max(0, min(r * 2, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def rounded_rect(canvas, x1, y1, x2, y2, r, fill, outline=''):
    return canvas.create_polygon(rounded_points(x1, y1, x2, y2, r), smooth=True, splinesteps=12,
                                 fill=fill, outline=outline or fill)


# ---------------------------------------------------------------- ikon vektor
def draw_icon(c, name, x, y, size=16, color=WHITE, width=None, tag=None):
    """Gambar ikon garis pada canvas c, kotak kiri-atas (x,y), ukuran size."""
    s = size / 24.0
    w = width or max(1.4, size / 10.0)
    kw = dict(fill=color, width=w, capstyle='round', joinstyle='round', tags=tag)

    def P(*pts):
        return [v * s + (x if i % 2 == 0 else y) for i, v in enumerate(pts)]

    def line(*pts, **extra):
        opts = dict(kw); opts.update(extra)
        c.create_line(*P(*pts), **opts)

    def oval(x1, y1, x2, y2, fill=''):
        c.create_oval(*P(x1, y1, x2, y2), outline=color, width=w, fill=fill, tags=tag)

    def arc(x1, y1, x2, y2, start, extent):
        c.create_arc(*P(x1, y1, x2, y2), start=start, extent=extent, style='arc', outline=color, width=w, tags=tag)

    def rect(x1, y1, x2, y2, r=3):
        c.create_line(*rounded_points(*P(x1, y1, x2, y2), r * s), smooth=True, splinesteps=8, **kw)

    def dot(cx, cy, r=1.6, fill=None):
        c.create_oval(*P(cx - r, cy - r, cx + r, cy + r), fill=fill or color, outline='', tags=tag)

    n = name
    if n == 'home':
        line(3, 11, 12, 3.5, 21, 11); line(5.5, 9.5, 5.5, 20, 18.5, 20, 18.5, 9.5); line(10, 20, 10, 14, 14, 14, 14, 20)
    elif n == 'users':
        oval(5, 4, 13, 12); arc(1.5, 13.5, 16.5, 28.5, 20, 140)
        arc(13, 5, 19, 11, 270, 200); arc(14, 14, 23, 26, 20, 110)
    elif n == 'user':
        oval(8, 3.5, 16, 11.5); arc(4, 13.5, 20, 29.5, 20, 140)
    elif n == 'chart':
        line(4, 20, 20, 20); line(7, 16, 7, 12); line(11.5, 16, 11.5, 6); line(16, 16, 16, 9.5)
    elif n == 'wallet':
        rect(3, 6, 21, 19, 3); line(3, 9.5, 21, 9.5); line(15, 14.5, 17.5, 14.5)
    elif n == 'phone':
        rect(7, 2.5, 17, 21.5, 2.5); line(10.5, 18.5, 13.5, 18.5)
    elif n == 'gear':
        oval(9, 9, 15, 15)
        import math
        for k in range(8):
            a = k * math.pi / 4
            line(12 + 6.2 * math.cos(a), 12 + 6.2 * math.sin(a), 12 + 9 * math.cos(a), 12 + 9 * math.sin(a))
        oval(5.8, 5.8, 18.2, 18.2)
    elif n == 'music':
        line(9, 18, 9, 5, 19, 3, 19, 16); oval(4, 15.5, 9.5, 20.5, fill=color); oval(13.5, 13.5, 19, 18.5, fill=color)
    elif n == 'refresh':
        arc(4, 4, 20, 20, 30, 270); line(19.5, 3.8, 19.5, 8.6, 14.7, 8.6)
    elif n == 'plus':
        line(12, 5, 12, 19); line(5, 12, 19, 12)
    elif n == 'import':
        line(12, 3.5, 12, 15); line(7.5, 10.5, 12, 15, 16.5, 10.5); line(4, 16.5, 4, 20, 20, 20, 20, 16.5)
    elif n == 'export':
        line(12, 15, 12, 3.5); line(7.5, 8, 12, 3.5, 16.5, 8); line(4, 16.5, 4, 20, 20, 20, 20, 16.5)
    elif n == 'external':
        line(13.5, 4, 20, 4, 20, 10.5); line(20, 4, 11, 13); line(17, 13.5, 17, 20, 4, 20, 4, 7, 10.5, 7)
    elif n == 'calendar':
        rect(3.5, 5, 20.5, 20.5, 3); line(3.5, 10, 20.5, 10); line(8, 3, 8, 7); line(16, 3, 16, 7)
    elif n == 'filter':
        line(4, 5, 20, 5, 14, 12.5, 14, 19, 10, 21, 10, 12.5, 4, 5)
    elif n == 'check':
        line(4.5, 12.5, 9.5, 17.5, 19.5, 6.5)
    elif n == 'edit':
        line(4, 20, 4, 16, 15.5, 4.5, 19.5, 8.5, 8, 20, 4, 20); line(13, 7, 17, 11)
    elif n == 'play':
        c.create_polygon(*P(7, 4.5, 19.5, 12, 7, 19.5), fill=color, outline=color, width=1, joinstyle='round', tags=tag)
    elif n == 'stop':
        c.create_polygon(rounded_points(*P(6, 6, 18, 18), 2.5 * s), smooth=True, fill=color, outline=color, tags=tag)
    elif n == 'more':
        dot(6, 12, 1.9); dot(12, 12, 1.9); dot(18, 12, 1.9)
    elif n == 'search':
        oval(4, 4, 16, 16); line(14.5, 14.5, 20, 20)
    elif n == 'info':
        oval(3, 3, 21, 21); line(12, 11, 12, 16.5); dot(12, 7.7, 1.3)
    elif n == 'alert':
        line(12, 3.5, 21, 19.5, 3, 19.5, 12, 3.5); line(12, 9.5, 12, 13.5); dot(12, 16.5, 1.2)
    elif n == 'wave':
        line(3, 12, 5, 12); line(7, 8, 7, 16); line(11, 4, 11, 20); line(15, 7.5, 15, 16.5); line(19, 10, 19, 14); line(21, 12, 21.5, 12)
    elif n == 'headphones':
        arc(4, 4, 20, 22, 0, 180); rect(3.5, 13, 8, 20, 2); rect(16, 13, 20.5, 20, 2)
    elif n == 'hash':
        line(9, 4, 7.5, 20); line(16.5, 4, 15, 20); line(4.5, 9, 20, 9); line(4, 15, 19.5, 15)
    elif n == 'wrench':
        line(14, 6, 18, 2.8); oval(10.5, 3.5, 20.5, 13.5); line(12.5, 11.5, 4.5, 19.5)
    elif n == 'circle':
        oval(5, 5, 19, 19)
    elif n == 'trash':
        line(4, 6.5, 20, 6.5); line(9, 6.5, 9.5, 3.5, 14.5, 3.5, 15, 6.5); line(6, 6.5, 7, 20.5, 17, 20.5, 18, 6.5)
    elif n == 'chevron-down':
        line(6.5, 9.5, 12, 15, 17.5, 9.5)
    elif n == 'chevron-left':
        line(14.5, 6, 8.5, 12, 14.5, 18)
    elif n == 'chevron-right':
        line(9.5, 6, 15.5, 12, 9.5, 18)
    elif n == 'cloud':
        arc(3, 10, 11, 18, 90, 180); arc(6, 4, 17, 15, 20, 160); arc(13, 8.5, 21, 18, 270, 180)
        line(7, 18, 17, 18); line(12, 11, 12, 16.5); line(9.8, 13.2, 12, 11, 14.2, 13.2)
    elif n == 'key':
        oval(3, 9, 11, 17); line(11, 13, 21, 13); line(17, 13, 17, 16.5); line(20, 13, 20, 15.5)
    elif n == 'database':
        oval(5, 3, 19, 8); line(5, 5.5, 5, 18.5); line(19, 5.5, 19, 18.5); arc(5, 9, 19, 14, 180, 180); arc(5, 16, 19, 21, 180, 180)
    elif n == 'folder':
        line(3, 6, 3, 19, 21, 19, 21, 8.5, 11.5, 8.5, 9.5, 5.5, 3, 5.5, 3, 6)
    elif n == 'tag':
        line(3.5, 3.5, 11.5, 3.5, 20.5, 12.5, 12.5, 20.5, 3.5, 11.5, 3.5, 3.5); dot(8, 8, 1.4)
    elif n == 'globe':
        oval(3, 3, 21, 21); line(3, 12, 21, 12); arc(8, 3, 16, 21, 90, 180); arc(8, 3, 16, 21, 270, 180)
    elif n == 'flag':
        line(5, 21, 5, 3.5); line(5, 4, 18.5, 4, 15.5, 8.5, 18.5, 13, 5, 13)
    elif n == 'pulse':
        line(3, 12, 7.5, 12, 10, 6, 14, 18, 16.5, 12, 21, 12)
    elif n == 'grid':
        rect(4, 4, 11, 11, 2); rect(13, 4, 20, 11, 2); rect(4, 13, 11, 20, 2); rect(13, 13, 20, 20, 2)
    elif n == 'sync':
        arc(4, 4, 20, 20, 40, 140); line(5.2, 6.2, 5.2, 10.4, 9.4, 10.4)
        arc(4, 4, 20, 20, 220, 140); line(18.8, 17.8, 18.8, 13.6, 14.6, 13.6)
    elif n == 'sun':
        oval(8, 8, 16, 16)
        import math
        for k in range(8):
            a = k * math.pi / 4
            line(12 + 6.5 * math.cos(a), 12 + 6.5 * math.sin(a), 12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a))
    elif n == 'moon':
        arc(4, 4, 20, 20, 300, 260); arc(9, 2, 23, 16, 205, 130)
    elif n == 'box':
        rect(4, 4, 20, 20, 3)
    elif n == 'box-check':
        c.create_polygon(rounded_points(*P(4, 4, 20, 20), 3 * s), smooth=True, fill=color, outline=color, tags=tag)
    elif n == 'x':
        line(6, 6, 18, 18); line(18, 6, 6, 18)
    elif n == 'logout':
        line(10, 4, 4, 4, 4, 20, 10, 20); line(9, 12, 20, 12); line(16, 8, 20, 12, 16, 16)
    else:
        dot(12, 12, 3)


# Glyph lama -> ikon vektor (dipakai otomatis oleh RoundButton).
GLYPH_ICONS = {
    '⟳': 'refresh', '↻': 'refresh', '⚑': 'filter', '＋': 'plus', '+': 'plus', '↗': 'external',
    '✓': 'check', '✎': 'edit', '▶': 'play', '■': 'stop', '⋯': 'more', '♫': 'music', '♪': 'music',
    '▦': 'calendar', 'ℹ': 'info', '▣': 'phone', '⚙': 'gear', '⌂': 'home', '♚': 'users', '▥': 'chart',
    '▯': 'phone', '≋': 'wave', '♙': 'user', '#': 'hash', '⚒': 'wrench', '!': 'alert', '○': 'circle',
    '●': 'flag', '◎': 'globe', '↓': 'import', '↑': 'export', '◉': 'pulse',
}


def split_glyph(text):
    text = text or ''
    stripped = text.lstrip()
    if stripped and stripped[0] in GLYPH_ICONS and (len(stripped) == 1 or stripped[1] == ' '):
        icon = GLYPH_ICONS[stripped[0]]
        rest = stripped[1:].strip()
        if icon == 'import' and rest.lower().startswith('ekspor'):
            icon = 'export'
        return icon, rest
    return None, text


# ---------------------------------------------------------------- tombol
class RoundButton(tk.Canvas):
    """Tombol sudut membulat dengan ikon vektor opsional.

    variant: primary | secondary | ghost | danger | subtle
    Kompatibel dengan pemanggilan lama (fg_color=PURPLE -> primary).
    """

    def __init__(self, parent, text, command, bg_color=None, fg_color=None, hover_color=None,
                 font_size=10, bold=True, padx=14, height=34, radius=9, icon=None, variant=None,
                 text_color=None, width=None, icon_only=False, **kw):
        self._bg = bg_color or bg_of(parent)
        glyph_icon, text = split_glyph(text)
        icon = icon or glyph_icon
        if variant is None:
            if fg_color == PURPLE:
                variant = 'primary'
            elif fg_color in (None, CARD, PANEL, SIDE, CARD_HI):
                variant = 'secondary'
            else:
                variant = 'custom'
        self.variant = variant
        if variant == 'primary':
            fill, hover, fgc, outline = PURPLE, mix(PURPLE, '#ffffff', 0.12), '#ffffff', ''
        elif variant == 'danger':
            fill, hover, fgc, outline = mix(self._bg, RED, 0.16), mix(self._bg, RED, 0.28), mix(RED, TINT, 0.25), ''
        elif variant == 'ghost':
            fill, hover, fgc, outline = self._bg, mix(self._bg, INK, 0.07), DIM, ''
        elif variant == 'subtle':
            fill, hover, fgc, outline = mix(self._bg, PURPLE, 0.16), mix(self._bg, PURPLE, 0.26), mix(PURPLE, TINT, 0.55 if THEME == 'dark' else 0.2), ''
        elif variant == 'custom':
            fill, hover, fgc, outline = fg_color, hover_color or mix(fg_color, '#ffffff', 0.12), '#ffffff', ''
        else:  # secondary
            fill = mix(self._bg, INK, 0.055 if THEME == 'dark' else 0.04)
            hover = mix(self._bg, INK, 0.11 if THEME == 'dark' else 0.08)
            fgc, outline = WHITE, mix(self._bg, INK, 0.13)
        if hover_color and variant != 'custom':
            hover = hover_color
        self._fill, self._hover, self._outline = fill, hover, outline
        self._fg = text_color or fgc
        self._hover_fg = WHITE if variant == 'ghost' else self._fg
        self._cmd = command
        self._text = text
        weight = 'bold' if (bold and variant in ('primary', 'custom')) else 'normal'
        family = FONT if weight == 'bold' else (FONT_SEMI if bold else FONT)
        self._font = (family, font_size, weight)
        isz = max(12, round(font_size * 1.55))
        gap = 7 if (icon and text) else 0
        tw = text_width(self._font, text) if text else 0
        content = (isz if icon else 0) + gap + tw
        w = width or max(height if (icon_only or not text) else 34, int(content + padx * 2))
        super().__init__(parent, width=w, height=height, bg=self._bg, bd=0, highlightthickness=0,
                         cursor='hand2', **kw)
        self._icon, self._isz, self._gap, self._content = icon, isz, gap, content
        self._radius, self._bh, self._bw = radius, height, w
        self._render(w)
        self.bind('<ButtonRelease-1>', self._click)
        self.bind('<Enter>', lambda e: self._paint(True))
        self.bind('<Leave>', lambda e: self._paint(False))
        self.bind('<Configure>', self._resized)

    def _resized(self, event):
        if event.width > 1 and abs(event.width - self._bw) > 1:
            self._render(event.width)

    def _render(self, w):
        self._bw = w
        self.delete('all')
        h = self._bh
        self._rect = rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, self._radius, self._fill, self._outline)
        x = (w - self._content) / 2
        if self._icon:
            draw_icon(self, self._icon, x, (h - self._isz) / 2, self._isz, self._fg, tag='fg')
            x += self._isz + self._gap
        if self._text:
            self.create_text(x, h / 2, text=self._text, anchor='w', fill=self._fg, font=self._font, tags='fg')

    def _click(self, event):
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height() and self._cmd:
            self._cmd()

    def _paint(self, hover):
        self.itemconfigure(self._rect, fill=self._hover if hover else self._fill,
                           outline=(self._outline or (self._hover if hover else self._fill)))
        if self._hover_fg != self._fg:
            for item in self.find_withtag('fg'):
                kind = self.type(item)
                opt = 'fill'
                if kind in ('oval', 'arc'):
                    opt = 'outline'
                self.itemconfigure(item, **{opt: self._hover_fg if hover else self._fg})

    def set_colors(self, fill, hover):
        self._fill, self._hover = fill, hover
        self._paint(False)


def menu_button(parent, text, items, icon=None, variant='secondary', **kw):
    """Tombol yang membuka menu tarik-turun. items: [(label, fungsi) | None]."""
    holder = {}

    def popup():
        if holder.get('menu') is not None:
            try:
                holder['menu'].destroy()
            except tk.TclError:
                pass
        m = tk.Menu(parent, tearoff=False)
        holder['menu'] = m
        for item in items:
            if item is None:
                m.add_separator()
            else:
                m.add_command(label=item[0], command=item[1])
        b = holder['b']
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 2)
    b = RoundButton(parent, text + '  ▾' if text else '▾', popup, icon=icon, variant=variant, **kw)
    holder['b'] = b
    return b


# ---------------------------------------------------------------- avatar & lencana
ACCENTS = [PURPLE, BLUE, GREEN, RED, AMBER]


def avatar(parent, text, color=PURPLE, size=40, bg=None, font_size=None):
    bg = bg or bg_of(parent)
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
    soft = mix(bg, color, 0.24)
    c.create_oval(1, 1, size - 1, size - 1, fill=soft, outline=mix(bg, color, 0.45))
    c.create_text(size / 2, size / 2, text=(text or '?')[:1].upper(), fill=mix(color, TINT, 0.35 if THEME == 'dark' else 0.15),
                  font=(FONT, font_size or max(9, int(size * 0.36)), 'bold'))
    return c


def icon_badge(parent, icon, accent=PURPLE, bg=None, size=40):
    """Lingkaran lembut berwarna dengan ikon vektor. icon boleh glyph lama."""
    if icon in GLYPH_ICONS:
        icon = GLYPH_ICONS[icon]
    bg = bg or bg_of(parent)
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
    rounded_rect(c, 0.5, 0.5, size - 0.5, size - 0.5, size * 0.3, mix(bg, accent, 0.18))
    isz = size * 0.5
    draw_icon(c, icon, (size - isz) / 2, (size - isz) / 2, isz, mix(accent, TINT, 0.15))
    return c


def icon(parent, name, size=16, color=DIM, bg=None):
    bg = bg or bg_of(parent)
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
    draw_icon(c, name, 0, 0, size, color)
    return c


def pill(parent, text, color=GREEN, bg=None, font_size=9):
    """Label status kecil berbentuk kapsul dengan titik warna."""
    bg = bg or bg_of(parent)
    f = (FONT, font_size, 'normal')
    tw = text_width(f, text)
    h = font_size * 2 + 6
    w = tw + 30
    c = tk.Canvas(parent, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
    rounded_rect(c, 0.5, 0.5, w - 0.5, h - 0.5, h / 2, mix(bg, color, 0.14))
    c.create_oval(10, h / 2 - 3, 16, h / 2 + 3, fill=color, outline='')
    c.create_text(21, h / 2, text=text, anchor='w', fill=mix(color, TINT, 0.3 if THEME == 'dark' else 0.25), font=f)
    return c


# ---------------------------------------------------------------- kartu
class RoundedPanel(tk.Frame):
    def __init__(self, parent, radius=14, outer=None, color=None, **kwargs):
        self._outer = outer or bg_of(parent)
        self._color = color or PANEL
        super().__init__(parent, bg=self._color, highlightthickness=0, bd=0, **kwargs)
        self._radius = radius
        self.bind('<Configure>', self._corners)

    def _corners(self, event=None):
        r = self._radius
        w = self.winfo_width(); h = self.winfo_height()
        if w < r * 2 or h < r * 2:
            return
        if not hasattr(self, '_corner_widgets'):
            self._corner_widgets = []
            for ox, oy in [(0, 0), (-r, 0), (0, -r), (-r, -r)]:
                c = tk.Canvas(self, width=r, height=r, bg=self._outer, highlightthickness=0, bd=0)
                c.create_oval(ox, oy, ox + 2 * r, oy + 2 * r, fill=self._color, outline=self._color)
                self._corner_widgets.append(c)
        for c, (x, y) in zip(self._corner_widgets, [(0, 0), (w - r, 0), (0, h - r), (w - r, h - r)]):
            c.place(x=x, y=y)


class NavItem(tk.Canvas):
    """Item navigasi sidebar: ikon + teks, latar & penanda saat aktif."""

    def __init__(self, parent, text, icon_name, command, height=42):
        super().__init__(parent, height=height, bg=SIDE, highlightthickness=0, bd=0, cursor='hand2')
        self._text, self._icon, self._cmd = text, icon_name, command
        self.active = False
        self._hover = False
        self.bind('<Configure>', lambda e: self._draw())
        self.bind('<ButtonRelease-1>', lambda e: self._cmd())
        self.bind('<Enter>', lambda e: self._set_hover(True))
        self.bind('<Leave>', lambda e: self._set_hover(False))

    def _set_hover(self, value):
        self._hover = value; self._draw()

    def set_active(self, value):
        self.active = value; self._draw()

    def _draw(self):
        self.delete('all')
        w = self.winfo_width(); h = int(self.cget('height'))
        if w <= 1:
            return
        if self.active:
            rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, 10, mix(SIDE, PURPLE, 0.22 if THEME == 'dark' else 0.12))
            rounded_rect(self, 0, h * 0.28, 3.5, h * 0.72, 2, PURPLE)
        elif self._hover:
            rounded_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, 10, mix(SIDE, INK, 0.05))
        color = WHITE if self.active else (WHITE if self._hover else DIM)
        draw_icon(self, self._icon, 16, (h - 18) / 2, 18, mix(PURPLE, TINT, 0.35 if THEME == 'dark' else 0.1) if self.active else color)
        self.create_text(46, h / 2, text=self._text, anchor='w', fill=color,
                         font=(FONT_SEMI if self.active else FONT, 10, 'normal'))


# ---------------------------------------------------------------- ttk & opsi
def setup_styles(root):
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    field = CARD
    style.configure('Dark.TCombobox', fieldbackground=field, background=field, foreground=WHITE,
                    arrowcolor=DIM, bordercolor=LINE, lightcolor=field, darkcolor=field,
                    selectbackground=field, selectforeground=WHITE, padding=(10, 7), arrowsize=14)
    style.map('Dark.TCombobox', fieldbackground=[('readonly', field), ('focus', field)],
              foreground=[('readonly', WHITE)], selectbackground=[('readonly', field)],
              selectforeground=[('readonly', WHITE)], bordercolor=[('focus', PURPLE), ('hover', mix(LINE, INK, 0.12))],
              background=[('active', CARD_HI), ('pressed', CARD_HI)], arrowcolor=[('hover', WHITE)])
    for orient in ('Vertical', 'Horizontal'):
        name = 'Dark.%s.TScrollbar' % orient
        style.configure(name, background=CARD_HI, troughcolor=PANEL, bordercolor=PANEL, lightcolor=CARD_HI,
                        darkcolor=CARD_HI, arrowcolor=DIM, gripcount=0, arrowsize=11, relief='flat')
        style.map(name, background=[('active', mix(CARD_HI, INK, 0.12)), ('pressed', PURPLE)])
    # Tabel gelap (Treeview)
    style.configure('Dark.Treeview', background=PANEL, fieldbackground=PANEL, foreground=WHITE,
                    bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, rowheight=36, font=(FONT, 10), borderwidth=0)
    style.map('Dark.Treeview', background=[('selected', mix(PANEL, PURPLE, 0.35))], foreground=[('selected', WHITE)])
    style.configure('Dark.Treeview.Heading', background=CARD_HI, foreground=DIM, bordercolor=CARD_HI,
                    lightcolor=CARD_HI, darkcolor=CARD_HI, relief='flat', font=(FONT, 9, 'bold'), padding=(10, 9))
    style.map('Dark.Treeview.Heading', background=[('active', mix(CARD_HI, INK, 0.06))])
    style.layout('Dark.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    # Formulir gelap (dipakai editor lagu)
    style.configure('Dark.TFrame', background=PANEL)
    style.configure('Dark.TLabel', background=PANEL, foreground=WHITE, font=(FONT, 10))
    style.configure('Dark.Muted.TLabel', background=PANEL, foreground=DIM, font=(FONT, 9))
    style.configure('Dark.TEntry', fieldbackground=CARD, foreground=WHITE, insertcolor=WHITE, bordercolor=LINE,
                    lightcolor=CARD, darkcolor=CARD, padding=(9, 7))
    style.map('Dark.TEntry', bordercolor=[('focus', PURPLE)])
    style.configure('Dark.TNotebook', background=PANEL, borderwidth=1, tabmargins=(0, 0, 0, 0),
                    bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL)
    style.configure('Dark.TNotebook.Tab', background=PANEL, foreground=DIM, padding=(18, 9), borderwidth=1,
                    font=(FONT, 10), lightcolor=PANEL, darkcolor=PANEL, bordercolor=LINE)
    style.map('Dark.TNotebook.Tab', background=[('selected', CARD)], foreground=[('selected', WHITE)],
              lightcolor=[('selected', CARD)], bordercolor=[('selected', LINE)], expand=[('selected', (0, 0, 0, 0))])
    style.configure('Dark.TButton', background=CARD_HI, foreground=WHITE, bordercolor=LINE, lightcolor=CARD_HI,
                    darkcolor=CARD_HI, padding=(12, 7), font=(FONT, 10), focuscolor=CARD_HI)
    style.map('Dark.TButton', background=[('active', mix(CARD_HI, INK, 0.08))])
    style.configure('Dark.TCheckbutton', background=PANEL, foreground=WHITE, indicatorbackground=CARD,
                    indicatorforeground=WHITE, font=(FONT, 10))
    # Opsi untuk widget tk klasik
    root.option_add('*TCombobox*Listbox.background', CARD)
    root.option_add('*TCombobox*Listbox.foreground', WHITE)
    root.option_add('*TCombobox*Listbox.selectBackground', PURPLE)
    root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
    root.option_add('*TCombobox*Listbox.font', (FONT, 10))
    root.option_add('*TCombobox*Listbox.relief', 'flat')
    root.option_add('*Entry.highlightThickness', 1)
    root.option_add('*Entry.highlightBackground', LINE)
    root.option_add('*Entry.highlightColor', PURPLE)
    root.option_add('*Entry.disabledBackground', CARD)
    root.option_add('*Text.highlightThickness', 1)
    root.option_add('*Text.highlightBackground', LINE)
    root.option_add('*Text.highlightColor', PURPLE)
    root.option_add('*Text.relief', 'flat')
    root.option_add('*Menu.background', CARD)
    root.option_add('*Menu.foreground', WHITE)
    root.option_add('*Menu.activeBackground', PURPLE)
    root.option_add('*Menu.activeForeground', '#ffffff')
    root.option_add('*Menu.relief', 'flat')
    root.option_add('*Menu.borderWidth', 1)
    root.option_add('*Menu.font', (FONT, 10))
    root.option_add('*Checkbutton.selectColor', CARD)
    root.option_add('*Checkbutton.activeBackground', PANEL)
    root.option_add('*Checkbutton.activeForeground', WHITE)
    root.option_add('*Checkbutton.highlightThickness', 0)
    return style


def styled_entry(parent, var, width=20, font_size=10, **kw):
    return tk.Entry(parent, textvariable=var, width=width, bg=CARD, fg=WHITE, insertbackground=WHITE,
                    relief='flat', font=(FONT, font_size), highlightthickness=1, highlightbackground=LINE,
                    highlightcolor=PURPLE, **kw)


def search_entry(parent, var, placeholder='Cari…', width=24):
    """Kolom cari dengan ikon dan teks petunjuk."""
    box = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE, highlightcolor=PURPLE)
    icon(box, 'search', 15, MUTED, CARD).pack(side='left', padx=(10, 4))
    e = tk.Entry(box, textvariable=var, width=width, bg=CARD, fg=WHITE, insertbackground=WHITE, relief='flat',
                 bd=0, font=(FONT, 10), highlightthickness=0)
    e.pack(side='left', ipady=8, padx=(2, 10))
    hint = tk.Label(box, text=placeholder, bg=CARD, fg=MUTED, font=(FONT, 10))

    def sync(*_):
        if var.get() or box.focus_get() is e:
            hint.place_forget()
        else:
            hint.place(in_=e, x=1, rely=0.5, anchor='w')
    e.bind('<FocusIn>', sync); e.bind('<FocusOut>', sync); var.trace_add('write', sync)
    hint.bind('<Button-1>', lambda ev: e.focus_set())
    box.after(50, sync)
    return box


def dark_checkbutton(parent, text, variable, bg=None, **kw):
    bg = bg or bg_of(parent)
    return tk.Checkbutton(parent, text=text, variable=variable, bg=bg, fg=WHITE, selectcolor=CARD,
                          activebackground=bg, activeforeground=WHITE, highlightthickness=0, bd=0,
                          font=(FONT, 10), cursor='hand2', **kw)


# ---------------------------------------------------------------- gulir (scroll)
class WheelScroller:
    """Satu pengendali roda mouse/touchpad untuk seluruh aplikasi.

    - Menggulir area yang ada di bawah kursor (kanvas terdekat yang bisa digulir),
      termasuk di jendela dialog.
    - Jarak gulir dalam piksel (tidak bergantung panjang halaman), halus, dan
      mendukung touchpad (delta kecil) maupun mouse (kelipatan 120).
    - Text/Listbox/Treeview yang bisa digulir memakai gulir bawaannya.
    - Roda mouse tidak lagi mengganti pilihan Combobox secara tidak sengaja.
    """
    STEP = 90          # piksel per satu klik roda
    FRAME_MS = 16

    def __init__(self, root, fallback=None):
        self.root = root
        self.fallback = fallback
        self.state = {}
        for cls in ('TCombobox', 'TSpinbox'):
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                try:
                    root.unbind_class(cls, seq)
                except tk.TclError:
                    pass
        root.bind_all('<MouseWheel>', self.on_wheel)
        root.bind_all('<Shift-MouseWheel>', lambda e: None)
        root.bind_all('<Button-4>', self.on_wheel)
        root.bind_all('<Button-5>', self.on_wheel)

    @staticmethod
    def _content_height(canvas):
        region = canvas.cget('scrollregion')
        try:
            y1, y2 = float(region.split()[1]), float(region.split()[3])
            return max(0.0, y2 - y1)
        except (IndexError, ValueError):
            box = canvas.bbox('all')
            return float(box[3] - box[1]) if box else 0.0

    def _scrollable(self, canvas):
        try:
            return self._content_height(canvas) > canvas.winfo_height() + 1
        except tk.TclError:
            return False

    def _find(self, widget):
        w = widget
        while w is not None:
            if isinstance(w, (tk.Text, tk.Listbox, ttk.Treeview)):
                try:
                    first, last = w.yview()
                    if first > 0.0 or last < 1.0:
                        return 'native'
                except tk.TclError:
                    pass
            if isinstance(w, tk.Canvas) and str(w.cget('yscrollcommand')) and self._scrollable(w):
                return w
            if isinstance(w, tk.Toplevel):
                return None
            w = getattr(w, 'master', None)
        return 'fallback'

    def on_wheel(self, event):
        try:
            hovered = self.root.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError):
            hovered = None
        if hovered is None:
            return
        target = self._find(hovered)
        if target == 'native':
            return
        if target == 'fallback':
            target = self.fallback() if self.fallback else None
            if target is None or not self._scrollable(target):
                return 'break'
        if target is None:
            return 'break'
        if event.num == 4:
            delta = 120
        elif event.num == 5:
            delta = -120
        else:
            delta = event.delta
            if abs(delta) < 1:
                return 'break'
            if abs(delta) < 120 and abs(delta) >= 1 and self.root.tk.call('tk', 'windowingsystem') == 'aqua':
                delta *= 30  # macOS mengirim delta kecil
        self.scroll(target, -delta / 120.0 * self.STEP)
        return 'break'

    def scroll(self, canvas, pixels):
        """Gulir langsung (tanpa animasi). Beberapa event roda dalam satu siklus
        digabung menjadi satu pergeseran, sehingga layar hanya digambar ulang sekali."""
        st = self.state.setdefault(canvas, {'pending': 0.0, 'job': None})
        st['pending'] = st.get('pending', 0.0) + pixels
        if st.get('job') is None:
            try:
                st['job'] = canvas.after(self.FRAME_MS, lambda: self._apply(canvas))
            except tk.TclError:
                self.state.pop(canvas, None)

    def _apply(self, canvas):
        st = self.state.get(canvas)
        if st is None:
            return
        pixels, st['pending'], st['job'] = st.get('pending', 0.0), 0.0, None
        try:
            total = self._content_height(canvas)
            limit = max(0.0, total - canvas.winfo_height())
            if total <= 0 or limit <= 0:
                return
            current = canvas.yview()[0] * total
            target = max(0.0, min(limit, current + pixels))
            if abs(target - current) >= 1:
                canvas.yview_moveto(target / total)
        except tk.TclError:
            self.state.pop(canvas, None)

    def reset(self, canvas):
        st = self.state.pop(canvas, None)
        if st and st.get('job'):
            try:
                canvas.after_cancel(st['job'])
            except tk.TclError:
                pass
