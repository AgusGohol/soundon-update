# Catatan pengembang — SoundOn Account Manager

Untuk Claude (atau pengembang lain) yang melanjutkan aplikasi ini di sesi baru.

## Sumber kode
- Kode terbaru = folder `SoundOn_Account_Manager/` di repo `AgusGohol/soundon-update`
  (sejak 3.16.1). Sebelumnya hanya ada di ZIP rilis:
  `https://github.com/AgusGohol/soundon-update/releases/latest/download/manifest.json`
  → `zip_name` → `https://github.com/AgusGohol/soundon-update/releases/download/<tag>/<zip_name>`
- Aplikasi Python/Tkinter + Playwright, Windows.
- Bahasa antarmuka & catatan: Bahasa Indonesia. Pengguna: Agus (admin), ±66 akun SoundOn.

## Merilis versi baru
1. Ubah versi di 3 tempat: `APP_VERSION` di `soundon_dashboard.py`, judul Studio di
   `upload_manager.py` (`SoundOn x.y.z — Studio unggah`), baris pertama `README.txt`.
2. Tambah entri di `docs/Riwayat_Perbaikan.txt` dengan format `x.y.z: Judul singkat.` lalu poin-poin.
   Judul itu otomatis jadi catatan di jendela pembaruan.
3. Cek lokal: `python tools/buat_rilis.py` → `dist/SoundOn_Update_x.y.z.zip` + `dist/manifest.json`
   (folder `dist/` tidak di-commit).
4. Commit lalu push. Workflow `.github/workflows/rilis.yml` (push ke `main` atau `claude/**`) membuat
   paket dengan `tools/buat_rilis.py` dan menerbitkan rilis **Latest** `vx.y.z` berisi ZIP +
   `manifest.json`, hanya bila tag itu belum ada. Tidak perlu token di sesi. Cara cadangan:
   - `gh release create vx.y.z dist/SoundOn_Update_x.y.z.zip dist/manifest.json --repo AgusGohol/soundon-update --latest --title "SoundOn x.y.z" --notes "<judul>"`
   - atau `python tools/terbitkan_rilis.py` (token di `~/.soundon_github_token`)
   - atau taruh kedua file di `%USERPROFILE%\SoundOnRilis\masuk` di komputer admin (Penerbit otomatis).
5. Cek: `.../releases/latest/download/manifest.json` menunjukkan versi baru. Semua klien memasang
   otomatis saat dibuka atau ≤20 menit bila sedang terbuka.

## Aturan yang tidak boleh dilanggar
- Updater tidak pernah menimpa `soundon.license`, `update_config.json`, atau folder data
  `~/SoundOnAccounts` (akun, profil Chrome, laporan). Jangan masukkan file itu ke ZIP.
- Isi ZIP hanya *.py, *.bat, *.txt, *.csv, *.json, *.md di akar, `docs/`, atau `tools/`.
- Bot unggah berhenti di halaman Review dan TIDAK PERNAH menekan Submit.
- Sinkron hanya membaca halaman SoundOn yang tampil (tanpa API privat, tanpa mengubah apa pun).
- Thread latar tidak menyentuh Tk langsung — pakai `ui_call(fn)`.
- Hanya halaman aktif yang hidup (batas handle Windows); halaman lain dihancurkan saat pindah menu.

## Berkas utama
- `soundon_dashboard.py` — aplikasi utama (Dashboard, Daftar Akun, Analytics, Penghasilan,
  Inventaris HP, Pengaturan), sinkron otomatis, pembaruan berkala, Penerbit otomatis.
- `auto_sync.py` — sinkron Streams/Pendengar/Saldo/Asal Streams lewat Chrome (CDP, port 20000+id).
- `updater.py` — pembaruan dari GitHub Releases (SHA-256, cadangan, exit code 75).
- `release_publisher.py`, `tools/buat_rilis.py`, `tools/terbitkan_rilis.py` — rilis.
- `upload_manager.py` — Studio unggah. `account_table.py`, `date_picker.py`, `ui_theme.py` — UI.
