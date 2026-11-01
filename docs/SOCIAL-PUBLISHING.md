# Kalender dan publikasi sosial

## Menggunakan kalender

1. Simpan revisi klip lalu ekspor MP4. Pada hasil ekspor, pilih **Jadwalkan**,
   atau buka **Kalender → Tambah jadwal**.
2. Pilih satu platform dan hasil ekspor. Isi judul, caption, tanggal, dan jam.
   Zona waktu default **WITA / Asia-Makassar**; tersedia WIB, WIT, dan UTC.
3. **Simpan draft** dapat dipakai sebelum akun terhubung. Buat satu jadwal per
   platform agar caption, audiens, dan privasinya dapat ditinjau terpisah.
4. Setelah koneksi siap, pilih akun, visibilitas/audiens yang sesuai, periksa
   preview, dan setujui pengiriman sebelum memilih **Jadwalkan publikasi**.
5. Tanggal kalender dapat dipilih untuk melihat status, mengedit, atau membatalkan
   jadwal yang belum mulai dikirim. Hasil yang sudah dikirim tidak dihapus dari
   platform dengan pembatalan lokal.

Jadwal menunjuk **hasil ekspor tertentu**, bukan revisi yang berubah kemudian.
Setelah menyunting klip, ekspor ulang dan pilih file baru bila ingin menerbitkan
hasil edit terbaru. SRT tidak ikut diunggah; subtitle yang dibakar pada MP4 ikut.

Waktu kalender adalah waktu mulai pengiriman. Upload, pemrosesan, dan moderasi
platform memerlukan waktu tambahan. Komputer, koneksi internet, dan Docker
harus aktif. Jadwal terlambat karena komputer mati diproses setelah publisher
kembali berjalan. Tidak ada jaminan tampil tepat pada detik yang dijadwalkan.

## Konfigurasi lokal

Koneksi belum aktif hanya karena fitur sudah diinstal. Tidak ada Client Secret,
access token, atau akun platform bawaan. Isi kredensial **secara lokal** pada
`.env`; jangan mengirimkannya melalui chat atau memasukkannya ke frontend.

Jalankan sekali:

```powershell
& services/backend/.venv/Scripts/python.exe scripts/init_social.py
```

Perintah mempertahankan `SOCIAL_ENCRYPTION_KEY` bila sudah tersedia. Simpan
cadangan `.env` secara privat. Kunci ini mengenkripsi token dan status upload;
menggantinya membuat koneksi yang tersimpan tidak dapat dibaca.

Setelah mengisi konfigurasi, terapkan env baru:

```powershell
& 'G:\Docker\Desktop\resources\bin\docker.exe' compose up -d --no-build api publisher
```

Halaman **Pengaturan → Koneksi akun** menunjukkan kesiapan dan callback URL
untuk setiap platform. Callback harus sama persis dengan yang didaftarkan di
portal developer. Nilainya mengikuti `APP_ORIGIN`.

## YouTube / Shorts

Mulai dari YouTube untuk instalasi localhost ini:

1. Masuk ke [Google Cloud](https://console.cloud.google.com/) dengan akun Google
   yang mengelola channel. Buat project, misalnya `Clipper Lokal`.
2. Buka **API Library**, cari **YouTube Data API v3**, lalu pilih **Enable**.
3. Siapkan layar persetujuan pada Google Auth Platform / OAuth consent screen.
   Isi nama aplikasi dan email kontak. Jika menggunakan mode External / Testing,
   tambahkan email Google pemilik channel sebagai pengguna uji. Email ini boleh
   berbeda dari email login aplikasi Clipper.
4. Di **Clients**, pilih **Create Client → Web application**. Pada **Authorized
   redirect URIs**, tambahkan persis:
   `http://localhost:8080/api/v1/social/oauth/youtube/callback`.
   Gunakan callback yang ditampilkan di Pengaturan bila `APP_ORIGIN` Anda berbeda.
5. Salin Client ID dan Client Secret ke dua variabel berikut dalam
   `G:\onDev\clipper\.env` melalui editor lokal:

   ```dotenv
   YOUTUBE_CLIENT_ID=isi_client_id_dari_google
   YOUTUBE_CLIENT_SECRET=isi_client_secret_dari_google
   ```

   Nilai di atas hanya penanda; gantikan dengan milik Anda. Jangan mengganti
   `SOCIAL_ENCRYPTION_KEY` yang sudah dibuat. Simpan Client Secret saat Google
   menampilkannya; jangan kirim melalui chat.
6. Dari terminal folder `G:\onDev\clipper`, jalankan perintah penerapan env pada
   bagian Konfigurasi lokal di atas. Buka `http://localhost:8080/settings?section=accounts`,
   pilih **Hubungkan YouTube / Shorts**, lalu pilih channel tujuan dan
   berikan izin upload serta pembacaan status/channel yang diminta.
7. Buat jadwal dari hasil ekspor. Untuk pengujian pertama, pilih **Privat**,
   tentukan audiens, dan periksa video sebelum menyetujui pengiriman. Setelah
   status selesai, periksa hasil melalui YouTube Studio.

Pada jadwal, pilih visibilitas dan audiens. Video tidak otomatis dibuat publik
   tanpa pilihan pengguna. YouTube menentukan penggolongan video sebagai Shorts.

Jika muncul `redirect_uri_mismatch`, cocokkan callback hingga port dan path.
Jika akses ditolak saat Testing, pastikan akun Google yang dipilih termasuk
pengguna uji. Token dapat kedaluwarsa/dicabut; hubungkan kembali ketika diminta.

Integrasi memakai OAuth upload + readonly (untuk channel/status), access token
yang dapat diperbarui, upload resumable, lalu pemeriksaan hasil pemrosesan.
Visibilitas aktual yang berbeda dari permintaan ditandai pada status kalender.
Rujukan: [OAuth web server](https://developers.google.com/identity/protocols/oauth2/web-server),
[upload resumable](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol),
[videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert).

## Instagram Reels

Integrasi ini menggunakan **Instagram API with Facebook Login**:

1. Gunakan akun Instagram profesional (Business/Creator) yang terhubung ke
   Facebook Page, lalu buat aplikasi Meta yang sesuai.
2. Siapkan izin `pages_show_list`, `pages_read_engagement`, `instagram_basic`,
   dan `instagram_content_publish`, termasuk akses/review yang diperlukan Meta.
3. Isi `META_CLIENT_ID`, `META_CLIENT_SECRET`, dan `META_GRAPH_VERSION` sesuai
   versi yang didukung aplikasi pada dashboard Meta.
4. Daftarkan callback kalender. Instalasi produksi memerlukan konfigurasi HTTPS
   yang sesuai. Isi `SOCIAL_PUBLIC_BASE_URL` dengan origin HTTPS yang dapat
   dijangkau Meta untuk mengakses route `/api/v1/social/media/*`.
5. Hubungkan akun melalui **Pengaturan → Koneksi akun**; akun profesional yang diotorisasi akan
   tersedia untuk dipilih sebagai tujuan.

Instalasi ini tetap di localhost sampai akses publik dikonfigurasi secara
terpisah. Tidak ada tunnel atau domain publik yang dibuat otomatis. URL localhost
tidak dapat dipakai Meta untuk mengambil video.

Media dibagikan melalui tautan bertanda tangan, berlaku maksimal 24 jam dan
hanya ketika publikasi terkait aktif. Endpoint tidak membuka daftar file/proyek.
Publisher menyiapkan salinan MP4 dengan audio AAC 128 kbps, membuat kontainer
Reel, menunggu pemrosesan, lalu menerbitkannya. Salinan sementara dibersihkan
setelah selesai; penghapusan proyek juga membersihkannya.
Rujukan: [koleksi API resmi Meta](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api).

## TikTok

Kalender TikTok dan adapter Direct Post disediakan, tetapi **Direct Post tidak
aktif secara default**. TikTok mensyaratkan izin dan audit untuk publikasi
publik, dan pedomannya tidak menerima utilitas yang hanya dipakai mengunggah
ke akun sendiri/tim. Jangan menganggap aplikasi lokal pribadi otomatis layak
untuk persetujuan publik. Gunakan draft kalender + unduh MP4 untuk unggah manual
selama jalur API yang sesuai belum tersedia.

Untuk aplikasi yang memenuhi persyaratan TikTok:

1. Siapkan Login Kit dan Content Posting API dengan izin `user.info.basic` dan
   `video.publish`, callback yang terdaftar, serta konfigurasi HTTPS yang diminta.
2. Isi `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`. Aktifkan
   `TIKTOK_DIRECT_POST_ENABLED=true` hanya ketika aplikasi memiliki akses yang
   sesuai, lalu hubungkan akun.
3. Form mengambil info kreator terbaru. Pilih privasi yang benar-benar tersedia;
   tidak ada privasi atau izin interaksi yang dipilih otomatis. Isi disclosure
   komersial/AI bila sesuai dan konfirmasi penggunaan musik sebelum menjadwalkan.

Publisher memeriksa kembali kemampuan akun, mengirim file dalam chunk, lalu
memantau status platform. Konten dari client yang belum diaudit dibatasi oleh
TikTok, termasuk pembatasan visibilitas; aplikasi tidak melewatinya.
Rujukan: [panduan penggunaan dan UX](https://developers.tiktok.com/docs/en/content-sharing-guidelines),
[Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post),
[transfer media](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide).

## Status, kegagalan, dan batas validasi

- **Draft** belum mengizinkan upload. **Terjadwal** diproses setelah waktunya tiba.
- **Mengunggah / Diproses platform** belum berarti konten terlihat publik.
- **Selesai** menunjukkan konfirmasi platform. Visibilitas tetap mengikuti
  pilihan akun dan aturan platform; YouTube privat tetap privat.
- **Gagal** dapat dikembalikan ke draft, diperbaiki, lalu dijadwalkan ulang.
- **Perlu diperiksa** berarti hasil panggilan tidak pasti, misalnya koneksi
  terputus setelah pengiriman. Aplikasi tidak membuat unggahan baru otomatis.
  **Periksa status** hanya memeriksa sesi/referensi yang sama. Jika referensi
  belum diterima, periksa platform secara langsung sebelum membuat jadwal baru.

Token disimpan terenkripsi, OAuth state sekali pakai terikat sesi, akses kalender
dipisahkan per akun, dan log akses menyembunyikan query callback/tautan media.
Pengujian otomatis memakai respons API simulasi dan akun QA lokal. Upload nyata
tidak dapat dinyatakan terverifikasi sebelum kredensial/izin dihubungkan dan
pengguna menjadwalkan konten untuk akun nyata.
