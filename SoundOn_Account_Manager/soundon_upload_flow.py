"""Screenshot-grounded bilingual SoundOn flow.

run() berhenti di Review. submit() (hanya bila pengguna mengaktifkan "Submit otomatis")
menekan Submit rilis satu kali, dengan pemeriksaan ketat sebelum dan sesudahnya."""
import re
import time
from pathlib import Path
from urllib.parse import urlparse

class NeedsAttention(Exception):
    pass

FORM_CONTROL = 'input:not([type=hidden]):not([type=file]), textarea, select, [role=combobox]'

# English source keys remain stable in queue files. Labels accept both site languages.
ALIASES = {
    'Track information': ('Informasi lagu', 'Informasi trek', 'Informasi track'),
    'Release Settings': ('Pengaturan rilis', 'Pengaturan Rilis'),
    'More release options': ('Opsi rilis lainnya', 'Opsi rilis lainnya', 'Opsi rilis tambahan'),
    'Review': ('Peninjauan', 'Tinjauan', 'Tinjau'),
    'Next': ('Selanjutnya', 'Berikutnya'),
    'Submit': ('Kirim', 'Kirimkan', 'Ajukan'),
    'Audio file': ('File audio', 'Berkas audio'),
    'Title': ('Judul', 'Judul lagu'),
    'Title language': ('Bahasa judul',),
    'English title': ('Judul dalam bahasa Inggris', 'Judul bahasa Inggris'),
    'Version': ('Versi',),
    'Genre': ('Genre',),
    'Subgenre': ('Subgenre', 'Subgenre musik'),
    'Instrumental': ('Instrumental',),
    'Primary artists': ('Artis utama',),
    'Songwriters': ('Penulis lagu', 'Penulis Lagu'),
    'Record label': ('Label rekaman',),
    'Cover art': ('Sampul', 'Sampul album', 'Gambar sampul'),
    'Previously released?': ('Pernah dirilis sebelumnya?', 'Sudah pernah dirilis?', 'Sebelumnya dirilis?'),
    'Time synchronization': ('Sinkronisasi waktu',),
    'Release date': ('Tanggal rilis',),
    'TikTok pre-release': ('Pra-rilis TikTok', 'Prarilis TikTok'),
    'What percentage of this track was written or composed by you?': ('Berapa persentase lagu ini yang Anda tulis atau komposisikan?', 'Berapa persentase lagu ini yang ditulis atau dikomposisikan oleh Anda?'),
    'Does this track have an existing publishing administrator or publisher?': ('Apakah lagu ini sudah memiliki administrator penerbitan atau penerbit?', 'Apakah lagu ini memiliki administrator penerbitan atau penerbit yang sudah ada?'),
    'Have you registered this track with a PRO/CMO?': ('Apakah Anda sudah mendaftarkan lagu ini ke PRO/CMO?', 'Apakah Anda telah mendaftarkan lagu ini ke PRO/CMO?'),
    'Commercial Music Licensing': ('Lisensi Musik Komersial', 'Lisensi musik komersial'),
    'YouTube Content ID': ('Content ID YouTube',),
    'Add': ('Tambah', 'Tambahkan'),
    'Save': ('Simpan',),
    'Confirm': ('Konfirmasi',),
    'Artist name': ('Nama artis',),
    'Lyrics language': ('Bahasa lirik',),
    'Explicit': ('Eksplisit',),
    'Lyrics': ('Lirik',),
    'Contributors': ('Kontributor',),
    'Production and additional contributors': ('Produksi dan kontributor tambahan',),
    'Lyricists': ('Penulis lirik',),
    'Role': ('Peran',),
    'Songwriter name': ('Nama penulis lagu',),
    'Full name': ('Nama lengkap',),
    'Name': ('Nama',),
}
VALUES = {
    'Yes': ('Ya',), 'No': ('Tidak',),
    'Local release': ('Rilis lokal',), 'Global release': ('Rilis global',),
    'Skip for now': ('Lewati untuk saat ini', 'Lewati untuk sekarang', 'Lewati dulu'),
    'No, I want to distribute a new release': ('Tidak, saya ingin mendistribusikan rilis baru', 'Tidak, saya ingin mendistribusikan rilisan baru'),
    'English': ('Inggris', 'Bahasa Inggris'),
    'Non-Explicit': ('Noneksplisit', 'Non-eksplisit', 'Non eksplisit', 'Tidak eksplisit', 'Non-Eksplisit', 'Nonexplicit'),
    'Explicit': ('Eksplisit',),
    'Clean': ('Bersih',),
    'Vocalist': ('Vokalis', 'Penyanyi'),
    'Producer': ('Produser',),
    'Composer': ('Komposer',),
    'Lyricist': ('Penulis lirik',),
    'Songwriter': ('Penulis lagu',),
    'Indonesian': ('Indonesia','Bahasa Indonesia','Bahasa Indonesia (Bahasa)'),
}

def aliases(caption):
    return tuple(dict.fromkeys((caption,)+ALIASES.get(caption,())))

def values(value):
    return tuple(dict.fromkeys((value,)+VALUES.get(value,())))

# Only identifies visible DOM controls near the screenshot's exact field caption.
# It does not set field values with JavaScript or dispatch synthetic form submits.
RESOLVE = r'''({caption, selector, key, root}) => {
 const scope=root || document;
 const norm = s => s.replace(/\((?:Optional|Opsional)\)/gi,'').replace(/\s+/g,' ').trim().toLocaleLowerCase();
 const visible = e => !!(e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
 const matches=e=>norm(e.innerText||'')===norm(caption)||norm(Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join(' '))===norm(caption);
 const labels = Array.from(scope.querySelectorAll('label,div,span,p,h1,h2,h3,h4,strong,b'))
   .filter(e => visible(e) && matches(e))
   .filter(e => !Array.from(e.children).some(c => visible(c) && matches(c)));
 const choices = new Set();
 for (const label of labels) {
   if(label.tagName==='LABEL' && label.htmlFor) {
     const e=document.getElementById(label.htmlFor);if(e && e.matches(selector)) choices.add(e);
   }
   let parent=label;
   for(let depth=0;parent && depth<6;depth++,parent=parent.parentElement) {
     const controls=Array.from(parent.querySelectorAll(selector)).filter(e=>visible(e) || e.type==='file');
     if(controls.length) { if(controls.length===1) choices.add(controls[0]);break; }
   }
 }
 if(choices.size!==1)return choices.size;
 const control=Array.from(choices)[0];control.setAttribute('data-soundon-bot',key);return 1;
}'''


def unique_visible(locator, caption):
    found = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    if len(found) != 1:
        raise NeedsAttention(caption + ': kontrol tidak ditemukan atau lebih dari satu. Periksa browser.')
    return found[0]


class Flow:
    def __init__(self, page, job, cancelled, log):
        self.page, self.job, self.cancelled, self.log = page, job, cancelled, log
        self.files_done=set()
        self.scope=None

    def check(self):
        if self.cancelled.is_set():raise NeedsAttention('Dihentikan pengguna. Draf tetap terbuka.')
        host=(urlparse(self.page.url).hostname or '').lower()
        if host not in {'soundon.global','www.soundon.global','us.soundon.global'}:
            raise NeedsAttention('Halaman keluar dari SoundOn; proses dihentikan.')
        # Review is checked by the caller BEFORE performing any form action.

    def heading(self, caption):
        for text in aliases(caption):
            locator=self.page.get_by_role('heading',name=re.compile('^'+re.escape(text)+'$',re.I))
            if any(locator.nth(i).is_visible() for i in range(locator.count())):return True
        return False

    def named(self,scope,role,caption,caption_values=False):
        candidates=[]
        for text in (values(caption) if caption_values else aliases(caption)):
            locator=scope.get_by_role(role,name=re.compile('^'+re.escape(text)+'$',re.I))
            for i in range(locator.count()):
                item=locator.nth(i)
                if item.is_visible():candidates.append(item)
        if len(candidates)!=1:raise NeedsAttention(caption+': kontrol tidak ditemukan atau ambigu.')
        return candidates[0]

    def has_control(self,caption):
        try:self.resolve(caption);return True
        except NeedsAttention:return False

    def stage(self):
        self.check()
        if self.heading('Review'):return 'review'
        # Final-action names are stop signals only. Never click these controls.
        # Only a final Submit outside an active dialog signals Review. Credit
        # dialogs also have Submit buttons, which save credit data to the draft.
        dialogs=self.page.get_by_role('dialog')
        if not any(dialogs.nth(i).is_visible() for i in range(dialogs.count())):
            try:self.named(self.page,'button','Submit');return 'review'
            except NeedsAttention:pass
        for caption,stage in [('More release options','options'),('Release Settings','settings'),('Track information','track')]:
            if self.heading(caption):return stage
        # Some SoundOn titles are plain divs, without an accessible heading role.
        # Detect actual form controls rather than sidebar labels (all steps appear there).
        try:self.named(self.page,'button','Next')
        except NeedsAttention:return 'unknown'
        if self.has_control('English title') and self.has_control('Version'):return 'track'
        if self.has_control('Title') and self.has_control('Title language'):return 'track'
        if self.has_control('Release date'):return 'settings'
        try:
            self.group('What percentage of this track was written or composed by you?','input[type=radio],[role=radio]')
            return 'options'
        except NeedsAttention:return 'unknown'

    def resolve(self, caption, selector=FORM_CONTROL):
        self.check()
        key='field-'+str(abs(hash(caption+selector)))
        for text in aliases(caption):
            count=self.page.evaluate(RESOLVE,{'caption':text,'selector':selector,'key':key,'root':self.scope.element_handle() if self.scope is not None else None})
            if count>1:raise NeedsAttention(caption+': lebih dari satu kolom cocok.')
            if count==1:return self.page.locator('[data-soundon-bot="'+key+'"]')
        raise NeedsAttention(caption+': tidak dapat mengenali kolom; periksa label/bahasa SoundOn.')

    def fill(self, caption, value, required=True, selector=FORM_CONTROL):
        self.check()
        if not value:
            if required:raise NeedsAttention('Data '+caption+' belum diisi dalam antrean.')
            return
        control=self.resolve(caption,selector)
        tag,kind=control.evaluate('(e) => [e.tagName.toLowerCase(), e.type || ""]')
        if tag not in ('input','textarea') or kind in ('radio','checkbox','button','submit','file'):
            raise NeedsAttention(caption+': jenis kolom belum didukung.')
        current=control.input_value()
        if current and current!=value:
            raise NeedsAttention(caption+': berisi nilai berbeda. Kosongkan/perbaiki draf dahulu.')
        control.fill(value,timeout=5000)
        control.press('Tab',timeout=5000)
        if control.input_value()!=value:raise NeedsAttention(caption+': nilai tidak diterima SoundOn.')
        self.log('Terisi: '+caption)

    def selected_value(self,control,choices):
        # Custom selects sometimes keep a blank search input while rendering
        # the selected value as a sibling span in the same field wrapper.
        return control.evaluate(r'''(e,choices)=>{
            const norm=s=>String(s||'').replace(/\s+/g,' ').trim().toLocaleLowerCase();
            const accepted=new Set(choices.map(norm));
            const visible=x=>x.getClientRects().length>0&&getComputedStyle(x).visibility!=='hidden';
            if(accepted.has(norm(e.value))||accepted.has(norm(e.textContent)))return true;
            let p=e.parentElement;
            for(let depth=0;p&&depth<4;depth++,p=p.parentElement){
                const controls=p.querySelectorAll('input:not([type=hidden]),select,textarea,[role=combobox]');
                if(controls.length>1)break;
                for(const x of p.querySelectorAll('span,div')){
                    if(visible(x)&&accepted.has(norm(x.textContent))&&!x.closest('[role=option],[role=listbox],[role=menu],[class*=option],[class*=dropdown],[class*=popup]'))return true;
                }
            }
            return false;
        }''',list(choices))

    def dropdown_option(self,control,value):
        try:return self.named(self.page,'option',value,caption_values=True)
        except NeedsAttention:pass
        key='option-'+str(abs(hash(value)))
        count=self.page.evaluate(r'''({control,choices,key})=>{
            const norm=s=>String(s||'').replace(/\s+/g,' ').trim().toLocaleLowerCase();
            const accepted=new Set(choices.map(norm));
            const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[aria-hidden=true]');
            const popups=Array.from(document.querySelectorAll('[role=listbox],[role=menu],[class*=dropdown],[class*=popup]')).filter(visible);
            const labelled=Array.from(document.querySelectorAll('div,span,li,button,p')).filter(e=>{
                if(!visible(e)||e===control||control.contains(e)||e.contains(control)||e.closest('[aria-disabled=true]')||e.disabled)return false;
                if(!accepted.has(norm(e.textContent)))return false;
                return !Array.from(e.children).some(c=>visible(c)&&accepted.has(norm(c.textContent)));
            });
            const scoped=labelled.filter(e=>popups.some(p=>p.contains(e)));
            const candidates=scoped.length?scoped:labelled;
            if(candidates.length!==1)return candidates.length;
            candidates[0].setAttribute('data-soundon-option',key);return 1;
        }''',{'control':control.element_handle(),'choices':list(values(value)),'key':key})
        if count!=1:raise NeedsAttention(value+': pilihan dropdown belum unik/tidak terlihat. Buka daftar bahasa/genre lalu kirim screenshot daftar yang terbuka.')
        return self.page.locator('[data-soundon-option="'+key+'"]')

    def choose(self, caption, value):
        if not value:raise NeedsAttention('Pilih '+caption+' pada data antrean.')
        control=self.resolve(caption)
        choices=values(value)
        tag=control.evaluate('(e)=>e.tagName.toLowerCase()')
        if tag=='select':
            options=control.locator('option');matching=[]
            accepted={v.casefold() for v in choices}
            for i in range(options.count()):
                if options.nth(i).inner_text().strip().casefold() in accepted:matching.append(i)
            if len(matching)!=1:raise NeedsAttention(caption+': pilihan '+value+' tidak ditemukan/ambigu.')
            control.select_option(index=matching[0],timeout=5000)
            if control.locator('option:checked').inner_text().strip().casefold() not in accepted:
                raise NeedsAttention(caption+': pilihan tidak tersimpan.')
        else:
            if self.selected_value(control,choices):
                self.log('Sudah dipilih: '+caption+' → '+value);return
            control.click(timeout=5000);self.check()
            if self.scope is not None and caption in ('Artist name','Name') and tag=='input':
                control.fill(value,timeout=5000)
            # Wait for the dropdown to finish rendering without repeated clicks.
            deadline=time.monotonic()+5;option=None
            while time.monotonic()<deadline:
                self.check()
                try:option=self.dropdown_option(control,value);break
                except NeedsAttention:
                    self.cancelled.wait(0.2)
            if option is None:
                raise NeedsAttention(caption+' → '+value+': opsi belum dikenali. Kirim screenshot daftar dropdown yang terbuka.')
            option.click(timeout=5000)
            deadline=time.monotonic()+5
            while not self.selected_value(control,choices):
                self.check()
                if time.monotonic()>deadline:
                    raise NeedsAttention(caption+': opsi diklik tetapi nilai belum terverifikasi. Periksa browser sebelum melanjutkan.')
                self.cancelled.wait(0.2)
        self.log('Dipilih dan diverifikasi: '+caption+' → '+value)

    def group(self, caption, selector):
        # More than one radio/switch belongs to the caption's smallest container.
        key='group-'+str(abs(hash(caption)))
        script=r'''({caption,selector,key})=>{
          const norm=s=>s.replace(/\((?:Optional|Opsional)\)/gi,'').replace(/\s+/g,' ').trim().toLocaleLowerCase();
          const visible=e=>e.getClientRects().length>0;
          const matches=e=>norm(e.innerText||'')===norm(caption)||norm(Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join(' '))===norm(caption);
          const labels=Array.from(document.querySelectorAll('label,div,span,p,h2,h3,h4')).filter(e=>visible(e)&&matches(e)).filter(e=>!Array.from(e.children).some(c=>visible(c)&&matches(c)));
          const groups=new Set();for(const l of labels){let p=l;for(let i=0;p&&i<7;i++,p=p.parentElement){if(p.querySelector(selector)){groups.add(p);break;}}}
          if(groups.size!==1)return groups.size;
          Array.from(groups)[0].setAttribute('data-soundon-bot',key);return 1;
        }'''
        for text in aliases(caption):
            count=self.page.evaluate(script,{'caption':text,'selector':selector,'key':key})
            if count>1:raise NeedsAttention(caption+': kelompok pilihan ambigu.')
            if count==1:return self.page.locator('[data-soundon-bot="'+key+'"]')
        raise NeedsAttention(caption+': tidak dapat mengenali kelompok pilihan; periksa bahasa formulir.')

    def radio_selected(self,control):
        if control.is_checked(timeout=5000):return True
        # Some custom radio components render their state on the enclosing
        # radio wrapper while the inner input's checked property stays false.
        return control.evaluate(r'''e=>{
            for(let p=e,depth=0;p&&depth<4;p=p.parentElement,depth++){
                const radios=p.matches('input[type=radio],[role=radio]')?[p]:Array.from(p.querySelectorAll('input[type=radio],[role=radio]'));
                if(radios.length!==1)break;
                if(p.getAttribute('aria-checked')==='true'||p.getAttribute('data-state')==='checked')return true;
                if(Array.from(p.classList).some(c=>/(?:^|[-_])radio(?:[-_].*)?[-_]checked$/.test(c)))return true;
            }
            return false;
        }''')

    def skip_pre_release(self):
        self.check()
        choices=[]
        for text in values('Skip for now'):
            loc=self.page.get_by_text(text,exact=True)
            for i in range(loc.count()):
                if loc.nth(i).is_visible():choices.append(loc.nth(i))
        if len(choices)!=1:raise NeedsAttention('Skip for now: teks pilihan tidak unik.')
        label=choices[0]
        selected=r'''e=>{
            for(let p=e,i=0;p&&i<7;p=p.parentElement,i++){
                const radios=Array.from(p.querySelectorAll('input[type=radio],[role=radio]'));
                if(radios.length>1)return false;
                if(radios.some(r=>r.checked||r.getAttribute('aria-checked')==='true'))return true;
                if(p.getAttribute('aria-checked')==='true'||p.getAttribute('data-state')==='checked')return true;
                if(Array.from(p.classList).some(c=>/(?:^|[-_])radio(?:[-_].*)?[-_]checked$/.test(c)))return true;
                if(radios.length===1&&Array.from(p.querySelectorAll('[class]')).some(n=>Array.from(n.classList).some(c=>/(?:^|[-_])radio(?:[-_].*)?[-_]checked$/.test(c))))return true;
            }
            return false;
        }'''
        if not label.evaluate(selected):label.click(timeout=5000)
        deadline=time.monotonic()+5
        while not label.evaluate(selected):
            self.check()
            if time.monotonic()>deadline:raise NeedsAttention('Skip for now: pilihan belum terverifikasi.')
            self.cancelled.wait(0.1)
        self.log('Dipilih dan diverifikasi: TikTok pre-release → Skip for now')

    def radio(self,caption,value):
        if not value:raise NeedsAttention('Pilihan '+caption+' belum ditentukan.')
        self.check()
        group=self.page if caption=='TikTok pre-release' and value=='Skip for now' else self.group(caption,'input[type=radio],[role=radio]')
        try:control=self.named(group,'radio',value,caption_values=True)
        except NeedsAttention:
            # Find the exact choice text in the group, then its one radio wrapper.
            found=[]
            for choice in values(value):
                texts=group.get_by_text(choice,exact=True)
                for i in range(texts.count()):
                    if texts.nth(i).is_visible():found.append(texts.nth(i))
            if len(found)!=1:raise NeedsAttention(caption+': label pilihan tidak ditemukan/ambigu.')
            text=found[0]
            controls=text.locator('xpath=ancestor::*[.//input[@type="radio"] or .//*[@role="radio"]][1]').locator('input[type=radio],[role=radio]')
            if controls.count()!=1:raise NeedsAttention(caption+': pilihan radio ambigu.')
            control=controls
        if self.radio_selected(control):
            self.log('Sudah dipilih: '+caption+' → '+value);return
        # SoundOn's custom radio handles clicks on its visible label/wrapper.
        # Clicking only the inner native input can leave React state unchanged.
        target_key='radio-target-'+str(abs(hash((caption,value))))
        marked=control.evaluate(r'''(e,key)=>{
            const visible=n=>n&&n.getClientRects().length>0;
            const candidates=[];
            if(e.labels)for(const l of e.labels)if(visible(l))candidates.push(l);
            for(const id of (e.getAttribute('aria-labelledby')||'').split(/\s+/)){
                const l=document.getElementById(id);if(visible(l))candidates.push(l);
            }
            const targets=[...new Set(candidates)];
            let target=targets.length===1?targets[0]:null;
            if(!target){
                const wrapper=e.closest('label,[role=radio]');
                if(visible(wrapper))target=wrapper;
            }
            if(!target)return false;
            target.setAttribute('data-soundon-radio-target',key);return true;
        }''',target_key)
        target=self.page.locator('[data-soundon-radio-target="'+target_key+'"]') if marked else control
        target.click(timeout=5000)
        deadline=time.monotonic()+5
        while not self.radio_selected(control):
            self.check()
            if time.monotonic()>deadline:
                raise NeedsAttention(caption+' → '+value+': label diklik tetapi status radio belum aktif. Pengisian dihentikan.')
            self.cancelled.wait(0.1)
        self.log('Dipilih: '+caption+' → '+value)

    def toggle(self,caption,value):
        if value not in ('On','Off'):raise NeedsAttention('Pilih On/Off untuk '+caption+'.')
        self.check()
        control=self.resolve(caption,'input[type=checkbox],[role=switch]')
        target=value=='On'
        if control.get_attribute('role')=='switch':
            current=control.get_attribute('aria-checked')
            if current not in ('true','false'):raise NeedsAttention(caption+': status switch tidak terbaca.')
            if (current=='true')!=target:control.click(timeout=5000)
            if control.get_attribute('aria-checked')!=str(target).lower():raise NeedsAttention(caption+': perubahan switch gagal.')
        else:control.set_checked(target,timeout=5000)
        self.log(caption+': '+value)

    def upload(self,key,caption,token):
        self.check()
        if key in self.files_done:return
        # A previously completed upload is represented in SoundOn's form state,
        # even when the native file input has been cleared after transfer.
        filename=Path(self.job[key]).name
        files=self.page.get_by_text(filename,exact=True)
        for i in range(files.count()):
            node=files.nth(i)
            if not node.is_visible():continue
            section=node
            for depth in range(6):
                labels=[section.get_by_text(text,exact=True) for text in aliases(caption)]
                if any(any(loc.nth(k).is_visible() for k in range(loc.count())) for loc in labels):
                    completed=section.get_by_text('Upload complete',exact=True)
                    if any(completed.nth(k).is_visible() for k in range(completed.count())):
                        self.files_done.add(key);self.log('File sudah selesai diunggah: '+caption);return
                    raise NeedsAttention(caption+': file ada tetapi pemrosesan belum selesai. Tunggu lalu ulangi.')
                section=section.locator('xpath=..')
        inputs=self.page.locator('input[type=file]');candidates=[]
        extensions=('.wav','.flac','.mp3','.aiff') if key=='audio' else ('.png','.jpg','.jpeg')
        for i in range(inputs.count()):
            control=inputs.nth(i);accept=(control.get_attribute('accept') or '').lower()
            if token in accept or any(ext in accept for ext in extensions):candidates.append(control)
        control=None
        if len(candidates)==1:control=candidates[0]
        else:
            # Duplicate hidden inputs are common in SoundOn. First scope the
            # control to its labelled audio section; otherwise use Add file's
            # chooser to identify the exact input activated by SoundOn itself.
            try:control=self.resolve(caption,'input[type=file]')
            except NeedsAttention:
                if key!='audio':raise
                self.log('Input audio belum unik; mencoba pemilih file dari tombol Add file/Tambah file.')
        if control is not None:
            self.set_file(control,self.job[key],caption)
        else:
            # SoundOn may create its file input only after the Add file button
            # is clicked. Capture Playwright's file chooser rather than guessing
            # the hidden input's position or automating the Windows dialog.
            pattern=re.compile(r'^\+?\s*(?:Add file|Tambah file|Tambahkan file|Tambahkan berkas|Pilih file)\s*$',re.I)
            try:button=unique_visible(self.page.get_by_role('button',name=pattern),'Add file / Tambah file')
            except NeedsAttention:
                button=unique_visible(self.page.get_by_text(pattern),'Add file / Tambah file')
            self.check()
            try:
                with self.page.expect_file_chooser(timeout=15000) as pending:
                    button.click(timeout=5000)
                chooser=pending.value
            except Exception as ex:
                raise NeedsAttention('Tombol file ditemukan, tetapi pemilih file tidak terbuka. Periksa browser; bot tidak mengulang klik.') from ex
            self.check()
            self.set_file(chooser.element,self.job[key],caption,chooser)
        self.files_done.add(key)
        self.log('File dipasang: '+caption+'; menunggu validasi SoundOn saat Next.')

    def set_file(self,control,path,caption,chooser=None):
        self.check()
        existing=control.evaluate('(e)=>Array.from(e.files).map(f=>f.name)')
        wanted=Path(path).name
        if existing:
            if existing!=[wanted]:raise NeedsAttention(caption+': file berbeda sudah ada di draf; tidak ditimpa.')
            self.log(caption+': file yang sama sudah terpasang; tidak diunggah ulang.')
            return
        if chooser is not None:chooser.set_files(path,timeout=30000)
        else:control.set_input_files(path,timeout=30000)

    def credit_dialog(self,caption):
        titles={
            'Primary artists':'Add primary artist',
            'Contributors':'Add a contributor',
            'Production and additional contributors':'Add production or additional contributors',
            'Songwriters':'Add songwriter',
            'Lyricists':'Add lyricist',
        }
        title=titles.get(caption)
        if title is None:raise NeedsAttention('Jenis kredit belum didukung: '+caption)
        dialog=unique_visible(self.page.get_by_role('dialog'),title)
        # Submission is permitted only within this specific, observed credit
        # dialog. An unrelated dialog or the final release page is never accepted.
        headings=dialog.get_by_text(title,exact=True)
        if not any(headings.nth(i).is_visible() for i in range(headings.count())):
            raise NeedsAttention('Judul dialog tidak sesuai '+title+'. Tidak menyimpan otomatis.')
        return dialog

    def save_credit(self,dialog):
        self.check()
        # This is the dialog-local Submit in the recorded Add ... forms,
        # not the release Submit on the Review page.
        known=('Add primary artist','Add a contributor','Add production or additional contributors','Add songwriter','Add lyricist')
        if not any(dialog.get_by_text(title,exact=True).count() for title in known):
            raise NeedsAttention('Submit hanya diizinkan pada dialog kredit yang dikenali.')
        button=self.named(dialog,'button','Submit')
        if not button.is_enabled():raise NeedsAttention('Kredit belum lengkap; Submit dialog belum aktif.')
        button.click(timeout=5000)
        deadline=time.monotonic()+10
        while dialog.is_visible():
            self.check()
            if time.monotonic()>deadline:raise NeedsAttention('Dialog kredit belum tertutup. Periksa validasi nama/profil di browser.')
            self.cancelled.wait(0.2)

    def add_person(self,caption,name,role=None):
        if not name:raise NeedsAttention('Data '+caption+' belum diisi.')
        self.check()
        # Bring the section into its scroll container before finding Add.
        # Lower credits can be clipped by SoundOn's fixed bottom action bar.
        heading_key='credit-heading-'+str(abs(hash(caption)))
        heading=None
        for text in aliases(caption):
            count=self.page.evaluate(r'''({caption,key})=>{
                const norm=s=>s.replace(/\((?:Optional|Opsional)\)/gi,'').replace(/\s+/g,' ').trim().toLowerCase();
                const visible=e=>e.getClientRects().length>0;
                const matches=e=>norm(e.innerText||'')===norm(caption)||norm(Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join(' '))===norm(caption);
                const labels=Array.from(document.querySelectorAll('label,div,span,p,h2,h3,h4')).filter(e=>visible(e)&&matches(e)).filter(e=>!Array.from(e.children).some(c=>visible(c)&&matches(c)));
                if(labels.length===1)labels[0].setAttribute('data-soundon-credit-heading',key);
                return labels.length;
            }''',{'caption':text,'key':heading_key})
            if count>1:raise NeedsAttention(caption+': judul bagian ambigu.')
            if count==1:
                heading=self.page.locator('[data-soundon-credit-heading="'+heading_key+'"]');break
        if heading is None:raise NeedsAttention(caption+': judul bagian tidak ditemukan.')
        heading.scroll_into_view_if_needed(timeout=5000)
        heading.evaluate('(e)=>e.scrollIntoView({block:"center",inline:"nearest"})')
        self.check()
        self.page.evaluate(r'''()=>{const norm=s=>s.replace(/\s+/g,' ').trim();for(const e of document.querySelectorAll('div,span,button')){if(/^\+?\s*(Add|Tambah|Tambahkan)$/.test(norm(e.textContent))&&!Array.from(e.children).some(c=>/^\+?\s*(Add|Tambah|Tambahkan)$/.test(norm(c.textContent))))e.setAttribute('data-soundon-add','true');}}''')
        group=self.group(caption,'button,[role=button],[data-soundon-add]')
        names=group.get_by_text(name,exact=True)
        existing=any(names.nth(i).is_visible() for i in range(names.count()))
        if existing:
            if role:
                shown=False
                for text in values(role):
                    roles=group.get_by_text(text,exact=True)
                    if any(roles.nth(i).is_visible() for i in range(roles.count())):shown=True;break
                if not shown:
                    raise NeedsAttention(caption+': nama sudah ada dengan peran berbeda. Periksa kredit yang sudah tersimpan.')
            self.log('Kredit sudah ada: '+caption+' → '+name);return
        pattern=re.compile(r'^\+?\s*(?:Add|Tambah|Tambahkan)$',re.I)
        try:button=unique_visible(group.get_by_role('button',name=pattern),caption+' Add')
        except NeedsAttention:button=unique_visible(group.get_by_text(pattern),caption+' Add')
        button.click(timeout=5000)
        deadline=time.monotonic()+5;dialog=None
        while time.monotonic()<deadline:
            self.check()
            try:dialog=self.credit_dialog(caption);break
            except NeedsAttention:self.cancelled.wait(0.2)
        if dialog is None:raise NeedsAttention('Dialog '+caption+' belum dikenali; periksa browser.')
        self.scope=dialog
        try:
            if role:self.choose('Role',role)
            label='Artist name' if caption in ('Primary artists','Contributors','Production and additional contributors') else 'Name'
            self.choose(label,name)
            self.save_credit(dialog)
        finally:self.scope=None
        # Locate section again after the modal updates the draft.
        group=self.group(caption,'button,[role=button],[data-soundon-add]')
        names=group.get_by_text(name,exact=True)
        if not any(names.nth(i).is_visible() for i in range(names.count())):
            raise NeedsAttention(caption+': dialog tertutup tetapi nama belum terlihat pada draf.')
        self.log('Kredit tersimpan: '+caption+' → '+name)

    def track(self):
        j=self.job
        self.upload('audio','Audio file','audio')
        self.fill('Title',j['title'])
        self.choose('Title language',j['language'])
        self.choose('Genre',j['genre'])
        for caption,key in [('English title','english_title'),('Record label','record_label')]:self.fill(caption,j.get(key,''),False)
        for caption,key in [('Version','version'),('Subgenre','subgenre')]:
            if j.get(key):self.choose(caption,j[key])
        self.radio('Instrumental',j['instrumental'])
        if j['instrumental']=='No':
            self.choose('Lyrics language',j['lyrics_language'])
            self.choose('Explicit',j['explicit'])
            self.fill('Lyrics',j.get('lyrics',''),False)
        self.add_person('Primary artists',j['artist'])
        self.add_person('Contributors',j['contributor'],j['contributor_role'])
        self.add_person('Production and additional contributors',j['producer'],j['producer_role'])
        self.add_person('Songwriters',j['songwriter'])
        if j['instrumental']=='No':self.add_person('Lyricists',j['lyricist'])
        if j.get('cover_mode')=='AI SoundOn':self.ai_cover()
        else:self.upload('cover','Cover art','image')
        self.log('Memilih Track distribution → Previously released?: '+j['previously_released'])
        self.radio('Previously released?',j['previously_released'])
        if j.get('upc') or j.get('isrc'):
            raise NeedsAttention('UPC/ISRC lama memerlukan formulir tambahan yang belum terlihat. Lengkapi di browser.')
        self.prepare_clip()

    def cover_ready(self):
        button=self.named(self.page,'button','Generate AI cover')
        return button.evaluate(r'''e=>{
            const norm=s=>(s||'').replace(/\s+/g,' ').trim();
            for(let p=e.parentElement,depth=0;p&&depth<8;p=p.parentElement,depth++){
                const heading=Array.from(p.querySelectorAll('*')).some(n=>
                    norm(n.innerText)==='Cover art'||norm(Array.from(n.childNodes).filter(x=>x.nodeType===3).map(x=>x.textContent).join(' '))==='Cover art');
                if(!heading)continue;
                const found=Array.from(p.querySelectorAll('*')).some(n=>{
                    const r=n.getBoundingClientRect();if(r.width<100||r.height<100)return false;
                    if(n.tagName==='IMG')return n.complete&&n.naturalWidth>0;
                    return n.tagName==='CANVAS'||getComputedStyle(n).backgroundImage!=='none';
                });
                if(found)return true;
                // This is the cover section. Never search unrelated sections.
                return false;
            }
            return false;
        }''')

    def clip_upload_complete(self):
        return self.page.locator('body').evaluate(r'''(root)=>{
            const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
            const norm=s=>(s||'').replace(/\s+/g,' ').trim();
            const labels=Array.from(root.querySelectorAll('*')).filter(e=>visible(e)&&/^Clip\s*1$/i.test(norm(e.innerText)));
            return labels.some(label=>{
                let row=label;
                for(let i=0;row&&i<6;i++,row=row.parentElement){
                    const text=norm(row.innerText);
                    if(/Upload complete|Unggah selesai|Unggahan selesai/i.test(text)){
                        // Stop at the clip row before reaching the full-audio section.
                        return !/Upload the full song file|Create several official sounds/i.test(text);
                    }
                }
                return false;
            });
        }''')

    def wait_clip_upload(self):
        self.log('Menunggu status Upload complete pada Clip 1.')
        deadline=time.monotonic()+120
        while not self.clip_upload_complete():
            self.check()
            if time.monotonic()>deadline:
                raise NeedsAttention('Status Upload complete pada Clip 1 belum dikenali. Periksa klip di browser.')
            self.cancelled.wait(0.5)
        self.check()
        self.log('Clip 1 Upload complete; siap melanjutkan ke Next.')

    def prepare_clip(self):
        self.check()
        body=self.page.locator('body').inner_text()
        if re.search(r'Clip\s*1',body,re.I):
            self.log('Klip TikTok sudah ada; tidak membuat ulang.');self.wait_clip_upload();return
        button=self.named(self.page,'button','Trim online')
        button.scroll_into_view_if_needed(timeout=5000)
        button.evaluate('(e)=>e.scrollIntoView({block:"center"})')
        self.log('Menggulir ke audio dan membuka Trim online.')
        button.click(timeout=5000)
        deadline=time.monotonic()+15;trim=None
        while time.monotonic()<deadline:
            self.check()
            ds=self.page.get_by_role('dialog')
            visible=[ds.nth(i) for i in range(ds.count()) if ds.nth(i).is_visible() and ds.nth(i).get_by_text('Trim online',exact=True).count()]
            if len(visible)==1:trim=visible[0];break
            self.cancelled.wait(0.2)
        if trim is None:raise NeedsAttention('Dialog Trim online belum terbuka.')
        self.confirm_trim(trim)
        self.wait_clip_upload()

    def ai_cover(self):
        self.check()
        if self.cover_ready():
            self.log('Cover sudah terpasang; tidak membuat ulang.');return
        self.named(self.page,'button','Generate AI cover').click(timeout=5000)
        deadline=time.monotonic()+10;dialog=None
        while time.monotonic()<deadline:
            self.check()
            ds=self.page.get_by_role('dialog')
            candidates=[ds.nth(i) for i in range(ds.count()) if ds.nth(i).is_visible() and ds.nth(i).get_by_text('Generate AI cover',exact=True).count()]
            if len(candidates)==1:dialog=candidates[0];break
            self.cancelled.wait(0.2)
        if dialog is None:raise NeedsAttention('Dialog Generate AI cover belum dikenali.')
        inputs=dialog.locator('textarea')
        if inputs.count()!=1:raise NeedsAttention('Kolom prompt cover AI belum unik.')
        inputs.fill('',timeout=5000)
        self.log('Prompt AI dikosongkan; memakai gaya pilihan SoundOn.')
        style=self.job.get('cover_style') or '3D Animation'
        unique_visible(dialog.get_by_text(style,exact=True),'Gaya cover AI').click(timeout=5000)
        self.named(dialog,'button','Generate').click(timeout=5000)
        self.log('Membuat cover AI SoundOn; menunggu hasil pertama.')
        deadline=time.monotonic()+180
        while True:
            self.check()
            use=self.named(dialog,'button','Use this')
            ready=dialog.locator('img').evaluate_all('(xs)=>xs.some(e=>e.complete&&e.naturalWidth>0&&e.getBoundingClientRect().width>=200&&e.getBoundingClientRect().height>=200)')
            if use.is_enabled() and ready:break
            if time.monotonic()>deadline:raise NeedsAttention('Cover AI belum selesai dalam 3 menit. Periksa dialog di browser sebelum melanjutkan.')
            self.cancelled.wait(0.5)
        use.click(timeout=5000)
        deadline=time.monotonic()+15
        while dialog.is_visible():
            self.check()
            if time.monotonic()>deadline:raise NeedsAttention('Use this sudah diklik tetapi dialog cover belum tertutup.')
            self.cancelled.wait(0.2)
        deadline=time.monotonic()+30
        while not self.cover_ready():
            self.check()
            if time.monotonic()>deadline:
                raise NeedsAttention('Cover AI belum terverifikasi setelah Use this. Periksa preview cover di browser.')
            self.cancelled.wait(0.3)
        self.log('Cover AI terpasang; periksa hasilnya pada Review.')

    def validation_dialog(self):
        dialogs=self.page.get_by_role('dialog')
        visible=[dialogs.nth(i) for i in range(dialogs.count()) if dialogs.nth(i).is_visible()]
        if len(visible)!=1:return False
        dialog=visible[0]
        text=dialog.inner_text()
        if 'errors detected' not in text.lower():
            raise NeedsAttention('SoundOn membuka dialog: '+text[:200]+'. Periksa di browser.')
        # Recorded Fix now opens Trim online for a missing TikTok clip. Never
        # choose Later: errors must be fixed before advancing.
        self.named(dialog,'button','Fix now').click(timeout=5000)
        deadline=time.monotonic()+15;trim=None
        while time.monotonic()<deadline:
            self.check()
            try:
                trim=unique_visible(self.page.get_by_role('dialog'),'Trim online')
                if trim.get_by_text('Trim online',exact=True).count():break
                trim=None
            except NeedsAttention:pass
            self.cancelled.wait(0.2)
        if trim is None:raise NeedsAttention('Validasi membutuhkan perbaikan selain klip. Periksa kolom merah di browser.')
        self.confirm_trim(trim)
        return True

    def trim_text(self,trim):
        # inner_text omits input.value. SoundOn renders the From/To values
        # as editable controls, so read them in their actual document order.
        return trim.evaluate(r'''root=>{
            const parts=[];
            function visit(n){
                if(n.nodeType===3){parts.push(n.nodeValue);return;}
                if(n.nodeType!==1||!n.getClientRects().length)return;
                if(['SCRIPT','STYLE','SVG'].includes(n.tagName))return;
                if(n.matches('input,textarea,select')){parts.push(n.value||'');return;}
                for(const child of n.childNodes)visit(child);
            }
            visit(root);return parts.join(' ').replace(/\s+/g,' ').trim();
        }''')

    def confirm_trim(self,trim):
        if self.job.get('clip_mode') not in ('SoundOn selected segment','First 15 seconds'):
            raise NeedsAttention('Pilih/konfirmasi segmen klip TikTok secara manual, lalu jalankan kembali.')
        self.log('Menunggu rentang trim dan tombol Confirm siap.')
        deadline=time.monotonic()+120
        confirm=None
        while time.monotonic()<deadline:
            self.check()
            text=self.trim_text(trim)
            segment=re.search(r'From\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*To\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*Length\s*:\s*(\d+(?:\.\d+)?)\s*s',text,re.I)
            if segment:
                a,b,c,d,length=map(float,segment.groups())
                start=a*60+b;end=c*60+d
                if b<60 and d<60 and length>0 and end>start and abs(end-start-length)<0.2:
                    try:
                        confirm=unique_visible(trim.get_by_role('button',name=re.compile(r'^\s*[✓✔]?\s*Confirm\s*$',re.I)),'Trim Confirm')
                    except NeedsAttention:
                        try:confirm=unique_visible(trim.get_by_text('Confirm',exact=True),'Trim Confirm')
                        except NeedsAttention:confirm=None
                    if confirm is not None and confirm.is_enabled():break
            self.cancelled.wait(0.3)
        else:raise NeedsAttention('Rentang klip atau tombol Confirm belum siap. Periksa Trim online.')
        self.check()
        deadline=time.monotonic()+180
        waiting_logged=False
        while True:
            self.check()
            # semi-spin is also a persistent layout wrapper after loading.
            # Inspect the actual click point instead of its mere visibility.
            loading=not confirm.evaluate(r'''e=>{
                const target=e.closest('button,[role=button]')||e;
                const r=target.getBoundingClientRect();
                if(!r.width||!r.height)return false;
                const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
                return !!hit&&target.contains(hit);
            }''')
            if loading:
                if not waiting_logged:
                    self.log('Loading SoundOn masih menutupi Confirm; menunggu hingga selesai.');waiting_logged=True
            else:
                try:
                    confirm.click(timeout=1500)
                    break
                except Exception as ex:
                    if type(ex).__name__!='TimeoutError':raise
                    # A timed-out action can complete just as its deadline
                    # expires. A closed trim dialog must never be clicked again.
                    if not trim.is_visible():break
                    if not waiting_logged:
                        self.log('Confirm belum dapat diklik; menunggu lapisan loading selesai.');waiting_logged=True
            if time.monotonic()>deadline:
                raise NeedsAttention('Confirm masih terhalang loading setelah 3 menit. Tunggu SoundOn selesai lalu lanjutkan.')
            self.cancelled.wait(0.3)
        self.log('Klip TikTok dikonfirmasi: '+segment.group(0))
        return True

    def continue_release_date(self):
        self.check()
        title=self.page.get_by_text('Release Date Too Soon',exact=True)
        if not any(title.nth(i).is_visible() for i in range(title.count())):return False
        button=unique_visible(self.page.get_by_role('button',name='No, continue with this date',exact=True),'Konfirmasi tanggal rilis')
        button.click(timeout=5000)
        self.log('Dipilih: No, continue with this date.')
        return True

    def release_date(self):
        from datetime import date
        target=date.fromisoformat(self.job['release_date'])
        self.continue_release_date()
        control=self.resolve('Release date','input:not([type=hidden]):not([type=file])')
        def accepted():
            value=control.input_value().strip()
            parts=re.findall(r'\d+',value)
            if len(parts)!=3:return False
            nums=list(map(int,parts))
            return nums in ([target.year,target.month,target.day],[target.month,target.day,target.year],[target.day,target.month,target.year])
        if accepted():
            self.log('Release date sudah sesuai: '+target.isoformat());return
        if control.input_value().strip():raise NeedsAttention('Release date berisi tanggal berbeda; perbaiki draf dahulu.')
        if control.is_editable():
            self.fill('Release date',target.isoformat(),selector='input:not([type=hidden]):not([type=file])');return
        control.click(timeout=5000)
        months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        for _ in range(121):
            self.check()
            result=self.page.evaluate(r'''({iso,year,month,day,months})=>{
                document.querySelectorAll('[data-soundon-date-action]').forEach(e=>e.removeAttribute('data-soundon-date-action'));
                const vis=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
                const norm=s=>(s||'').replace(/\s+/g,' ').trim();
                const headers=Array.from(document.querySelectorAll('*')).filter(e=>vis(e)&&/^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}$/.test(norm(e.innerText))).filter(e=>!Array.from(e.children).some(c=>vis(c)&&norm(c.innerText)===norm(e.innerText)));
                if(headers.length!==1)return {error:'Header bulan kalender belum unik.'};
                const h=headers[0],parts=norm(h.innerText).split(' '),m=months.indexOf(parts[0].slice(0,3))+1,y=Number(parts[1]);
                let panel=h.parentElement;
                for(let i=0;panel&&i<6;i++,panel=panel.parentElement){
                    if(panel.querySelector('td,[role=gridcell],[class*=day],[class*=date-cell]'))break;
                }
                if(!panel)return {error:'Panel kalender belum dikenali.'};
                let element;
                if(m===month&&y===year){
                    const full=Array.from(panel.querySelectorAll('[title],[data-date],[aria-label]')).filter(e=>vis(e)&&[e.title,e.getAttribute('data-date'),e.getAttribute('aria-label')].includes(iso));
                    element=full.find(e=>e.tagName==='TD'||e.getAttribute('role')==='gridcell')||full[0];
                    if(!element){
                        const cells=Array.from(panel.querySelectorAll('td,[role=gridcell],[class*=day],[class*=date-cell]')).filter(e=>vis(e)&&norm(e.innerText)===String(day)&&!/prev|next|outside|other-month/i.test(e.className));
                        const leaves=cells.filter(e=>!cells.some(c=>c!==e&&e.contains(c)));
                        if(leaves.length!==1)return {error:'Tanggal tujuan belum unik pada kalender.'};
                        element=leaves[0];
                    }
                    if(element.closest('[aria-disabled=true],[class*=disabled]'))return {error:'Tanggal rilis tidak tersedia di SoundOn: '+iso};
                }else{
                    const direction=y*12+m<year*12+month?'next':'prev';
                    const candidates=Array.from(panel.querySelectorAll('button,[role=button]')).filter(e=>vis(e)&&new RegExp(direction,'i').test(e.className+' '+e.getAttribute('aria-label')+' '+e.title)&&!/super|year|double/i.test(e.className+' '+e.getAttribute('aria-label')+' '+e.title));
                    if(candidates.length!==1)return {error:'Tombol pindah bulan belum dikenali.'};
                    element=candidates[0];
                }
                element.setAttribute('data-soundon-date-action','active');return {pick:m===month&&y===year,header:norm(h.innerText)};
            }''',{'iso':target.isoformat(),'year':target.year,'month':target.month,'day':target.day,'months':months})
            if result.get('error'):raise NeedsAttention('Release date: '+result['error'])
            action=self.page.locator('[data-soundon-date-action="active"]')
            action.click(timeout=5000)
            if result['pick']:
                control.press('Tab',timeout=5000)
                deadline=time.monotonic()+10
                while not accepted() and time.monotonic()<deadline:
                    self.check();self.continue_release_date();self.cancelled.wait(0.2)
                if not accepted():raise NeedsAttention('Release date: tanggal pilihan belum diterima SoundOn ('+control.input_value()+').')
                self.log('Dipilih dan diverifikasi: Release date → '+target.isoformat());return
            self.cancelled.wait(0.3)
        raise NeedsAttention('Release date: tanggal di luar batas navigasi kalender.')

    def settings(self):
        j=self.job
        self.radio('Time synchronization',j['time_mode'])
        # A date picker can expose both a combobox wrapper and its input.
        # Locate only the editable input to avoid treating them as two fields.
        self.release_date()
        if j['time_mode']=='Global release':raise NeedsAttention('Global release: waktu/zona belum dipetakan. Lengkapi di browser.')
        self.skip_pre_release()
        # Preserves the platform choices that SoundOn shows; does not select paid extras.
        self.log('Platform: memakai pilihan yang sudah tampil di SoundOn. Add-on tidak ditambahkan.')

    def options(self):
        j=self.job
        self.radio('What percentage of this track was written or composed by you?',j['ownership'])
        if j['ownership']=='Other':raise NeedsAttention('Persentase Other memerlukan kolom tambahan. Lengkapi di browser.')
        self.fill('ISWC',j.get('iswc',''),False)
        self.radio('Does this track have an existing publishing administrator or publisher?',j['publisher'])
        self.radio('Have you registered this track with a PRO/CMO?',j['pro'])
        if j['publisher']=='Yes' or j['pro']=='Yes':raise NeedsAttention('Data penerbit/PRO memerlukan formulir tambahan. Lengkapi di browser.')
        # Monetisasi: CML & CapCut mengikuti pilihan (bawaan On). YouTube Content ID adalah Add-on
        # berbayar, jadi tidak pernah diaktifkan otomatis.
        for caption,key in (('Commercial Music Licensing','cml'),('CapCut','capcut')):
            self.toggle(caption,j.get(key) or 'On')
            self.after_toggle(caption)
        self.toggle('YouTube Content ID','Off')

    def after_toggle(self,caption):
        # Bila SoundOn membuka dialog setelah switch (mis. syarat), jangan menebak: berhenti dan laporkan.
        self.cancelled.wait(0.8)
        dialogs=self.page.get_by_role('dialog')
        for i in range(dialogs.count()):
            if dialogs.nth(i).is_visible():
                text=re.sub(r'\s+',' ',dialogs.nth(i).inner_text())[:220]
                raise NeedsAttention(caption+': SoundOn membuka dialog ('+text+'). Kirim screenshot dialog ini agar bisa dipetakan.')

    def wait_clip_next(self):
        self.check()
        self.log('Pengisian tahap selesai; menunggu 3 detik sebelum klik Next.')
        self.cancelled.wait(3)
        self.check()

    def next(self,old_stage):
        self.check()
        if self.stage()=='review':return
        self.wait_clip_next()
        button=self.named(self.page,'button','Next')
        deadline=time.monotonic()+120
        while not button.is_enabled():
            self.check()
            if time.monotonic()>deadline:raise NeedsAttention('Next belum aktif. Periksa file dan kolom wajib di browser.')
            self.cancelled.wait(0.4)
        self.log('Klik Next dari tahap: '+old_stage)
        button.click(timeout=10000)
        deadline=time.monotonic()+120
        clip_fixed=False
        while time.monotonic()<deadline:
            self.check()
            stage=self.stage()
            if stage!='unknown' and stage!=old_stage:return
            if old_stage=='settings' and self.continue_release_date():
                continue
            dialogs=self.page.get_by_role('dialog')
            if any(dialogs.nth(i).is_visible() for i in range(dialogs.count())):
                if clip_fixed:raise NeedsAttention('SoundOn menampilkan validasi kembali; periksa browser.')
                clip_fixed=self.validation_dialog()
                if clip_fixed:
                    self.wait_clip_upload()
                    self.wait_clip_next()
                    self.named(self.page,'button','Next').click(timeout=10000)
                    deadline=time.monotonic()+120
                    continue
            errors=self.page.locator('[role=alert], [aria-invalid=true]')
            if any(errors.nth(i).is_visible() for i in range(errors.count())):
                raise NeedsAttention('SoundOn menampilkan validasi. Periksa kolom bertanda merah di browser.')
            self.cancelled.wait(0.4)
        raise NeedsAttention('SoundOn belum berpindah tahap. Periksa unggahan/validasi; tidak mengulang klik Next otomatis.')

    def run(self):
        stage=self.stage()
        if stage=='unknown':
            raise NeedsAttention('Buka Track information pada draf tujuan. Proses tidak membuat draf baru agar tidak menggandakan unggahan.')
        for _ in range(4):
            stage=self.stage()
            if stage=='review':
                self.log('Review terbuka. Bot berhenti; Submit tidak ditekan.')
                return 'Siap ditinjau'
            if stage=='track':self.track()
            elif stage=='settings':self.settings()
            elif stage=='options':self.options()
            else:raise NeedsAttention('Tahap halaman tidak dikenali.')
            self.next(stage)
        raise NeedsAttention('Batas tahap tercapai. Periksa browser.')


SUBMIT_DONE = re.compile(r'(submitted successfully|successfully submitted|submission (?:was )?successful|submit(?:ted)? success'
                         r'|release (?:has been )?submitted|under review|in review|pending review|berhasil (?:dikirim|diajukan|disubmit)'
                         r'|pengajuan berhasil|terkirim|sedang ditinjau|menunggu (?:peninjauan|tinjauan|review))', re.I)
SUBMIT_WAIT = 120          # detik menunggu tanda terkirim setelah Submit
SUBMIT_CONFIRM = ('Confirm', 'Konfirmasi', 'Submit', 'Kirim', 'Kirimkan', 'Ajukan', 'OK', 'Oke', 'Yes', 'Ya', 'Continue', 'Lanjutkan')


def _visible_dialogs(page):
    dialogs = page.get_by_role('dialog')
    return [dialogs.nth(i) for i in range(dialogs.count()) if dialogs.nth(i).is_visible()]


def _done_texts(page):
    try:
        done = page.get_by_text(SUBMIT_DONE)
        return {re.sub(r'\s+', ' ', done.nth(i).inner_text()).strip()
                for i in range(min(done.count(), 20)) if done.nth(i).is_visible()}
    except Exception:
        return set()


def submit_release(flow, mark):
    """Tekan Submit rilis SATU kali di halaman Review lalu pastikan SoundOn menerimanya.

    mark() dipanggil tepat sebelum klik agar antrean mencatat "Submit ditekan" — lagu itu tidak
    akan pernah dikirim ulang otomatis walaupun hasilnya tidak terbaca (mencegah rilis ganda).
    Dialog yang meminta centang persetujuan atau tidak dikenali menghentikan proses.
    """
    page, log = flow.page, flow.log
    if flow.stage() != 'review':
        raise NeedsAttention('Review belum terbuka; Submit tidak ditekan.')
    if _visible_dialogs(page):
        raise NeedsAttention('Ada dialog terbuka di Review; Submit tidak ditekan. Periksa browser.')
    errors = page.locator('[role=alert], [aria-invalid=true]')
    if any(errors.nth(i).is_visible() for i in range(errors.count())):
        raise NeedsAttention('Review menampilkan peringatan/kolom merah; Submit tidak ditekan.')
    button = flow.named(page, 'button', 'Submit')
    deadline = time.monotonic() + 60
    while not button.is_enabled():
        flow.check()
        if time.monotonic() > deadline:
            raise NeedsAttention('Tombol Submit belum aktif setelah 60 detik; periksa Review.')
        flow.cancelled.wait(0.5)
    flow.check()
    start_url = page.url
    # Teks "terkirim/under review" yang SUDAH tampil di Review (mis. keterangan) bukan tanda berhasil.
    baseline = _done_texts(page)
    mark()
    button.click(timeout=10000)
    log('Submit ditekan.')
    confirmed = False
    deadline = time.monotonic() + SUBMIT_WAIT
    while time.monotonic() < deadline:
        host = (urlparse(page.url).hostname or '').lower()
        if host not in {'soundon.global', 'www.soundon.global', 'us.soundon.global'}:
            raise NeedsAttention('Setelah Submit halaman keluar dari SoundOn. Cek Library SoundOn.')
        dialogs = _visible_dialogs(page)
        if dialogs:
            text = ' '.join(d.inner_text() for d in dialogs)
            if SUBMIT_DONE.search(text):
                log('SoundOn: ' + re.sub(r'\s+', ' ', text)[:160])
                return 'Terkirim'
            dialog = dialogs[-1]
            boxes = dialog.locator('input[type=checkbox], [role=checkbox]')
            if any(boxes.nth(i).is_visible() for i in range(boxes.count())):
                raise NeedsAttention('Setelah Submit, SoundOn meminta persetujuan (centang): '
                                     + re.sub(r'\s+', ' ', text)[:220] + '. Selesaikan di browser.')
            if confirmed:
                raise NeedsAttention('SoundOn menampilkan dialog lagi setelah konfirmasi: ' + re.sub(r'\s+', ' ', text)[:220])
            buttons = []
            for word in SUBMIT_CONFIRM:
                loc = dialog.get_by_role('button', name=re.compile(r'^\s*' + re.escape(word) + r'\s*$', re.I))
                buttons += [loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]
            if len(buttons) != 1:
                raise NeedsAttention('Dialog setelah Submit belum dikenali: ' + re.sub(r'\s+', ' ', text)[:220]
                                     + '. Kirim screenshot agar bisa dipetakan.')
            name = buttons[0].inner_text().strip()
            buttons[0].click(timeout=10000)
            confirmed = True
            log('Konfirmasi Submit: ' + name)
            flow.cancelled.wait(1)
            continue
        fresh = _done_texts(page) - baseline
        if fresh:
            log('SoundOn: ' + sorted(fresh)[0][:160])
            return 'Terkirim'
        if page.url != start_url:
            try:
                still_review = flow.stage() == 'review'
            except NeedsAttention:
                still_review = False
            if not still_review:
                log('Halaman berpindah dari Review: ' + page.url)
                return 'Terkirim'
        errors = page.locator('[role=alert], [aria-invalid=true]')
        if any(errors.nth(i).is_visible() for i in range(errors.count())):
            raise NeedsAttention('SoundOn menolak Submit (peringatan tampil). Periksa Review di browser.')
        flow.cancelled.wait(0.5)
    raise NeedsAttention('Submit sudah ditekan tetapi hasilnya belum terlihat. Cek Library SoundOn — '
                         'jangan unggah ulang agar tidak dobel.')


def validate_automatic(job):
    for key in ('title','artist','language','genre','release_date','songwriter','instrumental','previously_released','time_mode','ownership','publisher','pro','cml','capcut'):
        if not job.get(key):raise ValueError('Lengkapi data otomatis: '+key)
    for key,values in [('instrumental',('Yes','No')),('cml',('On','Off')),('capcut',('On','Off'))]:
        if job[key] not in values:raise ValueError('Pilihan tidak valid: '+key)
    if job['previously_released']!='No, I want to distribute a new release':
        raise ValueError('Otomatisasi saat ini untuk rilis baru. Rilis lama membutuhkan pemetaan kolom tambahan.')
    if job['time_mode']!='Local release':raise ValueError('Pilih Local release; waktu Global release belum dipetakan.')
    if job['ownership'] not in ('100%','0%'):raise ValueError('Persentase Other belum didukung.')
    if job['publisher']!='No' or job['pro']!='No':raise ValueError('Penerbit/PRO Yes belum didukung otomatis. Jangan pilih No bila tidak sesuai; lengkapi manual.')
    if job.get('upc') or job.get('isrc'):raise ValueError('Kode UPC/ISRC lama belum didukung otomatis.')


def validate_recorded_fields(job):
    for key in ('contributor','contributor_role','producer','producer_role','clip_mode'):
        if not job.get(key):raise ValueError('Lengkapi tab Kredit & Lirik: '+key)
    if job['instrumental']=='No':
        for key in ('lyrics_language','explicit','lyricist'):
            if not job.get(key):raise ValueError('Lagu non-instrumental memerlukan '+key)
        if job['explicit'] not in ('Explicit','Non-Explicit','Clean'):
            raise ValueError('Pilih Explicit, Non-Explicit, atau Clean sesuai lagu.')
    if job['clip_mode'] not in ('SoundOn selected segment','First 15 seconds','Manual'):
        raise ValueError('Pilih cara pembuatan klip TikTok.')
