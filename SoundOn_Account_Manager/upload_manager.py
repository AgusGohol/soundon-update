"""Antrean rilis lokal + asisten formulir SoundOn.

Bot mengisi formulir sampai Review. Submit rilis hanya ditekan bila pengguna mengaktifkan
"Submit otomatis" (sekali per lagu; lagu yang Submit-nya sudah ditekan tidak pernah dikirim ulang).
Folder pantau (upload_folder.py) memasukkan lagu ke antrean otomatis.
"""
import json
import os
import queue
import threading
import time
import uuid
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import urlparse
from soundon_upload_flow import Flow, NeedsAttention, validate_automatic, validate_recorded_fields, submit_release
import upload_folder
from datetime import datetime
import ui_theme as UI
from ui_theme import BG, PANEL, CARD, CARD_HI, LINE, WHITE, DIM, MUTED, PURPLE, GREEN, RED, BLUE, AMBER, FONT

FIELDS = {
    'title': ('Judul lagu', 'Track title', 'Song title'),
    'release_title': ('Judul rilis', 'Release title'),
    'artist': ('Nama artis', 'Artist name', 'Primary artist'),
    'language': ('Bahasa', 'Language'),
    'genre': ('Genre', 'Primary genre'),
    'release_date': ('Tanggal rilis', 'Release date'),
    'composer': ('Komposer', 'Composer'),
    'lyricist': ('Penulis lirik', 'Lyricist'),
    'isrc': ('ISRC',),
    'upc': ('UPC',),
    'copyright': ('Copyright',),
    'lyrics': ('Lirik', 'Lyrics'),
}

# Pengaman macet: proses unggah yang tidak membuat kemajuan selama STALL_SECONDS dilepas
# (lagu ditandai "Perlu tindakan", antrean lanjut). Semua tunggu yang wajar di alur berdetak
# lewat Flow.check(), dan satu panggilan Playwright paling lama ±60 detik, jadi 4 menit diam
# berarti Chrome/halaman tidak merespons. Setelah Hentikan, proses dilepas bila tidak berhenti
# sendiri dalam STOP_GRACE detik.
STALL_SECONDS = 240
STOP_GRACE = 20

def save_queue(path, jobs):
    temporary = str(path) + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(jobs, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)

def validate(job, account_ids):
    if str(job['account_id']) not in {str(x) for x in account_ids}:
        raise ValueError('Akun tidak ditemukan. Pilih akun yang masih terdaftar.')
    for key in ('title', 'artist'):
        if not job.get(key, '').strip():
            raise ValueError('Judul lagu dan nama artis wajib diisi.')
    for key in (('audio',) if job.get('cover_mode')=='AI SoundOn' else ('audio','cover')):
        if not Path(job.get(key, '')).is_file():
            raise ValueError('File ' + key + ' tidak ditemukan.')
    if Path(job['audio']).suffix.lower() not in {'.wav', '.flac', '.mp3', '.aiff', '.aif'}:
        raise ValueError('Pilih file audio, bukan folder atau arsip.')
    if job.get('cover_mode')!='AI SoundOn' and Path(job['cover']).suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
        raise ValueError('Cover harus berupa JPG atau PNG.')
    if job.get('release_date'):
        date.fromisoformat(job['release_date'])


def soundon_page(browser):
    pages = [p for c in browser.contexts for p in c.pages
             if (urlparse(p.url).hostname or '').lower() in
             {'www.soundon.global', 'soundon.global', 'us.soundon.global'}]
    if len(pages) != 1:
        raise ValueError('Sisakan satu tab SoundOn pada Chrome akun ini, lalu buka formulir unggahnya.')
    return pages[0]


def fill_visible_form(page, job, cancelled):
    """Exact accessible labels only; ambiguous or complex controls stay manual."""
    done, pending = [], []
    for key, labels in FIELDS.items():
        if cancelled.is_set():
            return done, pending + ['Dihentikan pengguna']
        value = job.get(key, '').strip()
        if not value:
            continue
        matches = []
        for label in labels:
            loc = page.get_by_label(label, exact=True)
            for i in range(loc.count()):
                item = loc.nth(i)
                if item.is_visible() and item.is_enabled():
                    # Deduplicate aliases that resolve to the same DOM control.
                    if not any(item.evaluate('(e, other) => e === other', old.element_handle()) for old in matches):
                        matches.append(item)
        if len(matches) != 1:
            pending.append(key + ': kolom tidak ditemukan/ambigu')
            continue
        control = matches[0]
        tag, kind = control.evaluate('(e) => [e.tagName.toLowerCase(), e.type || ""]')
        if tag not in ('input', 'textarea', 'select') or kind in ('checkbox', 'radio', 'file', 'hidden', 'submit', 'button'):
            pending.append(key + ': pilih secara manual')
            continue
        try:
            current = control.input_value()
            if current and current != value:
                pending.append(key + ': sudah berisi nilai berbeda; tidak ditimpa')
                continue
            if tag == 'select':
                control.select_option(label=value, timeout=3000)
            else:
                control.fill(value, timeout=3000)
            if tag != 'select' and control.input_value() != value:
                raise ValueError('nilai tidak tersimpan pada kolom')
            done.append(key)
        except Exception:
            pending.append(key + ': perlu diperiksa di browser')
    for key, token in (('audio', 'audio'), ('cover', 'image')):
        if cancelled.is_set():
            break
        # Do not infer by input order: multiple upload controls must stay manual.
        candidates = []
        inputs = page.locator('input[type=file]')
        for i in range(inputs.count()):
            control = inputs.nth(i)
            accept = (control.get_attribute('accept') or '').lower()
            extensions = ('.wav', '.flac', '.mp3', '.aiff') if key == 'audio' else ('.png', '.jpg', '.jpeg')
            if token in accept or any(ext in accept for ext in extensions):
                candidates.append(control)
        if len(candidates) != 1:
            pending.append(key + ': input file tidak ditemukan/ambigu')
            continue
        control = candidates[0]
        if control.evaluate('(e) => e.files.length'):
            pending.append(key + ': file sudah terpasang; tidak diunggah ulang')
            continue
        try:
            control.set_input_files(job[key], timeout=15000)
            done.append(key + ' (dipasang; cek hasil pemrosesan SoundOn)')
        except Exception:
            pending.append(key + ': gagal memasang file')
    return done, pending


class UploadManager:
    def __init__(self, root, accounts, base, open_account, port_for, ready):
        self.accounts = accounts
        self.open_account, self.port_for, self.ready = open_account, port_for, ready
        self.path = Path(base) / 'upload_queue.json'
        try:
            self.jobs = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []
        except (ValueError, OSError):
            messagebox.showerror('Antrean tidak terbaca', 'File upload_queue.json tidak dapat dibaca. Pulihkan cadangan sebelum melanjutkan.', parent=root)
            return
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.run = None              # proses unggah aktif: job, cancel, beat (detak terakhir), stop_at
        self.paused = False          # Hentikan menjeda antrean otomatis sampai Mulai unggah ditekan
        self.seen_files = {}
        cfg = UI.load_settings()
        self.watch = tk.BooleanVar(value=bool(cfg.get('upload_watch', False)))
        self.autosubmit = tk.BooleanVar(value=bool(cfg.get('upload_autosubmit', False)))
        self.date_offset = int(cfg.get('upload_date_offset', 7) or 7)
        try:
            import upload_quick
            monetize = 'On' if upload_quick.load_defaults().get('monetize', True) else 'Off'
        except Exception:
            monetize = 'On'
        for job in self.jobs:
            # Lagu dari tombol Unggah yang belum terkirim mengikuti pilihan monetisasi terbaru.
            if job.get('source') == 'cepat' and not job.get('submit_clicked') and job.get('status') != 'Terkirim':
                job['cml'] = job['capcut'] = monetize
            if job.get('status') == 'Memproses':
                job['status'] = 'Terputus — periksa browser sebelum melanjutkan'
        self.window = tk.Toplevel(root)
        self.window.title('SoundOn 3.18.3 — Studio unggah')
        self.window.geometry('1120x740');self.window.minsize(920,600)
        self.window.configure(bg=BG)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.configure_styles()
        # Header
        header=tk.Frame(self.window,bg=BG);header.pack(fill='x',padx=24,pady=(20,14))
        UI.icon_badge(header,'music',PURPLE,BG,44).pack(side='left',padx=(0,14))
        titles=tk.Frame(header,bg=BG);titles.pack(side='left')
        tk.Label(titles,text='Studio Unggah Lagu',bg=BG,fg=WHITE,font=(FONT,19,'bold')).pack(anchor='w')
        self.subtitle=tk.Label(titles,text='',bg=BG,fg=DIM,font=(FONT,10));self.subtitle.pack(anchor='w',pady=(1,0))
        # Ringkasan status
        self.stats_frame=tk.Frame(self.window,bg=BG);self.stats_frame.pack(fill='x',padx=20,pady=(0,12))
        self.stat_vars={}
        for col,(key,title,color,icon_name) in enumerate([('total','Total antrean',PURPLE,'music'),('wait','Menunggu',BLUE,'circle'),
                                                           ('review','Terkirim / Review',GREEN,'check'),('attention','Perlu tindakan',AMBER,'alert')]):
            shell=UI.RoundedPanel(self.stats_frame,outer=BG,color=PANEL,radius=12)
            shell.grid(row=0,column=col,sticky='nsew',padx=4);self.stats_frame.grid_columnconfigure(col,weight=1,uniform='studio_stats')
            inner=tk.Frame(shell,bg=PANEL);inner.pack(fill='both',expand=True,padx=14,pady=11)
            UI.icon_badge(inner,icon_name,color,PANEL,34).pack(side='left',padx=(0,11))
            texts=tk.Frame(inner,bg=PANEL);texts.pack(side='left')
            tk.Label(texts,text=title,bg=PANEL,fg=DIM,font=(FONT,9)).pack(anchor='w')
            var=tk.StringVar(value='0');self.stat_vars[key]=var
            tk.Label(texts,textvariable=var,bg=PANEL,fg=WHITE,font=(FONT,15,'bold')).pack(anchor='w')
        # Kartu utama: toolbar + tabel
        card=UI.RoundedPanel(self.window,outer=BG,color=PANEL,radius=14)
        # Aktivitas dipasang dari bawah lebih dulu agar selalu terlihat.
        log_card=UI.RoundedPanel(self.window,outer=BG,color=PANEL,radius=14);log_card.pack(side='bottom',fill='x',padx=24,pady=(0,20))
        log_head=tk.Frame(log_card,bg=PANEL);log_head.pack(fill='x',padx=16,pady=(12,6))
        UI.icon(log_head,'pulse',16,PURPLE,PANEL).pack(side='left',padx=(0,8))
        tk.Label(log_head,text='Aktivitas',bg=PANEL,fg=WHITE,font=(FONT,11,'bold')).pack(side='left')
        UI.RoundButton(log_head,'Bersihkan',self.clear_log,variant='ghost',font_size=9,height=26,padx=8).pack(side='right')
        logs=tk.Frame(log_card,bg=PANEL);logs.pack(fill='x',padx=16,pady=(0,14))
        self.log=tk.Text(logs,height=6,bg=CARD,fg=DIM,font=(FONT,9),wrap='word',state='disabled',relief='flat',padx=12,pady=10,
                         highlightthickness=1,highlightbackground=LINE,highlightcolor=LINE,insertbackground=WHITE)
        logbar=ttk.Scrollbar(logs,orient='vertical',command=self.log.yview,style='Dark.Vertical.TScrollbar');self.log.configure(yscrollcommand=logbar.set)
        logbar.pack(side='right',fill='y',padx=(6,0));self.log.pack(fill='both',expand=True)
        card.pack(fill='both',expand=True,padx=24,pady=(0,12))
        actions=tk.Frame(card,bg=PANEL);actions.pack(fill='x',padx=16,pady=(14,10))
        UI.RoundButton(actions,'Tambah lagu',self.editor,icon='plus',variant='primary').pack(side='left',padx=(0,6))
        UI.RoundButton(actions,'Edit',self.edit,icon='edit').pack(side='left',padx=(0,6))
        UI.RoundButton(actions,'Mulai unggah',self.open,icon='play',variant='subtle').pack(side='left',padx=(0,6))
        UI.RoundButton(actions,'Hentikan',self.stop,icon='stop',variant='danger').pack(side='left',padx=(0,6))
        UI.menu_button(actions,'Lainnya',[('Lanjutkan halaman aktif',self.start),('Tandai selesai peninjauan',self.reviewed),
                                          None,('Pengaturan unggah…',self.open_defaults),('Buka folder pantau',self.open_watch_folder),('Tanggal rilis otomatis (folder)…',self.ask_date_offset),
                                          None,('Hapus dari antrean',self.delete)],icon='more').pack(side='right')
        self.auto_next=tk.BooleanVar(value=True)
        UI.dark_checkbutton(actions,'  Lanjut ke lagu berikutnya',self.auto_next,PANEL).pack(side='right',padx=12)
        auto=tk.Frame(card,bg=UI.mix(PANEL,PURPLE,0.06));auto.pack(fill='x',padx=16,pady=(0,10))
        UI.icon(auto,'sync',16,PURPLE,auto.cget('bg')).pack(side='left',padx=(12,8),pady=8)
        UI.dark_checkbutton(auto,'  Folder pantau (unggah otomatis)',self.watch,auto.cget('bg'),command=self.settings_changed).pack(side='left')
        UI.dark_checkbutton(auto,'  Submit otomatis setelah Review',self.autosubmit,auto.cget('bg'),command=self.settings_changed).pack(side='left',padx=(16,0))
        UI.RoundButton(auto,'Buka folder',self.open_watch_folder,icon='folder',variant='ghost',font_size=9,height=28,padx=8).pack(side='right',padx=8,pady=4)
        self.watch_status=tk.StringVar()
        tk.Label(auto,textvariable=self.watch_status,bg=auto.cget('bg'),fg=MUTED,font=(FONT,9),anchor='w').pack(side='left',padx=14,fill='x',expand=True)
        self.summary=tk.StringVar()
        tk.Label(card,textvariable=self.summary,bg=PANEL,fg=MUTED,font=(FONT,9)).pack(anchor='w',padx=18,pady=(0,8))
        table=tk.Frame(card,bg=PANEL);table.pack(fill='both',expand=True,padx=16,pady=(0,14))
        self.tree=ttk.Treeview(table,columns=('account','title','artist','status'),show='headings',selectmode='browse',style='Dark.Treeview',height=8)
        for key,title,width in [('account','AKUN',170),('title','JUDUL LAGU',280),('artist','ARTIS',180),('status','STATUS',300)]:
            self.tree.heading(key,text=title,anchor='w');self.tree.column(key,width=width,minwidth=100,anchor='w')
        scrollbar=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview,style='Dark.Vertical.TScrollbar')
        self.tree.configure(yscrollcommand=scrollbar.set);scrollbar.pack(side='right',fill='y',padx=(6,0));self.tree.pack(fill='both',expand=True)
        self.tree.tag_configure('odd',background=UI.mix(PANEL,UI.INK,0.025))
        self.tree.tag_configure('attention',foreground=AMBER);self.tree.tag_configure('review',foreground=GREEN)
        self.tree.tag_configure('busy',foreground=BLUE)
        self.tree.bind('<Double-1>',lambda e:self.edit())
        self.empty_hint=tk.Label(table,text='Belum ada lagu di antrean. Klik Tambah lagu untuk memulai.',bg=PANEL,fg=MUTED,font=(FONT,10))
        self.redraw(); self.poll()
        self.window.after(2000,self.autorun_tick)

    def clear_log(self):
        self.log.configure(state='normal');self.log.delete('1.0','end');self.log.configure(state='disabled')

    def configure_styles(self):
        UI.setup_styles(self.window)

    def style_editor(self,widget):
        mapping={ttk.Frame:'Dark.TFrame',ttk.Label:'Dark.TLabel',ttk.Entry:'Dark.TEntry',ttk.Combobox:'Dark.TCombobox',ttk.Button:'Dark.TButton',ttk.Notebook:'Dark.TNotebook',ttk.Scrollbar:'Dark.Vertical.TScrollbar'}
        for kind,style in mapping.items():
            if isinstance(widget,kind):widget.configure(style=style);break
        if isinstance(widget,(ttk.Entry,ttk.Combobox)):widget.configure(font=(FONT,10))
        if isinstance(widget,tk.Canvas):widget.configure(bg=PANEL)
        if isinstance(widget,tk.Text):widget.configure(bg=CARD,fg=WHITE,insertbackground=WHITE,relief='flat',font=(FONT,10),padx=10,pady=8)
        for child in widget.winfo_children():self.style_editor(child)

    @staticmethod
    def status_label(status):
        icon={'Menunggu':'○','Memproses':'↻','Siap ditinjau':'✓','Selesai diperiksa manual':'✓','Perlu tindakan':'⚠','Terkirim':'✈'}.get(status,'•')
        return icon+'  '+status

    def next_pending(self,completed_id):
        position=next((i for i,j in enumerate(self.jobs) if j['id']==completed_id),-1)
        if position<0:return None
        return next((j for j in self.jobs[position+1:] if j.get('status')=='Menunggu'),None)

    def advance_queue(self,completed_id):
        if self.busy or self.cancel.is_set() or not self.auto_next.get():return
        job=self.next_pending(completed_id)
        if job is None:return
        self.tree.selection_set(job['id']);self.tree.see(job['id'])
        self.open()

    def redraw(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.summary.set(str(len(self.jobs))+' lagu dalam antrean  ·  '+('Submit otomatis setelah Review' if self.autosubmit.get() else 'Otomatis berhenti di Review')
                         +'  ·  Klik dua kali untuk mengubah')
        self.subtitle.config(text='Siapkan lagu, jalankan otomatis, lalu '+('rilis langsung dikirim (Submit otomatis aktif).' if self.autosubmit.get()
                                   else 'periksa hasil di Review. Submit tidak ditekan.'))
        waiting=sum(1 for j in self.jobs if j.get('source') in ('folder','cepat') and j.get('status')=='Menunggu')
        self.watch_status.set(('Dijeda — tekan Mulai unggah untuk melanjutkan' if self.paused else
                               ('Memantau folder SoundOnUnggah\\masuk'+(('  ·  %d lagu menunggu'%waiting) if waiting else '')))
                              if self.watch.get() else 'Folder pantau mati')
        statuses=[j.get('status','') for j in self.jobs]
        self.stat_vars['total'].set(str(len(statuses)))
        self.stat_vars['wait'].set(str(sum(st=='Menunggu' for st in statuses)))
        self.stat_vars['review'].set(str(sum(('ditinjau' in st.lower() or 'peninjauan' in st.lower() or 'diperiksa' in st.lower() or st=='Terkirim') for st in statuses)))
        self.stat_vars['attention'].set(str(sum((st=='Perlu tindakan' or st.startswith('Terputus')) for st in statuses)))
        if self.jobs:self.empty_hint.place_forget()
        else:self.empty_hint.place(relx=0.5,rely=0.55,anchor='center')
        for index,job in enumerate(self.jobs):
            account = next((a for a in self.accounts if str(a['id']) == str(job['account_id'])), {})
            self.tree.insert('', 'end', iid=job['id'], values=(account.get('name','Akun dihapus'),job['title'],job['artist'],self.status_label(job['status'])),tags=tuple(tag for tag,active in [('odd',index%2),('attention',job['status']=='Perlu tindakan' or job['status'].startswith('Terputus')),('review','peninjauan' in job['status'].lower() or 'ditinjau' in job['status'].lower() or 'diperiksa' in job['status'].lower() or job['status']=='Terkirim'),('busy',job['status']=='Memproses')] if active))
        if selected and self.tree.exists(selected[0]): self.tree.selection_set(selected[0])

    def selected(self):
        selection = self.tree.selection()
        return next((j for j in self.jobs if selection and j['id'] == selection[0]), None)

    def persist(self):
        save_queue(self.path, self.jobs); self.redraw()

    def edit(self):
        if self.busy:
            messagebox.showinfo('Sedang memproses','Tunggu proses unggah selesai atau tekan Hentikan.',parent=self.window);return
        if not self.selected():
            messagebox.showinfo('Pilih lagu','Klik salah satu lagu di tabel terlebih dahulu.',parent=self.window);return
        self.editor(self.selected())

    def new_song_template(self):
        previous=self.selected() or (self.jobs[-1] if self.jobs else None)
        if previous is None:return {}
        data=dict(previous)
        data['title']=''
        data['audio']=''
        data['cover']=''
        for key in ('id','draft_url','status','report','source','added','submit_clicked','submitted_at','lyrics'):
            data.pop(key,None)
        return data

    def editor(self, existing=None):
        if self.busy: return
        data=existing if existing is not None else self.new_song_template()
        if not self.accounts:
            messagebox.showinfo('Belum ada akun','Tambahkan akun melalui dashboard.',parent=self.window);return
        dialog=tk.Toplevel(self.window);dialog.title('Data lagu');dialog.geometry('860x780');dialog.minsize(760,620);dialog.configure(bg=PANEL)
        dhead=tk.Frame(dialog,bg=PANEL);dhead.pack(fill='x',padx=20,pady=(18,4))
        UI.icon_badge(dhead,'music',PURPLE,PANEL,36).pack(side='left',padx=(0,12))
        tk.Label(dhead,text='Ubah data lagu' if existing is not None else 'Tambah lagu baru',bg=PANEL,fg=WHITE,font=(FONT,14,'bold')).pack(side='left')
        notebook=ttk.Notebook(dialog);notebook.pack(fill='both',expand=True,padx=14,pady=(10,10))
        canvases=[]
        def scroll_tab(title):
            outer=ttk.Frame(notebook);notebook.add(outer,text=title)
            canvas=tk.Canvas(outer,highlightthickness=0);bar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            body=ttk.Frame(canvas,padding=15);item=canvas.create_window((0,0),window=body,anchor='nw')
            body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
            canvases.append(canvas);return body
        metadata=scroll_tab('Lagu & File');options=scroll_tab('Rilis & Hak');credits=scroll_tab('Kredit & Lirik')
        # Gulir roda mouse ditangani pengendali gulir global aplikasi.
        variables={}
        choices={str(a['id'])+' · '+a['name']:a['id'] for a in self.accounts}
        account=tk.StringVar(value=next((text for text,aid in choices.items() if data and str(aid)==str(data.get('account_id',''))),next(iter(choices))))
        ttk.Label(metadata,text='Akun tujuan').grid(row=0,column=0,sticky='w')
        ttk.Combobox(metadata,textvariable=account,values=list(choices),state='readonly',width=55).grid(row=0,column=1,sticky='ew',pady=4)
        specs=[('title','Title / judul lagu'),('artist','Primary artist'),('audio','File lagu'),('cover','Cover art'),('language','Title language'),('genre','Genre'),('songwriter','Songwriter (nama lengkap)'),('english_title','English title (opsional)'),('version','Version (opsional)'),('subgenre','Subgenre (opsional)'),('record_label','Record label (opsional)'),('upc','UPC lama (manual)'),('isrc','ISRC lama (manual)')]
        for row,(key,label) in enumerate(specs,1):
            ttk.Label(metadata,text=label).grid(row=row,column=0,sticky='w',pady=5)
            variables[key]=tk.StringVar(value=data.get(key,''))
            if key in ('upc','isrc'):
                metadata.grid_slaves(row=row,column=0)[0].grid_remove()
                continue
            ttk.Entry(metadata,textvariable=variables[key],width=55).grid(row=row,column=1,sticky='ew',pady=5)
            if key in ('audio','cover'):
                def pick(key=key):
                    path=filedialog.askopenfilename(parent=dialog)
                    if path:variables[key].set(path)
                ttk.Button(metadata,text='Pilih',command=pick).grid(row=row,column=2,padx=4)
        selections=[('instrumental','Instrumental',('Yes','No')),('previously_released','Previously released?',('No, I want to distribute a new release','Yes, I want to move my music from another distributor to SoundOn')),('time_mode','Time synchronization',('Local release','Global release')),('ownership','Bagian ditulis/dikomposisi oleh Anda',('100%','0%','Other')),('publisher','Sudah memiliki publisher?',('Yes','No')),('pro','Terdaftar PRO/CMO?',('Yes','No')),('cml','Commercial Music Licensing',('On','Off')),('capcut','CapCut monetization',('On','Off'))]
        for row,(key,label,values) in enumerate(selections):
            ttk.Label(options,text=label).grid(row=row,column=0,sticky='w',pady=7)
            variables[key]=tk.StringVar(value=data.get(key,''))
            ttk.Combobox(options,textvariable=variables[key],values=values,state='readonly',width=58).grid(row=row,column=1,sticky='ew',pady=7)
        for row,key,label in [(8,'release_date','Release date (YYYY-MM-DD)'),(9,'iswc','ISWC (opsional)')]:
            variables[key]=tk.StringVar(value=data.get(key,''))
            ttk.Label(options,text=label).grid(row=row,column=0,sticky='w',pady=7)
            ttk.Entry(options,textvariable=variables[key],width=58).grid(row=row,column=1,sticky='ew',pady=7)
        ttk.Label(options,text='Pilih hak/penerbit/PRO sesuai kondisi lagu. On pada CML/CapCut mengaktifkan opsi beserta ketentuannya di SoundOn. Baca ketentuan sebelum memilih.\nPlatform mengikuti pilihan draf SoundOn; TikTok pre-release dilewati dan YouTube Content ID dinonaktifkan. Add-on berbayar tidak ditambahkan.\nAlur otomatis awal: rilis baru, Local release, ownership 100%/0%, publisher/PRO No. Kondisi lain perlu pengisian manual.',wraplength=730,justify='left').grid(row=10,column=0,columnspan=2,pady=14,sticky='w')
        for row,key,label,opts in [(14,'cover_mode','Sumber cover',('File','AI SoundOn')),(16,'cover_style','Gaya cover AI',('3D Animation','Illustration Art','2D Animation','Masterpiece Art','Photographic Style','Cinematic Style','Silhouette Art','Pixel Art'))]:
            variables[key]=tk.StringVar(value=data.get(key,'File' if key=='cover_mode' else '3D Animation'))
            ttk.Label(metadata,text=label).grid(row=row,column=0,sticky='w',pady=4)
            ttk.Combobox(metadata,textvariable=variables[key],values=opts,state='readonly',width=52).grid(row=row,column=1,sticky='ew',pady=4)
        variables['cover_prompt']=tk.StringVar(value='')
        ttk.Label(metadata,text='Cover AI dibuat tanpa prompt.').grid(row=15,column=0,columnspan=2,sticky='w')
        ttk.Label(metadata,text='Mode AI SoundOn tidak memerlukan file cover. Prompt AI selalu dikosongkan. Hasil pertama dipasang otomatis dan dapat diperiksa di Review.',wraplength=720).grid(row=17,column=0,columnspan=3,pady=8,sticky='w')
        credit_specs=[('lyrics_language','Lyrics language'),('lyricist','Lyricist (nama lengkap)'),('contributor','Contributor / pelaku'),('contributor_role','Peran contributor, contoh Vocalist'),('producer','Production contributor'),('producer_role','Peran produksi, contoh Producer')]
        for row,(key,label) in enumerate(credit_specs):
            ttk.Label(credits,text=label).grid(row=row,column=0,sticky='w',pady=6)
            variables[key]=tk.StringVar(value=data.get(key,''))
            ttk.Entry(credits,textvariable=variables[key],width=52).grid(row=row,column=1,sticky='ew',pady=6)
        for row,key,label,choices_ in [(6,'explicit','Explicit',('Explicit','Non-Explicit','Clean')),(7,'clip_mode','Klip TikTok',('SoundOn selected segment','Manual'))]:
            variables[key]=tk.StringVar(value=('SoundOn selected segment' if key=='clip_mode' and data.get(key,'First 15 seconds')=='First 15 seconds' else data.get(key,'')))
            ttk.Label(credits,text=label).grid(row=row,column=0,sticky='w',pady=6)
            ttk.Combobox(credits,textvariable=variables[key],values=choices_,state='readonly',width=52).grid(row=row,column=1,sticky='ew',pady=6)
        ttk.Label(credits,text='Lirik (opsional)').grid(row=8,column=0,sticky='nw',pady=8)
        lyrics_box=tk.Text(credits,height=7,wrap='word');lyrics_box.grid(row=8,column=1,sticky='ew',pady=8)
        lyrics_box.insert('1.0',data.get('lyrics',''))
        ttk.Label(credits,text='Isi kredit sesuai pembuat lagu. Bot tidak menganggap penyanyi, produser, penulis lagu, dan penulis lirik orang yang sama. Nama harus tersedia pada pilihan akun SoundOn. SoundOn selected segment mengonfirmasi rentang pilihan SoundOn; Manual akan berhenti untuk pemilihan segmen. Cover menggunakan file pilihanmu.',wraplength=730,justify='left').grid(row=9,column=0,columnspan=2,pady=12,sticky='w')
        credits.columnconfigure(1,weight=1)
        def commit():
            job={key:v.get().strip() for key,v in variables.items()}
            job['lyrics']=lyrics_box.get('1.0','end-1c').strip()
            job.update(account_id=choices[account.get()],id=(existing or {}).get('id',uuid.uuid4().hex),status='Menunggu',report='')
            if existing and str(existing['account_id'])==str(job['account_id']):
                job['draft_url']=existing.get('draft_url','')
            try:
                validate(job,[a['id'] for a in self.accounts])
                if existing:self.jobs[self.jobs.index(existing)]=job
                else:self.jobs.append(job)
                self.persist();dialog.destroy()
            except (ValueError,OSError) as ex:messagebox.showerror('Periksa data',str(ex),parent=dialog)
        dfoot=tk.Frame(dialog,bg=PANEL);dfoot.pack(fill='x',padx=20,pady=(0,16))
        UI.RoundButton(dfoot,'Simpan lagu',commit,icon='check',variant='primary').pack(side='right')
        UI.RoundButton(dfoot,'Batal',dialog.destroy,variant='ghost').pack(side='right',padx=8)
        self.style_editor(dialog)
        metadata.columnconfigure(1,weight=1);options.columnconfigure(1,weight=1)

    def delete(self):
        job=self.selected()
        if not job:
            messagebox.showinfo('Pilih lagu','Klik lagu yang ingin dihapus dari antrean.',parent=self.window);return
        if not self.busy and job and messagebox.askyesno('Hapus antrean','Hapus data antrean ini? File lagu dan draf SoundOn tetap tersimpan.',parent=self.window):
            self.jobs.remove(job);self.persist()

    def account(self,job):
        return next((a for a in self.accounts if str(a['id'])==str(job['account_id'])),None)

    def open(self):
        if self.busy:
            messagebox.showinfo('Sedang memproses','Unggahan lain sedang berjalan. Tekan Hentikan bila ingin berhenti.',parent=self.window);return
        job=self.selected()
        if not job:
            # Tanpa pilihan: mulai dari lagu Menunggu pertama.
            job=next((j for j in self.jobs if j.get('status')=='Menunggu'),None)
            if not job:
                messagebox.showinfo('Tidak ada lagu','Tidak ada lagu berstatus Menunggu. Tambah lagu atau pilih lagu di tabel.',parent=self.window);return
            self.tree.selection_set(job['id']);self.tree.see(job['id'])
        self.paused=False;self.redraw()
        if job.get('submit_clicked'):
            messagebox.showwarning('Sudah di-Submit','Submit lagu ini sudah ditekan pada '+str(job['submit_clicked'])+'.\nCek Library SoundOn; lagu ini tidak dikirim ulang agar tidak dobel.',parent=self.window);return
        account=self.account(job)
        if not account:
            messagebox.showerror('Akun tidak ditemukan','Akun untuk lagu ini sudah dihapus. Edit lagu dan pilih akun lain.',parent=self.window);return
        try:
            validate(job,[a['id'] for a in self.accounts])
            validate_automatic(job);validate_recorded_fields(job)
        except (ValueError,OSError) as ex:
            messagebox.showerror('Periksa data',str(ex),parent=self.window);return
        target=job.get('draft_url') or 'https://www.soundon.global/library/publish/single'
        self.open_account(account,target_url=target)
        self.start(automatic=True,open_target=target)


    def reviewed(self):
        job=self.selected()
        if not job:
            messagebox.showinfo('Pilih lagu','Klik lagu yang sudah Anda periksa di tabel terlebih dahulu.',parent=self.window);return
        if not self.busy and job and messagebox.askyesno('Peninjauan manual','Sudah memeriksa semua data di browser? Ini hanya menandai antrean lokal; tidak mengirim rilis.',parent=self.window):
            job['status']='Selesai diperiksa manual';self.persist()

    def start(self, automatic=True, open_target=None, job=None, unattended=False):
        """unattended=True: dijalankan antrean otomatis (folder pantau) — tanpa dialog; kesalahan
        menjadi status "Perlu tindakan" dan antrean lanjut ke lagu berikutnya."""
        if self.busy:return
        job=job or self.selected()
        if not job:
            messagebox.showinfo('Pilih lagu','Klik lagu yang ingin dilanjutkan di tabel terlebih dahulu.',parent=self.window);return
        if job.get('submit_clicked'):
            if not unattended:
                messagebox.showwarning('Sudah di-Submit','Submit lagu ini sudah ditekan; cek Library SoundOn. Tidak dikirim ulang.',parent=self.window)
            return
        try:
            validate(job,[a['id'] for a in self.accounts])
            if automatic:
                validate_automatic(job);validate_recorded_fields(job)
        except (ValueError,OSError) as ex:
            if unattended:
                job.update(status='Perlu tindakan',report=str(ex));self.persist();return
            messagebox.showerror('Periksa data',str(ex),parent=self.window);return
        account=self.account(job)
        if unattended and account is None:
            job.update(status='Perlu tindakan',report='Akun lagu ini sudah dihapus.');self.persist();return
        if not unattended:
            if not open_target and not self.ready(account):
                messagebox.showinfo('Buka akun','Klik Buka akun, login, lalu buka formulir unggah lagu sebelum mengisi.',parent=self.window);return
            last_step='menekan Submit (Submit otomatis aktif)' if self.autosubmit.get() and automatic else 'Submit tidak ditekan'
            if not open_target and not messagebox.askyesno('Periksa halaman tujuan',f"Pastikan Chrome {account['name']} berada pada draf lagu {job['title']}.\nBot akan mengisi data dan {'menekan Next sampai Review' if automatic else 'berhenti di halaman aktif'}; {last_step}.",parent=self.window):return
        launched=False
        if unattended:
            open_target=job.get('draft_url') or 'https://www.soundon.global/library/publish/single'
            if not self.ready(account):
                if not self.open_account(account,target_url=open_target):
                    job.update(status='Perlu tindakan',report='Chrome akun tidak bisa dibuka.');self.persist();return
                launched=True
        auto_submit=bool(automatic and self.autosubmit.get())
        # Event baru per proses: proses lama yang dilepas pengaman macet tetap berstatus dihentikan
        # walaupun proses berikutnya dimulai.
        run={'job':job['id'],'cancel':threading.Event(),'beat':time.monotonic(),'stop_at':None}
        self.cancel=cancel=run['cancel'];self.run=run
        self.busy=True;job['status']='Memproses';self.persist()
        snapshot=dict(job)
        self.events.put(('log',snapshot['id'],'▶ %s · %s'%(account.get('name',''),snapshot['title'])))
        def beat():
            run['beat']=time.monotonic()
        def put(event):
            # Proses yang sudah dilepas tidak boleh mengubah antrean lagi, kecuali catatan
            # "Submit ditekan" (pengaman rilis ganda).
            if self.run is run or event[0]=='submitclick':self.events.put(event)
        def worker():
            own_page=None
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    if open_target:
                        put(('log',snapshot['id'],'Menunggu Chrome akun siap. Jika diminta, login pada browser.'))
                        for _ in range(120):
                            if cancel.is_set():raise NeedsAttention('Dihentikan pengguna.')
                            if self.ready(account):break
                            beat();cancel.wait(1)
                        else:raise NeedsAttention('Chrome akun belum siap; login lalu tekan Buka akun lagi.')
                    browser=pw.chromium.connect_over_cdp(f'http://127.0.0.1:{self.port_for(account)}',timeout=10000)
                    if unattended:
                        # Tab sendiri agar tab SoundOn lain milik pengguna tidak mengganggu.
                        page=None
                        if launched:
                            for _ in range(20):
                                found=[p for c in browser.contexts for p in c.pages if (urlparse(p.url).hostname or '').lower().endswith('soundon.global')]
                                if len(found)==1:page=found[0];break
                                beat();cancel.wait(0.5)
                        if page is None:
                            ctx=browser.contexts[0] if browser.contexts else browser.new_context()
                            page=ctx.new_page()
                        own_page=page
                    else:
                        page=soundon_page(browser)
                    # Tab di latar belakang diperlambat Chrome (animasi/timer berhenti), sehingga klik
                    # menunggu lama atau gagal. Tampilkan tab yang dipakai bot.
                    try:page.bring_to_front()
                    except Exception:pass
                    beat()
                    if open_target:
                        if page.url!=open_target:page.goto(open_target,wait_until='domcontentloaded',timeout=60000)
                        for _ in range(120):
                            if cancel.is_set():raise NeedsAttention('Dihentikan pengguna.')
                            low=page.url.lower()
                            if 'login' in low or 'signin' in low:
                                if unattended:raise NeedsAttention('Akun belum login di Chrome. Login sekali, lalu lagu ini bisa diulang.')
                            if Flow(page,snapshot,cancel,lambda text:None).stage()!='unknown':break
                            beat();cancel.wait(1)
                        else:raise NeedsAttention('Formulir unggah belum siap. Selesaikan login lalu tekan Buka akun lagi.')
                    if snapshot.get('draft_url') and snapshot['draft_url']!=page.url:
                        raise ValueError('Halaman berbeda dari draf yang dicatat untuk lagu ini. Buka draf sebelumnya sebelum melanjutkan.')
                    if automatic:
                        initial_stage=Flow(page,snapshot,cancel,lambda text:None).stage()
                        if initial_stage=='unknown':raise ValueError('Tahap formulir belum dikenali. Periksa bahasa dan halaman unggah; dukungan Indonesia/Inggris aktif. Kirim screenshot halaman penuh beserta catatan ini jika masih berhenti.')
                    put(('draft',snapshot['id'],page.url))
                    if automatic:
                        notes=[]
                        def log(text):
                            beat();notes.append(text);put(('log',snapshot['id'],text))
                        flow=Flow(page,snapshot,cancel,log,beat)
                        try:
                            status=flow.run()
                            if status=='Siap ditinjau' and auto_submit:
                                put(('draft',snapshot['id'],page.url))
                                status=submit_release(flow,lambda:put(('submitclick',snapshot['id'],datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
                                report='\n'.join(notes)+'\nRilis dikirim ke SoundOn (Submit otomatis).'
                            else:
                                report='\n'.join(notes)+'\nPeriksa seluruh informasi di Review. Tidak ada Submit yang ditekan.'
                        except NeedsAttention as ex:
                            status='Perlu tindakan'
                            report='\n'.join(notes)+'\n'+str(ex)
                        if status!='Terkirim':
                            put(('draft',snapshot['id'],page.url))
                        elif own_page is not None:
                            try:own_page.close()
                            except Exception:pass
                        put((snapshot['id'],status,report))
                    else:
                        done,pending=fill_visible_form(page,snapshot,cancel)
                        report='Terisi: '+(', '.join(done) or 'belum ada')+'\nPerlu manual: '+('; '.join(pending) or 'cek hasil di browser')
                        put((snapshot['id'],'Periksa halaman aktif',report))
            except Exception as ex:
                if 'page' in locals() and page is not None and ('initial_stage' not in locals() or initial_stage!='unknown'):
                    try:put(('draft',snapshot['id'],page.url))
                    except Exception:pass
                report='Playwright belum terpasang. Jalankan install_dependencies.bat.' if isinstance(ex,ImportError) else str(ex)
                put((snapshot['id'],'Perlu tindakan',report))
        threading.Thread(target=worker,daemon=True).start()

    # ------------------------------------------------------------ folder pantau
    def settings_changed(self):
        was=bool(UI.load_settings().get('upload_autosubmit',False))
        if self.autosubmit.get() and not was:
            if not messagebox.askyesno('Aktifkan Submit otomatis?',
                    'Setelah Review, bot akan menekan Submit dan rilis langsung dikirim ke SoundOn tanpa Anda periksa.\n\n'
                    'Pastikan data di data.txt / antrean sudah benar (judul, artis, kredit, tanggal). Rilis yang sudah dikirim '
                    'harus dibatalkan sendiri di SoundOn.\n\nAktifkan?',parent=self.window):
                self.autosubmit.set(False)
        try:UI.save_settings(upload_watch=self.watch.get(),upload_autosubmit=self.autosubmit.get())
        except OSError:pass
        if self.autosubmit.get():
            self.log_line('Submit otomatis AKTIF: setelah Review, rilis langsung dikirim ke SoundOn tanpa pemeriksaan manual.')
        if self.watch.get():
            upload_folder.ensure_folders();self.paused=False
            self.log_line('Folder pantau aktif: '+str(upload_folder.INBOX))
        self.redraw()

    def log_line(self,text):
        self.log.configure(state='normal');self.log.insert('end',text+'\n');self.log.see('end');self.log.configure(state='disabled')

    def open_watch_folder(self):
        upload_folder.ensure_folders()
        try:
            if os.name=='nt':os.startfile(str(upload_folder.ROOT))
            else:import subprocess;subprocess.Popen(['xdg-open',str(upload_folder.ROOT)])
        except OSError as ex:messagebox.showerror('Gagal membuka folder',str(ex),parent=self.window)

    def ask_date_offset(self):
        from tkinter import simpledialog
        value=simpledialog.askinteger('Tanggal rilis otomatis','Lagu dari folder pantau dirilis berapa hari setelah hari ini?\n(Bila data.txt tidak menulis tanggal_rilis.)',
                                      initialvalue=self.date_offset,minvalue=1,maxvalue=365,parent=self.window)
        if value:
            self.date_offset=value
            try:UI.save_settings(upload_date_offset=value)
            except OSError:pass

    def template_for(self,account_id):
        same=[j for j in self.jobs if str(j.get('account_id'))==str(account_id)]
        base=dict(same[-1]) if same else (dict(self.jobs[-1]) if self.jobs else {})
        if not same:
            for key in ('artist','title'):base.pop(key,None)      # artis akun lain tidak dipakai
        for key in ('id','draft_url','status','report','source','added','submit_clicked','submitted_at','lyrics','audio','cover','title'):
            base.pop(key,None)
        return base

    def auto_candidate(self,j):
        return (j.get('status')=='Menunggu' and not j.get('submit_clicked') and
                (j.get('source')=='cepat' or (j.get('source')=='folder' and self.watch.get())))

    def has_pending_auto(self):
        return bool(not self.paused and any(self.auto_candidate(j) for j in self.jobs))

    def open_defaults(self):
        import upload_quick
        upload_quick.edit_defaults(self.window,on_saved=lambda:(self.autosubmit.set(bool(UI.load_settings().get('upload_autosubmit'))),self.redraw()))

    def add_quick_jobs(self,jobs,account_name=''):
        """Dari tombol Unggah di baris akun: masuk antrean dan langsung diproses berurutan."""
        ids=[a['id'] for a in self.accounts]
        added=0
        for job in jobs:
            try:
                validate(job,ids);validate_automatic(job);validate_recorded_fields(job)
            except (ValueError,OSError) as ex:
                self.log_line('Tidak ditambahkan: %s — %s'%(job.get('title',''),ex));continue
            self.jobs.append(job);added+=1
        if added:
            self.paused=False;self.persist()
            self.log_line('%d lagu ditambahkan untuk %s; diunggah otomatis satu per satu.'%(added,account_name or 'akun'))
            self.window.after(500,self.autorun_tick_once)
        self.window.deiconify();self.window.lift()
        return added

    def autorun_tick_once(self):
        if not self.busy and not self.paused:
            job=next((j for j in self.jobs if self.auto_candidate(j)),None)
            if job is not None:
                if self.tree.exists(job['id']):self.tree.selection_set(job['id']);self.tree.see(job['id'])
                self.start(automatic=True,job=job,unattended=True)

    def import_folder(self):
        ids=[a['id'] for a in self.accounts]
        try:
            jobs,logs=upload_folder.scan(self.accounts,self.template_for,
                                         [lambda j:validate(j,ids),validate_automatic,validate_recorded_fields],
                                         self.seen_files,self.date_offset)
        except OSError as ex:
            jobs,logs=[],['Folder pantau: '+str(ex)]
        for text in logs:self.log_line(text)
        if jobs:
            self.jobs.extend(jobs);self.persist()

    def autorun_tick(self):
        if not self.window.winfo_exists():return
        try:
            if self.watch.get():
                self.import_folder()
            self.autorun_tick_once()
            if self.watch.get() and not self.busy:self.redraw()
        finally:
            if self.window.winfo_exists():self.window.after(5000,self.autorun_tick)

    def stop(self):
        self.cancel.set();self.paused=True
        if self.run is not None and self.run['stop_at'] is None:self.run['stop_at']=time.monotonic()
        if hasattr(self,'watch_status'):self.redraw()

    def poll(self):
        try:
            while True:
                jid,status,report=self.events.get_nowait()
                if jid=='draft':
                    job=next((j for j in self.jobs if j['id']==status),None)
                    if job:job['draft_url']=report;self.persist()
                    continue
                if jid=='submitclick':
                    job=next((j for j in self.jobs if j['id']==status),None)
                    if job:job['submit_clicked']=report;self.persist()
                    continue
                if jid=='log':
                    self.log.configure(state='normal');self.log.insert('end',report+'\n');self.log.see('end');self.log.configure(state='disabled')
                    continue
                job=next((j for j in self.jobs if j['id']==jid),None)
                if job:
                    job.update(status=status,report=report)
                    if status=='Terkirim':job['submitted_at']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    elif job.get('submit_clicked'):
                        job['report']=report+'\nSubmit sudah ditekan '+job['submit_clicked']+'; cek Library SoundOn. Tidak dikirim ulang.'
                self.busy=False;self.run=None;self.persist()
                if status in ('Siap ditinjau','Terkirim') and self.auto_next.get() and not self.cancel.is_set() and job and job.get('source')!='folder':
                    self.window.after(1000,lambda completed_id=jid:self.advance_queue(completed_id))
                self.log.configure(state='normal');self.log.insert('end',report+'\n\n');self.log.see('end');self.log.configure(state='disabled')
        except queue.Empty:pass
        self.watchdog()
        if self.window.winfo_exists():self.window.after(150,self.poll)

    def watchdog(self):
        """Lepaskan proses unggah yang macet agar antrean tidak tertahan selamanya."""
        run=self.run
        if not self.busy or run is None or not self.events.empty():return
        now=time.monotonic()
        if run['stop_at'] is not None and now-run['stop_at']>STOP_GRACE:
            reason='Dihentikan pengguna. Chrome tidak merespons, jadi proses dilepas. Draf tetap terbuka di browser.'
        elif now-run['beat']>STALL_SECONDS:
            reason=('Macet: tidak ada kemajuan selama %d menit (halaman SoundOn/Chrome tidak merespons). '
                    'Proses dilepas otomatis dan antrean lanjut. Periksa draf di browser, lalu ulangi lagu ini.'%(STALL_SECONDS//60))
        else:return
        run['cancel'].set();self.run=None
        self.events.put((run['job'],'Perlu tindakan',reason))

    def close(self):
        if self.busy:
            self.stop();messagebox.showinfo('Menghentikan','Tunggu proses aktif selesai sebelum menutup jendela.',parent=self.window);return
        self.window.destroy()


def show_upload_manager(root,accounts,base,open_account,port_for,ready):
    return UploadManager(root,accounts,base,open_account,port_for,ready)
