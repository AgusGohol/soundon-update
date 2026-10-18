"""SoundOn multi-account dashboard; optional read-only visible-page capture."""
import csv
import calendar
import json
import os
import shutil
import subprocess
import re
import socket
import threading
import time
import urllib.request
import sys
import tempfile
import hashlib
import urllib.parse
import base64
import tkinter as tk
from artist_finance import save_artist, month_total, rupiah, owner_groups, available_artists, assign_artists, rename_owner, remove_owner

# Izin perangkat SoundOn
from device_license import check_license, device_id
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, simpledialog, ttk

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_ok_license, _license_msg = check_license(_APP_DIR)
if not _ok_license:
    _lr = tk.Tk(); _lr.withdraw()
    messagebox.showwarning('Izin Perangkat SoundOn', _license_msg + '\n\nJalankan get-device-id.bat lalu kirim Kode Perangkat kepada Master.')
    _lr.destroy()
    raise SystemExit(3)

BASE = os.path.join(os.path.expanduser('~'), 'SoundOnAccounts')
FILE = os.path.join(BASE, 'accounts.json')
URL = 'https://www.soundon.global/library/login-after?lang=id&region=ID'
ROYALTY_URL = 'https://www.soundon.global/library/royalty'
STREAMS_URL = 'https://www.soundon.global/library/analytics?endTime=now-2&startTime=now-8'
os.makedirs(BASE, exist_ok=True)
import ui_theme as UI
from date_picker import PeriodButton, MonthButton
from ui_theme import (bg_of, BG, SIDE, PANEL, CARD, CARD_HI, LINE, WHITE, DIM, MUTED, PURPLE, GREEN, RED, BLUE, AMBER,
                      FONT, FONT_SEMI, RoundedPanel, RoundButton, icon_badge, avatar, pill, menu_button, ACCENTS)
APP_VERSION='3.16.1'
CATEGORY_FILE=os.path.join(BASE,'categories.json')
INVENTORY_FILE=os.path.join(BASE,'phone_inventory.json')
DEFAULT_CATEGORIES=['Indonesia','Negara Lain','Belum dikategorikan']
UPDATE_CONFIG=os.path.join(os.path.dirname(os.path.abspath(__file__)),'update_config.json')

# Pembaruan otomatis saat aplikasi dibuka (GitHub Releases). Gagal/offline = lanjut seperti biasa.
_restart_for_update=False
try:
    from updater import auto_update_on_start, EXIT_FOR_UPDATE
    if auto_update_on_start(_APP_DIR, APP_VERSION, BASE):
        raise SystemExit(EXIT_FOR_UPDATE)
except SystemExit:
    raise
except Exception:
    pass

# Komponen tampilan (RoundedPanel, RoundButton, ikon) ada di ui_theme.py.
def read_accounts():
    try:
        with open(FILE,encoding='utf-8') as f: data=json.load(f)
        return data if isinstance(data,list) else []
    except (OSError,ValueError): return []

accounts=read_accounts()
# Naik setiap data disimpan; halaman dirender ulang hanya bila data/filter berubah.
DATA_VERSION=[0]
OWNER_FILE=os.path.join(BASE,'owners.json')
def load_owners():
    try:
        with open(OWNER_FILE,encoding='utf-8') as f:data=json.load(f)
        return [x for x in data if isinstance(x,str) and x.strip()] if isinstance(data,list) else []
    except (OSError,ValueError):return []
owners=load_owners()
def save_owners():
    DATA_VERSION[0]+=1
    tmp=OWNER_FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(owners,f,ensure_ascii=False,indent=2)
    os.replace(tmp,OWNER_FILE)
def owner_names():
    names={name.casefold():name for name in owners}
    for a in accounts:
        for artist in a.get('artists',[]):
            name=' '.join(artist.get('owner','').split())
            if name:names.setdefault(name.casefold(),name)
    return sorted(names.values(),key=str.casefold)
def add_owner():
    name=simpledialog.askstring('Tambah Pemilik','Nama pemilik, misalnya Pak Mirwan:',parent=root)
    if name is None:return
    name=' '.join(name.split())
    if not name or name.casefold()=='belum ditentukan':
        messagebox.showerror('Nama tidak valid','Isi nama pemilik yang valid.',parent=root);return
    if name.casefold() in {x.casefold() for x in owner_names()}:
        messagebox.showinfo('Pemilik sudah ada','Nama tersebut sudah terdaftar.',parent=root);return
    owners.append(name)
    try:save_owners()
    except OSError as exc:
        owners.pop();messagebox.showerror('Gagal menyimpan',str(exc),parent=root);return
    if 'account_view_var' in globals():account_view_var.set('Per Pemilik')
    refresh()
def add_owner_artist(owner):
    import copy
    choices=available_artists(accounts)
    if not choices:
        messagebox.showinfo('Tidak ada artis tersedia','Semua artis yang tersedia sudah memiliki pemilik. Tambahkan akun/artis baru melalui Per Akun.',parent=root);return
    w=tk.Toplevel(root);w.title('Pilih Artis — Checklist');w.geometry('680x570');w.minsize(560,440)
    w.configure(bg=PANEL);w.transient(root);w.grab_set()
    label(w,'Pilih artis untuk '+owner,15,bold=True).pack(anchor='w',padx=20,pady=(20,8))
    label(w,'Centang beberapa artis sekaligus. Artis yang sudah dimiliki tidak ditampilkan.',10,DIM,wraplength=620,justify='left').pack(anchor='w',padx=20)
    label(w,'Untuk akun belum didata, nama akun akan dicatat sebagai nama artis setelah dipilih.',9,DIM,wraplength=620,justify='left').pack(anchor='w',padx=20,pady=(5,8))
    query=tk.StringVar();tk.Entry(w,textvariable=query,bg=CARD,fg=WHITE,insertbackground=WHITE,font=(FONT,11)).pack(fill='x',padx=20,pady=6)
    area=tk.Frame(w,bg=PANEL);area.pack(fill='both',expand=True,padx=20,pady=8)
    canvas=tk.Canvas(area,bg=PANEL,highlightthickness=0)
    scroll=ttk.Scrollbar(area,orient='vertical',command=canvas.yview);scroll.pack(side='right',fill='y')
    canvas.configure(yscrollcommand=scroll.set);canvas.pack(side='left',fill='both',expand=True)
    listing=tk.Frame(canvas,bg=PANEL);win=canvas.create_window((0,0),window=listing,anchor='nw')
    listing.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
    variables=[tk.BooleanVar(value=False) for _ in choices]
    def show(*args):
        clear(listing)
        for item,var in zip(choices,variables):
            if query.get().casefold() not in (item['name']+' '+item['account_name']).casefold():continue
            text=item['name']+f'  ·  Akun #{item["account_id"]}'
            if item['from_account']:text+=' (nama dari akun)'
            check=tk.Checkbutton(listing,text=text,variable=var,bg=CARD,fg=WHITE,selectcolor=PANEL,
                activebackground=CARD,activeforeground=WHITE,anchor='w',justify='left',wraplength=540,font=(FONT,11),padx=10,pady=9)
            check.pack(fill='x',pady=3)
    query.trace_add('write',show);show()
    def save():
        selected=[x for x,v in zip(choices,variables) if v.get()]
        before=copy.deepcopy(accounts)
        try:
            assign_artists(accounts,selected,owner)
            if os.path.isfile(FILE):shutil.copy2(FILE,FILE+'.before-checklist-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.bak')
            persist()
        except (ValueError,OSError) as exc:
            for a,old in zip(accounts,before):a.clear();a.update(old)
            messagebox.showerror('Tidak dapat menyimpan',str(exc),parent=w);return
        w.destroy();refresh()
    actions=tk.Frame(w,bg=PANEL);actions.pack(fill='x',padx=20,pady=(8,18))
    button(actions,'Simpan Pilihan',save,True).pack(side='right')
    button(actions,'Batal',w.destroy).pack(side='right',padx=8)


# Inventaris HP: jumlah HP yang dipakai akun dihitung otomatis dari seluruh akun.
def load_phone_inventory():
    defaults={'tersedia':0,'rusak':0,'service':0,'tidak_terpakai':0,'catatan':''}
    try:
        with open(INVENTORY_FILE,encoding='utf-8') as f: data=json.load(f)
        if not isinstance(data,dict): return defaults.copy()
        result={k:max(0,int(data.get(k,0))) for k in ('tersedia','rusak','service','tidak_terpakai')}
        result['catatan']=str(data.get('catatan',''))
        return result
    except (OSError,ValueError,TypeError): return defaults.copy()
phone_inventory=load_phone_inventory()
def assigned_phone_count():
    return sum(max(0,int(a.get('phone_count',0) or 0)) for a in accounts)
def save_phone_inventory():
    DATA_VERSION[0]+=1
    tmp=INVENTORY_FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f: json.dump(phone_inventory,f,ensure_ascii=False,indent=2)
    os.replace(tmp,INVENTORY_FILE)

def read_categories():
    try:
        with open(CATEGORY_FILE,encoding='utf-8') as f: saved=json.load(f)
        if isinstance(saved,list):
            return list(dict.fromkeys(DEFAULT_CATEGORIES+[x.strip() for x in saved if isinstance(x,str) and x.strip()]))
    except (OSError,ValueError): pass
    return DEFAULT_CATEGORIES.copy()
categories=read_categories()
def save_categories():
    DATA_VERSION[0]+=1
    tmp=CATEGORY_FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(categories,f,ensure_ascii=False,indent=2)
    os.replace(tmp,CATEGORY_FILE)
def account_category(a):
    return a.get('category') or 'Belum dikategorikan'


def persist():
    DATA_VERSION[0]+=1
    tmp=FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f: json.dump(accounts,f,indent=2,ensure_ascii=False)
    os.replace(tmp,FILE)

def chrome_path():
    candidates=[os.path.expandvars(p) for p in [r'%ProgramFiles%\Google\Chrome\Application\chrome.exe',r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe',r'%LocalAppData%\Google\Chrome\Application\chrome.exe']]
    return next((p for p in candidates if os.path.isfile(p)),None)

def profile(a): return os.path.join(BASE,'Account_'+str(a['id']))
def money(x, currency='IDR'):
    currency=str(currency or 'IDR').upper()
    value=f'{float(x):,.2f}'
    if currency=='IDR':return 'Rp '+value.replace(',','X').replace('.',',').replace('X','.')
    if currency=='USD':return '$'+value
    return currency+' '+value

def account_money(a):
    return money(a.get('balance',0),a.get('currency','IDR'))

def grouped_balance(members):
    totals={}
    for a in members:
        currency=str(a.get('currency') or 'IDR').upper()
        totals[currency]=totals.get(currency,0)+float(a.get('balance',0))
    return '  ·  '.join(money(v,k) for k,v in sorted(totals.items())) or '—'

def parse_balance(text):
    """Return (amount, ISO currency); no exchange-rate conversion."""
    raw=str(text).replace('\u00a0',' ').replace('\u202f',' ').strip()
    m=re.search(r'(?i)(?:\b(IDR|USD)\b|(?<!\w)(Rp|US\$|\$))\s*([0-9][0-9., ]*)',raw)
    if m:
        currency=(m.group(1) or ('IDR' if m.group(2).lower()=='rp' else 'USD')).upper()
        num=m.group(3).strip()
    else:
        m=re.search(r'(?i)([0-9][0-9., ]*)\s*\b(IDR|USD)\b',raw)
        if not m:raise ValueError('Nominal IDR/USD tidak ditemukan pada kartu saldo: '+raw[:100])
        num=m.group(1).strip();currency=m.group(2).upper()
    num=num.replace(' ','')
    if ',' in num and '.' in num:
        decimal=',' if num.rfind(',')>num.rfind('.') else '.'
        num=num.replace('.','').replace(',','.') if decimal==',' else num.replace(',','')
    elif ',' in num:
        parts=num.split(',')
        num=''.join(parts) if len(parts)>2 or (len(parts[-1])==3 and len(parts[0])<=3) else num.replace(',','.')
    elif '.' in num:
        parts=num.split('.')
        num=''.join(parts) if len(parts)>2 or (currency=='IDR' and len(parts[-1])==3) else num
    return float(num),currency

def number(x): return f'{int(x):,}'.replace(',','.')
def label(parent,text,size=10,color=WHITE,bold=False,**kw):
    return tk.Label(parent,text=text,font=(FONT,size,'bold' if bold else 'normal'),fg=color,bg=parent.cget('bg'),**kw)
def mix_card(color,t=0.07):return UI.mix(PANEL,color,t)

def button(parent,text,cmd,primary=False,**kw):
    return RoundButton(parent,text,cmd,variant='primary' if primary else kw.pop('variant','secondary'),**kw)

# Antrean aman-thread: thread latar belakang TIDAK boleh menyentuh Tk secara langsung
# (penyebab crash/macet acak). Mereka menitipkan fungsi ke sini; thread utama menjalankannya.
import queue as _queue
_ui_queue=_queue.Queue()
def ui_call(fn):
    _ui_queue.put(fn)
def _drain_ui_queue():
    try:
        for _ in range(50):
            fn=_ui_queue.get_nowait()
            try:fn()
            except Exception:
                import traceback;traceback.print_exc()
    except _queue.Empty:pass
    root.after(50,_drain_ui_queue)

def parse_amount(text,currency='IDR'):
    """Angka saldo dari input pengguna: '4.160.229', '4160229', '897,78', '897.78', '1.234,50'."""
    raw=str(text).strip().replace(' ','').replace('\u00a0','')
    raw=re.sub(r'(?i)^(rp|idr|usd|us\$|\$)','',raw)
    if not raw or not re.fullmatch(r'[0-9.,]+',raw):raise ValueError('Angka tidak valid: '+str(text))
    if ',' in raw and '.' in raw:
        dec=',' if raw.rfind(',')>raw.rfind('.') else '.'
        raw=raw.replace('.' if dec==',' else ',','').replace(dec,'.')
    elif ',' in raw:
        parts=raw.split(',')
        raw=''.join(parts) if len(parts)>2 or (len(parts[-1])==3 and str(currency).upper()=='IDR') else raw.replace(',','.')
    elif '.' in raw:
        parts=raw.split('.')
        if len(parts)>2 or (len(parts[-1])==3 and str(currency).upper()=='IDR'):raw=''.join(parts)
    value=float(raw)
    if value<0:raise ValueError('Angka tidak boleh negatif.')
    return value

def format_amount(value,currency='IDR'):
    """Isi awal kolom saldo: tanpa pemisah ribuan, koma sebagai desimal."""
    try:value=float(value or 0)
    except (TypeError,ValueError):value=0.0
    if str(currency).upper()=='IDR' and value.is_integer():return str(int(value))
    return f'{value:.2f}'.replace('.',',')

def upsert_record(a,record):
    """Satu catatan per periode+platform (yang terbaru); file data tidak terus membesar."""
    key=(record['start'],record['end'],record.get('platform','Semua Platform'))
    records=a.setdefault('records',[])
    records[:]=[r for r in records if (r.get('start'),r.get('end'),r.get('platform','Semua Platform'))!=key]
    records.append(record)

def parse_date(s): return date.fromisoformat(s.strip())
def check_range():
    try:
        start=parse_date(start_var.get()); end=parse_date(end_var.get())
        if end<start: raise ValueError()
        return start,end
    except ValueError:
        messagebox.showerror('Tanggal tidak valid','Gunakan YYYY-MM-DD. Tanggal akhir tidak boleh sebelum tanggal mulai.',parent=root)
        return None

def latest(a,start,end,platform):
    entries=[]
    for item in a.get('records',[]):
        try:
            s=parse_date(item['start']); e=parse_date(item['end'])
            if s==start and e==end and item.get('platform','Semua Platform')==platform: entries.append(item)
        except (KeyError,ValueError,TypeError): continue
    return max(entries,key=lambda r:r.get('updated','')) if entries else None

def port_for(a):
    # A stable, localhost-only debugging port for each account profile.
    return 20000 + int(a['id'])

def debugger_ready(a):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port_for(a)}/json/version',timeout=1) as response:
            return b'webSocketDebuggerUrl' in response.read()
    except Exception:
        return False

def open_account(a, target_url=URL):
    """Launch the selected account's separate Chrome profile at target_url."""
    chrome=chrome_path()
    if not chrome:
        messagebox.showerror('Chrome tidak ditemukan','Instal Google Chrome terlebih dahulu.',parent=root)
        return False
    os.makedirs(profile(a),exist_ok=True)
    try:
        subprocess.Popen([chrome,'--user-data-dir='+profile(a),
                          '--remote-debugging-address=127.0.0.1',
                          '--remote-debugging-port='+str(port_for(a)),
                          '--new-window',target_url])
        for delay in (3000,8000,15000):root.after(delay,poll_chrome_status)
        return True
    except OSError as ex:
        messagebox.showerror('Gagal membuka Chrome',str(ex),parent=root)
        return False

def open_soundon_page(a, target_url, page_title):
    """Navigate the selected account's own Chrome session without sharing logins."""
    if not debugger_ready(a):
        if open_account(a, target_url):
            status_var.set('Membuka '+page_title+': '+a.get('name','akun'))
        return
    status_var.set('Membuka '+page_title+': '+a.get('name','akun')+'…')
    def worker():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser=pw.chromium.connect_over_cdp(
                    f'http://127.0.0.1:{port_for(a)}',timeout=10000)
                contexts=browser.contexts
                if not contexts:
                    raise ValueError('Profil Chrome belum siap. Coba lagi sebentar.')
                pages=[p for ctx in contexts for p in ctx.pages
                       if urllib.parse.urlparse(p.url).hostname in ('soundon.global','www.soundon.global')]
                page=pages[-1] if pages else contexts[0].new_page()
                page.goto(target_url,wait_until='domcontentloaded',timeout=30000)
                page.bring_to_front()
                ui_call(lambda:status_var.set(page_title+' terbuka: '+a.get('name','akun')))
        except Exception as ex:
            msg=str(ex)
            if 'No module named' in msg and 'playwright' in msg:
                msg='Playwright belum terpasang. Jalankan install_dependencies.bat.'
            ui_call(lambda m=msg:messagebox.showwarning(
                'Gagal membuka '+page_title,
                m+'\n\nCoba buka akun lewat tombol Buka, lalu ulangi.',parent=root))
    threading.Thread(target=worker,daemon=True).start()

def open_streams(a):
    open_soundon_page(a, STREAMS_URL, 'Analytics / Streams')

def open_balance(a):
    open_soundon_page(a, ROYALTY_URL, 'Saldo / Penghasilan Saya')

def add_account():
    nid=max((int(a['id']) for a in accounts),default=0)+1
    name=simpledialog.askstring('Tambah akun','Nama akun:',initialvalue=f'Akun {nid}',parent=root)
    if name is None:return
    category=choose_category('Kategori akun baru')
    if category is None:return
    accounts.append({'id':nid,'name':name.strip() or f'Akun {nid}','category':category,'phone_count':0,'artist_count':0,'song_count':0,'records':[],'balance':0,'balance_updated':'','currency':'IDR'})
    persist(); refresh()

def choose_category(title, initial='Indonesia'):
    w=tk.Toplevel(root);w.title(title);w.configure(bg=PANEL);w.geometry('380x180')
    w.transient(root);w.grab_set();result=[None]
    label(w,'Pilih kategori / negara',12,bold=True).pack(anchor='w',padx=20,pady=(18,8))
    v=tk.StringVar(value=initial if initial in categories else 'Indonesia')
    ttk.Combobox(w,textvariable=v,values=categories,state='readonly',style='Dark.TCombobox').pack(fill='x',padx=20,ipady=5)
    def confirm():result[0]=v.get();w.destroy()
    button(w,'Simpan kategori',confirm,True).pack(pady=16)
    w.bind('<Escape>',lambda e:w.destroy());w.wait_window()
    return result[0]

def change_category(a):
    selected=choose_category('Pindahkan kategori: '+a['name'],account_category(a))
    if selected is not None:a['category']=selected;persist();refresh()

def add_category():
    name=simpledialog.askstring('Tambah kategori','Nama negara / kategori baru:',parent=root)
    if not name or not name.strip():return
    name=name.strip()
    if name not in categories:
        categories.append(name);save_categories()
        category_filter.configure(values=['Semua Kategori']+categories)
    refresh()

def edit_account_counts(a):
    """Modern combined editor for HP, artist and song counts."""
    w=tk.Toplevel(root);w.title('Atur Jumlah HP, Artis & Lagu');w.geometry('600x640')
    w.configure(bg=PANEL);w.transient(root);w.grab_set();w.resizable(False,False)
    try:
        w.update_idletasks()
        x=root.winfo_rootx()+(root.winfo_width()-600)//2
        y=root.winfo_rooty()+max(25,(root.winfo_height()-640)//2)
        w.geometry(f'600x640+{x}+{y}')
    except Exception: pass
    header=tk.Frame(w,bg=PANEL);header.pack(fill='x',padx=28,pady=(25,12))
    label(header,'Atur Jumlah HP, Artis & Lagu',15,bold=True).pack(anchor='w')
    profile_card=tk.Frame(w,bg=CARD,highlightbackground=LINE,highlightthickness=1);profile_card.pack(fill='x',padx=28,pady=(0,8))
    avatar(profile_card,a['name'],PURPLE,44,CARD).pack(side='left',padx=14,pady=11)
    profile_text=tk.Frame(profile_card,bg=CARD);profile_text.pack(side='left',fill='y',pady=10)
    label(profile_text,a['name'],13,WHITE,bold=True).pack(anchor='w')
    label(profile_text,'Akun #'+str(a['id'])+'  ·  '+account_category(a),9,DIM).pack(anchor='w',pady=(4,0))
    fields={}
    specs=[('phone','Jumlah HP','phone_count',BLUE,'HP yang digunakan untuk akun ini.'),
           ('users','Jumlah Artis','artist_count',GREEN,'Jumlah artis pada akun ini.'),
           ('music','Jumlah Lagu','song_count',PURPLE,'Jumlah lagu pada akun ini.')]
    for icon,title,key,color,desc in specs:
        card=tk.Frame(w,bg=CARD,highlightbackground=LINE,highlightthickness=1);card.pack(fill='x',padx=28,pady=6)
        left=tk.Frame(card,bg=CARD);left.pack(side='left',fill='x',expand=True,padx=15,pady=12)
        icon_badge(left,icon,color,CARD,38).pack(side='left',padx=(0,12))
        info=tk.Frame(left,bg=CARD);info.pack(side='left',fill='x',expand=True)
        label(info,title,11,WHITE,bold=True).pack(anchor='w')
        label(info,desc,9,DIM).pack(anchor='w',pady=(3,0))
        v=tk.StringVar(value=str(a.get(key,0)));fields[key]=v
        control=tk.Frame(card,bg=CARD);control.pack(side='right',padx=14)
        e=tk.Entry(control,textvariable=v,width=6,justify='center',bg=PANEL,fg=WHITE,insertbackground=WHITE,
            relief='flat',font=(FONT,13,'bold'),highlightthickness=1,highlightbackground=LINE,highlightcolor=PURPLE)
        e.pack(side='left',ipady=7)
        def adjust(delta,var=v):
            try:n=max(0,min(1000000,int(var.get() or 0)+delta))
            except ValueError:n=0
            var.set(str(n))
        RoundButton(control,'−',lambda v=v:adjust(-1,v),bg_color=CARD,padx=10,height=34,font_size=12).pack(side='left',padx=(7,3))
        RoundButton(control,'',lambda v=v:adjust(1,v),icon='plus',bg_color=CARD,variant='primary',height=34).pack(side='left',padx=(3,0))
    note_card=tk.Frame(w,bg=CARD,highlightbackground=LINE,highlightthickness=1);note_card.pack(fill='x',padx=28,pady=(9,6))
    label(note_card,'Catatan (opsional)',10,DIM,bold=True).pack(anchor='w',padx=14,pady=(10,5))
    notes=tk.Text(note_card,height=3,wrap='word',font=(FONT,10),bg=PANEL,fg=WHITE,insertbackground=WHITE,relief='flat',padx=10,pady=8)
    notes.insert('1.0',a.get('count_note',''));notes.pack(fill='x',padx=14,pady=(0,12))
    actions=tk.Frame(w,bg=PANEL);actions.pack(fill='x',padx=28,pady=(12,0))
    def save():
        values={}
        for key,v in fields.items():
            raw=v.get().strip()
            if not raw.isdecimal() or int(raw)>1000000:
                messagebox.showerror('Jumlah tidak valid','Isi bilangan bulat 0 sampai 1.000.000.',parent=w);return
            values[key]=int(raw)
        a.update(values);a['count_note']=notes.get('1.0','end-1c').strip();persist();w.destroy();refresh()
    button(actions,'✓  Simpan Perubahan',save,True).pack(side='right')
    button(actions,'Batal',w.destroy,variant='ghost').pack(side='right',padx=(0,9))
    w.bind('<Escape>',lambda e:w.destroy())

def artist_month_picker(parent, variable, callback=None):
    """Pemilih bulan penghasilan (nilai YYYY-MM)."""
    return MonthButton(parent, variable, callback)


def edit_artist_finance(a,default_owner="",target_artist=None):
    import copy
    w=tk.Toplevel(root);w.title('Pemilik & Penghasilan Artis');w.geometry('850x660')
    w.minsize(800,620);w.configure(bg=PANEL);w.transient(root);w.grab_set()
    label(w,'Pemilik & Penghasilan Artis',15,bold=True).pack(anchor='w',padx=22,pady=(20,6))
    label(w,a['name']+' · Input manual dalam rupiah',10,DIM).pack(anchor='w',padx=22)
    period=tk.StringVar(value=artist_month_var.get())
    line=tk.Frame(w,bg=PANEL);line.pack(fill='x',padx=22,pady=12)
    label(line,'Bulan penghasilan:',10,DIM).pack(side='left')
    selected=[target_artist]
    def populate():
        table.delete(*table.get_children())
        for artist in a.get('artists',[]):
            amount=artist.get('earnings',{}).get(period.get())
            table.insert('', 'end',iid=str(artist['id']),values=(artist['name'],artist['owner'],
                rupiah(amount) if amount is not None else 'Belum diisi'))
        if selected[0] is not None and table.exists(str(selected[0])):
            table.selection_set(str(selected[0]))
            choose()
        else:
            amount_var.set('')
        total_var.set('Total bulan ini: '+rupiah(month_total(a,period.get())))
    artist_month_picker(line,period,populate).pack(side='left',padx=9)
    tablebox=tk.Frame(w,bg=PANEL);tablebox.pack(fill='both',expand=True,padx=22)
    table=ttk.Treeview(tablebox,columns=('artist','owner','income'),show='headings',selectmode='browse',height=5,style='Dark.Treeview')
    for key,title,width in [('artist','Nama artis',300),('owner','Pemilik',210),('income','Penghasilan (IDR)',180)]:
        table.heading(key,text=title);table.column(key,width=width,minwidth=100,stretch=True)
    scroll=ttk.Scrollbar(tablebox,orient='vertical',command=table.yview,style='Dark.Vertical.TScrollbar')
    table.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)
    total_var=tk.StringVar();tk.Label(w,textvariable=total_var,bg=PANEL,fg=GREEN,font=(FONT,11,'bold')).pack(anchor='w',padx=22,pady=8)
    form=tk.Frame(w,bg=PANEL);form.pack(fill='x',padx=22,pady=6)
    name_var=tk.StringVar();owner_var=tk.StringVar(value=default_owner);amount_var=tk.StringVar()
    for title,var in [('Nama artis',name_var),('Pemilik artis',owner_var),('Penghasilan bulan terpilih (Rp)',amount_var)]:
        row=tk.Frame(form,bg=PANEL);row.pack(fill='x',pady=4)
        label(row,title,10,DIM,width=29,anchor='w').pack(side='left')
        if title=='Pemilik artis':
            ttk.Combobox(row,textvariable=var,values=owner_names(),style='Dark.TCombobox',font=(FONT,11)).pack(side='left',fill='x',expand=True,ipady=5)
        else:
            tk.Entry(row,textvariable=var,bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',font=(FONT,11)).pack(side='left',fill='x',expand=True,ipady=5)
    label(w,'Contoh nominal: 5000000 atau 5.000.000. Pemilik berlaku untuk seluruh riwayat artis.',9,DIM).pack(anchor='w',padx=22,pady=6)
    def choose(event=None):
        selection=table.selection()
        if not selection:return
        selected[0]=int(selection[0])
        artist=next(x for x in a.get('artists',[]) if x['id']==selected[0])
        name_var.set(artist['name']);owner_var.set(artist['owner'])
        amount_var.set(str(artist.get('earnings',{}).get(period.get(),'')))
    table.bind('<<TreeviewSelect>>',choose)
    def new():
        selected[0]=None
        for var in (name_var,owner_var,amount_var):var.set('')
        owner_var.set(default_owner)
        if table.selection():table.selection_remove(*table.selection())
    def commit(change):
        before=copy.deepcopy(a)
        try:
            change()
            if os.path.isfile(FILE):
                backup=FILE+".before-artists-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".bak"
                shutil.copy2(FILE,backup)
            persist()
        except (ValueError,OSError) as exc:
            a.clear();a.update(before)
            messagebox.showerror('Tidak dapat menyimpan',str(exc),parent=w);return False
        populate();refresh();return True
    def save():
        def change():
            artist=save_artist(a,selected[0],name_var.get(),owner_var.get(),period.get(),amount_var.get())
            selected[0]=artist['id']
        commit(change)
    def remove_month():
        if selected[0] is None:return
        if not messagebox.askyesno('Hapus penghasilan','Hapus penghasilan artis terpilih untuk '+period.get()+'?',parent=w):return
        def change():
            artist=next(x for x in a['artists'] if x['id']==selected[0])
            artist.get('earnings',{}).pop(period.get(),None)
        commit(change)
    def remove_artist():
        if selected[0] is None:return
        if not messagebox.askyesno('Hapus artis','Hapus artis terpilih beserta seluruh riwayat penghasilannya?',parent=w):return
        target=selected[0]
        def change():a['artists']=[x for x in a['artists'] if x['id']!=target]
        if commit(change):new()
    actions=tk.Frame(w,bg=PANEL);actions.pack(side='bottom',fill='x',padx=22,pady=(10,18),before=tablebox)
    for title,fn in [('Tambah Artis',new),('Simpan',save),('Hapus Bulan',remove_month),('Hapus Artis',remove_artist),('Tutup',w.destroy)]:
        button(actions,title,fn,title=='Simpan').pack(side='left',padx=(0,7))
    populate()


def render_artist_finance(parent,a):
    section=tk.Frame(parent,bg=CARD);section.pack(fill='x',pady=(12,0))
    top=tk.Frame(section,bg=CARD);top.pack(fill='x',padx=14,pady=(10,6))
    label(top,'PEMILIK & PENGHASILAN · '+artist_month_var.get(),9,DIM,bold=True).pack(anchor='w')
    button(top,'Atur Pemilik & Penghasilan',lambda:edit_artist_finance(a)).pack(anchor='w',pady=(6,0))
    rows=tk.Frame(section,bg=CARD);rows.pack(fill='x',padx=14,pady=(0,10))
    for col,weight in enumerate([3,2,2]):rows.columnconfigure(col,weight=weight,uniform='artist')
    for col,title in enumerate(['Nama artis','Pemilik','Penghasilan (IDR)']):
        label(rows,title,10,DIM,bold=True,anchor='w').grid(row=0,column=col,sticky='ew',padx=5,pady=5)
    artists=a.get('artists',[])
    for row,artist in enumerate(artists,1):
        amount=artist.get('earnings',{}).get(artist_month_var.get())
        for col,value in enumerate([artist['name'],artist['owner'],rupiah(amount) if amount is not None else 'Belum diisi']):
            cell=label(rows,value,11,GREEN if col==2 and amount is not None else WHITE,anchor='w')
            cell.configure(wraplength=230,justify='left')
            cell.grid(row=row,column=col,sticky='ew',padx=5,pady=5)
            cell.bind('<Configure>',lambda e,l=cell:l.configure(wraplength=max(50,e.width-6)))
    if not artists:
        label(rows,'Belum ada data artis.',10,DIM).grid(row=1,column=0,columnspan=3,sticky='w',padx=5,pady=7)
    label(section,'Total bulan terpilih: '+rupiah(month_total(a,artist_month_var.get())),11,GREEN,bold=True).pack(anchor='w',padx=19,pady=(0,12))


def rename(a):
    name=simpledialog.askstring('Ubah nama','Nama akun:',initialvalue=a['name'],parent=root)
    if name and name.strip():a['name']=name.strip();persist();refresh()

def delete(a):
    delete_accounts([a])

def delete_accounts(targets):
    """Hapus satu atau beberapa akun beserta profil Chrome-nya (dengan konfirmasi)."""
    targets=[a for a in targets if a in accounts]
    if not targets:return
    names='\n'.join('•  '+a['name']+'  (#'+str(a['id'])+')' for a in targets[:12])
    if len(targets)>12:names+=f'\n…dan {len(targets)-12} akun lainnya'
    title='Hapus akun' if len(targets)==1 else f'Hapus {len(targets)} akun'
    if not messagebox.askyesno(title,f'{names}\n\nAkun di atas, data lokalnya, dan profil Chrome-nya akan dihapus permanen. '
                               'Data di SoundOn tidak terpengaruh.\n\nLanjutkan?',icon='warning',parent=root):return
    failed=[]
    for a in targets:
        try:
            if os.path.exists(profile(a)):shutil.rmtree(profile(a))
        except OSError:
            failed.append(a);continue
        accounts.remove(a);_chrome_status.pop(str(a['id']),None)
    persist()
    try:account_table.clear_selection()
    except NameError:pass
    refresh()
    if failed:
        messagebox.showwarning('Sebagian belum terhapus','Profil Chrome akun berikut sedang dipakai. Tutup jendela Chrome-nya lalu hapus lagi:\n\n'+
                               '\n'.join('•  '+a['name'] for a in failed),parent=root)


def parse_streams_display(text):
    """Read English/Indonesian formatted SoundOn metrics; abbreviated counts approximate."""
    import unicodedata
    raw = unicodedata.normalize('NFKC', str(text)).lower()
    clean = ''.join(ch for ch in raw if not ch.isspace() and
                    unicodedata.category(ch) != 'Cf')
    m = re.fullmatch(r'([\d.,]+)(ribu|rb|juta|jt|k|m|b)?', clean)
    if not m:
        raise ValueError('Format angka tidak dikenal: ' + str(text))
    num, unit = m.groups()
    if unit:
        # Both "27,5 rb" and "27.5K" represent 27,500.
        # Multiple separators: last separator is decimal when final group isn't 3 digits.
        if ',' in num and '.' in num:
            decimal = ',' if num.rfind(',') > num.rfind('.') else '.'
            other = '.' if decimal == ',' else ','
            numeric = num.replace(other, '').replace(decimal, '.')
        elif ',' in num or '.' in num:
            sep = ',' if ',' in num else '.'
            parts = num.split(sep)
            numeric = (''.join(parts) if len(parts)>2 else
                       num.replace(sep, '.') if len(parts[-1]) != 3 else
                       num.replace(sep, '.') if len(parts[0]) <= 2 else ''.join(parts))
        else:
            numeric = num
        multiplier = {'ribu':1000,'rb':1000,'k':1000,
                      'juta':1000000,'jt':1000000,'m':1000000,'b':1000000000}[unit]
        return round(float(numeric)*multiplier), True
    if ',' in num and '.' in num:
        decimal = ',' if num.rfind(',') > num.rfind('.') else '.'
        integer, fractional = num.rsplit(decimal, 1)
        if len(fractional) == 3:
            num = num.replace(',', '').replace('.', '')
        else:
            raise ValueError('Angka metrik tanpa satuan harus bilangan bulat: '+str(text))
    elif ',' in num or '.' in num:
        sep = ',' if ',' in num else '.'
        groups = num.split(sep)
        if not all(len(g)==3 for g in groups[1:]):
            raise ValueError('Angka metrik tanpa satuan harus bilangan bulat: '+str(text))
        num = ''.join(groups)
    return int(num), False

# Card headings differ according to the account's SoundOn interface language.
METRIC_LABELS = {
    'streams': ('Streams',),
    'listeners': ('Pendengar', 'Listeners'),
}

# ---------------------------------------------------------------- sinkron otomatis
import auto_sync
SYNC_LOG=os.path.join(BASE,'sync_log.txt')
_sync_state={'running':False,'stop':False,'text':''}

def sync_settings():
    st=UI.load_settings()
    try:hour=max(0,min(23,int(st.get('sync_hour',8))))
    except (TypeError,ValueError):hour=8
    return {'enabled':bool(st.get('sync_enabled',True)),'hour':hour,'open_closed':bool(st.get('sync_open_closed',True)),
            'balance':bool(st.get('sync_balance',True)),'regions':bool(st.get('sync_regions',True)),
            'last_date':st.get('sync_last_date',''),'last_summary':st.get('sync_last_summary','')}

def _sync_log(text):
    try:
        with open(SYNC_LOG,'a',encoding='utf-8') as f:f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S')+'  '+text+'\n')
    except OSError:pass

def _read_card_any(page,kind):
    try:value=visible_metric_card(page,kind)
    except Exception:value=None
    return value or auto_sync.read_card_fallback(page,kind)

def _set_sync_status(text):
    _sync_state['text']=text
    try:sync_status.set(text)
    except NameError:pass

def _upload_busy_accounts():
    um=globals().get('upload_manager_window')
    if um is None or not getattr(um,'busy',False):return set()
    return {str(j.get('account_id')) for j in getattr(um,'jobs',[]) if j.get('status')=='Memproses'}

def month_period(year,month):
    """Periode satu bulan penuh (berhenti di hari ini untuk bulan berjalan)."""
    first=date(year,month,1)
    last=date(year,month,calendar.monthrange(year,month)[1])
    return first,min(last,date.today())

def daily_periods():
    """Sinkron harian membaca data bulanan: bulan ini, ditambah bulan lalu pada tanggal 1–3
    (agar total bulan lalu lengkap, karena data SoundOn tertunda ±2 hari)."""
    t=date.today();periods=[month_period(t.year,t.month)]
    if t.day<=3:
        prev=t.replace(day=1)-timedelta(days=1);periods.append(month_period(prev.year,prev.month))
    return periods

def ask_month_and_sync():
    """Pilih bulan lalu jalankan sinkron untuk bulan itu."""
    w=tk.Toplevel(root);w.title('Sinkron per bulan');w.configure(bg=PANEL);w.transient(root);w.resizable(False,False)
    body=tk.Frame(w,bg=PANEL);body.pack(padx=22,pady=20)
    label(body,'Sinkron per bulan',14,bold=True).pack(anchor='w')
    label(body,'Baca data satu bulan penuh untuk semua akun.',9,DIM).pack(anchor='w',pady=(2,12))
    mv=tk.StringVar(value=date.today().strftime('%Y-%m'))
    MonthButton(body,mv).pack(anchor='w')
    acts=tk.Frame(body,bg=PANEL);acts.pack(fill='x',pady=(16,0))
    def go():
        y,m=map(int,mv.get().split('-'))
        if date(y,m,1)>date.today():
            messagebox.showinfo('Bulan belum berjalan','Pilih bulan ini atau bulan sebelumnya.',parent=w);return
        w.destroy();start_sync(periods=[month_period(y,m)])
    button(acts,'Mulai sinkron',go,True,icon='sync').pack(side='right')
    button(acts,'Batal',w.destroy,variant='ghost').pack(side='right',padx=6)

def start_sync(auto=False,periods=None):
    """Baca Streams & Pendengar semua akun dari Analytics SoundOn (di latar belakang)."""
    if _sync_state['running']:
        if not auto:messagebox.showinfo('Sinkron berjalan','Sinkron sedang berjalan: '+_sync_state['text'],parent=root)
        return
    if not accounts:
        if not auto:messagebox.showinfo('Belum ada akun','Tambahkan akun terlebih dahulu.',parent=root)
        return
    if periods is None and auto:periods=daily_periods()
    if periods is None:
        try:start=parse_date(start_var.get());end=parse_date(end_var.get())
        except ValueError:start=end=date.today()
        if end<start:start,end=end,start
        periods=[(start,end)]
    start,end=periods[0]
    plat=platform_var.get()
    note=''
    if plat not in auto_sync.SUPPORTED_PLATFORMS:
        note=f'\n\nPlatform {plat} belum didukung sinkron otomatis; yang dibaca: Semua Platform.'
        plat='Semua Platform'
    cfg=sync_settings()
    targets=list(accounts)
    if not auto:
        minutes=max(1,round(len(targets)*(35+(25 if cfg['balance'] else 0)+(60 if cfg['regions'] else 0))/60))
        extra='Chrome akun yang tertutup akan dibuka (diperkecil) lalu ditutup lagi.' if cfg['open_closed'] else 'Hanya akun yang Chrome-nya sedang terbuka yang dibaca.'
        what='Streams & Pendengar'+(', Saldo' if cfg['balance'] else '')+(', Asal Streams per artis' if cfg['regions'] else '')
        ptxt=', '.join(f'{p[0]} s.d. {p[1]}' for p in periods)
        if not messagebox.askyesno('Sinkron semua akun',f'Baca {what} untuk {len(targets)} akun\nPeriode: {ptxt} · {plat}\n\n{extra}\n'
                                   f'Perkiraan waktu ± {minutes} menit. Aplikasi tetap bisa dipakai.{note}\n\nMulai sekarang?',parent=root):return
    _sync_state.update(running=True,stop=False)
    _set_sync_status(f'Sinkron dimulai · {len(targets)} akun')
    busy=_upload_busy_accounts()
    def apply_balance(a,amount,currency):
        if a in accounts:
            a['balance']=amount;a['currency']=currency;a['balance_updated']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            persist()
            if active_page=='Dashboard':refresh()
    def apply_region(a,row):
        if a in accounts:
            existing=a.setdefault('region_records',[])
            existing[:]=[old for old in existing if not (str(old.get('artist_id'))==str(row['artist_id']) and old.get('start')==row['start']
                         and old.get('end')==row['end'] and old.get('platform')==row['platform'])]
            existing.append(row);persist()
    def apply_result(a,record):
        if a in accounts:
            upsert_record(a,record);persist()
            # Hanya Dashboard yang diperbarui langsung; halaman lain ikut saat dibuka berikutnya.
            if active_page=='Dashboard':refresh()
    syncer=auto_sync.Syncer(start=start,end=end,periods=periods,platform=plat,open_closed=cfg['open_closed'],chrome_path=chrome_path,
        profile_dir=profile,port_for=port_for,ready=debugger_ready,read_card=_read_card_any,parse_number=parse_streams_display,
        on_progress=lambda i,n,a:ui_call(lambda:_set_sync_status(f'Sinkron {i}/{n} · {a.get("name","")}')),
        on_result=lambda a,r:ui_call(lambda:apply_result(a,r)),should_stop=lambda:_sync_state['stop'],
        busy_account=lambda a:str(a['id']) in busy,log=_sync_log,
        read_balance=visible_available_balance if cfg['balance'] else None,
        on_balance=lambda a,n,c:ui_call(lambda:apply_balance(a,n,c)),
        read_regions=(lambda page:page.evaluate(REGION_SVG_JS)) if cfg['regions'] else None,
        on_region=lambda a,row:ui_call(lambda:apply_region(a,row)))
    def worker():
        try:summary=syncer.run(targets);error=None
        except Exception as exc:
            summary=None;error=str(exc)
            if 'No module named' in error and 'playwright' in error:error='Playwright belum terpasang. Jalankan install_dependencies.bat.'
            _sync_log('ERROR: '+error)
        ui_call(lambda:_finish_sync(summary,error,auto))
    threading.Thread(target=worker,daemon=True).start()

def _finish_sync(summary,error,auto):
    _sync_state['running']=False
    stamp=datetime.now().strftime('%d/%m %H:%M')
    if error:
        text=f'Sinkron gagal ({stamp}): {error}'
    else:
        text=(f'Sinkron {stamp}: {len(summary["ok"])} berhasil · {len(summary["login"])} perlu login · '
              f'{len(summary["lewati"])} dilewati · {len(summary["gagal"])} gagal'+(' · dihentikan' if _sync_state['stop'] else ''))
    _set_sync_status(text)
    try:UI.save_settings(sync_last_date=date.today().isoformat(),sync_last_summary=text)
    except OSError:pass
    refresh()
    if not auto:
        detail=''
        if summary:
            for key,title in (('login','Perlu login'),('gagal','Gagal')):
                if summary[key]:
                    detail+=f'\n\n{title}:\n'+'\n'.join('•  '+a.get('name','')+' — '+n for a,n in summary[key][:10])
                    if len(summary[key])>10:detail+=f'\n…dan {len(summary[key])-10} lainnya'
        messagebox.showinfo('Sinkron selesai',text+detail+'\n\nLaporan lengkap: Pengaturan > Sinkron Otomatis > Lihat laporan.',parent=root)

def stop_sync():
    if _sync_state['running']:
        _sync_state['stop']=True;_set_sync_status('Menghentikan sinkron setelah akun ini…')

def open_sync_log():
    if not os.path.exists(SYNC_LOG):
        messagebox.showinfo('Belum ada laporan','Sinkron belum pernah dijalankan.',parent=root);return
    try:
        if os.name=='nt':os.startfile(SYNC_LOG)
        else:subprocess.Popen(['xdg-open',SYNC_LOG])
    except OSError as ex:messagebox.showerror('Gagal membuka laporan',str(ex),parent=root)

def _sync_scheduler():
    """Sekali sehari pada jam yang dipilih (atau saat aplikasi dibuka setelah jam itu)."""
    try:
        cfg=sync_settings();now=datetime.now()
        if cfg['enabled'] and not _sync_state['running'] and accounts and now.hour>=cfg['hour'] and cfg['last_date']!=date.today().isoformat():
            start_sync(auto=True)
    finally:
        root.after(60000,_sync_scheduler)

# ---------------------------------------------------------------- pembaruan saat aplikasi terbuka
# Selain saat dibuka, aplikasi memeriksa GitHub tiap 20 menit. Versi baru diunduh & diverifikasi
# di latar, lalu dipasang saat aplikasi sedang tidak sinkron/mengunggah (hitung mundur 30 detik,
# bisa ditunda). Data, lisensi, dan profil Chrome tidak disentuh.
UPDATE_CHECK_SECONDS=20*60
_update_state={'checking':False,'last_check':time.time(),'ready':None,'snooze_until':0.0,'dialog':None}

def _app_busy():
    if _sync_state['running']:return True
    um=globals().get('upload_manager_window')
    return bool(um is not None and getattr(um,'busy',False))

def _update_check_worker():
    import updater as upd
    try:
        found=upd.check_while_running(os.path.dirname(os.path.abspath(__file__)),APP_VERSION,BASE)
        if found:ui_call(lambda f=found:_update_state.__setitem__('ready',f))
    except Exception:
        pass
    finally:
        _update_state['checking']=False

def _update_watcher():
    try:
        now=time.time()
        if _update_state['ready'] is None:
            if not _update_state['checking'] and now-_update_state['last_check']>=UPDATE_CHECK_SECONDS:
                _update_state['checking']=True;_update_state['last_check']=now
                threading.Thread(target=_update_check_worker,daemon=True).start()
        elif now>=_update_state['snooze_until'] and _update_state['dialog'] is None and not _app_busy():
            _offer_update()
    finally:
        root.after(60000,_update_watcher)

def _apply_ready_update():
    global _restart_for_update
    import updater as upd
    manifest,(staging,extract)=_update_state['ready']
    if _app_busy():
        _update_state['snooze_until']=time.time()+60;return
    if not upd.register_attempt(BASE,manifest['version'],APP_VERSION):
        _update_state['ready']=None;return
    try:
        upd.launch_installer(staging,extract,os.path.dirname(os.path.abspath(__file__)),sys.executable,BASE,manifest['version'])
    except Exception as exc:
        _update_state['ready']=None
        status_var.set('Pembaruan gagal dijalankan: '+str(exc));return
    _restart_for_update=True
    root.destroy()

def _offer_update(seconds=30):
    manifest=_update_state['ready'][0]
    win=tk.Toplevel(root);_update_state['dialog']=win
    win.title('Pembaruan tersedia');win.configure(bg=PANEL);win.resizable(False,False);win.transient(root)
    body=tk.Frame(win,bg=PANEL,padx=24,pady=20);body.pack(fill='both')
    label(body,'Versi baru tersedia: '+str(manifest['version']),13,bold=True).pack(anchor='w')
    notes=str(manifest.get('notes','')).strip()
    if notes:label(body,notes[:220],9,DIM,wraplength=400,justify='left').pack(anchor='w',pady=(6,0))
    left=tk.IntVar(value=seconds)
    msg=label(body,'',10,GREEN,wraplength=400,justify='left');msg.pack(anchor='w',pady=(12,0))
    label(body,'Aplikasi ditutup, dicadangkan, diperbarui, lalu dibuka kembali otomatis. Data akun tidak berubah.',
          9,DIM,wraplength=400,justify='left').pack(anchor='w',pady=(4,0))
    row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=(16,0))
    state={'alive':True}
    def close():
        state['alive']=False;_update_state['dialog']=None
        try:win.destroy()
        except tk.TclError:pass
    def now():
        close();_apply_ready_update()
    def later():
        _update_state['snooze_until']=time.time()+3600;close()
        status_var.set('Pembaruan %s ditunda 1 jam (atau dipasang saat aplikasi dibuka lagi).'%manifest['version'])
    def tick():
        if not state['alive']:return
        if _app_busy():                       # sinkron/unggah baru dimulai: tunda dulu
            _update_state['snooze_until']=time.time()+60;close();return
        n=left.get()
        msg.config(text='Memperbarui otomatis dalam %d detik…'%n)
        if n<=0:now();return
        left.set(n-1);win.after(1000,tick)
    button(row,'Perbarui sekarang',now,True,icon='refresh').pack(side='left')
    button(row,'Nanti (1 jam)',later,variant='ghost').pack(side='right')
    win.protocol('WM_DELETE_WINDOW',later)
    win.update_idletasks()
    try:
        x=root.winfo_rootx()+(root.winfo_width()-win.winfo_reqwidth())//2
        y=root.winfo_rooty()+max(40,(root.winfo_height()-win.winfo_reqheight())//3)
        win.geometry(f'+{x}+{y}')
    except tk.TclError:pass
    tick()

def visible_metric_card(page, kind):
    """Match the metric heading, not translated page title or a generic h5."""
    for heading in METRIC_LABELS[kind]:
        cards = page.locator('.so-card').filter(
            has=page.locator('h6').get_by_text(heading, exact=True))
        if cards.count():
            values = cards.first.locator('h5')
            if values.count():
                return values.first.inner_text(timeout=5000).strip()
    return None

# Only reads rendered, already-authenticated Artist Insights charts; no private API.
# ECharts SVG labels can be in separate SVG groups, so pair by rendered Y position.
REGION_SVG_JS = r"""() => {
  const heading = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
    .find(el => /^(streams by region|stream berdasarkan wilayah|stream menurut wilayah|streams berdasarkan wilayah)$/i.test(el.textContent.trim()));
  if (!heading) return {error: 'Judul Streams by region tidak ditemukan.'};
  let node = heading.parentElement, chart = null;
  for (let i=0; node && i<7; i++, node=node.parentElement) {
    chart = node.querySelector('[_echarts_instance_] svg');
    if (chart) break;
  }
  if (!chart) return {error: 'Grafik SVG Streams by region belum tersedia. Tunggu grafik dimuat.'};
  const visible = el => {const r=el.getBoundingClientRect();return r.width>0 && r.height>0};
  const text = [...chart.querySelectorAll('text')].filter(visible).map(el=>{
    const r=el.getBoundingClientRect();
    return {text:el.textContent.trim(), y:(r.top+r.bottom)/2};
  });
  const countries=text.filter(t=>/^(US|USA|ID|IDN|PH|GB|MY)\s*[-–]\s*.+$/i.test(t.text)
    || /^[A-Z]{2,3}\s*[-–]\s*.+$/.test(t.text));
  const percents=text.filter(t=>/^\d+(?:[.,]\d+)?\s*%$/.test(t.text));
  if (!countries.length || !percents.length)
    return {error:'Nama negara atau persentase SVG tidak ditemukan. Pastikan grafik terlihat penuh.'};
  const matches=[];
  for (const country of countries) {
    const nearest=[...percents].sort((a,b)=>Math.abs(a.y-country.y)-Math.abs(b.y-country.y))[0];
    if (Math.abs(nearest.y-country.y)>13) continue;
    const code=country.text.split(/\s*[-–]\s*/)[0].toUpperCase();
    const value=Number(nearest.text.replace('%','').replace(',','.').trim());
    if (Number.isFinite(value) && value>=0 && value<=100)
      matches.push({code,name:country.text,percent:value});
  }
  const unique=[...new Map(matches.map(x=>[x.code,x])).values()];
  if (!unique.length) return {error:'Persentase dan nama negara tidak sejajar; pembacaan dibatalkan.'};
  return {regions:unique};
}"""

def read_regions(a):
    period=check_range()
    if not period:return
    if not messagebox.askyesno('Periksa filter Artist Insights',
        'Buka ARTIST INSIGHTS → Overview pada Chrome akun ini dan tampilkan grafik Streams by region.\n\n'
        f'Samakan tanggal SoundOn dengan {period[0]} s.d. {period[1]} dan platform dengan {platform_var.get()}.\n'
        'Pastikan filter SoundOn bukan Last 7 Days jika dashboard memilih satu bulan.\n\n'
        'Data disimpan PER ARTIS (bukan otomatis untuk seluruh akun). Lanjut membaca?',parent=root):return
    if not debugger_ready(a):
        messagebox.showwarning('Chrome belum terhubung','Buka akun dari tombol Buka aplikasi, lalu buka Artist Insights.',parent=root)
        return
    status_var.set('Membaca asal Streams '+a['name']+'…')
    def work():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser=pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port_for(a)}',timeout=10000)
                pages=[page for ctx in browser.contexts for page in ctx.pages
                       if 'soundon.global' in page.url and '/analytics/artist' in page.url]
                if not pages:raise ValueError('Buka halaman Artist Insights (bukan Analytics seluruh akun) pada Chrome akun ini.')
                matches=[]
                for page in reversed(pages):
                    result=page.evaluate(REGION_SVG_JS)
                    if result.get('regions'):
                        artist_id=urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query).get('id',[''])[0]
                        if not artist_id:raise ValueError('ID artis tidak ditemukan di URL Artist Insights.')
                        matches.append((artist_id,result['regions'],page.url))
                if not matches:raise ValueError('Grafik Streams by region belum terbaca. Buka Artist Insights → Overview, gulir ke grafik, dan tunggu hingga muncul.')
                artist_id,regions,url=matches[0]
                ui_call(lambda:finish_regions(a,period,artist_id,regions,url))
        except Exception as ex:
            msg=str(ex)
            if 'No module named' in msg and 'playwright' in msg:msg='Playwright belum terpasang. Jalankan install_dependencies.bat.'
            ui_call(lambda m=msg:messagebox.showerror('Gagal membaca asal Streams',m,parent=root))
    threading.Thread(target=work,daemon=True).start()

def finish_regions(a,period,artist_id,regions,url):
    name=simpledialog.askstring('Nama artis',
        'Masukkan nama artis yang sedang dibuka pada Artist Insights.\n'
        'Persentase ini milik artis tersebut, bukan otomatis seluruh akun:',parent=root)
    if not name or not name.strip():return
    start,end=period;platform=platform_var.get()
    row={'start':str(start),'end':str(end),'platform':platform,
         'artist_id':artist_id,'artist_name':name.strip(),'regions':regions,
         'updated':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
         'source':'SVG Artist Insights; filter tanggal/platform dikonfirmasi pengguna'}
    existing=a.setdefault('region_records',[])
    # Replace a previous reading for the same artist, platform and exact period.
    existing[:]=[old for old in existing if not (str(old.get('artist_id'))==str(artist_id) and old.get('start')==row['start'] and old.get('end')==row['end'] and old.get('platform')==platform)]
    existing.append(row)
    persist();refresh()
    if active_page=='Analytics':
        render_active_page()
    us=next((x['percent'] for x in regions if x['code'] in ('US','USA')),None)
    idn=next((x['percent'] for x in regions if x['code'] in ('ID','IDN')),None)
    fmt=lambda x: ('—' if x is None else f'{x:.2f}%'.replace('.',','))
    messagebox.showinfo('Asal Streams tersimpan',
        f'{a["name"]} · {name.strip()}\n🇮🇩 Indonesia: {fmt(idn)}\n🇺🇸 Amerika Serikat: {fmt(us)}\n'
        f'Periode dikonfirmasi: {start} – {end}\n{len(regions)} wilayah terbaca.',parent=root)

# Saldo di "Penghasilan Saya" bisa disembunyikan (****) dengan ikon mata. Cari teks bintang
# yang terlihat lalu kembalikan posisi ikon terdekat di sebelahnya untuk diklik.
REVEAL_BALANCE_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const masked = [...document.querySelectorAll('body *')].filter(e =>
      [...e.childNodes].some(n => n.nodeType === 3 && /^\s*[*•●]{3,}\s*$/.test(n.textContent)) && vis(e));
  for (const m of masked) {
    const mr = m.getBoundingClientRect();
    let box = m.parentElement;
    for (let k = 0; k < 4 && box; k++, box = box.parentElement) {
      const cand = [...box.querySelectorAll('svg, img, i, [class*="eye"], [class*="Eye"], [role="button"], span, button')]
        .filter(e => e !== m && !e.contains(m) && !m.contains(e) && vis(e))
        .filter(e => !/[A-Za-z0-9]/.test((e.textContent || '').replace(/[*•●]/g, '')))
        .filter(e => { const r = e.getBoundingClientRect(); return r.width <= 48 && r.height <= 48 &&
                         Math.abs((r.top + r.bottom) / 2 - (mr.top + mr.bottom) / 2) < 22 && r.left >= mr.left; });
      if (cand.length) {
        const dist = e => { const r = e.getBoundingClientRect();
          return Math.abs((r.top + r.bottom) / 2 - (mr.top + mr.bottom) / 2) * 3 + (r.left - mr.right); };
        cand.sort((a, b) => dist(a) - dist(b));
        const r = cand[0].getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2];
      }
    }
  }
  return null;
}"""

def reveal_balance(page):
    """Klik ikon mata bila saldo masih tersembunyi (****). True bila ada yang diklik."""
    try:
        point=page.evaluate(REVEAL_BALANCE_JS)
        if point:
            page.mouse.click(point[0],point[1])
            page.wait_for_timeout(1200)
            return True
    except Exception:
        pass
    return False

def visible_available_balance(page):
    """Read labelled available balance; retain the known legacy primary card."""
    reveal_balance(page)
    labels=re.compile(r'(?i)saldo\s+(?:yang\s+)?(?:tersedia|dapat\s+ditarik)|available\s+(?:balance|earnings|to\s+(?:withdraw|withdrawal)|for\s+withdrawal)|withdrawable\s+(?:balance|amount)|balance\s+available|jumlah\s+yang\s+dapat\s+ditarik|akun\s+(?:IDR|USD)|(?:IDR|USD)\s+account')
    label_currency=re.compile(r'(?i)akun\s+(IDR|USD)|(IDR|USD)\s+account')
    selectors=['[class*="royalty-page"] [class*="top-card"]',
               '[class*="royalty"] [class*="card"]',
               '[class*="earnings"] [class*="card"]']
    for selector in selectors:
        cards=page.locator(selector)
        for i in range(cards.count()):
            card=cards.nth(i)
            if not card.is_visible():continue
            text=card.inner_text(timeout=5000)
            if not labels.search(text):continue
            if re.search(r'[*•●]{3,}',text):continue          # masih tersembunyi
            lc=label_currency.search(text)
            card_currency=(lc.group(1) or lc.group(2)).upper() if lc else None
            values=card.locator('h2, h3, [class*="amount"], [class*="balance-value"]')
            candidates=[values.nth(j).inner_text(timeout=3000) for j in range(values.count())]+[text]
            for value in candidates:
                value=value.strip()
                if not re.search(r'(?i)\b(?:IDR|USD)\b|Rp|\$',value):
                    # Kartu "Akun IDR/USD": angka tanpa simbol mata uang.
                    if card_currency and re.fullmatch(r'[0-9][0-9., ]*',value):value=value+' '+card_currency
                    else:continue
                try:
                    n,currency=parse_balance(value)
                    return n,currency,value
                except ValueError:continue
    # Previous releases read the first primary top-card amount on My Earnings.
    # Restrict this fallback to that exact legacy DOM, never generic page amounts.
    legacy=page.locator('[class*="royalty-page"] [class*="top-card"] h2 span[style*="overflow-wrap"]')
    if legacy.count() and legacy.first.is_visible():
        text=legacy.first.inner_text(timeout=5000).strip()
        try:
            n,currency=parse_balance(text)
            return n,currency,text
        except ValueError:pass
    return None


def read_visible(a,kind):
    """Read only the currently open, already-authenticated SoundOn page via local CDP."""
    period=check_range() if kind!='balance' else None
    if kind!='balance' and not period:return
    if period:period=(period[0],period[1],platform_var.get())
    if kind in ('streams','listeners'):
        if not messagebox.askyesno('Cocokkan periode SoundOn',
            f'Atur filter tanggal di halaman SoundOn menjadi {period[0]} s.d. {period[1]} '
            f'dan platform menjadi {platform_var.get()} terlebih dahulu.\n\n'
            'Apakah angka '+('Streams' if kind=='streams' else 'Pendengar')+' yang sedang tampil sudah sesuai?',parent=root):return
    if not debugger_ready(a):
        messagebox.showwarning('Chrome belum terhubung',
            'Tutup seluruh jendela Chrome untuk akun ini, klik Buka dari aplikasi, '
            'login jika perlu, lalu buka halaman Analytics atau Penghasilan Saya. '
            'Setelah halaman terlihat, ulangi Baca.\n\n'
            'Chrome yang dibuka sebelum upgrade tidak dapat dibaca otomatis.',parent=root)
        return
    status_var.set('Membaca '+kind+' dari halaman Chrome '+a['name']+'…')
    def work():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser=pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port_for(a)}',timeout=10000)
                pages=[page for context in browser.contexts for page in context.pages if 'soundon.global' in page.url]
                if not pages:raise ValueError('Tab SoundOn tidak ditemukan pada Chrome akun ini.')
                result=None
                for page in reversed(pages):
                    if kind in ('streams','listeners'):
                        text_value=visible_metric_card(page,kind)
                        if text_value is not None:
                            n,approx=parse_streams_display(text_value)
                            result=(n,approx,text_value)
                            break
                    else:
                        result=visible_available_balance(page)
                        if result is None:
                            try:page.wait_for_selector('[class*="royalty"] h2, [class*="earnings"] h2',state='visible',timeout=4000)
                            except Exception:pass
                            result=visible_available_balance(page)
                        if result is not None:break
                if result is None:raise ValueError('Kartu '+({'streams':'Streams','listeners':'Pendengar / Listeners','balance':'saldo'}[kind])+' tidak ditemukan. Buka Analytics untuk Streams/Pendengar, atau My Earnings untuk saldo tersedia. Tunggu sampai angkanya tampil.')
                ui_call(lambda r=result:finish_read(a,kind,period,r))
        except Exception as ex:
            msg=str(ex)
            if 'No module named' in msg and 'playwright' in msg:msg='Playwright belum terpasang. Jalankan install_dependencies.bat satu kali, lalu coba lagi.'
            ui_call(lambda m=msg:messagebox.showerror('Gagal membaca halaman',m,parent=root))
    threading.Thread(target=work,daemon=True).start()

def finish_read(a,kind,period,result):
    n,approx,raw=result
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if kind=='balance':
        a['balance']=n;a['currency']=approx;a['balance_updated']=now
        persist();refresh()
        messagebox.showinfo('Saldo terbaca',f'{a["name"]}: {account_money(a)}',parent=root)
    else:
        start,end,plat=period
        # Preserve the other metric for this exact date range and platform.
        old=latest(a,start,end,plat)
        record={'start':str(start),'end':str(end),'platform':plat,
                'streams':(n if kind=='streams' else old.get('streams',0) if old else 0),
                'listeners':(n if kind=='listeners' else old.get('listeners',0) if old else 0),
                'updated':now,'source':'visible SoundOn page'}
        if old:
            for key in ('streams_display','streams_approx','listeners_display','listeners_approx'):
                if key in old:record[key]=old[key]
        record[kind+'_display']=raw
        record[kind+'_approx']=approx
        upsert_record(a,record)
        persist();refresh()
        note=' (perkiraan karena SoundOn menyingkat angka)' if approx else ''
        title='Streams' if kind=='streams' else 'Pendengar'
        messagebox.showinfo(title+' terbaca',f'{a["name"]}: {raw} → {number(n)}{note}\nPeriode: {start} s.d. {end}',parent=root)

def edit(a):
    period=check_range()
    if not period:return
    start,end=period; plat=platform_var.get(); old=latest(a,start,end,plat)
    w=tk.Toplevel(root);w.title('Data SoundOn — '+a['name']);w.geometry('510x735');w.configure(bg=PANEL);w.transient(root);w.grab_set()
    label(w,'Input data dari SoundOn',15,bold=True).pack(anchor='w',padx=24,pady=(22,5))
    label(w,f'{start} s.d. {end} · {plat}',10,DIM).pack(anchor='w',padx=24,pady=(0,8))
    label(w,'Angka periode harus sesuai filter. Saldo adalah saldo saat ini.',9,DIM,wraplength=450,justify='left').pack(anchor='w',padx=24,pady=(0,14))
    fields={}
    for name,key,value in [('Streams (periode)','streams',old.get('streams',0) if old else 0),('Pendengar (periode)','listeners',old.get('listeners',0) if old else 0),('Saldo tersedia','balance',format_amount(a.get('balance',0),a.get('currency','IDR')))]:
        row=tk.Frame(w,bg=PANEL);row.pack(fill='x',padx=24,pady=7)
        label(row,name,10,DIM).pack(anchor='w')
        v=tk.StringVar(value=str(value)); fields[key]=v
        tk.Entry(row,textvariable=v,bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',font=(FONT,11)).pack(fill='x',ipady=8,pady=(5,0))
    currency_row=tk.Frame(w,bg=PANEL);currency_row.pack(fill='x',padx=24,pady=5)
    label(currency_row,'Mata uang saldo',10,DIM).pack(anchor='w')
    currency_var=tk.StringVar(value=a.get('currency','IDR'))
    ttk.Combobox(currency_row,textvariable=currency_var,values=['IDR','USD'],state='readonly',width=15,style='Dark.TCombobox').pack(anchor='w',pady=4)
    hp_row=tk.Frame(w,bg=PANEL);hp_row.pack(fill='x',padx=24,pady=7)
    label(hp_row,'Jumlah HP untuk akun ini',10,DIM).pack(anchor='w')
    hp_var=tk.StringVar(value=str(a.get('phone_count',0)))
    tk.Entry(hp_row,textvariable=hp_var,bg=CARD,fg=WHITE,insertbackground=WHITE,
             relief='flat',font=(FONT,11)).pack(fill='x',ipady=8,pady=(5,0))
    catalog_vars={}
    for title,key in [('Jumlah artis','artist_count'),('Jumlah lagu','song_count')]:
        row=tk.Frame(w,bg=PANEL);row.pack(fill='x',padx=24,pady=6)
        label(row,title,10,DIM).pack(anchor='w')
        v=tk.StringVar(value=str(a.get(key,0)));catalog_vars[key]=v
        tk.Entry(row,textvariable=v,bg=CARD,fg=WHITE,insertbackground=WHITE,
            relief='flat',font=(FONT,11)).pack(fill='x',ipady=7,pady=(4,0))
    def save_data():
        try:
            values={k:int(v.get().strip().replace('.','').replace(',','').replace(' ','')) for k,v in fields.items() if k in ('streams','listeners')}
            values['balance']=parse_amount(fields['balance'].get(),currency_var.get())
            if any(v<0 for v in values.values()):raise ValueError()
            hp_text=hp_var.get().strip()
            if not hp_text.isdecimal():raise ValueError()
            hp_value=int(hp_text)
            if hp_value>100000:raise ValueError()
            catalog_values={k:int(v.get().strip()) for k,v in catalog_vars.items() if v.get().strip().isdecimal()}
            if len(catalog_values)!=2 or any(n>1000000 for n in catalog_values.values()):raise ValueError()
        except ValueError:
            messagebox.showerror('Angka tidak valid','Isi angka positif. Contoh saldo IDR: 4.160.229 atau 4160229; USD: 12,50 atau 12.50.',parent=w);return
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        upsert_record(a,{'start':str(start),'end':str(end),'platform':plat,'streams':values['streams'],'listeners':values['listeners'],'updated':now,'source':'input manual'})
        balance_changed=abs(values['balance']-float(a.get('balance') or 0))>0.004 or currency_var.get()!=a.get('currency','IDR')
        a['balance']=values['balance'];a['currency']=currency_var.get()
        if balance_changed or not a.get('balance_updated'):a['balance_updated']=now
        a['phone_count']=hp_value;a.update(catalog_values)
        persist();w.destroy();refresh()
    button(w,'Simpan data periode',save_data,True).pack(anchor='e',padx=24,pady=18)

def panel(parent):return RoundedPanel(parent,outer=parent.cget('bg'))
def clear(parent):
    for c in parent.winfo_children():c.destroy()

# Chrome status is checked in a worker thread; the Tk event loop never waits
# on a localhost socket for every account during search, sort or refresh.
_chrome_status={}
_status_busy=False

def poll_chrome_status():
    global _status_busy
    if _status_busy:return
    _status_busy=True
    snapshot=[(str(a['id']),a) for a in accounts]
    def worker():
        result={key:debugger_ready(a) for key,a in snapshot}
        def done():
            global _status_busy
            _status_busy=False
            if result!=_chrome_status:
                _chrome_status.clear();_chrome_status.update(result)
                sidebar_connected.set(str(sum(bool(v) for v in result.values())))
                # Hanya Dashboard yang menampilkan status Chrome; halaman lain tidak dibangun ulang.
                if active_page=='Dashboard':refresh()
        ui_call(done)
    threading.Thread(target=worker,daemon=True).start()

def _page_key():
    return (DATA_VERSION[0],platform_var.get(),start_var.get(),end_var.get())

def _sync_pages():
    # Halaman dirender ulang hanya bila data atau filter berubah (tidak basi, tidak berat).
    if active_page!='Dashboard' and page_rendered.get(active_page)!=_page_key():
        render_active_page();page_rendered[active_page]=_page_key()

def short_name(text,limit=26):
    text=str(text)
    return text if len(text)<=limit else text[:limit-1].rstrip()+'…'

def short_time(value):
    try:return datetime.strptime(str(value)[:19],'%Y-%m-%d %H:%M:%S').strftime('%d/%m %H:%M')
    except (TypeError,ValueError):return str(value or '—')[:16]

def refresh():
    try:
        start=parse_date(start_var.get());end=parse_date(end_var.get())
        if end<start:raise ValueError()
    except ValueError:return
    plat=platform_var.get();query=search_var.get().lower().strip();selected_category=category_var.get()
    data=[]
    for a in accounts:
        if query and query not in a['name'].lower() and query not in str(a['id']):continue
        if selected_category!='Semua Kategori' and account_category(a)!=selected_category:continue
        data.append((a,latest(a,start,end,plat)))
    key=sort_var.get()
    if key=='Streams terbanyak':data.sort(key=lambda x:x[1].get('streams',-1) if x[1] else -1,reverse=True)
    elif key=='Streams tersedikit':data.sort(key=lambda x:x[1].get('streams',float('inf')) if x[1] else float('inf'))
    elif key=='Saldo terbesar':data.sort(key=lambda x:(x[0].get('currency','IDR'),float(x[0].get('balance',0))),reverse=True)
    elif key=='Nama A–Z':data.sort(key=lambda x:x[0]['name'].lower())
    total_stream=sum(r.get('streams',0) for a,r in data if r)
    total_listeners=sum(r.get('listeners',0) for a,r in data if r)
    total_balance=grouped_balance([a for a,r in data])
    update_country_panels(start,end,plat)
    update_inventory_dashboard()
    connected=sum(bool(_chrome_status.get(str(a['id']),False)) for a in accounts)
    sidebar_total.set(str(len(accounts)))
    sidebar_connected.set(str(connected))
    last_update.set('Diperbarui lokal: '+datetime.now().strftime('%d/%m/%Y %H:%M'))
    status_var.set(f'{len(data)} akun ditampilkan  ·  {sum(bool(r) for a,r in data)} akun memiliki data periode ini  ·  Streams bertanda ≈ adalah perkiraan')
    if view_var.get()=='Kolom Negara':
        if account_table.winfo_manager():account_table.pack_forget()
        if sel_bar.winfo_manager():sel_bar.pack_forget()
        if not country_box.winfo_manager():country_box.pack(fill='both',expand=True)
        clear(rows)
        for _c in range(12):rows.grid_columnconfigure(_c,weight=0,uniform='',minsize=0)
        render_country_columns(data)
        totals_var.set(f'TOTAL  ·  Streams: {number(total_stream)}   ·   Pendengar: {number(total_listeners)}   ·   Saldo: {total_balance}')
        _sync_pages()
        return
    if sel_bar.winfo_manager() and not account_table.selected:sel_bar.pack_forget()
    if country_box.winfo_manager():country_box.pack_forget();clear(rows)
    if not account_table.winfo_manager():account_table.pack(fill='both',expand=True,padx=8,pady=8)
    table_rows=[]
    for idx,(a,r) in enumerate(data):
        streams=number(r.get('streams',0)) if r else '—'
        if r and r.get('streams_approx'):streams+=' ≈'
        table_rows.append({'account':a,'idx':str(idx+1),'name':a['name'],'sub':'#'+str(a['id'])+'  ·  '+account_category(a),
            'accent':ACCENTS[idx%len(ACCENTS)],'online':bool(_chrome_status.get(str(a['id']),False)),
            'has_period':bool(r),'streams':streams,'listeners':number(r.get('listeners',0)) if r else '—',
            'hp':number(a.get('phone_count',0)),'artists':number(a.get('artist_count',0)),'songs':number(a.get('song_count',0)),
            'balance':account_money(a) if a.get('balance_updated') else 'Belum dibaca','balance_known':bool(a.get('balance_updated')),
            'chart':r.get('streams',0) if r else None,'updated':short_time(r.get('updated')) if r else '—'})
    account_table.set_rows(table_rows,'Belum ada akun yang cocok. Ubah filter atau klik Tambah Akun.')
    _selection_changed(len(account_table.selected))
    totals_var.set(f'TOTAL  ·  Streams: {number(total_stream)}   ·   Pendengar: {number(total_listeners)}   ·   Saldo: {total_balance}')
    _sync_pages()

def render_country_columns(data):
    """Show country groups in two independent side-by-side columns."""
    grouped={}
    for a,r in data:grouped.setdefault(account_category(a),[]).append((a,r))
    names=[c for c in categories if c in grouped]
    names += [c for c in grouped if c not in names]
    if not names:
        label(rows,'Tidak ada akun pada kategori ini.',12,DIM).pack(padx=22,pady=30)
        return
    for i,name in enumerate(names):
        col=i%2; row=i//2
        rows.grid_columnconfigure(col,weight=1,uniform='country')
        group=tk.Frame(rows,bg=CARD,highlightbackground=LINE,highlightthickness=1)
        group.grid(row=row,column=col,sticky='nsew',padx=10,pady=10)
        members=grouped[name]
        gs=sum((r or {}).get('streams',0) for a,r in members)
        gl=sum((r or {}).get('listeners',0) for a,r in members)
        gb=sum(float(a.get('balance',0)) for a,r in members)
        header=tk.Frame(group,bg=CARD);header.pack(fill='x',padx=14,pady=(13,8))
        label(header,name,14,bold=True).pack(side='left')
        label(header,f'{len(members)} akun',9,DIM).pack(side='right')
        label(group,f'Streams {number(gs)}   ·   Pendengar {number(gl)}',10,GREEN).pack(anchor='w',padx=14)
        label(group,f'Jumlah HP {sum(int(a.get("phone_count",0)) for a,r in members)}',10,BLUE).pack(anchor='w',padx=14,pady=(2,0))
        label(group,f'Saldo {grouped_balance([a for a,r in members])}',10,DIM).pack(anchor='w',padx=14,pady=(2,10))
        for a,r in members:
            line=tk.Frame(group,bg=PANEL);line.pack(fill='x',padx=10,pady=5)
            top=tk.Frame(line,bg=PANEL);top.pack(fill='x',padx=10,pady=(9,2))
            label(top,a['name'],11,bold=True).pack(side='left')
            label(top,'● Aktif' if _chrome_status.get(str(a['id']),False) else '● Tertutup',9,GREEN if _chrome_status.get(str(a['id']),False) else DIM).pack(side='right')
            metrics=tk.Frame(line,bg=PANEL);metrics.pack(fill='x',padx=10)
            streams=(number(r.get('streams',0))+(' ≈' if r.get('streams_approx') else '')) if r else '—'
            label(metrics,f'Streams: {streams}  |  Pendengar: {number(r.get("listeners",0)) if r else "—"}',9,DIM).pack(anchor='w')
            label(metrics,f'Jumlah HP: {a.get("phone_count",0)}',9,BLUE).pack(anchor='w',pady=(3,0))
            label(metrics,f'Saldo: {account_money(a) if a.get("balance_updated") else "—"}',9,DIM).pack(anchor='w',pady=(3,0))
            acts=tk.Frame(line,bg=PANEL);acts.pack(fill='x',padx=8,pady=(4,8))
            button(acts,'Buka',lambda a=a:open_streams(a),True,height=28,font_size=9,padx=10).pack(side='left',padx=2)
            for title,fn in [('Streams',lambda a=a:read_visible(a,'streams')),('Pendengar',lambda a=a:read_visible(a,'listeners')),('Saldo',lambda a=a:read_visible(a,'balance'))]:
                button(acts,title,fn,height=28,font_size=9,padx=9).pack(side='left',padx=2)
            RoundButton(acts,'',lambda a=a:show_actions(a),icon='more',height=28,padx=6).pack(side='left',padx=2)

def restart_app():
    """Buka ulang aplikasi (dipakai saat mengganti mode tampilan)."""
    app_dir=os.path.dirname(os.path.abspath(__file__))
    bat=os.path.join(app_dir,'run_app.bat')
    try:
        if os.name=='nt' and os.path.exists(bat):
            subprocess.Popen(['cmd','/c',bat],cwd=app_dir,creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0),close_fds=True)
        else:
            subprocess.Popen([sys.executable,os.path.join(app_dir,'soundon_dashboard.py')],cwd=app_dir)
    except OSError as ex:
        messagebox.showerror('Gagal membuka ulang',str(ex)+'\n\nTutup lalu buka aplikasi secara manual.',parent=root);return
    os._exit(75)

def set_theme(mode):
    if mode==UI.THEME:return
    um=globals().get('upload_manager_window')
    if um is not None and getattr(um,'busy',False):
        messagebox.showinfo('Unggahan berjalan','Tunggu unggahan selesai atau tekan Hentikan sebelum mengganti tampilan.',parent=root);return
    try:UI.save_settings(theme=mode)
    except OSError as ex:
        messagebox.showerror('Gagal menyimpan',str(ex),parent=root);return
    if messagebox.askyesno('Ganti tampilan',('Mode terang' if mode=='light' else 'Mode gelap')+' dipilih.\n\nBuka ulang aplikasi sekarang untuk menerapkannya?',parent=root):
        restart_app()

def show_actions(a):
    w=tk.Toplevel(root);w.title(a['name']);w.configure(bg=PANEL);w.transient(root);w.resizable(False,False)
    head=tk.Frame(w,bg=PANEL);head.pack(fill='x',padx=20,pady=(20,14))
    avatar(head,a['name'],PURPLE,40,PANEL).pack(side='left',padx=(0,12))
    ht=tk.Frame(head,bg=PANEL);ht.pack(side='left')
    label(ht,a['name'],13,bold=True).pack(anchor='w')
    label(ht,'Akun #'+str(a['id'])+'  ·  '+account_category(a),9,DIM).pack(anchor='w')
    items=[('Ubah nama','edit',lambda:rename(a),'secondary'),
           ('Atur jumlah HP, artis & lagu','grid',lambda:edit_account_counts(a),'secondary'),
           ('Pindahkan kategori / negara','tag',lambda:change_category(a),'secondary'),
           ('Kredensial login','key',lambda:edit_credentials(a),'secondary'),
           ('Hapus akun & profil','trash',lambda:delete(a),'danger')]
    for text,icon_name,fn,variant in items:
        RoundButton(w,text,lambda fn=fn:(w.destroy(),fn()),icon=icon_name,variant=variant,width=320,height=38).pack(padx=20,pady=3)
    tk.Frame(w,bg=PANEL,height=14).pack()
    w.update_idletasks()
    try:w.geometry(f'+{root.winfo_pointerx()-180}+{max(20,root.winfo_pointery()-120)}')
    except tk.TclError:pass

def open_update_settings():
    """Pengaturan pembaruan otomatis dari GitHub Releases + pemeriksaan manual."""
    import updater as upd
    app_dir=os.path.dirname(os.path.abspath(__file__))
    win=tk.Toplevel(root)
    win.title('Pembaruan aplikasi')
    win.configure(bg=PANEL)
    win.transient(root)
    win.resizable(False,False)
    body=tk.Frame(win,bg=PANEL);body.pack(fill='both',expand=True,padx=24,pady=22)
    head=tk.Frame(body,bg=PANEL);head.pack(fill='x')
    icon_badge(head,'cloud',PURPLE,PANEL,40).pack(side='left',padx=(0,12))
    ht=tk.Frame(head,bg=PANEL);ht.pack(side='left')
    label(ht,'Pembaruan Aplikasi',15,bold=True).pack(anchor='w')
    label(ht,'Versi terpasang: '+APP_VERSION,9,DIM).pack(anchor='w')
    cfg=upd.load_config(app_dir)
    label(body,'REPO GITHUB',8,MUTED,bold=True).pack(anchor='w',pady=(20,6))
    repo_var=tk.StringVar(value=cfg.get('github_repo',''))
    UI.styled_entry(body,repo_var,width=52,font_size=10).pack(fill='x',ipady=7)
    label(body,'Format: username/nama-repo',8,MUTED).pack(anchor='w',pady=(4,0))
    auto_var=tk.BooleanVar(value=cfg.get('auto_update',True))
    UI.dark_checkbutton(body,'  Perbarui otomatis setiap kali aplikasi dibuka',auto_var,PANEL).pack(anchor='w',pady=(14,0))
    note_box=UI.RoundedPanel(body,outer=PANEL,color=mix_card(BLUE),radius=10);note_box.pack(fill='x',pady=(14,0))
    note=tk.Frame(note_box,bg=mix_card(BLUE));note.pack(fill='x',padx=14,pady=11)
    UI.icon(note,'info',16,BLUE,mix_card(BLUE)).pack(side='left',anchor='n',padx=(0,9),pady=1)
    label(note,'Aplikasi mencocokkan SHA-256, mencadangkan file lama ke SoundOnAccounts\\update_backups, lalu membuka ulang. '
          'Data akun, antrean, profil Chrome dan soundon.license tidak disentuh.',9,DIM,wraplength=470,justify='left').pack(side='left')
    status=tk.StringVar(value='Belum diperiksa.')
    status_label=tk.Label(body,textvariable=status,bg=PANEL,fg=DIM,font=(FONT,9),wraplength=520,justify='left')
    status_label.pack(anchor='w',pady=(14,0))
    def set_status(text,color=DIM):
        status.set(text);status_label.configure(fg=color)

    def save_source():
        try:repo=upd.normalize_repo(repo_var.get())
        except ValueError as exc:
            messagebox.showerror('Repo tidak valid',str(exc),parent=win);return False
        repo_var.set(repo)
        new_cfg=dict(cfg,github_repo=repo,auto_update=auto_var.get())
        try:upd.save_config(app_dir,new_cfg)
        except OSError as exc:
            messagebox.showerror('Gagal menyimpan',str(exc),parent=win);return False
        cfg.update(new_cfg)
        if active_page=='Pengaturan':render_active_page()
        return True

    def check():
        if not save_source():return
        url=upd.manifest_url_for(cfg)
        if not url:
            messagebox.showinfo('Sumber belum diatur','Isi repo GitHub tempat rilis aplikasi diterbitkan, contoh: username/soundon-update.',parent=win);return
        set_status('Memeriksa pembaruan…',DIM)
        def worker():
            try:
                manifest=upd.read_manifest(url,cfg.get('github_repo',''))
                newer=upd.version_newer(manifest['version'],APP_VERSION)
                def finish():
                    global _restart_for_update
                    if not win.winfo_exists():return
                    if not newer:
                        set_status('✓  Sudah versi terbaru (rilis GitHub: '+manifest['version']+').',GREEN);return
                    set_status('Versi '+manifest['version']+' tersedia. '+str(manifest.get('notes','')),AMBER)
                    if messagebox.askyesno('Pasang pembaruan','Pasang versi '+manifest['version']+' sekarang?\n\nPastikan tidak ada unggahan yang sedang berjalan. '
                                           'Aplikasi akan ditutup, dicadangkan, lalu dibuka kembali.',parent=win):
                        set_status('Mengunduh pembaruan…',DIM);win.update_idletasks()
                        try:upd.begin_update(manifest,app_dir,sys.executable,BASE)
                        except Exception as exc:
                            messagebox.showerror('Pembaruan gagal',str(exc),parent=win);set_status('Pembaruan gagal: '+str(exc),RED);return
                        _restart_for_update=True
                        root.destroy()
                ui_call(finish)
            except Exception as exc:
                msg=str(exc)
                if 'HTTP Error 404' in msg:msg='Belum ada rilis di repo ini (manifest.json tidak ditemukan), atau repo bersifat privat.'
                ui_call(lambda m=msg: set_status('Gagal memeriksa: '+m,RED) if win.winfo_exists() else None)
        threading.Thread(target=worker,daemon=True).start()
    actions=tk.Frame(body,bg=PANEL);actions.pack(fill='x',pady=(18,0))
    button(actions,'Periksa sekarang',check,True,icon='refresh').pack(side='left',padx=(0,8))
    button(actions,'Simpan',lambda:save_source() and set_status('Pengaturan pembaruan tersimpan.',GREEN),icon='check').pack(side='left')
    button(actions,'Tutup',win.destroy,variant='ghost').pack(side='right')
    win.update_idletasks()
    try:
        x=root.winfo_rootx()+(root.winfo_width()-win.winfo_reqwidth())//2
        y=root.winfo_rooty()+max(40,(root.winfo_height()-win.winfo_reqheight())//3)
        win.geometry(f'+{x}+{y}')
    except tk.TclError:pass


def _open_path(path):
    try:
        os.makedirs(path,exist_ok=True)
        if os.name=='nt':os.startfile(path)
        else:subprocess.Popen(['xdg-open',path])
    except OSError as ex:messagebox.showerror('Gagal membuka folder',str(ex),parent=root)

def open_publisher_settings():
    """Token GitHub untuk Penerbit Otomatis (hanya di komputer admin)."""
    import release_publisher as rp, updater as upd
    repo=upd.load_config(_APP_DIR).get('github_repo') or upd.DEFAULT_GITHUB_REPO
    win=tk.Toplevel(root);win.title('Penerbit otomatis');win.configure(bg=PANEL);win.resizable(False,False);win.transient(root)
    body=tk.Frame(win,bg=PANEL,padx=24,pady=20);body.pack(fill='both')
    label(body,'Penerbit Otomatis',14,bold=True).pack(anchor='w')
    label(body,'Hanya untuk komputer admin. Dengan token ini, paket rilis yang masuk ke folder\n'+str(rp.INBOX)+
          '\nlangsung diterbitkan ke GitHub ('+repo+') dan semua aplikasi klien memperbarui otomatis.',9,DIM,justify='left').pack(anchor='w',pady=(4,10))
    label(body,'Buat di GitHub > Settings > Developer settings > Fine-grained tokens: Repository access = hanya '+repo+
          ', Permissions > Contents = Read and write.',9,MUTED,wraplength=460,justify='left').pack(anchor='w',pady=(0,8))
    var=tk.StringVar(value=rp.load_token())
    ent=UI.styled_entry(body,var,width=52,show='•')
    ent.pack(fill='x',ipady=4)
    msg=tk.StringVar(value='Token tersimpan.' if var.get() else 'Belum ada token.')
    msg_l=tk.Label(body,textvariable=msg,font=(FONT,9),fg=DIM,bg=PANEL,wraplength=460,justify='left');msg_l.pack(anchor='w',pady=(8,0))
    def say(text,color=DIM):
        if win.winfo_exists():msg.set(text);msg_l.config(fg=color)
    def save():
        token=var.get().strip()
        try:rp.save_token(token)
        except (rp.PublishError,OSError) as ex:say(str(ex),RED);return
        if not token:say('Token dihapus. Penerbit otomatis mati.',AMBER);return
        say('Menguji token…')
        def work():
            try:text,col='✓  '+rp.check_token(token,repo)+' Folder rilis: '+str(rp.INBOX),GREEN
            except rp.PublishError as ex:text,col=str(ex),RED
            ui_call(lambda:say(text,col))
        threading.Thread(target=work,daemon=True).start()
    def remove():
        var.set('');save()
    row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=(14,0))
    button(row,'Simpan & uji',save,True,icon='check').pack(side='left')
    button(row,'Hapus token',remove,variant='danger').pack(side='left',padx=8)
    button(row,'Tutup',lambda:(win.destroy(),render_active_page() if active_page=='Pengaturan' else None),variant='ghost').pack(side='right')
    win.update_idletasks()
    try:
        x=root.winfo_rootx()+(root.winfo_width()-win.winfo_reqwidth())//2
        y=root.winfo_rooty()+max(40,(root.winfo_height()-win.winfo_reqheight())//3)
        win.geometry(f'+{x}+{y}')
    except tk.TclError:pass

_publish_state={'busy':False}
def _publisher_watcher():
    """Komputer admin: terbitkan paket di ~/SoundOnRilis/masuk ke GitHub (cek tiap menit)."""
    try:
        import release_publisher as rp
        if not _publish_state['busy'] and rp.load_token() and (rp.INBOX/'manifest.json').exists():
            import updater as upd
            repo=upd.load_config(_APP_DIR).get('github_repo') or upd.DEFAULT_GITHUB_REPO
            _publish_state['busy']=True
            ui_call(lambda:status_var.set('Menerbitkan rilis baru ke GitHub…'))
            def work():
                try:
                    v=rp.process_inbox(repo)
                    if v:
                        _update_state['last_check']=0      # aplikasi ini sendiri ikut memperbarui
                        ui_call(lambda:status_var.set('Rilis %s diterbitkan ke GitHub. Semua aplikasi memperbarui otomatis.'%v))
                except Exception as ex:
                    ui_call(lambda m=str(ex):status_var.set('Penerbitan rilis gagal: '+m))
                finally:
                    _publish_state['busy']=False
            threading.Thread(target=work,daemon=True).start()
    except Exception:
        _publish_state['busy']=False
    finally:
        root.after(60000,_publisher_watcher)


# Dedicated sidebar pages. The dashboard remains mounted behind the page overlay;
# switching pages does not destroy browser sessions or rebuild the main window.
active_page='Dashboard'
page_overlay=None
page_body=None
page_window=None
page_bodies={}
page_windows={}
page_rendered={}
page_title=None
page_subtitle=None
nav_controls={}

def _transfer_key(password, salt):
    try:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError('Library cryptography belum terpasang. Jalankan install_dependencies.bat.')
    kdf=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=390000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8'))))

def edit_credentials(a):
    w=tk.Toplevel(root);w.title('Kredensial — '+a.get('name','Akun'));w.geometry('500x360')
    w.configure(bg=PANEL);w.transient(root);w.grab_set();w.resizable(False,False)
    label(w,'Kredensial akun',15,bold=True).pack(anchor='w',padx=25,pady=(24,5))
    label(w,'Data ini tersimpan lokal dan hanya ikut transfer jika Anda mengekspor paket akun.',9,DIM,wraplength=440,justify='left').pack(anchor='w',padx=25,pady=(0,15))
    vals={}
    for title,key,show in [('Email / username','login_email',''),('Password','login_password','•')]:
        row=tk.Frame(w,bg=PANEL);row.pack(fill='x',padx=25,pady=8)
        label(row,title,10,DIM).pack(anchor='w',pady=(0,5))
        v=tk.StringVar(value=str(a.get(key,'')));vals[key]=v
        e=tk.Entry(row,textvariable=v,show=show,bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',font=(FONT,11))
        e.pack(fill='x',ipady=8)
    def save_creds():
        a['login_email']=vals['login_email'].get().strip();a['login_password']=vals['login_password'].get()
        persist();w.destroy();refresh();messagebox.showinfo('Tersimpan','Kredensial akun tersimpan secara lokal.',parent=root)
    button(w,'Simpan Kredensial',save_creds,True).pack(anchor='e',padx=25,pady=(18,0))

def export_transfer_package():
    if not accounts:
        messagebox.showinfo('Transfer Akun','Belum ada akun untuk diekspor.',parent=root);return
    password=simpledialog.askstring('Password Transfer','Buat password transfer (minimal 8 karakter):',show='*',parent=root)
    if password is None:return
    if len(password)<8:
        messagebox.showerror('Password terlalu pendek','Gunakan minimal 8 karakter.',parent=root);return
    confirm=simpledialog.askstring('Konfirmasi Password','Ulangi password transfer:',show='*',parent=root)
    if confirm!=password:
        messagebox.showerror('Tidak cocok','Konfirmasi password tidak cocok.',parent=root);return
    path=filedialog.asksaveasfilename(title='Ekspor Paket Akun',defaultextension='.sndpack',initialfile='SoundOn_Transfer_'+date.today().isoformat()+'.sndpack',filetypes=[('SoundOn Transfer','*.sndpack')],parent=root)
    if not path:return
    try:
        salt=os.urandom(16);fernet=_transfer_key(password,salt)
        payload={'format':'soundon-transfer-v1','created':datetime.now().isoformat(timespec='seconds'),'accounts':accounts,'categories':categories,'phone_inventory':phone_inventory,'owners':owners}
        encrypted=fernet.encrypt(json.dumps(payload,ensure_ascii=False).encode('utf-8'))
        wrapper={'format':'soundon-transfer-encrypted-v1','salt':base64.b64encode(salt).decode('ascii'),'data':encrypted.decode('ascii')}
        with open(path,'w',encoding='utf-8') as f:json.dump(wrapper,f,ensure_ascii=False)
        messagebox.showinfo('Ekspor berhasil','Paket akun berhasil dibuat.\n\nPassword transfer harus diberikan secara terpisah kepada penerima.\nCookies/session Chrome tidak disertakan.',parent=root)
    except Exception as ex:messagebox.showerror('Ekspor gagal',str(ex),parent=root)

def import_transfer_package():
    path=filedialog.askopenfilename(title='Impor Paket Akun',filetypes=[('SoundOn Transfer','*.sndpack'),('Semua file','*.*')],parent=root)
    if not path:return
    password=simpledialog.askstring('Password Transfer','Masukkan password transfer:',show='*',parent=root)
    if password is None:return
    try:
        from cryptography.fernet import InvalidToken
        with open(path,encoding='utf-8') as f:wrapper=json.load(f)
        salt=base64.b64decode(wrapper['salt']);fernet=_transfer_key(password,salt)
        payload=json.loads(fernet.decrypt(wrapper['data'].encode('ascii')).decode('utf-8'))
        incoming=payload.get('accounts',[])
        if not isinstance(incoming,list):raise ValueError('Isi paket tidak valid.')
    except Exception as ex:
        msg='Password transfer salah atau paket rusak.' if ex.__class__.__name__=='InvalidToken' else str(ex)
        messagebox.showerror('Impor gagal',msg,parent=root);return
    choice=messagebox.askyesnocancel('Cara Impor',f'Ditemukan {len(incoming)} akun.\n\nYA = Gabungkan dengan data saat ini\nTIDAK = Ganti seluruh data akun\nBATAL = Batalkan',parent=root)
    if choice is None:return
    # ID akun menentukan folder profil Chrome (Account_<id>). ID yang bentrok dengan
    # profil yang sudah ada diberi ID baru agar akun tidak memakai login akun lain.
    def used_profile_ids():
        ids=set()
        try:
            for name in os.listdir(BASE):
                m=re.fullmatch(r'Account_(\d+)',name)
                if m and os.path.isdir(os.path.join(BASE,name)):ids.add(int(m.group(1)))
        except OSError:pass
        return ids
    if choice is False:
        taken=used_profile_ids()
        kept=[];next_id=max(list(taken)+[int(x.get('id',0) or 0) for x in incoming]+[0])+1
        for src in incoming:
            item=dict(src)
            try:item_id=int(item.get('id'))
            except (TypeError,ValueError):item_id=None
            if item_id is None or item_id in taken or item_id in {k['id'] for k in kept}:
                item_id=next_id;next_id+=1
            item['id']=item_id;kept.append(item)
        accounts.clear();accounts.extend(kept)
    else:
        # Merge as new local accounts; assign fresh IDs so profiles never collide.
        next_id=max([int(a.get('id',0)) for a in accounts]+list(used_profile_ids())+[0])+1
        for src in incoming:
            item=dict(src);item['id']=next_id;next_id+=1
            # Browser session/profile is intentionally recreated locally.
            accounts.append(item)
    _chrome_status.clear()
    incoming_owners=payload.get('owners',[])
    if isinstance(incoming_owners,list):
        if choice is False:owners.clear()
        for name in incoming_owners:
            if isinstance(name,str) and name.strip() and name.casefold() not in {x.casefold() for x in owners}:owners.append(name.strip())
        save_owners()
    for c in payload.get('categories',[]):
        if isinstance(c,str) and c.strip() and c.strip() not in categories:categories.append(c.strip())
    inv=payload.get('phone_inventory')
    if isinstance(inv,dict):
        for k in ('tersedia','service','rusak','tidak_terpakai'):
            try: phone_inventory[k]=max(0,int(inv.get(k,phone_inventory.get(k,0))))
            except (TypeError,ValueError): pass
        phone_inventory['catatan']=str(inv.get('catatan',phone_inventory.get('catatan','')))
        save_phone_inventory()
    persist();save_categories();refresh()
    messagebox.showinfo('Impor berhasil',f'{len(incoming)} akun berhasil diimpor.\nProfil Chrome baru akan digunakan di komputer ini; login ulang ke SoundOn bila diperlukan.',parent=root)

def backup_account_data():
    path=filedialog.asksaveasfilename(title='Cadangkan data akun',defaultextension='.json',
        initialfile='soundon_accounts_backup_'+date.today().isoformat()+'.json',
        filetypes=[('JSON','*.json')],parent=root)
    if not path:return
    try:
        with open(path,'w',encoding='utf-8') as f:
            json.dump({'accounts':accounts,'categories':categories,'phone_inventory':phone_inventory,'owners':owners},f,ensure_ascii=False,indent=2)
        messagebox.showinfo('Backup berhasil','Data akun, kategori, dan inventaris HP berhasil dicadangkan. Profil Chrome tidak termasuk.',parent=root)
    except OSError as ex:messagebox.showerror('Backup gagal',str(ex),parent=root)

def page_section(parent,title,description='',icon_name=None,accent=PURPLE):
    box=panel(parent);box.pack(fill='x',padx=8,pady=(10,4))
    inner=tk.Frame(box,bg=PANEL);inner.pack(fill='x',padx=18,pady=14)
    head=tk.Frame(inner,bg=PANEL);head.pack(fill='x',pady=(0,10 if not description else 0))
    if icon_name:icon_badge(head,icon_name,accent,PANEL,34).pack(side='left',padx=(0,12))
    texts=tk.Frame(head,bg=PANEL);texts.pack(side='left',fill='x',expand=True)
    label(texts,title,13,bold=True).pack(anchor='w')
    if description:label(texts,description,9,DIM,wraplength=1000,justify='left').pack(anchor='w',pady=(2,12))
    return inner

def page_metric(parent,title,value,color=PURPLE,icon_name=None):
    box=UI.RoundedPanel(parent,outer=bg_of(parent),color=CARD,radius=10)
    col=len(parent.grid_slaves());parent.grid_columnconfigure(col,weight=1,uniform='page_metric')
    box.grid(row=0,column=col,sticky='nsew',padx=4)
    inner=tk.Frame(box,bg=CARD);inner.pack(fill='both',expand=True,padx=14,pady=12)
    if icon_name:icon_badge(inner,icon_name,color,CARD,34).pack(side='left',padx=(0,12))
    texts=tk.Frame(inner,bg=CARD);texts.pack(side='left',fill='x',expand=True)
    label(texts,title,9,DIM).pack(anchor='w')
    label(texts,value,16,WHITE,bold=True).pack(anchor='w')

def page_account_actions(parent,a,with_data=True):
    action=tk.Frame(parent,bg=PANEL);action.pack(side='right',padx=8)
    items=[('Buka',lambda a=a:open_account(a)),
           ('Streams',lambda a=a:read_visible(a,'streams')),
           ('Pendengar',lambda a=a:read_visible(a,'listeners')),
           ('Saldo',lambda a=a:read_visible(a,'balance'))]
    items.append(('Asal Streams',lambda a=a:read_regions(a)))
    if with_data:items.append(('Data',lambda a=a:edit(a)))
    items.append(('⋯',lambda a=a:show_actions(a)))
    for title,fn in items:
        if title=='⋯':RoundButton(action,'',fn,icon='more',height=30,padx=7).pack(side='left',padx=2)
        else:button(action,title,fn,title=='Buka',font_size=9,padx=10,height=30).pack(side='left',padx=2)

def commit_ownership_change(change):
    import copy
    before=copy.deepcopy(accounts);previous=owners[:]
    try:
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        for path in (FILE,OWNER_FILE):
            if os.path.isfile(path):shutil.copy2(path,path+'.before-ownership-'+stamp+'.bak')
        change();save_owners();persist()
    except (ValueError,OSError) as exc:
        for a,old in zip(accounts,before):a.clear();a.update(old)
        owners[:]=previous
        try:save_owners();persist()
        except OSError:pass
        messagebox.showerror('Tidak dapat menyimpan',str(exc),parent=root);return
    refresh()

def edit_owner_name(owner):
    name=simpledialog.askstring('Ubah Nama Pemilik','Nama pemilik yang benar:',initialvalue=owner,parent=root)
    if name is not None:commit_ownership_change(lambda:rename_owner(accounts,owners,owner,name))

def delete_owner_name(owner):
    if messagebox.askyesno('Hapus Pemilik',f'Hapus pemilik {owner}?\nArtisnya akan masuk Belum ditentukan. Riwayat penghasilan dan akun tetap tersimpan.',parent=root):
        commit_ownership_change(lambda:remove_owner(accounts,owners,owner))

def artist_options(a,artist):
    menu=tk.Menu(root,tearoff=False,bg=PANEL,fg=WHITE,activebackground=PURPLE,activeforeground=WHITE)
    menu.add_command(label='Atur Artis & Penghasilan Manual',command=lambda:edit_artist_finance(a,target_artist=artist['id'] if artist else None))
    menu.add_command(label='Terakhir sinkron: '+(a.get('balance_updated') or 'Belum pernah'),state='disabled')
    if artist:
        def rename_artist():
            name=simpledialog.askstring('Ubah Nama Artis','Nama artis yang benar:',initialvalue=artist['name'],parent=root)
            if name is None:return
            def change():
                value=name.strip()
                if not value:raise ValueError('Nama artis wajib diisi.')
                if any(x is not artist and x['name'].casefold()==value.casefold() for x in a.get('artists',[])):
                    raise ValueError('Nama artis tersebut sudah ada pada akun ini.')
                artist['name']=value
            commit_ownership_change(change)
        def release():
            if messagebox.askyesno('Lepaskan Artis',f'Lepaskan {artist["name"]} dari pemiliknya?\nRiwayat penghasilan tetap tersimpan dan artis bisa dipilih oleh pemilik lain.',parent=root):
                commit_ownership_change(lambda:artist.update(owner=''))
        def delete_artist():
            if messagebox.askyesno('Hapus Artis Permanen',f'Hapus {artist["name"]} beserta seluruh riwayat penghasilannya? Akun SoundOn tetap ada.',parent=root):
                commit_ownership_change(lambda:a['artists'].remove(artist))
        menu.add_command(label='Ubah Nama Artis',command=rename_artist)
        if artist.get('owner'):menu.add_command(label='Lepaskan dari Pemilik',command=release)
        menu.add_command(label='Hapus Artis Permanen',command=delete_artist)
        menu.add_separator()
    menu.add_command(label='Kelola Akun SoundOn',command=lambda:show_actions(a))
    menu.tk_popup(root.winfo_pointerx(),root.winfo_pointery())


def card_frame(parent,color=None):
    """Kartu ringan: satu Frame bergaris tepi (bukan 5 widget seperti RoundedPanel)."""
    return tk.Frame(parent,bg=color or PANEL,highlightthickness=1,highlightbackground=LINE,highlightcolor=LINE)

def render_owner_card(parent,group,index):
    outer=card_frame(parent)
    body=tk.Frame(outer,bg=PANEL);body.pack(fill='x',padx=16,pady=14)
    top=tk.Frame(body,bg=PANEL);top.pack(fill='x')
    unassigned=group['owner']=='Belum ditentukan'
    avatar(top,group['owner'] if not unassigned else '?',MUTED if unassigned else ACCENTS[index%len(ACCENTS)],44,PANEL).pack(side='left',padx=(0,12))
    if not unassigned:
        owner_actions=tk.Frame(top,bg=PANEL);owner_actions.pack(side='right',padx=(8,0))
        RoundButton(owner_actions,'Ubah Nama',lambda:edit_owner_name(group['owner']),icon='edit',variant='ghost',font_size=9,padx=8,height=28).pack(side='left',padx=2)
        RoundButton(owner_actions,'Hapus',lambda:delete_owner_name(group['owner']),icon='trash',variant='ghost',font_size=9,padx=8,height=28,text_color=RED).pack(side='left',padx=2)
    titles=tk.Frame(top,bg=PANEL);titles.pack(side='left',fill='x',expand=True)
    title=label(titles,group['owner'],14,bold=True,anchor='w',justify='left',wraplength=350)
    title.pack(fill='x')
    titles.bind('<Configure>',lambda e:title.configure(wraplength=max(100,e.width-6)))
    artist_count=sum(entry['artist'] is not None for entry in group['entries'])
    label(titles,f'{artist_count} artis  ·  {len(group["accounts"])} akun SoundOn',9,DIM).pack(anchor='w',pady=(2,0))
    summary_box=tk.Frame(body,bg=mix_card(GREEN));summary_box.pack(fill='x',pady=(12,10))
    summary=tk.Frame(summary_box,bg=mix_card(GREEN));summary.pack(fill='x',padx=14,pady=10)
    linked=list(group['accounts'].values())
    synced=[a for a in linked if a.get('balance_updated')]
    label(summary,'Saldo akun terkait',9,DIM).pack(side='left')
    label(summary,grouped_balance(synced) if synced else 'Belum disinkronkan',13,GREEN if synced else MUTED,bold=True).pack(side='right')
    heading=tk.Frame(body,bg=PANEL);heading.pack(fill='x',pady=(2,6))
    label(heading,'ARTIS',8,MUTED,bold=True).pack(side='left')
    if not unassigned:
        button(heading,'＋  Tambah Artis',lambda:add_owner_artist(group['owner']),variant='subtle',height=28,font_size=9,padx=10).pack(side='right')
    if not group['entries']:
        label(body,'Belum ada artis. Klik Tambah Artis.',10,DIM).pack(anchor='w',pady=10)
    for entry in sorted(group['entries'],key=lambda e:(e['artist']['name'] if e['artist'] else e['account']['name']).casefold()):
        a=entry['account'];artist=entry['artist'];amount=entry['amount']
        row_box=tk.Frame(body,bg=CARD);row_box.pack(fill='x',pady=2)
        row=tk.Frame(row_box,bg=CARD);row.pack(fill='x',padx=4)
        row.columnconfigure(0,weight=1)
        name=artist['name'] if artist else a['name']
        name_label=label(row,name,10,WHITE,bold=True,anchor='w',justify='left',wraplength=240)
        name_label.grid(row=0,column=0,sticky='ew',padx=(10,6),pady=10)
        name_label.bind('<Configure>',lambda e,l=name_label:l.configure(wraplength=max(60,e.width-4)))
        has_balance=bool(a.get('balance_updated'))
        income=label(row,account_money(a) if has_balance else 'Belum sinkron',10,
                     GREEN if has_balance else DIM,bold=has_balance,anchor='e')
        income.grid(row=0,column=1,sticky='e',padx=(4,8),pady=8)
        actions=tk.Frame(row,bg=CARD);actions.grid(row=0,column=2,sticky='e',padx=(0,7),pady=6)
        RoundButton(actions,'Sinkron',lambda a=a:read_visible(a,'balance'),icon='sync',bg_color=CARD,font_size=9,padx=8,height=28).pack(side='left',padx=2)
        RoundButton(actions,'Buka',lambda a=a:open_balance(a),icon='external',bg_color=CARD,font_size=9,padx=8,height=28).pack(side='left',padx=2)
        RoundButton(actions,'',lambda a=a,artist=artist:artist_options(a,artist),icon='more',bg_color=CARD,height=28,padx=6).pack(side='left',padx=2)
    return outer


_render_token=[0]
def build_in_batches(builders,place,batch=4):
    """Bangun kartu sedikit demi sedikit agar jendela tetap responsif (tidak 'Not Responding')."""
    token=_render_token[0]
    def run(i=0):
        if token!=_render_token[0]:return      # halaman sudah diganti/dirender ulang
        for b in builders[i:i+batch]:
            try:place(b())
            except tk.TclError:return
        if i+batch<len(builders):root.after(1,lambda:run(i+batch))
        else:root.after_idle(_page_region)
    run()

def render_active_page():
    if active_page=='Dashboard' or page_body is None:return
    _render_token[0]+=1
    # Simpan posisi gulir: render ulang (mis. setelah Sinkron) tidak melompat ke atas.
    keep=page_canvas.yview()[0] if page_canvas is not None else 0
    clear(page_body)
    def restore(pos=keep):
        try:
            page_body.update_idletasks()
            _page_region()
            page_canvas.yview_moveto(pos)
        except tk.TclError:pass
    root.after(0,restore)
    try:start=parse_date(start_var.get());end=parse_date(end_var.get())
    except ValueError:start=end=date.today()
    platform=platform_var.get()
    if active_page=='Daftar Akun':
        controls=page_section(page_body,'Pemilik & Daftar Artis',
            'Saldo tersedia dibaca dari My Earnings melalui Sinkron. Satu akun dihitung sekali pada total pemilik.','users')
        tools_row=tk.Frame(controls,bg=PANEL);tools_row.pack(fill='x')
        button(tools_row,'＋  Tambah Pemilik',add_owner,True).pack(side='left',padx=(0,8))
        button(tools_row,'＋  Tambah Akun',add_account).pack(side='left',padx=(0,8))
        button(tools_row,'Kategori Negara',add_category,icon='tag').pack(side='left',padx=(0,8))
        button(tools_row,'⟳  Refresh',lambda:(poll_chrome_status(),refresh())).pack(side='left')
        label(tools_row,f'{len(accounts)} akun terdaftar',9,DIM).pack(side='right',padx=4)
        global account_view_var
        if 'account_view_var' not in globals():
            account_view_var=tk.StringVar(value='Per Pemilik')
        period_controls=tk.Frame(page_body,bg=PANEL);period_controls.pack(fill='x',pady=(12,8),padx=8)
        UI.icon(period_controls,'info',15,MUTED,PANEL).pack(side='left',padx=(12,6))
        label(period_controls,'Saldo terakhir tersinkron · Klik Buka, login ke My Earnings, lalu Sinkron.',9,DIM).pack(side='left')
        view=ttk.Combobox(period_controls,textvariable=account_view_var,values=['Per Pemilik','Per Akun'],state='readonly',width=14,style='Dark.TCombobox')
        view.pack(side='right',padx=(6,12))
        label(period_controls,'Tampilan',9,DIM).pack(side='right')
        view.bind('<<ComboboxSelected>>',lambda e:render_active_page())
        account_grid=tk.Frame(page_body,bg=PANEL)
        account_grid.pack(fill='x',padx=10,pady=(0,8))
        cards=[]
        builders=[]
        if account_view_var.get()=='Per Pemilik':
            for idx,group in enumerate(owner_groups(accounts,artist_month_var.get(),owners)):
                builders.append(lambda group=group,idx=idx:render_owner_card(account_grid,group,idx))
        else:
            def build_account_card(a,idx):
                outer=card_frame(account_grid)
                body=tk.Frame(outer,bg=PANEL);body.pack(fill='x',padx=16,pady=14)
                top=tk.Frame(body,bg=PANEL);top.pack(fill='x')
                avatar(top,a['name'],ACCENTS[idx%len(ACCENTS)],44,PANEL).pack(side='left',padx=(0,12))
                titlebox=tk.Frame(top,bg=PANEL);titlebox.pack(side='left',fill='x',expand=True)
                name_label=label(titlebox,a['name'],14,bold=True,anchor='w',justify='left',wraplength=350)
                name_label.pack(fill='x')
                titlebox.bind('<Configure>',lambda e,l=name_label:l.configure(wraplength=max(100,e.width-6)))
                label(titlebox,f'{account_category(a)}   ·   Akun #{a["id"]}',9,DIM).pack(anchor='w',pady=(4,0))
                tools=tk.Frame(body,bg=PANEL);tools.pack(fill='x',pady=(10,0))
                button(tools,'Atur HP, Artis & Lagu',lambda a=a:edit_account_counts(a),variant='subtle',icon='edit',font_size=9,height=30).pack(side='left',padx=(0,6))
                button(tools,'Kredensial',lambda a=a:edit_credentials(a),icon='key',font_size=9,height=30).pack(side='left',padx=(0,6))
                button(tools,'Kelola',lambda a=a:show_actions(a),icon='more',font_size=9,height=30).pack(side='left')
                tk.Frame(body,bg=LINE,height=1).pack(fill='x',pady=(12,10))
                stats=tk.Frame(body,bg=PANEL);stats.pack(fill='x')
                for col,(title,key,color,icon_name) in enumerate([('Jumlah HP','phone_count',BLUE,'phone'),
                        ('Jumlah artis','artist_count',GREEN,'users'),('Jumlah lagu','song_count',PURPLE,'music')]):
                    stats.columnconfigure(col,weight=1,uniform='metrics')
                    tile_box=tk.Frame(stats,bg=CARD);tile_box.grid(row=0,column=col,sticky='nsew',padx=(0,6) if col<2 else 0)
                    tile=tk.Frame(tile_box,bg=CARD);tile.pack(fill='both',expand=True,padx=12,pady=10)
                    icon_badge(tile,icon_name,color,CARD,30).pack(side='left',padx=(0,10))
                    tt=tk.Frame(tile,bg=CARD);tt.pack(side='left')
                    label(tt,title,8,DIM).pack(anchor='w')
                    label(tt,number(a.get(key,0)),14,WHITE,bold=True).pack(anchor='w')
                render_artist_finance(body,a)
                foot=tk.Frame(body,bg=PANEL);foot.pack(fill='x',pady=(10,0))
                page_account_actions(foot,a)
                return outer
            for idx,a in enumerate(sorted(accounts,key=lambda a:(account_category(a),a['name'].lower()))):
                builders.append(lambda a=a,idx=idx:build_account_card(a,idx))
        layout_state=[None]
        def arrange_cards(event=None):
            width=event.width if event is not None else page_canvas.winfo_width()-20
            columns=2 if width>=1180 else 1
            if columns==layout_state[0]:return
            layout_state[0]=columns
            account_grid.columnconfigure(0,weight=1,uniform='accounts')
            account_grid.columnconfigure(1,weight=1 if columns==2 else 0,uniform='accounts' if columns==2 else '',minsize=0)
            for idx,card in enumerate(cards):
                card.grid(row=idx//columns,column=idx%columns,sticky='nsew',
                          padx=(0,8) if columns==2 and idx%2==0 else (8,0) if columns==2 else 0,pady=8)
        account_grid.bind('<Configure>',arrange_cards)
        columns=2 if page_canvas.winfo_width()-20>=1180 else 1
        layout_state[0]=columns
        account_grid.columnconfigure(0,weight=1,uniform='accounts')
        account_grid.columnconfigure(1,weight=1 if columns==2 else 0,uniform='accounts' if columns==2 else '',minsize=0)
        def place(card):
            idx=len(cards);cards.append(card);cols=layout_state[0] or 1
            card.grid(row=idx//cols,column=idx%cols,sticky='nsew',
                      padx=(0,8) if cols==2 and idx%2==0 else (8,0) if cols==2 else 0,pady=8)
        build_in_batches(builders,place)
        if not accounts and not owners:label(page_body,'Klik Tambah Pemilik atau Tambah Akun untuk memulai.',12,DIM).pack(pady=20)
    elif active_page=='Analytics':
        # Periode sama dengan Dashboard (satu periode untuk semua menu).
        intro=page_section(page_body,'Asal Streams  ·  Region Insights',
            'Hasil hanya ditampilkan jika periode pembacaannya sama dengan periode yang dipilih.','globe',BLUE)
        controls=tk.Frame(intro,bg=PANEL);controls.pack(fill='x',pady=(0,6))
        label(controls,'PERIODE',8,MUTED,bold=True).pack(side='left',padx=(0,10))
        PeriodButton(controls,start_var,end_var,refresh).pack(side='left')
        label(controls,'Samakan periode di Artist Insights SoundOn sebelum membaca data.',9,MUTED).pack(side='left',padx=14)
        try:
            selected_start=parse_date(start_var.get())
            selected_end=parse_date(end_var.get())
        except ValueError:
            selected_start=selected_end=date.today()
        batch_jobs=[]
        for cat in categories:
            members=[(a,latest(a,selected_start,selected_end,platform)) for a in accounts if account_category(a)==cat]
            if not members:continue
            group=page_section(page_body,cat,f'{len(members)} akun · asal Streams {selected_start} s.d. {selected_end}','flag' if cat.casefold()=='indonesia' else 'globe',RED if cat.casefold()=='indonesia' else BLUE)
            def build_region_card(a,r,idx,group=group):
                acct_shell=tk.Frame(group,bg=CARD);acct_shell.pack(fill='x',pady=4)
                acct_box=tk.Frame(acct_shell,bg=CARD);acct_box.pack(fill='x',pady=2)
                top=tk.Frame(acct_box,bg=CARD);top.pack(fill='x',padx=16,pady=(12,6))
                avatar(top,a['name'],ACCENTS[idx%len(ACCENTS)],36,CARD).pack(side='left',padx=(0,12))
                namebox=tk.Frame(top,bg=CARD);namebox.pack(side='left',fill='x',expand=True)
                label(namebox,a['name'],11,bold=True).pack(anchor='w')
                label(namebox,'Streams '+(number(r.get('streams',0)) if r else '—')+
                    '   ·   Pendengar '+(number(r.get('listeners',0)) if r else '—'),9,DIM).pack(anchor='w',pady=(2,0))
                button(top,'Baca Asal Streams',lambda a=a:read_regions(a),True,icon='sync',font_size=9,height=30).pack(side='right')
                button(top,'↗  Buka Streams',lambda a=a:open_streams(a),font_size=9,height=30).pack(side='right',padx=8)
                saved=[]
                for rec in a.get('region_records',[]):
                    if rec.get('platform')!=platform:continue
                    try:
                        rec_start=date.fromisoformat(rec['start'])
                    except (ValueError,KeyError,TypeError):continue
                    if rec_start==selected_start and rec.get('end')==str(selected_end):saved.append(rec)
                # Deduplicate legacy entries for identical artist and date ranges.
                unique={}
                for rec in sorted(saved,key=lambda x:x.get('updated','')):
                    unique[(rec.get('artist_id') or rec.get('artist_name'),rec.get('start'),rec.get('end'),rec.get('platform'))]=rec
                saved=list(unique.values())
                if not saved:
                    label(acct_box,'Belum ada pembacaan untuk tanggal yang dipilih. Samakan periode Artist Insights, lalu klik Baca Asal Streams.',
                        9,MUTED,wraplength=900,justify='left').pack(anchor='w',padx=64,pady=(0,14))
                    return acct_shell
                for rec in sorted(saved,key=lambda x:(x.get('start',''),x.get('artist_name','')),reverse=True):
                    record=tk.Frame(acct_box,bg=PANEL);record.pack(fill='x',padx=14,pady=(2,12))
                    header=tk.Frame(record,bg=PANEL);header.pack(fill='x',padx=15,pady=(11,8))
                    UI.icon(header,'music',15,PURPLE,PANEL).pack(side='left',padx=(0,7))
                    label(header,rec.get('artist_name','Artis'),11,bold=True).pack(side='left')
                    label(header,rec.get('start','?')+'  →  '+rec.get('end','?'),9,BLUE).pack(side='right')
                    regions={str(v.get('code','')).upper():v.get('percent') for v in rec.get('regions',[])}
                    for codes,title,color in [(('ID','IDN'),'INDONESIA',GREEN),
                                              (('US','USA'),'AMERIKA SERIKAT',PURPLE)]:
                        value=next((regions[c] for c in codes if c in regions),None)
                        line=tk.Frame(record,bg=PANEL);line.pack(fill='x',padx=15,pady=5)
                        label(line,title,9,DIM,bold=True).pack(side='left')
                        label(line,('—' if value is None else f'{float(value):.2f}%'.replace('.',',')),
                            12,color,bold=True).pack(side='right')
                        bar=tk.Canvas(record,height=8,bg=CARD,highlightthickness=0)
                        bar.pack(fill='x',padx=15,pady=(0,7))
                        def paint(event,b=bar,v=value,c=color):
                            b.delete('all');width=max(0,event.width)
                            b.create_rectangle(0,0,width,8,fill=LINE,outline='')
                            if v is not None:b.create_rectangle(0,0,width*max(0,min(100,float(v)))/100,8,fill=c,outline='')
                        bar.bind('<Configure>',paint)
                    label(record,'Platform: '+rec.get('platform','—')+'   ·   Dibaca: '+rec.get('updated','—')+
                        '   ·   Data artis, bukan total akun',8,DIM).pack(anchor='w',padx=15,pady=(2,11))
                return acct_shell
            batch_jobs.extend((lambda a=a,r=r,idx=idx,build=build_region_card:build(a,r,idx)) for idx,(a,r) in enumerate(sorted(members,key=lambda item:item[0]['name'].lower())))
        build_in_batches(batch_jobs,lambda card:None,batch=6)
        if not accounts:label(page_body,'Belum ada akun.',12,DIM).pack(pady=20)
    elif active_page=='Penghasilan':
        # Two independent currencies: never add USD to IDR without a real exchange rate.
        def balance_known(a):
            return bool(a.get('balance_updated'))

        def balance_amount(a):
            try:return float(a.get('balance') or 0)
            except (ValueError,TypeError):return 0.0

        def currency_of(a):
            return str(a.get('currency') or 'IDR').upper()

        def currency_total(members,currency):
            return sum(balance_amount(a) for a in members if currency_of(a)==currency and balance_known(a))

        def money_or_dash(a):
            return account_money(a) if balance_known(a) else 'Belum dibaca'

        def earnings_card(parent,caption,value,subtitle,accent,icon_name):
            outer=UI.RoundedPanel(parent,outer=PANEL,color=CARD,radius=12)
            outer.pack(side='left',fill='both',expand=True,padx=6)
            inner=tk.Frame(outer,bg=CARD);inner.pack(fill='both',expand=True,padx=18,pady=16)
            top=tk.Frame(inner,bg=CARD);top.pack(fill='x')
            icon_badge(top,icon_name,accent,CARD,34).pack(side='left',padx=(0,10))
            label(top,caption,9,DIM).pack(side='left')
            label(inner,value,20,WHITE,bold=True).pack(anchor='w',pady=(12,2))
            label(inner,subtitle,9,MUTED).pack(anchor='w')
            return outer

        heading=tk.Frame(page_body,bg=PANEL);heading.pack(fill='x',padx=18,pady=(18,6))
        icon_badge(heading,'wallet',GREEN,PANEL,34).pack(side='left',padx=(0,12))
        heading_left=tk.Frame(heading,bg=PANEL);heading_left.pack(side='left',fill='x',expand=True)
        label(heading_left,'Ringkasan Penghasilan',13,bold=True).pack(anchor='w')
        label(heading_left,'Saldo tersedia dari pembacaan terakhir · IDR dan USD ditampilkan terpisah.',9,DIM).pack(anchor='w',pady=(2,0))
        button(heading,'⟳  Refresh',render_active_page).pack(side='right',padx=(8,0))

        indonesia=[a for a in accounts if account_category(a).casefold()=='indonesia']
        usa=[a for a in accounts if account_category(a).casefold() in ('amerika serikat','united states','usa','us')]
        other=[a for a in accounts if a not in indonesia and a not in usa]
        summary=tk.Frame(page_body,bg=PANEL);summary.pack(fill='x',padx=11,pady=(13,18))
        earnings_card(summary,'Total saldo Indonesia',money(currency_total(indonesia,'IDR'),'IDR'),f'{len(indonesia)} akun · Rupiah',RED,'flag')
        earnings_card(summary,'Total saldo Amerika Serikat',money(currency_total(usa,'USD'),'USD'),f'{len(usa)} akun · Dolar AS',BLUE,'globe')
        earnings_card(summary,'Akun terdaftar',str(len(accounts)),f'{len(indonesia)} Indonesia · {len(usa)} Amerika Serikat',AMBER,'users')

        def country_panel(parent,title,members,currency,accent,icon_name):
            shell=UI.RoundedPanel(parent,outer=PANEL,color=CARD,radius=12)
            shell.pack(side='left',fill='both',expand=True,padx=6,anchor='n')
            header=tk.Frame(shell,bg=CARD);header.pack(fill='x',padx=16,pady=(16,12))
            icon_badge(header,icon_name,accent,CARD,36).pack(side='left',padx=(0,12))
            titlebox=tk.Frame(header,bg=CARD);titlebox.pack(side='left',fill='x',expand=True)
            label(titlebox,title,13,bold=True).pack(anchor='w')
            label(titlebox,f'{len(members)} akun  ·  Saldo tersedia',9,DIM).pack(anchor='w',pady=(2,0))
            label(header,money(currency_total(members,currency),currency),15,WHITE,bold=True).pack(side='right')
            table=tk.Frame(shell,bg=CARD);table.pack(fill='x',padx=12,pady=(0,14))
            table.grid_columnconfigure(1,weight=1)
            for col,(text,anchor) in enumerate([('#','w'),('AKUN','w'),(f'SALDO ({currency})','e'),('','e')]):
                tk.Label(table,text=text,font=(FONT,8,'bold'),fg=MUTED,bg=CARD_HI,anchor=anchor,padx=10,pady=9).grid(row=0,column=col,sticky='nsew')
            if not members:
                label(table,'Belum ada akun dalam kategori ini.',10,MUTED).grid(row=1,column=0,columnspan=4,pady=24)
            for i,a in enumerate(sorted(members,key=lambda x:x.get('name','').casefold()),1):
                r=i*2-1
                label(table,str(i),9,MUTED).grid(row=r,column=0,sticky='w',padx=10,pady=10)
                name=tk.Frame(table,bg=CARD);name.grid(row=r,column=1,sticky='w',padx=10,pady=8)
                label(name,short_name(a.get('name','Akun'),26),10,bold=True).pack(anchor='w')
                updated=a.get('balance_updated') or ''
                label(name,('Diperbarui '+short_time(updated)) if updated else 'Belum ada pembacaan saldo',8,MUTED).pack(anchor='w',pady=(1,0))
                label(table,money_or_dash(a),10,GREEN if balance_known(a) else MUTED,bold=balance_known(a),anchor='e').grid(row=r,column=2,sticky='e',padx=10)
                actions=tk.Frame(table,bg=CARD)
                actions.grid(row=r,column=3,sticky='e',padx=(4,6))
                button(actions,'↗  Buka',lambda a=a:open_balance(a),font_size=9,height=30,padx=10).pack(side='left',padx=(0,5))
                button(actions,'Baca Saldo',lambda a=a:read_visible(a,'balance'),True,icon='sync',font_size=9,height=30,padx=10).pack(side='left')
                tk.Frame(table,bg=LINE,height=1).grid(row=r+1,column=0,columnspan=4,sticky='ew')
            return shell

        countries=tk.Frame(page_body,bg=PANEL);countries.pack(fill='x',padx=11,pady=(0,16))
        country_panel(countries,'Indonesia',indonesia,'IDR',RED,'flag')
        country_panel(countries,'Amerika Serikat',usa,'USD',BLUE,'globe')

        if other:
            extra=page_section(page_body,'Kategori Lain',f'{len(other)} akun di luar kategori Indonesia dan Amerika Serikat.','tag',AMBER)
            for a in sorted(other,key=lambda x:x.get('name','').casefold()):
                row=tk.Frame(extra,bg=PANEL);row.pack(fill='x',pady=4)
                label(row,a.get('name','Akun'),10,bold=True).pack(side='left')
                label(row,'  ·  '+account_category(a),9,DIM).pack(side='left')
                button(row,'Baca Saldo',lambda a=a:read_visible(a,'balance'),True,icon='sync',font_size=9,height=30).pack(side='right')
                button(row,'↗  Buka',lambda a=a:open_balance(a),font_size=9,height=30).pack(side='right',padx=6)
                label(row,money_or_dash(a),10,GREEN if balance_known(a) else MUTED).pack(side='right',padx=16)

        footer_box=UI.RoundedPanel(page_body,outer=PANEL,color=mix_card(BLUE),radius=10);footer_box.pack(fill='x',padx=17,pady=(3,19))
        footer=tk.Frame(footer_box,bg=mix_card(BLUE));footer.pack(fill='x',padx=16,pady=12)
        UI.icon(footer,'info',18,BLUE,mix_card(BLUE)).pack(side='left',anchor='n',padx=(0,10),pady=2)
        label(footer,'Saldo tersedia bukan pendapatan periode. Nilai IDR dan USD tidak dijumlahkan atau dikonversi secara otomatis. '
            'Klik Baca Saldo setelah membuka akun dan login di Chrome.',9,DIM,wraplength=1000,justify='left').pack(side='left',anchor='w')
    elif active_page=='Inventaris HP':
        intro=page_section(page_body,'Inventaris Perangkat',
            'HP yang digunakan pada akun dihitung otomatis dari Daftar Akun. HP lainnya dapat dicatat di bawah.','phone',PURPLE)
        assigned=assigned_phone_count()
        total=assigned+sum(phone_inventory[k] for k in ('tersedia','service','rusak','tidak_terpakai'))
        metrics=[('Dipakai akun',assigned,PURPLE,'phone'),('Tersedia',phone_inventory['tersedia'],GREEN,'check'),
                 ('Service',phone_inventory['service'],BLUE,'wrench'),('Rusak',phone_inventory['rusak'],RED,'alert'),
                 ('Tidak terpakai',phone_inventory['tidak_terpakai'],MUTED,'circle'),('Total seluruh HP',total,AMBER,'grid')]
        stats=tk.Frame(intro,bg=PANEL);stats.pack(fill='x',pady=(0,14))
        for title,value,color,icon_name in metrics: page_metric(stats,title,number(value),color,icon_name)
        note=tk.Frame(intro,bg=PANEL);note.pack(fill='x',pady=(0,14))
        UI.icon(note,'info',15,MUTED,PANEL).pack(side='left',anchor='n',padx=(0,8),pady=1)
        label(note,'Dipakai Akun berubah otomatis mengikuti jumlah HP pada setiap akun. Jangan masukkan HP yang sama lagi ke kategori Tersedia, Service, Rusak, atau Tidak Terpakai.',9,DIM,wraplength=1000,justify='left').pack(side='left',anchor='w')
        label(intro,'UBAH JUMLAH',8,MUTED,bold=True).pack(anchor='w',pady=(4,6))
        form=tk.Frame(intro,bg=PANEL);form.pack(fill='x',pady=(0,6));entries={}
        editable=[('Tersedia','tersedia',GREEN),('Service','service',BLUE),('Rusak','rusak',RED),('Tidak terpakai','tidak_terpakai',MUTED)]
        for i,(title,key,color) in enumerate(editable):
            shell=UI.RoundedPanel(form,outer=PANEL,color=CARD,radius=10);shell.grid(row=0,column=i,sticky='nsew',padx=4,pady=0);form.grid_columnconfigure(i,weight=1,uniform='inv_form')
            item=tk.Frame(shell,bg=CARD);item.pack(fill='both',expand=True,padx=14,pady=12)
            head_row=tk.Frame(item,bg=CARD);head_row.pack(fill='x',pady=(0,8))
            tk.Canvas(head_row,width=8,height=8,bg=CARD,highlightthickness=0).pack(side='left',padx=(0,7))
            head_row.winfo_children()[-1].create_oval(0,0,8,8,fill=color,outline='')
            label(head_row,title,9,DIM).pack(side='left')
            entry=tk.Entry(item,font=(FONT,15,'bold'),fg=WHITE,bg=PANEL,insertbackground=WHITE,relief='flat',highlightthickness=1,highlightbackground=LINE,highlightcolor=PURPLE,width=9)
            entry.insert(0,str(phone_inventory[key]));entry.pack(anchor='w',fill='x',ipady=5,ipadx=6);entries[key]=entry
        label(intro,'CATATAN INVENTARIS',8,MUTED,bold=True).pack(anchor='w',pady=(16,6))
        notes=tk.Text(intro,height=4,wrap='word',font=(FONT,10),bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',padx=12,pady=10)
        notes.insert('1.0',phone_inventory.get('catatan',''));notes.pack(fill='x',pady=(0,12))
        def save_inventory_form():
            try:
                values={k:int(e.get().strip()) for k,e in entries.items()}
                if any(v<0 or v>1000000 for v in values.values()): raise ValueError()
            except ValueError:
                messagebox.showerror('Jumlah HP tidak valid','Masukkan bilangan bulat 0 sampai 1.000.000.',parent=root);return
            previous=phone_inventory.copy();phone_inventory.update(values);phone_inventory['catatan']=notes.get('1.0','end-1c').strip()
            try: save_phone_inventory()
            except OSError as ex:
                phone_inventory.clear();phone_inventory.update(previous);messagebox.showerror('Gagal menyimpan',str(ex),parent=root);return
            update_inventory_dashboard();render_active_page();messagebox.showinfo('Inventaris tersimpan','Data inventaris HP berhasil disimpan.',parent=root)
        button(intro,'✓  Simpan Inventaris',save_inventory_form,True).pack(anchor='w',pady=(4,8))
        label(intro,'Disimpan di '+INVENTORY_FILE,8,MUTED,wraplength=950,justify='left').pack(anchor='w',pady=(6,0))
    elif active_page=='Pengaturan':
        import updater as _upd
        _cfg=_upd.load_config(_APP_DIR)
        # Pembaruan
        upd=page_section(page_body,'Pembaruan Aplikasi','Versi baru dipasang otomatis dari GitHub saat aplikasi dibuka, dan diperiksa tiap 20 menit selama aplikasi terbuka.','cloud',PURPLE)
        info_row=tk.Frame(upd,bg=PANEL);info_row.pack(fill='x')
        for cap,val,col in [('Versi terpasang',APP_VERSION,WHITE),
                            ('Pembaruan otomatis','Aktif' if _cfg.get('auto_update') else 'Mati',GREEN if _cfg.get('auto_update') else RED),
                            ('Sumber',_cfg.get('github_repo') or 'Belum diatur',DIM)]:
            cell=tk.Frame(info_row,bg=PANEL);cell.pack(side='left',padx=(0,40))
            label(cell,cap,8,MUTED).pack(anchor='w')
            label(cell,val,11,col,bold=True).pack(anchor='w',pady=(2,0))
        button(info_row,'Periksa Pembaruan',open_update_settings,True,icon='refresh').pack(side='right')
        import release_publisher as _rp
        pub=tk.Frame(upd,bg=PANEL);pub.pack(fill='x',pady=(14,0))
        _on=bool(_rp.load_token())
        label(pub,'Penerbit otomatis (komputer admin)',10,WHITE,bold=True).pack(anchor='w')
        label(pub,('Aktif — paket rilis yang masuk ke folder '+str(_rp.INBOX)+' langsung diterbitkan ke GitHub, lalu semua aplikasi memperbarui otomatis.')
              if _on else 'Mati. Isi token GitHub di komputer admin agar rilis baru bisa diterbitkan tanpa unggah manual.',
              9,GREEN if _on else DIM,wraplength=820,justify='left').pack(anchor='w',pady=(2,6))
        prow=tk.Frame(pub,bg=PANEL);prow.pack(fill='x')
        button(prow,'Atur token penerbit…',open_publisher_settings,icon='cloud').pack(side='left')
        if _on:
            button(prow,'Buka folder rilis',lambda:_open_path(str(_rp.RELEASE_DIR)),variant='ghost').pack(side='left',padx=8)
        # Tampilan (mode terang/gelap)
        look=page_section(page_body,'Tampilan','Pilih mode gelap atau terang. Aplikasi dibuka ulang otomatis untuk menerapkannya.','sun',AMBER)
        modes=tk.Frame(look,bg=PANEL);modes.pack(fill='x')
        for col,(mode,title,desc,icon_name) in enumerate([('dark','Mode gelap','Nyaman di ruangan redup.','moon'),
                                                         ('light','Mode terang','Jelas di ruangan terang.','sun')]):
            active=UI.THEME==mode
            preview=UI.PALETTES[mode]
            card=tk.Frame(modes,bg=CARD,highlightthickness=2,highlightbackground=PURPLE if active else LINE,cursor='hand2')
            card.grid(row=0,column=col,sticky='nsew',padx=(0,10));modes.grid_columnconfigure(col,weight=1,uniform='modes')
            sw=tk.Canvas(card,width=120,height=64,bg=CARD,highlightthickness=0);sw.pack(side='left',padx=12,pady=12)
            UI.rounded_rect(sw,0,0,120,64,8,preview['BG']);UI.rounded_rect(sw,0,0,32,64,8,preview['SIDE'])
            UI.rounded_rect(sw,40,10,112,30,5,preview['PANEL']);UI.rounded_rect(sw,40,36,84,54,5,preview['PANEL'])
            UI.rounded_rect(sw,88,38,112,52,4,preview['PURPLE'])
            texts=tk.Frame(card,bg=CARD);texts.pack(side='left',fill='x',expand=True)
            label(texts,title+('  ·  aktif' if active else ''),11,PURPLE if active else WHITE,bold=True).pack(anchor='w')
            label(texts,desc,9,DIM).pack(anchor='w')
            for w in (card,sw,texts)+tuple(texts.winfo_children()):
                w.bind('<ButtonRelease-1>',lambda e,m=mode:set_theme(m))
        # Sinkron otomatis
        cfg=sync_settings()
        syn=page_section(page_body,'Sinkron Otomatis','Membaca Streams, Pendengar, Saldo, dan Asal Streams semua akun dari SoundOn sekali sehari. '
                         'Sinkron harian membaca data bulanan: Bulan ini (dan Bulan lalu pada tanggal 1–3).','sync',GREEN)
        en_var=tk.BooleanVar(value=cfg['enabled']);oc_var=tk.BooleanVar(value=cfg['open_closed']);hr_var=tk.StringVar(value='%02d:00'%cfg['hour'])
        bal_var=tk.BooleanVar(value=cfg['balance']);reg_var=tk.BooleanVar(value=cfg['regions'])
        def save_sync(*_):
            try:UI.save_settings(sync_enabled=en_var.get(),sync_open_closed=oc_var.get(),sync_hour=int(hr_var.get()[:2]),
                                 sync_balance=bal_var.get(),sync_regions=reg_var.get())
            except (OSError,ValueError):pass
        row1=tk.Frame(syn,bg=PANEL);row1.pack(fill='x',pady=(0,6))
        UI.dark_checkbutton(row1,'  Aktifkan sinkron harian pukul',en_var,PANEL,command=save_sync).pack(side='left')
        hr=ttk.Combobox(row1,textvariable=hr_var,values=['%02d:00'%h for h in range(24)],state='readonly',width=7,style='Dark.TCombobox')
        hr.pack(side='left',padx=8);hr.bind('<<ComboboxSelected>>',save_sync)
        UI.dark_checkbutton(syn,'  Buka Chrome akun yang tertutup (diperkecil), lalu tutup lagi setelah dibaca',oc_var,PANEL,command=save_sync).pack(anchor='w')
        UI.dark_checkbutton(syn,'  Baca juga Saldo tersedia (My Earnings)',bal_var,PANEL,command=save_sync).pack(anchor='w')
        UI.dark_checkbutton(syn,'  Baca juga Asal Streams per artis (Indonesia / Amerika Serikat), maks. 12 artis per akun',reg_var,PANEL,command=save_sync).pack(anchor='w')
        label(syn,'Akun yang belum login dilewati dan dicatat di laporan. Platform yang didukung: Semua Platform dan Spotify.',9,MUTED).pack(anchor='w',pady=(6,4))
        info=tk.Frame(syn,bg=PANEL);info.pack(fill='x',pady=(4,0))
        label(info,_sync_state['text'] or cfg['last_summary'] or 'Belum pernah dijalankan.',9,DIM).pack(side='left')
        button(info,'Lihat laporan',open_sync_log,icon='info',font_size=9,height=30).pack(side='right')
        button(info,'Hentikan',stop_sync,variant='danger',icon='stop',font_size=9,height=30).pack(side='right',padx=6)
        button(info,'Sinkron per bulan…',ask_month_and_sync,True,icon='sync',font_size=9,height=30).pack(side='right')
        # Data & transfer
        data_sec=page_section(page_body,'Data & Transfer Akun','Cadangkan data atau pindahkan akun ke komputer lain.','database',BLUE)
        for title,desc,fn,icon_name in [('Cadangkan data akun','Simpan akun, kategori, pemilik, dan inventaris ke file JSON.',backup_account_data,'export'),
                                        ('Ekspor paket akun','Buat file .sndpack terenkripsi untuk dipindahkan ke pengguna lain.',export_transfer_package,'export'),
                                        ('Impor paket akun','Tambahkan akun dari file .sndpack.',import_transfer_package,'import')]:
            row_box=UI.RoundedPanel(data_sec,outer=PANEL,color=CARD,radius=10);row_box.pack(fill='x',pady=3)
            row=tk.Frame(row_box,bg=CARD);row.pack(fill='x',padx=14,pady=11)
            icon_badge(row,icon_name,BLUE,CARD,32).pack(side='left',padx=(0,12))
            texts=tk.Frame(row,bg=CARD);texts.pack(side='left',fill='x',expand=True)
            label(texts,title,10,bold=True).pack(anchor='w')
            label(texts,desc,9,DIM).pack(anchor='w')
            button(row,title.split()[0],fn,font_size=9,height=30).pack(side='right')
        # Kategori
        cat_sec=page_section(page_body,'Kategori Negara','Kategori dipakai untuk mengelompokkan akun dan ringkasan negara.','tag',AMBER)
        chips=tk.Frame(cat_sec,bg=PANEL);chips.pack(fill='x')
        for cat in categories:
            n=sum(1 for a in accounts if account_category(a)==cat)
            pill(chips,f'{cat}  ·  {n}',AMBER if n else MUTED,PANEL,9).pack(side='left',padx=(0,6),pady=2)
        button(chips,'＋  Tambah kategori',add_category,variant='subtle',font_size=9,height=28).pack(side='left',padx=(6,0))
        # Lokasi data
        loc=page_section(page_body,'Lokasi Data','Data akun dan profil Chrome tersimpan terpisah dari folder aplikasi.','folder',GREEN)
        for cap,val in [('Folder data',BASE),('Folder aplikasi',_APP_DIR)]:
            r=tk.Frame(loc,bg=PANEL);r.pack(fill='x',pady=2)
            label(r,cap,9,MUTED,width=16,anchor='w').pack(side='left')
            label(r,val,9,WHITE).pack(side='left')
        label(loc,'Backup JSON tidak mencakup profil Chrome. Pembaruan aplikasi tidak menyentuh folder data.',9,DIM).pack(anchor='w',pady=(8,0))

def switch_page(name):
    global active_page,page_body,page_window
    previous=active_page
    active_page=name
    for title,widget in nav_controls.items():
        widget.set_active(title==name)
    if name=='Dashboard':
        _render_token[0]+=1
        for other in list(page_bodies):
            try:
                page_canvas.delete(page_windows[other]);page_bodies[other].destroy()
            except tk.TclError:pass
            page_bodies.pop(other,None);page_windows.pop(other,None);page_rendered.pop(other,None)
        if page_overlay is not None:page_overlay.pack_forget()
        if not dash.winfo_manager():dash.pack(fill='both',expand=True)
        refresh()
        return
    page_title.configure(text=name)
    page_subtitle.configure(text={
        'Daftar Akun':'Kelola pemilik, artis, penghasilan, dan akun SoundOn.',
        'Analytics':'Bandingkan Streams dan Pendengar berdasarkan negara.',
        'Penghasilan':'Pantau saldo tersedia seluruh akun.',
        'Inventaris HP':'Pantau HP dipakai akun, tersedia, service, rusak, dan tidak terpakai.',
        'Pengaturan':'Atur data, transfer akun, dan pembaruan SoundOn Account Manager.'}.get(name,''))
    # Sembunyikan Dashboard sepenuhnya (bukan ditimpa) agar tidak ada sisa gambar.
    if dash.winfo_manager():dash.pack_forget()
    if not page_overlay.winfo_manager():page_overlay.pack(fill='both',expand=True)
    # Keep each sidebar page alive after its first render. Switching back no longer
    # destroys and rebuilds dozens of widgets, making Analytics/Penghasilan feel instant.
    # Hanya halaman yang sedang dibuka yang hidup. Halaman lain dihapus agar jumlah
    # widget tidak menumpuk (penumpukan ribuan widget membuat aplikasi crash di Windows).
    _render_token[0]+=1
    for other in [n for n in page_bodies if n!=name]:
        try:
            page_canvas.delete(page_windows[other]);page_bodies[other].destroy()
        except tk.TclError:pass
        page_bodies.pop(other,None);page_windows.pop(other,None);page_rendered.pop(other,None)
    if name not in page_bodies:
        body=tk.Frame(page_canvas,bg=PANEL)
        win=page_canvas.create_window((0,0),window=body,anchor='nw',width=max(1,page_canvas.winfo_width()))
        body.bind('<Configure>',lambda e,n=name:_page_region() if n==active_page else None)
        page_bodies[name]=body;page_windows[name]=win
    page_body=page_bodies[name];page_window=page_windows[name]
    page_canvas.itemconfigure(page_window,state='normal')
    scroller.reset(page_canvas)
    _page_region()
    page_canvas.yview_moveto(0)
    if page_rendered.get(name)!=_page_key():
        # Let the header/navigation repaint first, then do the one-time heavy render.
        page_subtitle.configure(text=page_subtitle.cget('text')+'  ·  Memuat…')
        def first_render(target=name):
            if active_page!=target:return
            page_subtitle.configure(text={
                'Daftar Akun':'Kelola pemilik, artis, penghasilan, dan akun SoundOn.',
                'Analytics':'Bandingkan Streams dan Pendengar berdasarkan negara.',
                'Penghasilan':'Pantau saldo tersedia seluruh akun.',
                'Inventaris HP':'Pantau HP dipakai akun, tersedia, service, rusak, dan tidak terpakai.',
                'Pengaturan':'Atur data, transfer akun, dan pembaruan SoundOn Account Manager.'}.get(target,''))
            render_active_page();page_rendered[target]=_page_key()
        root.after_idle(first_render)

root=tk.Tk();artist_month_var=tk.StringVar(master=root,value=date.today().strftime('%Y-%m'));root.title('SoundOn — Account Manager Dashboard');root.geometry('1600x910');root.minsize(1280,690);root.configure(bg=BG)
style=UI.setup_styles(root)
root.option_add('*TCombobox.font',(FONT,10))
sidebar=tk.Frame(root,bg=SIDE,width=232,highlightthickness=0)
sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
tk.Frame(root,bg=LINE,width=1).pack(side='left',fill='y')
brand=tk.Frame(sidebar,bg=SIDE);brand.pack(fill='x',padx=18,pady=(24,26))
_logo=tk.Canvas(brand,width=40,height=40,bg=SIDE,highlightthickness=0)
UI.rounded_rect(_logo,0,0,40,40,11,PURPLE);UI.draw_icon(_logo,'music',9,9,22,'#ffffff');_logo.pack(side='left')
_brand_text=tk.Frame(brand,bg=SIDE);_brand_text.pack(side='left',padx=(11,0))
label(_brand_text,'SoundOn',15,bold=True).pack(anchor='w')
label(_brand_text,'Account Manager',9,DIM).pack(anchor='w')
label(sidebar,'MENU',8,MUTED,bold=True).pack(anchor='w',padx=24,pady=(0,6))
nav=tk.Frame(sidebar,bg=SIDE);nav.pack(fill='x',padx=12)
for title,icon_name in [('Dashboard','home'),('Daftar Akun','users'),('Analytics','chart'),('Penghasilan','wallet'),
                        ('Inventaris HP','phone'),('Pengaturan','gear')]:
    control=UI.NavItem(nav,title,icon_name,lambda title=title:switch_page(title))
    control.pack(fill='x',pady=2)
    control.set_active(title=='Dashboard')
    nav_controls[title]=control
def launch_upload_manager():
    from upload_manager import show_upload_manager
    global upload_manager_window
    if 'upload_manager_window' in globals() and upload_manager_window.window.winfo_exists():
        upload_manager_window.window.deiconify();upload_manager_window.window.lift();return
    upload_manager_window=show_upload_manager(root,accounts,BASE,open_account,port_for,debugger_ready)
label(sidebar,'STUDIO',8,MUTED,bold=True).pack(anchor='w',padx=24,pady=(16,6))
_studio_nav=tk.Frame(sidebar,bg=SIDE);_studio_nav.pack(fill='x',padx=12)
UI.NavItem(_studio_nav,'Unggah Lagu','music',launch_upload_manager).pack(fill='x',pady=2)
_foot=tk.Frame(sidebar,bg=SIDE);_foot.pack(side='bottom',fill='x',padx=16,pady=(0,14))
label(_foot,'Versi '+APP_VERSION,8,MUTED).pack(side='left',padx=(8,0))
RoundButton(_foot,'Terang' if UI.THEME=='dark' else 'Gelap',lambda:set_theme('light' if UI.THEME=='dark' else 'dark'),
            icon='sun' if UI.THEME=='dark' else 'moon',variant='ghost',height=28,font_size=9,padx=8).pack(side='right')
button(sidebar,'＋  Tambah Akun',add_account,True,height=38).pack(side='bottom',fill='x',padx=16,pady=(10,10))
sidebar_info=UI.RoundedPanel(sidebar,outer=SIDE,color=PANEL,radius=12);sidebar_info.pack(side='bottom',fill='x',padx=16,pady=(0,4))
sidebar_total=tk.StringVar(value='0');sidebar_connected=tk.StringVar(value='0')
for _cap,_var,_col,_ic in [('Total akun',sidebar_total,WHITE,'users'),('Chrome aktif',sidebar_connected,GREEN,'globe')]:
    _row=tk.Frame(sidebar_info,bg=PANEL);_row.pack(fill='x',padx=14,pady=(12,0) if _cap=='Total akun' else (6,12))
    UI.icon_badge(_row,_ic,_col if _col!=WHITE else PURPLE,PANEL,32).pack(side='left')
    _txt=tk.Frame(_row,bg=PANEL);_txt.pack(side='left',padx=(10,0))
    label(_txt,_cap,8,DIM).pack(anchor='w')
    tk.Label(_txt,textvariable=_var,font=(FONT,14,'bold'),fg=_col,bg=PANEL).pack(anchor='w')
main=tk.Frame(root,bg=BG);main.pack(side='left',fill='both',expand=True,padx=24,pady=20)
# Halaman Dashboard (tata letak seperti 3.12.1). Saat pindah halaman, frame ini
# disembunyikan sepenuhnya, bukan ditimpa, agar tidak ada sisa gambar/bayangan.
dash=tk.Frame(main,bg=BG);dash.pack(fill='both',expand=True)
head=tk.Frame(dash,bg=BG);head.pack(fill='x',pady=(0,16))
left_head=tk.Frame(head,bg=BG);left_head.pack(side='left')
label(left_head,'Dashboard',22,bold=True).pack(anchor='w')
last_update=tk.StringVar(value='')
_sub=tk.Frame(left_head,bg=BG);_sub.pack(anchor='w',pady=(2,0))
tk.Label(_sub,textvariable=last_update,font=(FONT,9),fg=MUTED,bg=BG).pack(side='left')
sync_status=tk.StringVar(value=sync_settings()['last_summary'])
tk.Label(_sub,textvariable=sync_status,font=(FONT,9),fg=PURPLE,bg=BG).pack(side='left',padx=(14,0))
# Satu periode untuk Dashboard dan Analytics.
today=date.today();first=today.replace(day=1)
start_var=tk.StringVar(value=str(first));end_var=tk.StringVar(value=str(today));platform_var=tk.StringVar(value='Semua Platform')
analytics_start_var=start_var;analytics_end_var=end_var
def _period_changed():
    refresh()
button(head,'⟳  Refresh',lambda:(poll_chrome_status(),refresh())).pack(side='right',padx=(8,0))
menu_button(head,'Sinkron',[('Sinkron semua akun (periode terpilih)',lambda:start_sync()),('Sinkron per bulan…',ask_month_and_sync),
                            ('Hentikan sinkron',stop_sync),None,
                            ('Lihat laporan sinkron',open_sync_log),('Pengaturan sinkron…',lambda:switch_page('Pengaturan'))],
            icon='sync',variant='subtle').pack(side='right',padx=(8,0))
platforms=['Semua Platform','Spotify','TikTok','Amazon Music','YouTube Music','Apple Music','Lainnya']
ttk.Combobox(head,textvariable=platform_var,values=platforms,state='readonly',style='Dark.TCombobox',width=16).pack(side='right',padx=(8,0))
platform_var.trace_add('write',lambda *_:refresh())
period_button=PeriodButton(head,start_var,end_var,_period_changed);period_button.pack(side='right')
# Dua ringkasan negara di bagian atas dashboard: Indonesia dan Amerika Serikat.
US_NAMES=('amerika serikat','united states','usa','us')
def in_country(a,country):
    cat=account_category(a).casefold()
    return cat in US_NAMES if country=='Amerika Serikat' else cat==country.casefold()
summary=tk.Frame(dash,bg=BG);summary.pack(fill='x',pady=(0,14))
country_panel_vars=[]
for idx,country in enumerate(('Indonesia','Amerika Serikat')):
    box=panel(summary)
    box.grid(row=0,column=idx,sticky='nsew',padx=(0,7) if idx==0 else (7,0))
    summary.grid_columnconfigure(idx,weight=1,uniform='country_summary')
    header=tk.Frame(box,bg=PANEL);header.pack(fill='x',padx=18,pady=(14,10))
    icon_badge(header,'flag' if idx==0 else 'globe',RED if idx==0 else BLUE,PANEL,34).pack(side='left',padx=(0,10))
    tk.Label(header,text=country,font=(FONT,13,'bold'),fg=WHITE,bg=PANEL).pack(side='left')
    body=tk.Frame(box,bg=PANEL);body.pack(fill='x',padx=14,pady=(0,14))
    fields={}
    specs=[('Streams',PURPLE,'wave'),('Pendengar',GREEN,'headphones'),('Saldo Tersedia',BLUE,'wallet'),('Jumlah Akun',AMBER,'users')]
    for n,(title,accent,glyph) in enumerate(specs):
        cell=tk.Frame(body,bg=CARD);cell.grid(row=n//2,column=n%2,sticky='nsew',padx=4,pady=4)
        body.grid_columnconfigure(n%2,weight=1,uniform='metric')
        inner=tk.Frame(cell,bg=CARD);inner.pack(fill='both',expand=True,padx=14,pady=12)
        icon_badge(inner,glyph,accent,CARD,36).pack(side='left',padx=(0,12))
        text=tk.Frame(inner,bg=CARD);text.pack(side='left',fill='both',expand=True)
        label(text,title,9,DIM).pack(anchor='w')
        val=tk.StringVar(value='—')
        tk.Label(text,textvariable=val,font=(FONT,15,'bold'),fg=WHITE,bg=CARD,anchor='w').pack(anchor='w',pady=(1,0))
        fields[title]=val
    country_panel_vars.append((country,fields))

# Ringkasan Inventaris HP pada Dashboard utama.
inventory_dash=panel(dash);inventory_dash.pack(fill='x',pady=(0,14))
inv_head=tk.Frame(inventory_dash,bg=PANEL);inv_head.pack(fill='x',padx=18,pady=(12,8))
label(inv_head,'Inventaris HP',13,bold=True).pack(side='left')
button(inv_head,'Buka Inventaris',lambda:switch_page('Inventaris HP'),icon='external',height=30,font_size=9).pack(side='right')
inv_metrics=tk.Frame(inventory_dash,bg=PANEL);inv_metrics.pack(fill='x',padx=14,pady=(0,14))
inventory_dashboard_vars={}
for i,(title,color,glyph) in enumerate([('DIPAKAI AKUN',PURPLE,'phone'),('TERSEDIA',GREEN,'check'),('SERVICE',BLUE,'wrench'),('RUSAK',RED,'alert'),('TIDAK TERPAKAI',MUTED,'circle'),('TOTAL HP',AMBER,'grid')]):
    cell=tk.Frame(inv_metrics,bg=CARD);cell.grid(row=0,column=i,sticky='nsew',padx=4,pady=0);inv_metrics.grid_columnconfigure(i,weight=1,uniform='inv')
    inner=tk.Frame(cell,bg=CARD);inner.pack(fill='both',expand=True,padx=12,pady=10)
    icon_badge(inner,glyph,color,CARD,32).pack(side='left',padx=(0,10))
    text=tk.Frame(inner,bg=CARD);text.pack(side='left',fill='both',expand=True)
    label(text,title.capitalize() if title!='TOTAL HP' else 'Total HP',9,DIM).pack(anchor='w')
    v=tk.StringVar(value='0');inventory_dashboard_vars[title]=v
    tk.Label(text,textvariable=v,font=(FONT,14,'bold'),fg=WHITE,bg=CARD,anchor='w').pack(anchor='w')
def update_inventory_dashboard():
    assigned=assigned_phone_count();others=sum(phone_inventory[k] for k in ('tersedia','service','rusak','tidak_terpakai'))
    vals={'DIPAKAI AKUN':assigned,'TERSEDIA':phone_inventory['tersedia'],'SERVICE':phone_inventory['service'],'RUSAK':phone_inventory['rusak'],'TIDAK TERPAKAI':phone_inventory['tidak_terpakai'],'TOTAL HP':assigned+others}
    for k,v in vals.items(): inventory_dashboard_vars[k].set(number(v))

def update_country_panels(start,end,platform):
    # Ringkasan selalu memuat semua akun negara tersebut, tidak terpengaruh pencarian/filter tabel.
    for country,fields in country_panel_vars:
        members=[a for a in accounts if in_country(a,country)]
        recs=[latest(a,start,end,platform) for a in members]
        fields['Streams'].set(number(sum((r or {}).get('streams',0) for r in recs)))
        fields['Pendengar'].set(number(sum((r or {}).get('listeners',0) for r in recs)))
        fields['Saldo Tersedia'].set(grouped_balance(members))
        fields['Jumlah Akun'].set(str(len(members)))
bar=tk.Frame(dash,bg=BG);bar.pack(fill='x',pady=(0,10))
label(bar,'Daftar Akun',14,bold=True).pack(side='left',padx=(0,6))
category_var=tk.StringVar(value='Semua Kategori')
category_filter=ttk.Combobox(bar,textvariable=category_var,values=['Semua Kategori']+categories,state='readonly',style='Dark.TCombobox',width=17)
category_filter.pack(side='left',padx=6)
category_var.trace_add('write',lambda *_:refresh())
button(bar,'＋  Kategori',add_category,height=32,font_size=9).pack(side='left',padx=3)
view_var=tk.StringVar(value='Tabel Semua')
view_filter=ttk.Combobox(bar,textvariable=view_var,values=['Kolom Negara','Tabel Semua'],state='readonly',style='Dark.TCombobox',width=13)
view_filter.pack(side='left',padx=6)
view_var.trace_add('write',lambda *_:refresh())
search_var=tk.StringVar();sort_var=tk.StringVar(value='Streams terbanyak')
search=UI.search_entry(bar,search_var,'Cari nama atau ID akun…',width=22)
search.pack(side='right',padx=(8,0))
_search_job=None
def delayed_search(*_):
    global _search_job
    if _search_job is not None:root.after_cancel(_search_job)
    _search_job=root.after(180,refresh)
search_var.trace_add('write',delayed_search)
ttk.Combobox(bar,textvariable=sort_var,values=['Streams terbanyak','Streams tersedikit','Saldo terbesar','Nama A–Z'],state='readonly',style='Dark.TCombobox',width=17).pack(side='right',padx=6)
sort_var.trace_add('write',lambda *_:refresh())
label(bar,'Urutkan',9,DIM).pack(side='right')
status_var=tk.StringVar();tk.Label(dash,textvariable=status_var,font=(FONT,9),fg=MUTED,bg=BG,anchor='w').pack(side='bottom',fill='x',pady=(4,0))
total_line=tk.Frame(dash,bg=BG);total_line.pack(side='bottom',fill='x',pady=(10,0))
totals_var=tk.StringVar();tk.Label(total_line,textvariable=totals_var,font=(FONT,10,'bold'),fg=GREEN,bg=BG,anchor='w').pack(side='left')
wrap=panel(dash);wrap.pack(fill='both',expand=True)
from account_table import AccountTable
def _row_menu(r):
    a=r['account']
    return [('Baca Streams',lambda:read_visible(a,'streams')),('Baca Pendengar',lambda:read_visible(a,'listeners')),
            ('Baca Saldo',lambda:read_visible(a,'balance'))]
# Bilah pilihan: muncul saat ada akun yang dicentang (untuk hapus sekaligus).
sel_bar=tk.Frame(wrap,bg=UI.mix(PANEL,RED,0.08))
sel_text=tk.StringVar()
UI.icon(sel_bar,'box-check',16,PURPLE,UI.mix(PANEL,RED,0.08)).pack(side='left',padx=(14,8),pady=10)
tk.Label(sel_bar,textvariable=sel_text,bg=UI.mix(PANEL,RED,0.08),fg=WHITE,font=(FONT,10,'bold')).pack(side='left')
RoundButton(sel_bar,'Batal',lambda:account_table.clear_selection(),variant='ghost',height=30,font_size=9).pack(side='right',padx=(4,10))
RoundButton(sel_bar,'Hapus akun terpilih',lambda:delete_accounts([r['account'] for r in account_table.selected_rows()]),
            icon='trash',variant='danger',height=30,font_size=9).pack(side='right')
def _selection_changed(count):
    if count:
        sel_text.set(f'{count} akun dipilih')
        if not sel_bar.winfo_manager() and account_table.winfo_manager():sel_bar.pack(fill='x',padx=8,pady=(8,0),before=account_table)
    elif sel_bar.winfo_manager():sel_bar.pack_forget()
account_table=AccountTable(wrap,{'open':lambda r:open_streams(r['account']),'data':lambda r:edit(r['account']),
                                 'more':lambda r:show_actions(r['account']),'delete':lambda r:delete_accounts([r['account']])},_row_menu)
account_table.on_selection=_selection_changed
account_table.pack(fill='both',expand=True,padx=8,pady=8)
# Tampilan Kolom Negara (kartu) memakai area gulir sendiri.
country_box=tk.Frame(wrap,bg=PANEL)
canvas=tk.Canvas(country_box,bg=PANEL,highlightthickness=0)
scroll=ttk.Scrollbar(country_box,orient='vertical',command=canvas.yview,style='Dark.Vertical.TScrollbar')
canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y',padx=(0,4),pady=10);canvas.pack(side='left',fill='both',expand=True,padx=(6,0),pady=6)
rows=tk.Frame(canvas,bg=PANEL);win_id=canvas.create_window((0,0),window=rows,anchor='nw')
rows.bind('<Configure>',lambda e:canvas.configure(scrollregion=(0,0,canvas.winfo_width(),rows.winfo_reqheight())))
canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win_id,width=e.width))
# Full-size independent content surface for sidebar pages; dashboard widgets stay intact.
page_overlay=tk.Frame(main,bg=BG)
page_header=tk.Frame(page_overlay,bg=BG);page_header.pack(fill='x',pady=(0,16))
page_title=label(page_header,'Daftar Akun',22,bold=True);page_title.pack(anchor='w')
page_subtitle=label(page_header,'',10,DIM);page_subtitle.pack(anchor='w',pady=(2,0))
page_wrap=panel(page_overlay);page_wrap.pack(fill='both',expand=True)
page_canvas=tk.Canvas(page_wrap,bg=PANEL,highlightthickness=0)
page_scroll=ttk.Scrollbar(page_wrap,orient='vertical',command=page_canvas.yview,style='Dark.Vertical.TScrollbar')
page_canvas.configure(yscrollcommand=page_scroll.set)
page_scroll.pack(side='right',fill='y',padx=(0,4),pady=10);page_canvas.pack(side='left',fill='both',expand=True,padx=(4,0),pady=4)
page_body=None
page_window=None
def _page_region():
    if page_body is None:return
    try:page_canvas.configure(scrollregion=(0,0,page_canvas.winfo_width(),page_body.winfo_reqheight()))
    except tk.TclError:pass

def _resize_page_windows(event):
    for win in list(page_windows.values()):
        try: page_canvas.itemconfigure(win,width=event.width)
        except tk.TclError: pass
    root.after_idle(_page_region)
page_canvas.bind('<Configure>',_resize_page_windows)
# Satu pengendali gulir untuk seluruh aplikasi (lihat ui_theme.WheelScroller).
def _active_scroll_canvas():
    if active_page!='Dashboard' and page_overlay.winfo_manager():return page_canvas
    return canvas if country_box.winfo_manager() else account_table.body
scroller=UI.WheelScroller(root,_active_scroll_canvas)
root.after(50,_drain_ui_queue)
refresh()
# Status Chrome tiap akun diperiksa di latar belakang (localhost saja) setiap 20 detik.
def _chrome_status_loop():
    poll_chrome_status()
    root.after(20000,_chrome_status_loop)
root.after(1500,_chrome_status_loop)
root.after(180000,_sync_scheduler)   # cek jadwal sinkron 3 menit setelah aplikasi dibuka, lalu tiap menit
root.after(60000,_update_watcher)    # cek pembaruan GitHub tiap 20 menit selama aplikasi terbuka
try:
    import release_publisher as _rp_boot
    if _rp_boot.load_token():_rp_boot.ensure_folders()
except Exception:pass
root.after(20000,_publisher_watcher)  # komputer admin: terbitkan rilis dari ~/SoundOnRilis/masuk
root.mainloop()
if _restart_for_update:
    # 75 = keluar untuk pembaruan; run_app.bat menutup konsol lama tanpa pause.
    os._exit(75)
