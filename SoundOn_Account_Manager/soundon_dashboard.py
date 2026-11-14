"""SoundOn multi-account dashboard; optional read-only visible-page capture."""
import calendar
import json
import os
import shutil
import subprocess
import re
import threading
import time
import urllib.request
import sys
import urllib.parse
import base64
import tkinter as tk
if sys.stdout is None or sys.stderr is None:
    # Dibuka dengan pythonw (tanpa jendela cmd): pesan galat dicatat ke file.
    try:
        _log_path=os.path.join(os.path.expanduser('~'),'SoundOnAccounts','app_log.txt')
        os.makedirs(os.path.dirname(_log_path),exist_ok=True)
        _big=os.path.exists(_log_path) and os.path.getsize(_log_path)>1_000_000
        sys.stdout=sys.stderr=open(_log_path,'w' if _big else 'a',encoding='utf-8',buffering=1)
        print('--- dibuka',time.strftime('%Y-%m-%d %H:%M:%S'))
    except OSError:
        pass
from artist_finance import save_artist, owner_groups, available_artists, assign_artists, rename_owner, remove_owner

# Izin perangkat SoundOn
from device_license import check_license
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
from ui_theme import (bg_of, BG, SIDE, PANEL, CARD, LINE, WHITE, DIM, MUTED, PURPLE, GREEN, RED, BLUE, AMBER,
                      FONT, RoundedPanel, RoundButton, icon_badge, avatar, pill, menu_button, ACCENTS)
APP_VERSION='3.22.2'
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
    get_list_vars()['view'].set('Per Pemilik')
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
                          # Jangan perlambat tab/jendela yang tidak terlihat: bot unggah dan sinkron
                          # tetap berjalan normal saat Chrome diminimalkan atau tertutup jendela lain.
                          '--disable-background-timer-throttling',
                          '--disable-renderer-backgrounding',
                          '--disable-backgrounding-occluded-windows',
                          '--new-window',target_url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
                # SoundOn kadang menyelipkan halaman promosi paket; buka ulang tujuan.
                for _ in range(auto_sync.PROMO_SKIPS):
                    time.sleep(2)
                    try:promo=bool(auto_sync.UPGRADE_URL.search(urllib.parse.urlsplit(page.url).path or '')
                                   or page.get_by_text(auto_sync.UPGRADE_TEXT).count())
                    except Exception:promo=False
                    if not promo:break
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

def edit_artists(a,default_owner="",target_artist=None):
    """Artis pada akun ini beserta pemiliknya (tambah, ubah nama/pemilik, hapus)."""
    import copy
    w=tk.Toplevel(root);w.title('Artis & Pemilik');w.geometry('760x560')
    w.minsize(700,500);w.configure(bg=PANEL);w.transient(root);w.grab_set()
    label(w,'Artis & Pemilik',15,bold=True).pack(anchor='w',padx=22,pady=(20,6))
    label(w,a['name']+' · Saldo akun dibaca otomatis lewat Sinkron',10,DIM).pack(anchor='w',padx=22,pady=(0,12))
    selected=[target_artist]
    def populate():
        table.delete(*table.get_children())
        for artist in a.get('artists',[]):
            table.insert('', 'end',iid=str(artist['id']),values=(artist['name'],artist.get('owner') or 'Belum ditentukan'))
        if selected[0] is not None and table.exists(str(selected[0])):
            table.selection_set(str(selected[0]))
            choose()
    tablebox=tk.Frame(w,bg=PANEL);tablebox.pack(fill='both',expand=True,padx=22)
    table=ttk.Treeview(tablebox,columns=('artist','owner'),show='headings',selectmode='browse',height=6,style='Dark.Treeview')
    for key,title,width in [('artist','Nama artis',360),('owner','Pemilik',260)]:
        table.heading(key,text=title);table.column(key,width=width,minwidth=120,stretch=True)
    scroll=ttk.Scrollbar(tablebox,orient='vertical',command=table.yview,style='Dark.Vertical.TScrollbar')
    table.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)
    form=tk.Frame(w,bg=PANEL);form.pack(fill='x',padx=22,pady=(14,6))
    name_var=tk.StringVar();owner_var=tk.StringVar(value=default_owner)
    for title,var in [('Nama artis',name_var),('Pemilik artis',owner_var)]:
        row=tk.Frame(form,bg=PANEL);row.pack(fill='x',pady=4)
        label(row,title,10,DIM,width=16,anchor='w').pack(side='left')
        if title=='Pemilik artis':
            ttk.Combobox(row,textvariable=var,values=owner_names(),style='Dark.TCombobox',font=(FONT,11)).pack(side='left',fill='x',expand=True,ipady=5)
        else:
            tk.Entry(row,textvariable=var,bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',font=(FONT,11)).pack(side='left',fill='x',expand=True,ipady=5)
    def choose(event=None):
        selection=table.selection()
        if not selection:return
        selected[0]=int(selection[0])
        artist=next(x for x in a.get('artists',[]) if x['id']==selected[0])
        name_var.set(artist['name']);owner_var.set(artist.get('owner',''))
    table.bind('<<TreeviewSelect>>',choose)
    def new():
        selected[0]=None
        name_var.set('');owner_var.set(default_owner)
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
            artist=save_artist(a,selected[0],name_var.get(),owner_var.get())
            selected[0]=artist['id']
        commit(change)
    def remove_artist():
        if selected[0] is None:return
        if not messagebox.askyesno('Hapus artis','Hapus artis terpilih dari akun ini?',parent=w):return
        target=selected[0]
        def change():a['artists']=[x for x in a['artists'] if x['id']!=target]
        if commit(change):new()
    actions=tk.Frame(w,bg=PANEL);actions.pack(side='bottom',fill='x',padx=22,pady=(10,18),before=tablebox)
    for title,fn in [('Tambah Artis',new),('Simpan',save),('Hapus Artis',remove_artist),('Tutup',w.destroy)]:
        button(actions,title,fn,title=='Simpan').pack(side='left',padx=(0,7))
    populate()


def render_artists(parent,a):
    section=tk.Frame(parent,bg=CARD);section.pack(fill='x',pady=(12,0))
    top=tk.Frame(section,bg=CARD);top.pack(fill='x',padx=14,pady=(10,6))
    label(top,'ARTIS & PEMILIK',9,DIM,bold=True).pack(side='left')
    button(top,'Atur Artis & Pemilik',lambda:edit_artists(a),font_size=9,height=28).pack(side='right')
    rows=tk.Frame(section,bg=CARD);rows.pack(fill='x',padx=14,pady=(0,10))
    for col,weight in enumerate([3,2]):rows.columnconfigure(col,weight=weight,uniform='artist')
    for col,title in enumerate(['Nama artis','Pemilik']):
        label(rows,title,10,DIM,bold=True,anchor='w').grid(row=0,column=col,sticky='ew',padx=5,pady=5)
    artists=a.get('artists',[])
    for row,artist in enumerate(artists,1):
        for col,value in enumerate([artist['name'],artist.get('owner') or 'Belum ditentukan']):
            cell=label(rows,value,11,WHITE,anchor='w')
            cell.configure(wraplength=230,justify='left')
            cell.grid(row=row,column=col,sticky='ew',padx=5,pady=5)
            cell.bind('<Configure>',lambda e,l=cell:l.configure(wraplength=max(50,e.width-6)))
    if not artists:
        label(rows,'Belum ada data artis.',10,DIM).grid(row=1,column=0,columnspan=2,sticky='w',padx=5,pady=7)


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
import transactions as TX
SYNC_LOG=os.path.join(BASE,'sync_log.txt')
_sync_state={'running':False,'stop':False,'text':''}

def _sync_workers(value):
    try:return max(1,min(3,int(value)))
    except (TypeError,ValueError):return 1

def sync_settings():
    st=UI.load_settings()
    try:hour=max(0,min(23,int(st.get('sync_hour',8))))
    except (TypeError,ValueError):hour=8
    return {'enabled':bool(st.get('sync_enabled',True)),'hour':hour,'open_closed':bool(st.get('sync_open_closed',True)),
            'balance':bool(st.get('sync_balance',True)),'regions':bool(st.get('sync_regions',True)),
            'retry_failed':bool(st.get('sync_retry_failed',True)),
            'transactions':bool(st.get('sync_transactions',True)),
            'workers':_sync_workers(st.get('sync_workers',1)),'hidden':bool(st.get('sync_hidden',True)),
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

def start_sync(auto=False,periods=None,only_ids=None,plat=None):
    """Baca Streams & Pendengar semua akun dari Analytics SoundOn (di latar belakang).
    only_ids: hanya akun ini (Ulangi yang belum berhasil), tanpa konfirmasi."""
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
    plat=plat or platform_var.get()
    note=''
    if plat not in auto_sync.SUPPORTED_PLATFORMS:
        note=f'\n\nPlatform {plat} belum didukung sinkron otomatis; yang dibaca: Semua Platform.'
        plat='Semua Platform'
    cfg=sync_settings()
    targets=list(accounts)
    if only_ids is not None:
        wanted={str(x) for x in only_ids}
        targets=[a for a in accounts if str(a['id']) in wanted]
        if not targets:
            messagebox.showinfo('Tidak ada akun','Akun yang perlu diulang sudah tidak ada di daftar.',parent=root);return
    if not auto and only_ids is None:
        minutes=max(1,round(len(targets)*(35+(25 if cfg['balance'] else 0)+(60 if cfg['regions'] else 0)+(20 if cfg['transactions'] else 0))/60/cfg['workers']))
        extra=(('Chrome akun yang tertutup dibuka '+('tanpa jendela (tersembunyi)' if cfg['hidden'] else '(diperkecil)')+' lalu ditutup lagi.')
               if cfg['open_closed'] else 'Hanya akun yang Chrome-nya sedang terbuka yang dibaca.')
        if cfg['workers']>1:extra+=f'\n{cfg["workers"]} Chrome dibaca bersamaan.'
        what='Streams & Pendengar'+(', Saldo' if cfg['balance'] else '')+(', Asal Streams per artis' if cfg['regions'] else '')+(', Riwayat Transaksi' if cfg['transactions'] else '')
        ptxt=', '.join(f'{p[0]} s.d. {p[1]}' for p in periods)
        if not messagebox.askyesno('Sinkron semua akun',f'Baca {what} untuk {len(targets)} akun\nPeriode: {ptxt} · {plat}\n\n{extra}\n'
                                   f'Perkiraan waktu ± {minutes} menit. Aplikasi tetap bisa dipakai.{note}\n\nMulai sekarang?',parent=root):return
    _sync_state.update(running=True,stop=False,periods=list(periods),plat=plat)
    _set_sync_status(f'Sinkron dimulai · {len(targets)} akun'+(' (ulang)' if only_ids is not None else ''))
    busy=_upload_busy_accounts()
    def apply_balance(a,amount,currency):
        if a in accounts:
            a['balance']=amount;a['currency']=currency;a['balance_updated']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            persist()
            if active_page=='Dashboard':refresh()
    def apply_transactions(a,rows):
        if a in accounts:
            a['transactions']=TX.merge(a.get('transactions'),rows);persist()
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
        on_region=lambda a,row:ui_call(lambda:apply_region(a,row)),retry_failed=cfg['retry_failed'],
        workers=cfg['workers'],hidden=cfg['hidden'],
        on_transactions=(lambda a,rows:ui_call(lambda:apply_transactions(a,rows))) if cfg['transactions'] else None)
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
    if summary:
        # Akun yang belum berhasil disimpan agar bisa diulang (juga setelah aplikasi dibuka ulang).
        pending=[str(a['id']) for key in ('login','gagal','lewati') for a,_ in summary[key]]
        retry={'ids':pending,'platform':_sync_state.get('plat','Semua Platform'),
               'periods':[[str(s),str(e)] for s,e in _sync_state.get('periods',[])]}
        try:UI.save_settings(sync_retry=retry)
        except OSError:pass
    refresh()
    if not auto:
        detail=''
        if summary:
            for key,title in (('login','Perlu login'),('gagal','Gagal'),('lewati','Dilewati')):
                if summary[key]:
                    detail+=f'\n\n{title}:\n'+'\n'.join('•  '+a.get('name','')+' — '+n for a,n in summary[key][:10])
                    if len(summary[key])>10:detail+=f'\n…dan {len(summary[key])-10} lainnya'
        _sync_done_dialog(text+detail,[a for a,_ in summary['login']] if summary else [])

SYNC_LINE=re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}):\d{2}\s+\[(OK|LOGIN|LEWATI|GAGAL)\] (.*) \(#([^)]+)\): (.*)$')

def _sync_log_lines(limit=4_000_000):
    """Baris laporan sinkron (bagian akhir, maks. 4 MB agar tetap cepat), atau None bila belum ada."""
    try:
        with open(SYNC_LOG,'rb') as f:
            f.seek(0,2);size=f.tell();f.seek(max(0,size-limit));data=f.read()
    except OSError:
        return None
    return data.decode('utf-8','replace').splitlines()

def sync_results():
    """Semua hasil per akun di laporan, urut waktu: [(waktu, STATUS, id, nama, catatan)]."""
    out=[]
    for line in _sync_log_lines() or []:
        m=SYNC_LINE.match(line)
        if m:out.append((m.group(1),m.group(2),m.group(4),m.group(3),m.group(5)))
    return out

def latest_sync_status():
    """Status TERBARU tiap akun dari seluruh laporan: {id: STATUS}. Putaran ulang yang hanya berisi
    beberapa akun tidak menghapus hasil akun lain dari putaran sebelumnya."""
    return {aid:status for _,status,aid,_,_ in sync_results()}

def _retry_from_log():
    """Akun yang status terbarunya belum berhasil menurut sync_log.txt (ditulis semua versi), dengan
    periode dan platform sinkron terakhir. None bila belum pernah sinkron."""
    lines=_sync_log_lines()
    if lines is None:return None
    start=max((i for i,line in enumerate(lines) if 'Mulai sinkron ' in line),default=None)
    if start is None:return None
    m=re.search(r'Mulai sinkron \d+ akun · (.+) · ([^·]+)$',lines[start])
    periods=re.findall(r'(\d{4}-\d{2}-\d{2}) s\.d\. (\d{4}-\d{2}-\d{2})',m.group(1)) if m else []
    return {'ids':[i for i,st in latest_sync_status().items() if st!='OK'],'periods':periods,
            'platform':m.group(2).strip() if m else 'Semua Platform'}

def _pending_retry():
    """(akun, periode, platform) dari sinkron terakhir yang belum berhasil, atau None bila belum
    ada catatan sinkron sama sekali."""
    data=_retry_from_log() or UI.load_settings().get('sync_retry')
    if not data:return None
    ids={str(x) for x in data.get('ids',[])}
    try:periods=[(parse_date(s),parse_date(e)) for s,e in data.get('periods',[])]
    except (TypeError,ValueError):periods=[]
    return [a for a in accounts if str(a['id']) in ids],periods,data.get('platform') or 'Semua Platform'

def retry_failed_sync():
    """Sinkron ulang hanya akun yang belum berhasil pada sinkron terakhir (periode yang sama)."""
    pending=_pending_retry()
    if pending is None:
        messagebox.showinfo('Tidak ada yang diulang','Belum ada catatan sinkron. Jalankan sinkron terlebih dahulu.',parent=root);return
    targets,periods,plat=pending
    if not targets:
        messagebox.showinfo('Tidak ada yang diulang','Semua akun berhasil pada sinkron terakhir.',parent=root);return
    start_sync(periods=periods or None,only_ids=[a['id'] for a in targets],plat=plat)

def open_login_accounts(items):
    """Buka Chrome akun yang perlu login (satu jendela per akun) untuk login sekali."""
    for a in items:
        if not debugger_ready(a):open_account(a)

def _sync_done_dialog(text,login_items):
    pending=len((_pending_retry() or ([],))[0])
    if not pending:
        messagebox.showinfo('Sinkron selesai',text+'\n\nLaporan lengkap: Pengaturan > Sinkron Otomatis > Lihat laporan.',parent=root);return
    w=tk.Toplevel(root);w.title('Sinkron selesai');w.configure(bg=PANEL);w.transient(root);w.resizable(False,False)
    body=tk.Frame(w,bg=PANEL);body.pack(padx=22,pady=18,fill='both')
    label(body,'Sinkron selesai',14,bold=True).pack(anchor='w')
    label(body,text,10,justify='left',wraplength=520).pack(anchor='w',pady=(8,0))
    hint=('Login dulu lewat "Buka akun yang perlu login", lalu klik Ulangi.' if login_items else
          'Ulangi membaca lagi hanya akun di atas, dengan periode yang sama.')
    label(body,hint+'\nBisa juga nanti dari menu Sinkron > Ulangi akun yang belum berhasil.',9,DIM,justify='left',wraplength=520).pack(anchor='w',pady=(10,0))
    acts=tk.Frame(body,bg=PANEL);acts.pack(fill='x',pady=(16,0))
    def again():
        w.destroy();retry_failed_sync()
    button(acts,f'Ulangi yang belum berhasil ({pending})',again,True,icon='sync').pack(side='right')
    if login_items:
        button(acts,'Buka akun yang perlu login',lambda:open_login_accounts(login_items)).pack(side='right',padx=6)
    button(acts,'Tutup',w.destroy,variant='ghost').pack(side='right',padx=(0,6))

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
    try:
        if um is not None and um.window.winfo_exists() and (um.busy or um.has_pending_auto()):return True
    except Exception:
        pass
    return False

def _quick_pending(sources=('folder','cepat')):
    try:
        with open(os.path.join(BASE,'upload_queue.json'),encoding='utf-8') as f:
            return any(j.get('source') in sources and j.get('status')=='Menunggu' and not j.get('submit_clicked') for j in json.load(f))
    except (OSError,ValueError):
        return False

def quick_upload(a):
    """Tombol Unggah di baris akun: pilih file lagu -> langsung diunggah ke akun ini."""
    import upload_quick
    def go():
        artist=upload_quick.choose_artist(root,a)
        if not artist:return
        files=upload_quick.pick_files(root,a)
        if not files:return
        if a.get('upload_artist')!=artist:
            a['upload_artist']=artist
            try:persist()
            except OSError:pass
        d=upload_quick.load_defaults()
        jobs=[upload_quick.build_job(a,artist,f,d) for f in files]
        launch_upload_manager()
        um=globals().get('upload_manager_window')
        if um is None or not um.window.winfo_exists():return
        n=um.add_quick_jobs(jobs,a.get('name',''))
        status_var.set('%d lagu untuk %s masuk antrean unggah.'%(n,a.get('name','')))
    if not upload_quick.defaults_confirmed():
        upload_quick.edit_defaults(root,on_saved=go,first_time=True)
    else:
        go()

def _upload_watch_tick():
    """Folder pantau: buka Studio otomatis bila ada lagu baru atau antrean otomatis yang menunggu."""
    try:
        if UI.load_settings().get('upload_watch') or _quick_pending(('cepat',)):
            um=globals().get('upload_manager_window')
            open_now=um is not None and um.window.winfo_exists()
            if not open_now:
                import upload_folder
                pending=any(p.suffix.lower() in upload_folder.AUDIO_EXT for d in upload_folder.INBOX.glob('*') if d.is_dir() for p in d.iterdir()) \
                    if upload_folder.INBOX.exists() else False
                if not pending:
                    pending=_quick_pending()
                if pending:
                    launch_upload_manager()
                    status_var.set('Folder pantau: lagu baru ditemukan, Studio unggah dibuka otomatis.')
    except Exception:
        pass
    finally:
        root.after(30000,_upload_watch_tick)

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
    text=(f'{a["name"]} · {name.strip()}\n🇮🇩 Indonesia: {fmt(idn)}\n🇺🇸 Amerika Serikat: {fmt(us)}\n'
          f'Periode dikonfirmasi: {start} – {end}\n{len(regions)} wilayah terbaca.')
    warn=DC.region_warnings(idn,us)
    if warn:
        messagebox.showwarning('Peringatan Asal Streams',text+'\n\n⚠ '+' dan '.join(warn).replace('AS','Amerika Serikat').replace('ID','Indonesia')
                               +'. Periksa artis ini.',parent=root)
    else:
        messagebox.showinfo('Asal Streams tersimpan',text,parent=root)

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
    w=tk.Toplevel(root);w.title('Data SoundOn — '+a['name']);w.geometry('510x600');w.configure(bg=PANEL);w.transient(root);w.grab_set()
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
    label(w,'Jumlah HP, artis & lagu diatur lewat ⋯ > Atur jumlah HP, artis & lagu.',9,MUTED).pack(anchor='w',padx=24,pady=(6,0))
    def save_data():
        try:
            values={k:int(v.get().strip().replace('.','').replace(',','').replace(' ','')) for k,v in fields.items() if k in ('streams','listeners')}
            values['balance']=parse_amount(fields['balance'].get(),currency_var.get())
            if any(v<0 for v in values.values()):raise ValueError()
        except ValueError:
            messagebox.showerror('Angka tidak valid','Isi angka positif. Contoh saldo IDR: 4.160.229 atau 4160229; USD: 12,50 atau 12.50.',parent=w);return
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        upsert_record(a,{'start':str(start),'end':str(end),'platform':plat,'streams':values['streams'],'listeners':values['listeners'],'updated':now,'source':'input manual'})
        balance_changed=abs(values['balance']-float(a.get('balance') or 0))>0.004 or currency_var.get()!=a.get('currency','IDR')
        a['balance']=values['balance'];a['currency']=currency_var.get()
        if balance_changed or not a.get('balance_updated'):a['balance_updated']=now
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

HARI=['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
BULAN=['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember']
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
    update_overview(start,end,plat)
    connected=sum(bool(_chrome_status.get(str(a['id']),False)) for a in accounts)
    sidebar_total.set(str(len(accounts)))
    sidebar_connected.set(str(connected))
    last_update.set('Diperbarui lokal: '+datetime.now().strftime('%d/%m/%Y %H:%M'))
    status_var.set(f'{len(data)} akun ditampilkan  ·  {sum(bool(r) for a,r in data)} akun memiliki data periode ini  ·  Streams bertanda ≈ adalah perkiraan')
    now=datetime.now()
    greeting_var.set(f'{UI.greeting(now)}  ·  {HARI[now.weekday()]}, {now.day} {BULAN[now.month-1]} {now.year}')
    if sel_bar.winfo_manager() and not account_table.selected:sel_bar.pack_forget()
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

def restart_app():
    """Buka ulang aplikasi (dipakai saat mengganti mode tampilan)."""
    app_dir=os.path.dirname(os.path.abspath(__file__))
    bat=os.path.join(app_dir,'run_app.bat')
    import updater as _upd
    try:
        if _upd.app_command(app_dir):
            subprocess.Popen(_upd.app_command(app_dir),cwd=app_dir,creationflags=_upd.DETACHED|_upd.CREATE_NO_WINDOW,close_fds=True)
        elif os.name=='nt' and os.path.exists(bat):
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
    items=[('Unggah lagu ke akun ini','music',lambda:quick_upload(a),'primary'),
           ('Ubah nama','edit',lambda:rename(a),'secondary'),
           ('Atur jumlah HP, artis & lagu','grid',lambda:edit_account_counts(a),'secondary'),
           ('Pindahkan kategori / negara','tag',lambda:change_category(a),'secondary'),
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

def page_account_actions(parent,a):
    action=tk.Frame(parent,bg=PANEL);action.pack(side='right',padx=8)
    items=[('Buka',lambda a=a:open_account(a)),
           ('Streams',lambda a=a:read_visible(a,'streams')),
           ('Pendengar',lambda a=a:read_visible(a,'listeners')),
           ('Saldo',lambda a=a:read_visible(a,'balance'))]
    items.append(('Asal Streams',lambda a=a:read_regions(a)))
    items.append(('Data',lambda a=a:edit(a)))
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
    if messagebox.askyesno('Hapus Pemilik',f'Hapus pemilik {owner}?\nArtisnya akan masuk Belum ditentukan. Akun tetap tersimpan.',parent=root):
        commit_ownership_change(lambda:remove_owner(accounts,owners,owner))

def artist_options(a,artist):
    menu=tk.Menu(root,tearoff=False,bg=PANEL,fg=WHITE,activebackground=PURPLE,activeforeground=WHITE)
    menu.add_command(label='Atur Artis & Pemilik',command=lambda:edit_artists(a,target_artist=artist['id'] if artist else None))
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
            if messagebox.askyesno('Lepaskan Artis',f'Lepaskan {artist["name"]} dari pemiliknya?\nArtis bisa dipilih oleh pemilik lain.',parent=root):
                commit_ownership_change(lambda:artist.update(owner=''))
        def delete_artist():
            if messagebox.askyesno('Hapus Artis Permanen',f'Hapus {artist["name"]} dari daftar artis? Akun SoundOn tetap ada.',parent=root):
                commit_ownership_change(lambda:a['artists'].remove(artist))
        menu.add_command(label='Ubah Nama Artis',command=rename_artist)
        if artist.get('owner'):menu.add_command(label='Lepaskan dari Pemilik',command=release)
        menu.add_command(label='Hapus Artis Permanen',command=delete_artist)
        menu.add_separator()
    menu.add_command(label='Kelola Akun SoundOn',command=lambda:show_actions(a))
    menu.tk_popup(root.winfo_pointerx(),root.winfo_pointery())


def fixed_area():
    """Panel di atas daftar yang tetap terlihat saat halaman digulir."""
    box=panel(page_fixed);box.pack(fill='x',pady=(0,12))
    inner=tk.Frame(box,bg=PANEL);inner.pack(fill='x',padx=18,pady=14)
    return inner

def clear_traces(variables):
    """Lepas pemantau variabel dari tampilan sebelumnya (widgetnya sudah dihancurkan)."""
    for var in variables:
        for trace in var.trace_info():
            try:var.trace_remove(*trace)
            except tk.TclError:pass

def stat_row(parent,specs,height=110):
    """Deret kartu ringkasan. specs=[(judul, ikon, nilai, keterangan[, chip, warna])]."""
    row=tk.Frame(parent,bg=PANEL);row.pack(fill='x')
    cards=[]
    for i,spec in enumerate(specs):
        title,icon,value,sub=spec[:4]
        card=DC.StatCard(row,title,icon,height=height);card.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 6,0))
        row.grid_columnconfigure(i,weight=1,uniform='stat')
        card.set(value,sub,*(spec[4:6] if len(spec)>4 else ()))
        cards.append(card)
    return cards

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
        a=entry['account'];artist=entry['artist']
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
    clear(page_body);clear(page_fixed)
    # Frame kosong tidak mengecil sendiri di Tk: tanpa ini halaman tanpa ringkasan tetap (Inventaris,
    # Pengaturan) menyisakan ruang kosong setinggi ringkasan halaman sebelumnya.
    page_fixed.configure(height=1)
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
        v=get_list_vars();clear_traces(v.values())
        month=v['month'].get()
        q=v['q'].get().strip().casefold()
        def match(*texts):return not q or any(q in str(t).casefold() for t in texts)
        def acct_income(a):return money_by_currency(accounts_month([a],month,'income'))
        top=fixed_area()
        bar_f=tk.Frame(top,bg=PANEL);bar_f.pack(fill='x',pady=(0,12))
        button(bar_f,'＋  Tambah Pemilik',add_owner,True).pack(side='left',padx=(0,8))
        ttk.Combobox(bar_f,textvariable=v['view'],values=['Per Pemilik','Per Akun'],state='readonly',width=12,style='Dark.TCombobox').pack(side='left',padx=(0,12))
        label(bar_f,'BULAN',8,MUTED,bold=True).pack(side='left',padx=(0,8))
        MonthButton(bar_f,v['month']).pack(side='left')
        search_box=UI.search_entry(bar_f,v['q'],'Cari pemilik, artis, atau akun…',width=24);search_box.pack(side='right')
        if _list_focus[0]:
            # Halaman dibangun ulang saat mengetik: kembalikan kursor ke kolom cari.
            _list_focus[0]=False
            for w in search_box.winfo_children():
                if isinstance(w,tk.Entry):w.focus_set();w.icursor('end')
        rerender=lambda *_:root.after_idle(render_active_page)
        if v['view'].get()=='Per Pemilik':
            groups=[g for g in owner_groups(accounts,owners)
                    if match(g['owner'],*[e['account']['name'] for e in g['entries']],*[(e['artist'] or {}).get('name','') for e in g['entries']])]
            names=[g['owner'] for g in groups]
            if v['owner'].get() not in names:v['owner'].set(names[0] if names else '')
            idx=names.index(v['owner'].get()) if names else 0
            # ---- Halaman per pemilik: ‹ 1 2 3 … ›
            pager=tk.Frame(top,bg=PANEL);pager.pack(fill='x',pady=(0,12))
            label(pager,f'PEMILIK {idx+1 if names else 0} DARI {len(names)}',8,MUTED,bold=True).pack(side='left',padx=(0,10))
            def go(i):
                if names:v['owner'].set(names[max(0,min(len(names)-1,i))]);root.after_idle(render_active_page)
            RoundButton(pager,'‹',lambda:go(idx-1),height=30,padx=10).pack(side='left',padx=(0,4))
            lo=max(0,min(idx-4,len(names)-9));hi=min(len(names),lo+9)
            for i in range(lo,hi):
                text=f'{i+1}  {short_name(names[i],16)}'
                RoundButton(pager,text,lambda i=i:go(i),variant='primary' if i==idx else 'secondary',height=30,font_size=9,padx=10).pack(side='left',padx=2)
            RoundButton(pager,'›',lambda:go(idx+1),height=30,padx=10).pack(side='left',padx=(4,0))
            g=groups[idx] if groups else None
            linked=list(g['accounts'].values()) if g else []
            synced=[a for a in linked if a.get('balance_updated')]
            stat_row(top,[('Artis','music',str(sum(e['artist'] is not None for e in g['entries'])) if g else '0',
                           f'{len(linked)} akun SoundOn'),
                          ('Saldo','wallet',grouped_balance(synced) if synced else '—','dari sinkron terakhir'),
                          ('Pendapatan '+month,'flag',money_by_currency(accounts_month(linked,month,'income')),
                           f'{sum(1 for a in linked if any(x["income"] for x in TX.month_summary(a.get("transactions"),month).values()))} akun berpendapatan'),
                          ('Ditarik '+month,'export',money_by_currency(accounts_month(linked,month,'out')),'dari riwayat transaksi')])
            if not g:
                label(page_body,'Belum ada pemilik yang cocok. Klik Tambah Pemilik.',11,DIM).pack(pady=24)
            else:
                # Grafik pendapatan 6 bulan pemilik ini (per mata uang yang dimiliki).
                y,mo=map(int,month.split('-'));labels=[]
                for _ in range(6):
                    labels.append('%04d-%02d'%(y,mo));mo-=1
                    if mo==0:y,mo=y-1,12
                labels=labels[::-1]
                currencies=sorted({str(a.get('currency') or 'IDR').upper() for a in linked}) or ['IDR']
                charts=tk.Frame(page_body,bg=PANEL);charts.pack(fill='x',padx=12,pady=(12,0))
                for i,c in enumerate(currencies[:2]):
                    charts.grid_columnconfigure(i,weight=1,uniform='oc')
                    ch=DC.LineChart(charts,f'Pendapatan {g["owner"]} per bulan ({c})',height=200)
                    ch.grid(row=0,column=i,sticky='nsew',padx=(0,6) if i==0 and len(currencies)>1 else (6,0) if i else 0)
                    ch.set(money(accounts_month(linked,month,'income').get(c,0),c)+' · '+month,[BULAN_PENDEK[int(m[5:])-1] for m in labels],
                           [(c,GREEN if c=='IDR' else DC.ACCENT,[accounts_month(linked,m,'income').get(c) for m in labels])])
                table=DC.GroupTable(page_body,[('artis','ARTIS',32,'w'),('akun','AKUN SOUNDON',26,'w'),('saldo','SALDO',20,'e'),('inc','PENDAPATAN '+month,22,'e')],
                                    actions_width=190,empty_text='Belum ada artis. Klik ＋ Artis.')
                table.pack(fill='x',padx=12,pady=12)
                unassigned=g['owner']=='Belum ditentukan'
                rows=[{'kind':'group','title':g['owner'],'sub':f'{len(linked)} akun SoundOn · pendapatan dihitung per akun',
                       'actions':[] if unassigned else [('＋ Artis',lambda o=g['owner']:add_owner_artist(o),False),
                                                        ('Ubah nama',lambda o=g['owner']:edit_owner_name(o),False),
                                                        ('Hapus',lambda o=g['owner']:delete_owner_name(o),False)]}]
                shown=set()
                for n,e in enumerate(sorted(g['entries'],key=lambda e:(e['account']['name'].casefold(),(e['artist'] or {}).get('name','')))):
                    a=e['account'];art=e['artist'];name=art['name'] if art else a['name']
                    if not match(g['owner'],name,a['name']):continue
                    first=a['id'] not in shown;shown.add(a['id'])
                    inc=accounts_month([a],month,'income');out_=accounts_month([a],month,'out')
                    rows.append({'kind':'item','name':name,'accent':ACCENTS[n%len(ACCENTS)],
                        'cells':{'artis':name,'akun':(a['name'],WHITE,False),
                                 'saldo':((account_money(a),GREEN,True) if a.get('balance_updated') else ('Belum sinkron',MUTED,False)) if first else ('〃',MUTED,False),
                                 'inc':((money_by_currency(inc),WHITE if inc else MUTED,bool(inc)) if first else ('〃',MUTED,False))},
                        'subs':{'artis':'' if art else 'nama akun (belum ada artis)','akun':f'{account_category(a)} · #{a["id"]}',
                                'saldo':short_time(a.get('balance_updated')) if first and a.get('balance_updated') else '',
                                'inc':('ditarik '+money_by_currency(out_)) if first and out_ else ''},
                        'actions':[('Sinkron',lambda a=a:start_sync(only_ids=[a['id']]),True),('Buka',lambda a=a:open_balance(a),False),
                                   ('⋯',lambda a=a,art=art:artist_options(a,art),False)]})
                table.set(rows)
        else:
            synced=[a for a in accounts if a.get('balance_updated')]
            stat_row(top,[('Akun SoundOn','globe',str(len(accounts)),f'{sum(1 for a in accounts if _chrome_status.get(str(a["id"]),False))} Chrome aktif'),
                          ('Total HP','phone',number(sum(int(a.get('phone_count',0) or 0) for a in accounts)),
                           f'{number(sum(int(a.get("song_count",0) or 0) for a in accounts))} lagu'),
                          ('Saldo akun','wallet',grouped_balance(synced) if synced else '—','dari sinkron terakhir'),
                          ('Pendapatan '+month,'flag',money_by_currency(accounts_month(accounts,month,'income')),'semua akun')])
            table=DC.GroupTable(page_body,[('akun','AKUN',34,'w'),('hp','HP',8,'e'),('artis','ARTIS',8,'e'),('lagu','LAGU',8,'e'),
                                           ('saldo','SALDO',21,'e'),('inc','PENDAPATAN',21,'e')],actions_width=250,
                                empty_text='Belum ada akun yang cocok.')
            table.pack(fill='x',padx=12,pady=12)
            rows=[]
            for cat in categories+sorted({account_category(a) for a in accounts}-set(categories)):
                members=[a for a in accounts if account_category(a)==cat and match(a['name'],a['id'],*[x['name'] for x in a.get('artists',[])])]
                if not members:continue
                linked=[a for a in members if a.get('balance_updated')]
                rows.append({'kind':'group','title':cat,'sub':f'{len(members)} akun · pendapatan {money_by_currency(accounts_month(members,month,"income"))}',
                             'right':grouped_balance(linked) if linked else ''})
                for n,a in enumerate(sorted(members,key=lambda a:a['name'].casefold())):
                    artists=', '.join(x['name'] for x in a.get('artists',[])) or 'belum ada artis'
                    inc=accounts_month([a],month,'income')
                    rows.append({'kind':'item','name':a['name'],'accent':ACCENTS[n%len(ACCENTS)],
                        'cells':{'akun':a['name'],'hp':number(a.get('phone_count',0)),'artis':number(a.get('artist_count',0)),
                                 'lagu':number(a.get('song_count',0)),
                                 'saldo':(account_money(a),GREEN,True) if a.get('balance_updated') else ('Belum sinkron',MUTED,False),
                                 'inc':(money_by_currency(inc),WHITE if inc else MUTED,bool(inc))},
                        'subs':{'akun':f'#{a["id"]} · {artists}','saldo':short_time(a.get('balance_updated')) if a.get('balance_updated') else '',
                                'inc':month},
                        'actions':[('Buka',lambda a=a:open_account(a),True),('Atur',lambda a=a:edit_account_counts(a),False),
                                   ('Artis',lambda a=a:edit_artists(a),False),('⋯',lambda a=a:show_actions(a),False)]})
            table.set(rows)
        # Pilihan berubah → bangun ulang halaman (ringkasan & halaman pemilik ikut berubah).
        _search_job=[None]
        def delayed(*_):
            _list_focus[0]=True
            if _search_job[0]:root.after_cancel(_search_job[0])
            _search_job[0]=root.after(400,render_active_page)
        v['q'].trace_add('write',delayed)
        v['view'].trace_add('write',rerender)
        v['month'].trace_add('write',rerender)
    elif active_page=='Analytics':
        # Periode sama dengan Dashboard (satu periode untuk semua menu).
        analytics_vars=get_analytics_vars()
        try:
            selected_start=parse_date(start_var.get());selected_end=parse_date(end_var.get())
        except ValueError:
            selected_start=selected_end=date.today()
        data=[(a,latest(a,selected_start,selected_end,platform),region_readings(a,selected_start,selected_end,platform)) for a in accounts]
        all_reads=[x for _,_,rs in data for x in rs]
        def mean(key):
            vals=[x[key] for x in all_reads if x[key] is not None]
            return (sum(vals)/len(vals)) if vals else None
        pct=lambda v:'—' if v is None else ('%.1f%%'%v).replace('.',',')
        # Bagian tetap (tidak ikut digulir): periode, filter, ringkasan.
        v=analytics_vars;clear_traces(v.values())
        intro=fixed_area()
        controls=tk.Frame(intro,bg=PANEL);controls.pack(fill='x',pady=(0,12))
        label(controls,'PERIODE',8,MUTED,bold=True).pack(side='left',padx=(0,10))
        PeriodButton(controls,start_var,end_var,refresh).pack(side='left',padx=(0,12))
        for var,values,width in [(v['show'],['Sudah dibaca','Ada peringatan','Belum dibaca','Semua akun'],15),
                                 (v['cat'],['Semua Kategori']+categories,17),
                                 (v['sort'],['Indonesia % tertinggi','Amerika Serikat % tertinggi','Nama A–Z'],24)]:
            ttk.Combobox(controls,textvariable=var,values=values,state='readonly',style='Dark.TCombobox',width=width).pack(side='left',padx=(0,8))
        UI.search_entry(controls,v['q'],'Cari akun atau artis…',width=22).pack(side='right')
        tiles=tk.Frame(intro,bg=PANEL);tiles.pack(fill='x')
        read_accounts=sum(1 for _,_,rs in data if rs)
        warned=[x for x in all_reads if DC.region_warnings(x['id_pct'],x['us_pct'])]
        for i,(title,icon,value,sub) in enumerate([
                ('Akun sudah dibaca','users',f'{read_accounts}/{len(accounts)}',f'{len(accounts)-read_accounts} akun belum dibaca'),
                ('Rata-rata Indonesia','flag',pct(mean('id_pct')),'dari semua artis terbaca'),
                ('Rata-rata AS','globe',pct(mean('us_pct')),'dari semua artis terbaca'),
                ('Artis terbaca','music',str(len(all_reads)),'pada periode ini'),
                ('Peringatan','alert',str(len(warned)),f'AS > {DC.WARN_US}% atau ID > {DC.WARN_ID}%')]):
            card=DC.StatCard(tiles,title,icon,height=110);card.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 6,0))
            tiles.grid_columnconfigure(i,weight=1,uniform='an')
            if title=='Peringatan' and warned:card.set(value,sub,'Periksa',RED)
            else:card.set(value,sub)
        # Daftar per artis (digulir). Hanya tabel yang diperbarui saat filter berubah.
        label(page_body,f'Periode {selected_start} s.d. {selected_end} · {platform}. Persentase milik artis yang dibaca, bukan total akun. '
              'Klik Baca untuk membaca Asal Streams akun itu.',9,MUTED).pack(anchor='w',padx=16,pady=(12,6))
        table=DC.RegionTable(page_body,open_streams,read_regions);table.pack(fill='x',padx=12,pady=(0,12))
        def rows():
            q=v['q'].get().strip().casefold();show=v['show'].get();cat=v['cat'].get();key=v['sort'].get()
            picked=[]
            for idx,(a,r,rs) in enumerate(data):
                if cat!='Semua Kategori' and account_category(a)!=cat:continue
                if show=='Sudah dibaca' and not rs:continue
                if show=='Belum dibaca' and rs:continue
                if show=='Ada peringatan':
                    rs=[x for x in rs if DC.region_warnings(x['id_pct'],x['us_pct'])]
                    if not rs:continue
                if q and q not in a['name'].casefold() and not any(q in x['artist'].casefold() for x in rs):continue
                picked.append((a,r,rs))
            if key=='Nama A–Z':picked.sort(key=lambda x:x[0]['name'].casefold())
            else:
                k='id_pct' if key.startswith('Indonesia') else 'us_pct'
                picked.sort(key=lambda x:max([y[k] for y in x[2] if y[k] is not None] or [-1]),reverse=True)
            out=[]
            for n,(a,r,rs) in enumerate(picked):
                base={'account':a,'name':a['name'],'sub':f'{account_category(a)} · #{a["id"]}','accent':ACCENTS[n%len(ACCENTS)],
                      'streams':number(r.get('streams',0)) if r else '—'}
                if not rs:out.append(dict(base,artist=None,first=True));continue
                k='us_pct' if key.startswith('Amerika') else 'id_pct'
                for j,x in enumerate(sorted(rs,key=lambda y:-(y[k] if y[k] is not None else -1))):
                    out.append(dict(base,first=j==0,**x))
            return out
        def update_table(*_):
            if table.winfo_exists():table.set(rows())
        for var in (v['show'],v['cat'],v['sort'],v['q']):
            var.trace_add('write',update_table)
        update_table()
        if not accounts:label(page_body,'Belum ada akun.',12,DIM).pack(pady=20)
    elif active_page=='Penghasilan':
        # Dua mata uang terpisah (kiri IDR, kanan USD): USD tidak pernah dijumlahkan ke IDR.
        def known(a):return bool(a.get('balance_updated'))
        def amount(a):
            try:return float(a.get('balance') or 0)
            except (ValueError,TypeError):return 0.0
        def cur(a):return str(a.get('currency') or 'IDR').upper()
        v=get_earnings_vars();clear_traces(v.values())
        month=v['month'].get()
        sums={a['id']:TX.month_summary(a.get('transactions'),month) for a in accounts}
        def inc(a,c=None):return (sums[a['id']].get(c or cur(a)) or {}).get('income',0)
        def out(a,c=None):return (sums[a['id']].get(c or cur(a)) or {}).get('out',0)
        total=lambda c,f:sum(f(a,c) for a in accounts)
        saldo=lambda c:sum(amount(a) for a in accounts if cur(a)==c and known(a))
        # ---- Bagian tetap: filter + ringkasan
        top=fixed_area()
        bar_f=tk.Frame(top,bg=PANEL);bar_f.pack(fill='x',pady=(0,12))
        label(bar_f,'BULAN',8,MUTED,bold=True).pack(side='left',padx=(0,8))
        MonthButton(bar_f,v['month']).pack(side='left',padx=(0,12))
        for var,values,width in [(v['show'],['Semua akun','Ada saldo','Ada pendapatan','Saldo 0','Belum dibaca'],14),
                                 (v['sort'],['Saldo terbesar','Pendapatan terbesar','Nama A–Z'],18)]:
            ttk.Combobox(bar_f,textvariable=var,values=values,state='readonly',style='Dark.TCombobox',width=width).pack(side='left',padx=(0,8))
        button(bar_f,'Ekspor CSV',lambda:export_recap_csv(v['month'].get()),icon='export').pack(side='right')
        UI.search_entry(bar_f,v['q'],'Cari akun…',width=20).pack(side='right',padx=(0,8))
        synced=[a.get('balance_updated') for a in accounts if known(a)]
        unread=sum(1 for a in accounts if not known(a))
        stat_row(top,[('Saldo Rupiah','flag',money(saldo('IDR'),'IDR'),('Sinkron '+short_time(max(synced))) if synced else 'Belum disinkronkan'),
                      ('Saldo Dolar AS','globe',money(saldo('USD'),'USD'),f'{unread} akun belum dibaca' if unread else 'Semua akun terbaca'),
                      ('Pendapatan Rupiah','wallet',money(total('IDR',inc),'IDR'),f'{month} · ditarik {money(total("IDR",out),"IDR")}'),
                      ('Pendapatan Dolar AS','wallet',money(total('USD',inc),'USD'),f'{month} · ditarik {money(total("USD",out),"USD")}'),
                      ('Akun berpendapatan','users',f'{sum(1 for a in accounts if inc(a))}/{len(accounts)}',
                       f'{sum(1 for a in accounts if a.get("transactions"))} akun punya riwayat transaksi')])
        # ---- Bagian digulir: grafik 6 bulan + tabel IDR (kiri) & USD (kanan)
        body=tk.Frame(page_body,bg=PANEL);body.pack(fill='x',padx=12,pady=12)
        # Kiri IDR, kanan USD; bila halaman terlalu sempit, ditumpuk atas-bawah.
        side=max(page_canvas.winfo_width(),main.winfo_width()-40)>=1050   # lebar kanvas bisa belum terukur saat pertama dibuka
        body.grid_columnconfigure(0,weight=1,uniform='cur')
        if side:body.grid_columnconfigure(1,weight=1,uniform='cur')
        def months_back(m,n=6):
            y,mo=map(int,m.split('-'));res=[]
            for _ in range(n):
                res.append('%04d-%02d'%(y,mo));mo-=1
                if mo==0:y,mo=y-1,12
            return res[::-1]
        labels=months_back(month);short=[BULAN_PENDEK[int(m[5:])-1] for m in labels]
        series=lambda c:[sum(TX.month_summary(a.get('transactions'),m).get(c,{}).get('income',0) for a in accounts) or None for m in labels]
        tables={}
        for col,(c,title,color) in enumerate([('IDR','Rupiah (IDR)',GREEN),('USD','Dolar AS (USD)',DC.ACCENT)]):
            chart=DC.LineChart(body,f'Pendapatan {title} per bulan',height=210)
            r0,c0=(0,col) if side else (col*2,0)
            pad=((0,6) if col==0 else (6,0)) if side else 0
            chart.grid(row=r0,column=c0,sticky='nsew',padx=pad,pady=(0,12))
            chart.set(money(total(c,inc),c)+' · '+month,short,[(title.split(' (')[0],color,series(c))])
            t=DC.GroupTable(body,[('akun','AKUN',40,'w'),('saldo','SALDO',30,'e'),('inc','PENDAPATAN',30,'e')],actions_width=136,
                            empty_text='Tidak ada akun yang cocok dengan filter.')
            t.grid(row=r0+1,column=c0,sticky='new',padx=pad,pady=(0,12))
            tables[c]=t
        def update_tables(*_):
            q=v['q'].get().strip().casefold();show=v['show'].get();key=v['sort'].get()
            for c,title in (('IDR','Rupiah (IDR)'),('USD','Dolar AS (USD)')):
                t=tables[c]
                if not t.winfo_exists():return
                group=[a for a in accounts if cur(a)==c]
                total_n=len(group)
                group=[a for a in group if (not q or q in a['name'].casefold() or q in str(a['id']))
                       and not (show=='Ada saldo' and not (known(a) and amount(a)>0))
                       and not (show=='Ada pendapatan' and not inc(a,c))
                       and not (show=='Saldo 0' and not (known(a) and amount(a)==0))
                       and not (show=='Belum dibaca' and known(a))]
                if key=='Nama A–Z':group.sort(key=lambda a:a['name'].casefold())
                elif key=='Pendapatan terbesar':group.sort(key=lambda a:inc(a,c),reverse=True)
                else:group.sort(key=lambda a:(known(a),amount(a)),reverse=True)
                hi_s=max([amount(a) for a in group if known(a)] or [0]) or 1
                hi_i=max([inc(a,c) for a in group] or [0]) or 1
                rows=[{'kind':'group','title':title,'sub':f'{len(group)} dari {total_n} akun',
                       'right':'Saldo '+money(saldo(c),c)}]
                for n,a in enumerate(group):
                    i_=inc(a,c);o_=out(a,c)
                    rows.append({'kind':'item',
                        'cells':{'akun':a['name'],'saldo':(account_money(a),GREEN if known(a) and amount(a)>0 else MUTED,True) if known(a) else ('Belum dibaca',MUTED,False),
                                 'inc':(money(i_,c),WHITE if i_ else MUTED,bool(i_))},
                        'subs':{'akun':f'{account_category(a)} · #{a["id"]}',
                                'saldo':short_time(a.get('balance_updated')) if known(a) else '',
                                'inc':('ditarik '+money(o_,c)) if o_ else ('—' if a.get('transactions') else 'belum ada riwayat')},
                        'actions':[('Buka',lambda a=a:open_balance(a),False),('Sinkron',lambda a=a:start_sync(only_ids=[a['id']]),True)]})
                t.set(rows)
        for key in ('show','sort','q'):v[key].trace_add('write',update_tables)
        v['month'].trace_add('write',lambda *_:root.after_idle(render_active_page))
        update_tables()
        if not accounts:label(page_body,'Belum ada akun.',12,DIM).pack(pady=20)
    elif active_page=='Inventaris HP':
        assigned=assigned_phone_count()
        others={k:phone_inventory[k] for k in ('tersedia','service','rusak','tidak_terpakai')}
        total=assigned+sum(others.values())
        with_hp=sum(1 for a in accounts if int(a.get('phone_count',0) or 0)>0)
        # ---- Ringkasan tetap
        top=fixed_area()
        stat_row(top,[('Dipakai akun','phone',number(assigned),f'di {with_hp} dari {len(accounts)} akun'),
                      ('Tersedia','check',number(others['tersedia']),'siap dipakai'),
                      ('Service','wrench',number(others['service']),'sedang diperbaiki'),
                      ('Rusak','alert',number(others['rusak']),'tidak bisa dipakai'),
                      ('Tidak terpakai','circle',number(others['tidak_terpakai']),'disimpan'),
                      ('Total HP','grid',number(total),'semua status')])
        # ---- Komposisi
        comp=page_section(page_body,'Komposisi HP','Perbandingan jumlah HP per status. "Dipakai akun" dihitung otomatis dari jumlah HP setiap akun.','chart',PURPLE)
        bar_c=DC.StackedBar(comp);bar_c.pack(fill='x')
        bar_c.set([('Dipakai akun',assigned,PURPLE),('Tersedia',others['tersedia'],GREEN),('Service',others['service'],BLUE),
                   ('Rusak',others['rusak'],RED),('Tidak terpakai',others['tidak_terpakai'],MUTED)])
        # ---- Ubah jumlah (HP di luar akun)
        edit_sec=page_section(page_body,'Ubah jumlah HP di luar akun',
            'Jangan masukkan HP yang sudah dipakai akun ke status lain. Klik − / + atau ketik angkanya, lalu Simpan.','edit',GREEN)
        form=tk.Frame(edit_sec,bg=PANEL);form.pack(fill='x');values={}
        for i,(title,key,color,hint) in enumerate([('Tersedia','tersedia',GREEN,'siap dipakai'),('Service','service',BLUE,'sedang diperbaiki'),
                                                   ('Rusak','rusak',RED,'tidak bisa dipakai'),('Tidak terpakai','tidak_terpakai',MUTED,'disimpan')]):
            shell=UI.RoundedPanel(form,outer=PANEL,color=CARD,radius=12);shell.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 6,0))
            form.grid_columnconfigure(i,weight=1,uniform='inv')
            item=tk.Frame(shell,bg=CARD);item.pack(fill='both',expand=True,padx=16,pady=14)
            head_row=tk.Frame(item,bg=CARD);head_row.pack(fill='x')
            dot=tk.Canvas(head_row,width=10,height=10,bg=CARD,highlightthickness=0);dot.pack(side='left',padx=(0,8))
            dot.create_oval(1,1,9,9,fill=color,outline='')
            label(head_row,title,10,WHITE,bold=True).pack(side='left')
            label(item,hint,8,MUTED).pack(anchor='w',pady=(2,10))
            row=tk.Frame(item,bg=CARD);row.pack(fill='x')
            var=tk.StringVar(value=str(phone_inventory[key]));values[key]=var
            def step(var=var,d=1):
                try:n=int(var.get().strip() or 0)
                except ValueError:n=0
                var.set(str(max(0,n+d)))
            RoundButton(row,'−',lambda var=var:step(var,-1),height=34,padx=12,font_size=12).pack(side='left')
            tk.Entry(row,textvariable=var,font=(FONT,16,'bold'),fg=WHITE,bg=PANEL,insertbackground=WHITE,relief='flat',justify='center',
                     highlightthickness=1,highlightbackground=LINE,highlightcolor=PURPLE,width=6).pack(side='left',fill='x',expand=True,padx=8,ipady=4)
            RoundButton(row,'+',lambda var=var:step(var,1),height=34,padx=12,font_size=12).pack(side='left')
        label(edit_sec,'CATATAN',8,MUTED,bold=True).pack(anchor='w',pady=(16,6))
        notes=tk.Text(edit_sec,height=3,wrap='word',font=(FONT,10),bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',padx=12,pady=10)
        notes.insert('1.0',phone_inventory.get('catatan',''));notes.pack(fill='x',pady=(0,12))
        def save_inventory_form():
            try:
                new_values={k:int(v.get().strip()) for k,v in values.items()}
                if any(n<0 or n>1000000 for n in new_values.values()):raise ValueError()
            except ValueError:
                messagebox.showerror('Jumlah HP tidak valid','Masukkan bilangan bulat 0 sampai 1.000.000.',parent=root);return
            previous=phone_inventory.copy();phone_inventory.update(new_values);phone_inventory['catatan']=notes.get('1.0','end-1c').strip()
            try:save_phone_inventory()
            except OSError as ex:
                phone_inventory.clear();phone_inventory.update(previous);messagebox.showerror('Gagal menyimpan',str(ex),parent=root);return
            render_active_page();messagebox.showinfo('Inventaris tersimpan','Data inventaris HP berhasil disimpan.',parent=root)
        foot=tk.Frame(edit_sec,bg=PANEL);foot.pack(fill='x')
        button(foot,'✓  Simpan Inventaris',save_inventory_form,True).pack(side='left')
        label(foot,'Disimpan di '+INVENTORY_FILE,8,MUTED).pack(side='left',padx=14)
        # ---- HP per akun
        per=page_section(page_body,'HP per akun','Jumlah HP yang dipakai setiap akun SoundOn. Klik Atur untuk mengubah jumlah HP, artis, dan lagu.','phone',BLUE)
        table=DC.GroupTable(per,[('akun','AKUN',46,'w'),('hp','HP',18,'e'),('artis','ARTIS',18,'e'),('lagu','LAGU',18,'e')],actions_width=90)
        table.pack(fill='x')
        rows=[]
        for cat in categories+sorted({account_category(a) for a in accounts}-set(categories)):
            members=sorted([a for a in accounts if account_category(a)==cat],key=lambda a:-int(a.get('phone_count',0) or 0))
            if not members:continue
            hp_sum=sum(int(a.get('phone_count',0) or 0) for a in members)
            rows.append({'kind':'group','title':cat,'sub':f'{len(members)} akun','right':f'{number(hp_sum)} HP'})
            for n,a in enumerate(members):
                hp=int(a.get('phone_count',0) or 0)
                rows.append({'kind':'item','name':a['name'],'accent':ACCENTS[n%len(ACCENTS)],
                    'cells':{'akun':a['name'],'hp':(number(hp),WHITE if hp else MUTED,bool(hp)),'artis':number(a.get('artist_count',0)),
                             'lagu':number(a.get('song_count',0))},
                    'subs':{'akun':f'#{a["id"]}'+(' · '+a['count_note'][:60] if a.get('count_note') else '')},
                    'actions':[('Atur',lambda a=a:edit_account_counts(a),True)]})
        table.set(rows)
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
        rt_var=tk.BooleanVar(value=cfg['retry_failed']);hid_var=tk.BooleanVar(value=cfg['hidden'])
        tx_var=tk.BooleanVar(value=cfg['transactions'])
        wk_var=tk.StringVar(value=str(cfg['workers']))
        def save_sync(*_):
            try:UI.save_settings(sync_enabled=en_var.get(),sync_open_closed=oc_var.get(),sync_hour=int(hr_var.get()[:2]),
                                 sync_balance=bal_var.get(),sync_regions=reg_var.get(),sync_retry_failed=rt_var.get(),sync_transactions=tx_var.get(),
                                 sync_hidden=hid_var.get(),sync_workers=_sync_workers(wk_var.get()))
            except (OSError,ValueError):pass
        row1=tk.Frame(syn,bg=PANEL);row1.pack(fill='x',pady=(0,6))
        UI.dark_checkbutton(row1,'  Aktifkan sinkron harian pukul',en_var,PANEL,command=save_sync).pack(side='left')
        hr=ttk.Combobox(row1,textvariable=hr_var,values=['%02d:00'%h for h in range(24)],state='readonly',width=7,style='Dark.TCombobox')
        hr.pack(side='left',padx=8);hr.bind('<<ComboboxSelected>>',save_sync)
        UI.dark_checkbutton(syn,'  Buka Chrome akun yang tertutup (diperkecil), lalu tutup lagi setelah dibaca',oc_var,PANEL,command=save_sync).pack(anchor='w')
        UI.dark_checkbutton(syn,'  Baca juga Saldo tersedia (My Earnings)',bal_var,PANEL,command=save_sync).pack(anchor='w')
        UI.dark_checkbutton(syn,'  Baca juga Asal Streams per artis (Indonesia / Amerika Serikat), maks. 12 artis per akun',reg_var,PANEL,command=save_sync).pack(anchor='w')
        UI.dark_checkbutton(syn,'  Baca juga Riwayat Transaksi (untuk Rekap pendapatan bulanan di Penghasilan)',tx_var,PANEL,command=save_sync).pack(anchor='w')
        UI.dark_checkbutton(syn,'  Sembunyikan Chrome sinkron (tanpa jendela; bila SoundOn menolak, akun itu dibaca dengan Chrome diperkecil)',
                            hid_var,PANEL,command=save_sync).pack(anchor='w')
        row_wk=tk.Frame(syn,bg=PANEL);row_wk.pack(fill='x',pady=(2,2))
        label(row_wk,'  Chrome yang berjalan bersamaan',10).pack(side='left')
        wk=ttk.Combobox(row_wk,textvariable=wk_var,values=['1','2','3'],state='readonly',width=4,style='Dark.TCombobox')
        wk.pack(side='left',padx=8);wk.bind('<<ComboboxSelected>>',save_sync)
        label(row_wk,'Lebih banyak = lebih cepat, tetapi komputer lebih berat.',9,MUTED).pack(side='left')
        UI.dark_checkbutton(syn,'  Ulangi otomatis sekali akun yang perlu login, dilewati, atau gagal di akhir sinkron',rt_var,PANEL,command=save_sync).pack(anchor='w')
        label(syn,'Akun yang belum login dilewati dan dicatat di laporan. Platform yang didukung: Semua Platform dan Spotify.',9,MUTED).pack(anchor='w',pady=(6,4))
        info=tk.Frame(syn,bg=PANEL);info.pack(fill='x',pady=(4,0))
        label(info,_sync_state['text'] or cfg['last_summary'] or 'Belum pernah dijalankan.',9,DIM).pack(side='left')
        button(info,'Lihat laporan',open_sync_log,icon='info',font_size=9,height=30).pack(side='right')
        # Menjalankan/menghentikan/mengulang sinkron ada di menu Sinkron (Dashboard).
        label(syn,'Jalankan, hentikan, atau ulangi sinkron dari menu Sinkron di Dashboard.',9,MUTED).pack(anchor='w',pady=(8,0))
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
        'Daftar Akun':'Kelola pemilik, artis, dan akun SoundOn.',
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
                'Daftar Akun':'Kelola pemilik, artis, dan akun SoundOn.',
                'Analytics':'Bandingkan Streams dan Pendengar berdasarkan negara.',
                'Penghasilan':'Pantau saldo tersedia seluruh akun.',
                'Inventaris HP':'Pantau HP dipakai akun, tersedia, service, rusak, dan tidak terpakai.',
                'Pengaturan':'Atur data, transfer akun, dan pembaruan SoundOn Account Manager.'}.get(target,''))
            render_active_page();page_rendered[target]=_page_key()
        root.after_idle(first_render)

root=tk.Tk();root.title('SoundOn — Account Manager Dashboard');root.geometry('1600x910');root.minsize(1280,690);root.configure(bg=BG)
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
_foot=tk.Frame(sidebar,bg=SIDE);_foot.pack(side='bottom',fill='x',padx=16,pady=(0,14))
label(_foot,'Versi '+APP_VERSION,8,MUTED).pack(side='left',padx=(8,0))
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
import dashboard_charts as DC
# ---- Kepala: sapaan, total Streams (besar) + chip, tombol aksi; kanan: periode, platform, refresh.
head=tk.Frame(dash,bg=BG);head.pack(fill='x',pady=(0,14))
left_head=tk.Frame(head,bg=BG);left_head.pack(side='left',anchor='n')
greeting_var=tk.StringVar(value=UI.greeting())
tk.Label(left_head,textvariable=greeting_var,font=(FONT,10),fg=DIM,bg=BG).pack(anchor='w')
hero_title=tk.StringVar(value='Total Streams')
tk.Label(left_head,textvariable=hero_title,font=(FONT,10),fg=MUTED,bg=BG).pack(anchor='w',pady=(10,0))
hero_row=tk.Frame(left_head,bg=BG);hero_row.pack(anchor='w')
hero_value=tk.StringVar(value='—')
tk.Label(hero_row,textvariable=hero_value,font=(FONT,30,'bold'),fg=WHITE,bg=BG).pack(side='left')
hero_chip=tk.Frame(hero_row,bg=BG);hero_chip.pack(side='left',padx=(12,0),pady=(10,0))
hero_sub=tk.StringVar(value='')
tk.Label(left_head,textvariable=hero_sub,font=(FONT,9),fg=MUTED,bg=BG).pack(anchor='w',pady=(0,10))
hero_actions=tk.Frame(left_head,bg=BG);hero_actions.pack(anchor='w')
menu_button(hero_actions,'Sinkron',[('Sinkron semua akun (periode terpilih)',lambda:start_sync()),('Sinkron per bulan…',ask_month_and_sync),
                            ('Ulangi akun yang belum berhasil',retry_failed_sync),('Hentikan sinkron',stop_sync),None,
                            ('Lihat laporan sinkron',open_sync_log),('Pengaturan sinkron…',lambda:switch_page('Pengaturan'))],
            icon='sync',variant='primary').pack(side='left',padx=(0,8))
button(hero_actions,'Unggah lagu',lambda:launch_upload_manager(),icon='music').pack(side='left',padx=(0,8))
button(hero_actions,'Laporan',open_sync_log,icon='info').pack(side='left')
right_head=tk.Frame(head,bg=BG);right_head.pack(side='right',anchor='n')
# Satu periode untuk Dashboard dan Analytics.
today=date.today();first=today.replace(day=1)
start_var=tk.StringVar(value=str(first));end_var=tk.StringVar(value=str(today));platform_var=tk.StringVar(value='Semua Platform')
button(right_head,'⟳  Refresh',lambda:(poll_chrome_status(),refresh())).pack(side='right',padx=(8,0))
# Hanya platform yang bisa dibaca sinkron (auto_sync.SUPPORTED_PLATFORMS).
ttk.Combobox(right_head,textvariable=platform_var,values=list(auto_sync.SUPPORTED_PLATFORMS),state='readonly',style='Dark.TCombobox',width=16).pack(side='right',padx=(8,0))
platform_var.trace_add('write',lambda *_:refresh())
period_button=PeriodButton(right_head,start_var,end_var,refresh);period_button.pack(side='right')
US_NAMES=('amerika serikat','united states','usa','us')
def in_country(a,country):
    cat=account_category(a).casefold()
    return cat in US_NAMES if country=='Amerika Serikat' else cat==country.casefold()
# ---- Kartu: Indonesia, Amerika Serikat, Pendengar, Saldo, + Tambah akun.
cards=tk.Frame(dash,bg=BG);cards.pack(fill='x',pady=(0,14))
stat_cards={
    'Indonesia':DC.StatCard(cards,'Indonesia','flag'),
    'Amerika Serikat':DC.StatCard(cards,'Amerika Serikat','globe'),
    'Pendengar':DC.StatCard(cards,'Pendengar','headphones'),
    'Saldo':DC.StatCard(cards,'Saldo tersedia','wallet'),
}
for i,card in enumerate(list(stat_cards.values())+[DC.AddCard(cards,'Tambah akun SoundOn baru ke dashboard',lambda:add_account())]):
    card.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 6,0))
    cards.grid_columnconfigure(i,weight=1 if i<4 else 0,uniform='cards' if i<4 else '')
# ---- Tab: Ringkasan (grafik) | Daftar Akun (tabel).
tabs_row=tk.Frame(dash,bg=BG);tabs_row.pack(fill='x',pady=(0,12))
last_update=tk.StringVar(value='')
sync_status=tk.StringVar(value=sync_settings()['last_summary'])
tk.Label(tabs_row,textvariable=sync_status,font=(FONT,9),fg=DIM,bg=BG).pack(side='right')
tk.Label(tabs_row,textvariable=last_update,font=(FONT,9),fg=MUTED,bg=BG).pack(side='right',padx=(0,14))
views=tk.Frame(dash,bg=BG);views.pack(fill='both',expand=True)
overview_view=tk.Frame(views,bg=BG)
table_view=tk.Frame(views,bg=BG)
def show_dashboard_tab(name):
    for v in (overview_view,table_view):v.pack_forget()
    # Tab Daftar Akun: kartu disembunyikan agar tabel lega (total tetap terlihat di atas).
    if name=='Daftar Akun':cards.pack_forget()
    elif not cards.winfo_manager():cards.pack(fill='x',pady=(0,14),before=tabs_row)
    (overview_view if name=='Ringkasan' else table_view).pack(fill='both',expand=True)
    try:UI.save_settings(dashboard_tab=name)
    except OSError:pass
_tab=UI.load_settings().get('dashboard_tab','Ringkasan')
_tab=_tab if _tab in ('Ringkasan','Daftar Akun') else 'Ringkasan'
dashboard_tabs=DC.Segmented(tabs_row,['Ringkasan','Daftar Akun'],_tab,show_dashboard_tab);dashboard_tabs.pack(side='left')
for c in range(3):overview_view.grid_columnconfigure(c,weight=1,uniform='ov')
overview_view.grid_rowconfigure(0,weight=3);overview_view.grid_rowconfigure(1,weight=2)
line_chart=DC.LineChart(overview_view,'Streams per bulan',height=200)
line_chart.grid(row=0,column=0,columnspan=2,sticky='nsew',padx=(0,6),pady=(0,12))
bar_chart=DC.BarChart(overview_view,'Akun teratas · periode ini',height=200)
bar_chart.grid(row=0,column=2,sticky='nsew',padx=(6,0),pady=(0,12))
activity=DC.Activity(overview_view,'Aktivitas sinkron terakhir',on_link=open_sync_log,height=170)
activity.grid(row=1,column=0,sticky='nsew',padx=(0,6))
balance_list=DC.BarList(overview_view,'Saldo tersedia',height=170)
balance_list.grid(row=1,column=1,sticky='nsew',padx=6)
status_grid=DC.StatusGrid(overview_view,'Status sinkron akun',height=170)
status_grid.grid(row=1,column=2,sticky='nsew',padx=(6,0))
show_dashboard_tab(_tab)

def monthly_series(members,key,platform,months=6):
    """Total per bulan (6 bulan terakhir, terlama dulu) dari catatan bulanan sinkron; None bila kosong."""
    y,m=date.today().year,date.today().month;seq=[]
    for _ in range(months):
        seq.append('%04d-%02d'%(y,m));m-=1
        if m==0:y,m=y-1,12
    out=[]
    for month in reversed(seq):
        total=None
        for a in members:
            best=None
            for r in a.get('records',[]):
                if (r.get('start')==month+'-01' and str(r.get('end',''))[:7]==month
                        and r.get('platform','Semua Platform')==platform and (best is None or r['end']>best['end'])):best=r
            if best:total=(total or 0)+best.get(key,0)
        out.append(total)
    return out

def region_readings(a,start,end,platform):
    """Pembacaan Asal Streams akun untuk periode & platform (satu per artis, terbaru):
    [{'artist','id_pct','us_pct','updated'}]."""
    unique={}
    for rec in sorted(a.get('region_records',[]),key=lambda x:x.get('updated','')):
        if rec.get('platform')!=platform or rec.get('start')!=str(start) or rec.get('end')!=str(end):continue
        unique[(rec.get('artist_id') or rec.get('artist_name'))]=rec
    out=[]
    for rec in unique.values():
        regions={str(v.get('code','')).upper():v.get('percent') for v in rec.get('regions',[])}
        pick=lambda codes:next((float(regions[c]) for c in codes if regions.get(c) is not None),None)
        out.append({'artist':rec.get('artist_name') or 'Artis','id_pct':pick(('ID','IDN')),'us_pct':pick(('US','USA')),
                    'updated':short_time(rec.get('updated'))})
    return out

_analytics_vars={}
def get_analytics_vars():
    """Filter halaman Analytics (tetap selama aplikasi terbuka)."""
    if not _analytics_vars:
        _analytics_vars.update(show=tk.StringVar(value='Sudah dibaca'),cat=tk.StringVar(value='Semua Kategori'),
                               sort=tk.StringVar(value='Indonesia % tertinggi'),q=tk.StringVar())
    return _analytics_vars

def _last_full_month():
    """Bulan lalu (YYYY-MM): pendapatan SoundOn masuk sekitar tanggal 24-25 untuk bulan sebelumnya."""
    t=date.today().replace(day=1)-timedelta(days=1)
    return t.strftime('%Y-%m')

def export_recap_csv(month):
    """Simpan rekap pendapatan satu bulan ke CSV (bisa dibuka di Excel)."""
    import csv
    path=filedialog.asksaveasfilename(title='Ekspor rekap pendapatan',defaultextension='.csv',
                                      initialfile=f'Rekap_Pendapatan_SoundOn_{month}.csv',filetypes=[('CSV','*.csv')],parent=root)
    if not path:return
    try:
        with open(path,'w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f,delimiter=';')
            w.writerow(['Bulan','ID akun','Akun','Kategori','Mata uang','Pendapatan','Ditarik','Jumlah transaksi'])
            for a in sorted(accounts,key=lambda a:a['name'].casefold()):
                for c,v in TX.month_summary(a.get('transactions'),month).items():
                    w.writerow([month,a['id'],a['name'],account_category(a),c,f'{v["income"]:.2f}'.replace('.',','),
                                f'{v["out"]:.2f}'.replace('.',','),v['count']])
    except OSError as ex:
        messagebox.showerror('Gagal menyimpan',str(ex),parent=root);return
    messagebox.showinfo('Rekap tersimpan','Rekap '+month+' disimpan ke:\n'+path,parent=root)

def money_by_currency(totals):
    """{'IDR': x, 'USD': y} -> 'Rp x · $y' (mata uang tidak dijumlahkan)."""
    parts=[money(v,c) for c,v in sorted(totals.items()) if v]
    return '  ·  '.join(parts) if parts else '—'

def accounts_month(members,month,key):
    """Total pendapatan ('income') atau penarikan ('out') beberapa akun pada satu bulan, per mata uang."""
    out={}
    for a in members:
        for c,v in TX.month_summary(a.get('transactions'),month).items():
            out[c]=out.get(c,0)+v[key]
    return out

_list_vars={}
_list_focus=[False]
def get_list_vars():
    """Pilihan halaman Daftar Akun (tetap selama aplikasi terbuka)."""
    if not _list_vars:
        _list_vars.update(view=tk.StringVar(value='Per Pemilik'),q=tk.StringVar(),owner=tk.StringVar(),
                          month=tk.StringVar(value=_last_full_month()))
    return _list_vars

_earnings_vars={}
def get_earnings_vars():
    """Filter halaman Penghasilan (tetap selama aplikasi terbuka)."""
    if not _earnings_vars:
        _earnings_vars.update(country=tk.StringVar(value='Semua negara'),show=tk.StringVar(value='Semua akun'),
                              sort=tk.StringVar(value='Saldo terbesar'),q=tk.StringVar(),
                              month=tk.StringVar(value=_last_full_month()))
    return _earnings_vars

def open_region_warnings():
    """Buka Analytics dengan filter "Ada peringatan"."""
    v=get_analytics_vars();v['q'].set('');v['show'].set('Ada peringatan')
    switch_page('Analytics')

BULAN_PENDEK=['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des']
def _last_months(n=6):
    y,m=date.today().year,date.today().month;out=[]
    for _ in range(n):
        out.append(BULAN_PENDEK[m-1]);m-=1
        if m==0:y,m=y-1,12
    return out[::-1]

def _change(series):
    """(teks chip, warna) bulan lalu dibanding bulan sebelumnya, atau ('', None)."""
    if len(series)>=3 and series[-2] and series[-3]:
        pct=(series[-2]-series[-3])/series[-3]*100
        return ('%+.0f%%'%pct,GREEN if pct>=0 else RED)
    return ('',None)

def update_overview(start,end,platform):
    """Kepala, kartu, dan tab Ringkasan. Semua akun dihitung (tidak terpengaruh filter tabel)."""
    recs={str(a['id']):latest(a,start,end,platform) for a in accounts}
    def total(members,key):return sum((recs[str(a['id'])] or {}).get(key,0) for a in members)
    ind=[a for a in accounts if in_country(a,'Indonesia')];usa=[a for a in accounts if in_country(a,'Amerika Serikat')]
    all_streams=total(accounts,'streams')
    hero_title.set(f'Total Streams  ·  {start} s.d. {end}')
    hero_value.set(number(all_streams))
    for w in hero_chip.winfo_children():w.destroy()
    series_all=monthly_series(accounts,'streams',platform)
    text,col=_change(series_all)
    if text:UI.pill(hero_chip,text+' '+_last_months()[-2],col,BG).pack(side='left')
    warned=sum(1 for a in accounts for x in region_readings(a,start,end,platform) if DC.region_warnings(x['id_pct'],x['us_pct']))
    if warned:
        chip=UI.pill(hero_chip,f'⚠ {warned} artis perlu dicek (AS > {DC.WARN_US}% / ID > {DC.WARN_ID}%)',RED,BG)
        chip.configure(cursor='hand2');chip.bind('<ButtonRelease-1>',lambda e:open_region_warnings())
        chip.pack(side='left',padx=(8,0))
    hero_sub.set(f'Indonesia: {number(total(ind,"streams"))}   ·   Amerika Serikat: {number(total(usa,"streams"))}   ·   {len(accounts)} akun')
    months=_last_months()
    for country,members in (('Indonesia',ind),('Amerika Serikat',usa)):
        series=monthly_series(members,'streams',platform);text,col=_change(series)
        stat_cards[country].set(number(total(members,'streams')),(f'{len(members)} akun' if not text else f'{months[-2]} vs {months[-3]}'),
                                text,col or GREEN,series)
    listeners=monthly_series(accounts,'listeners',platform)
    stat_cards['Pendengar'].set(number(total(accounts,'listeners')),f'Indonesia {number(total(ind,"listeners"))} · AS {number(total(usa,"listeners"))}',
                                '',GREEN,listeners)
    idr=[a for a in accounts if a.get('currency','IDR')=='IDR' and a.get('balance_updated')]
    usd=[a for a in accounts if a.get('currency')=='USD' and a.get('balance_updated')]
    idr_total=sum(float(a.get('balance',0)) for a in idr);usd_total=sum(float(a.get('balance',0)) for a in usd)
    synced=[a.get('balance_updated') for a in accounts if a.get('balance_updated')]
    stat_cards['Saldo'].set(money(idr_total,'IDR'),(money(usd_total,'USD')+'  ·  ' if usd else '')+('Sinkron '+short_time(max(synced)) if synced else 'Belum disinkronkan'))
    # Ringkasan
    line_chart.set(number(series_all[-1] or 0)+' bulan ini',months,
                   [('Indonesia',DC.ACCENT,monthly_series(ind,'streams',platform)),('Amerika Serikat',DC.SECOND,monthly_series(usa,'streams',platform))])
    top=sorted(((a,(recs[str(a['id'])] or {}).get('streams',0)) for a in accounts if recs[str(a['id'])]),key=lambda x:x[1],reverse=True)[:7]
    bar_chart.set(number(top[0][1]) if top else '—',[(a['name'].split()[0][:8],a['name'],v) for a,v in top])
    ranked=sorted(idr,key=lambda a:float(a.get('balance',0)),reverse=True)[:5]
    hi=max([float(a.get('balance',0)) for a in ranked] or [1]) or 1
    balance_list.set(money(idr_total,'IDR'),[(a['name'],money(float(a.get('balance',0)),'IDR'),float(a.get('balance',0))/hi,DC.ACCENT if i==0 else UI.mix(PANEL,UI.INK,0.35))
                                             for i,a in enumerate(ranked)],sub=(money(usd_total,'USD')+' dari akun USD') if usd else '')
    run=sync_results()
    rows=[]
    for when,status,aid,name,note in reversed(run[-5:]):
        short=note.split(' · ')[0] if status=='OK' else note
        rows.append((status,name,short[:40],short_time(when+':00')))
    activity.set(rows)
    by_id={aid:status for _,status,aid,_,_ in run}                      # status terbaru tiap akun
    ids={str(a['id']) for a in accounts}
    ok=sum(1 for aid,s in by_id.items() if s=='OK' and aid in ids)
    status_grid.set(f'{ok}/{len(accounts)} berhasil' if by_id else 'Belum ada sinkron',
                    [(a['name'],by_id.get(str(a['id']))) for a in sorted(accounts,key=lambda a:int(a['id']))])
bar=tk.Frame(table_view,bg=BG);bar.pack(fill='x',pady=(0,10))
label(bar,'Daftar Akun',14,bold=True).pack(side='left',padx=(0,6))
category_var=tk.StringVar(value='Semua Kategori')
category_filter=ttk.Combobox(bar,textvariable=category_var,values=['Semua Kategori']+categories,state='readonly',style='Dark.TCombobox',width=17)
category_filter.pack(side='left',padx=6)
category_var.trace_add('write',lambda *_:refresh())
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
status_var=tk.StringVar();tk.Label(table_view,textvariable=status_var,font=(FONT,9),fg=MUTED,bg=BG,anchor='w').pack(side='bottom',fill='x',pady=(4,0))
total_line=tk.Frame(table_view,bg=BG);total_line.pack(side='bottom',fill='x',pady=(10,0))
totals_var=tk.StringVar();tk.Label(total_line,textvariable=totals_var,font=(FONT,10,'bold'),fg=GREEN,bg=BG,anchor='w').pack(side='left')
wrap=panel(table_view);wrap.pack(fill='both',expand=True)
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
account_table=AccountTable(wrap,{'open':lambda r:open_streams(r['account']),'data':lambda r:edit(r['account']),'upload':lambda r:quick_upload(r['account']),
                                 'more':lambda r:show_actions(r['account']),'delete':lambda r:delete_accounts([r['account']])},_row_menu)
account_table.on_selection=_selection_changed
account_table.pack(fill='both',expand=True,padx=8,pady=8)
# Full-size independent content surface for sidebar pages; dashboard widgets stay intact.
page_overlay=tk.Frame(main,bg=BG)
page_header=tk.Frame(page_overlay,bg=BG);page_header.pack(fill='x',pady=(0,16))
page_title=label(page_header,'Daftar Akun',22,bold=True);page_title.pack(anchor='w')
page_subtitle=label(page_header,'',10,DIM);page_subtitle.pack(anchor='w',pady=(2,0))
# Bagian atas yang tidak ikut digulir: ringkasan & filter penting tiap halaman.
page_fixed=tk.Frame(page_overlay,bg=BG);page_fixed.pack(fill='x')
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
    return account_table.body
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
root.after(15000,_upload_watch_tick)  # folder pantau Studio unggah
root.mainloop()
if _restart_for_update:
    # 75 = keluar untuk pembaruan; run_app.bat menutup konsol lama tanpa pause.
    os._exit(75)
