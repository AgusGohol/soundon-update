import os, json, hashlib, base64, socket, subprocess
from datetime import date
N=19134667727689715426502366656823330949653608651056833211287270304714556782359006354898759667488345401064709168350494207727776047018436720556033585145114860230035796734563200968008129936073480837227694196551895008058658101108426607668960297391871940518553909183615225025332212417543346573042733592621966605101332001227614031567906492422254822475717919396203419404008670809859827667284589078509826088665933967341846617112770317325793145162156484197256925091200585667383762058311249434059372806409254621371179573550071908796913273529960430511459559022754005503659410464448879926464262295288570411718013875368372352825043
E=65537
K=(N.bit_length()+7)//8
PREFIX=bytes.fromhex('3031300d060960864801650304020105000420')

def _raw_id():
    parts=[]
    try:
        import winreg
        k=winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\\Microsoft\\Cryptography')
        parts.append(str(winreg.QueryValueEx(k,'MachineGuid')[0]))
    except Exception: pass
    try:
        out=subprocess.check_output(['powershell','-NoProfile','-Command','(Get-CimInstance Win32_ComputerSystemProduct).UUID'], text=True, timeout=5, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).strip()
        if out: parts.append(out)
    except Exception: pass
    if not parts: parts=[socket.gethostname()]
    return '|'.join(parts)

def device_id():
    h=hashlib.sha256(('SOUNDON-DEVICE-V1|'+_raw_id()).encode()).hexdigest().upper()[:20]
    return 'SND-'+'-'.join(h[i:i+4] for i in range(0,20,4))

def _canon(p): return json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def verify(payload,sig_b64):
    try:
        sig=base64.b64decode(sig_b64); m=pow(int.from_bytes(sig,'big'),E,N).to_bytes(K,'big')
        digest=PREFIX+hashlib.sha256(_canon(payload)).digest()
        return m==b'\x00\x01'+b'\xff'*(K-len(digest)-3)+b'\x00'+digest
    except Exception: return False

def check_license(base_dir):
    path=os.path.join(base_dir,'soundon.license')
    if not os.path.exists(path): return False,'Perangkat ini belum mendapat izin dari Master.\n\nKode Perangkat: '+device_id()
    try:
        obj=json.load(open(path,'r',encoding='utf-8')); p=obj['license']; sig=obj['signature']
    except Exception: return False,'File izin soundon.license rusak atau tidak valid.'
    if not verify(p,sig): return False,'File izin tidak sah atau telah diubah.'
    if p.get('device_id')!=device_id(): return False,'Izin ini dibuat untuk perangkat lain.\n\nKode Perangkat: '+device_id()
    exp=(p.get('expires') or '').strip()
    if exp:
        try:
            if date.today()>date.fromisoformat(exp): return False,'Masa berlaku izin perangkat telah berakhir pada '+exp+'.'
        except Exception: return False,'Tanggal masa berlaku pada file izin tidak valid.'
    return True,''
