import tkinter as tk
from tkinter import messagebox
from device_license import device_id
code=device_id()
r=tk.Tk(); r.withdraw(); r.clipboard_clear(); r.clipboard_append(code); r.update()
messagebox.showinfo('Kode Perangkat SoundOn','Kirim kode berikut kepada Master:\n\n'+code+'\n\nKode sudah disalin ke clipboard.')
r.destroy()
