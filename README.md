# Clipper

Workspace editorial berbahasa Indonesia untuk mengunggah MP4 atau mengimpor URL video publik, membuat klip
manual atau kandidat dari transkrip, memperbaiki subtitle, dan mengekspor video
vertikal. Nuxt/Vue/TypeScript + Tailwind CSS v4/Lucide, FastAPI, PostgreSQL,
Celery/Redis, FFmpeg, faster-whisper lokal, dan DeepSeek.

Status implementasi dan bukti yang **sudah** diuji ada di
[docs/PROGRESS.md](docs/PROGRESS.md). Ini bukan klaim production-ready. Tidak ada
akun bawaan, data demo pada aplikasi, atau fallback AI palsu.

## Kandidat konten game

Pada **Buat kandidat → Jenis konten**, pilih **Game / gameplay**. Profil ini
memilih momen utuh: ucapan lucu streamer, punchline, karakter mati, gagal lucu,
clutch/comeback dan pertarungan bos. Hook harus memiliki kutipan yang cocok
dengan segmen transkrip; payoff yang jelas dan hook yang cepat lebih diutamakan
daripada label jenis kejadian. Komedi saat menu/story tetap bisa menjadi hook.
Kandidat cerita biasa disaring dan hook duplikat digabung.
Durasi mengikuti minimum/maksimum yang dipilih dan hasil boleh lebih sedikit.

Aktifkan **Analisis frame video dengan AI** untuk mengirim sampel gambar ke
DeepSeek melalui koneksi API yang sudah dikonfigurasi. Dibutuhkan model dengan
dukungan gambar (misalnya `deepseek-flash`). Maksimal 360 frame per proses,
berjarak sekitar 5 detik atau lebih untuk video panjang, dibaca dalam kelompok
12 gambar. Waktu frame berasal dari video; model hanya mengembalikan ID frame
sebagai bukti. Pemeriksaan ini juga dapat menghasilkan kandidat dari video
tanpa ucapan. Rentang klip visual dibuat otomatis di sekitar kejadian dan perlu
ditinjau; sampling dapat melewatkan kejadian singkat. Suara game belum dianalisis.
Pengiriman frame memakai kuota AI tambahan, dan gambar sementara dibersihkan
setelah proses. Profil Umum / percakapan tetap tersedia.

Kandidat visual yang belum memiliki subtitle diperiksa lagi melalui audio
rentang klip dengan Whisper lokal. Pemeriksaan membandingkan audio asli dan
salinan dengan normalisasi ucapan untuk membantu suara streamer yang tertutup
efek pertarungan. Hasil bertimestamp valid digabung tanpa menduplikasi ucapan;
audio video yang ditonton/diekspor tetap asli. Untuk kandidat lama yang kosong, buka editor
lalu pilih **Buat subtitle dari audio**. Simpan perubahan terlebih dahulu;
hasil disimpan sebagai revisi baru dan tidak menimpa edit yang lebih baru.
Bahasa otomatis mengikuti transkrip video bila tersedia. Musik/efek pertarungan
tanpa ucapan yang dikenali dapat tetap menghasilkan subtitle kosong; deskripsi
aksi dari frame tidak dijadikan dialog. Hasil pengenalan tetap perlu ditinjau.
`WHISPER_SUBTITLE_MODEL` dapat mengganti model khusus pemeriksaan klip; jika
kosong, sistem memakai `WHISPER_MODEL`. Versi algoritma dan konfigurasi model
menjadi bagian identitas pekerjaan, sehingga hasil kosong dari konfigurasi lama
tidak menghalangi percobaan dengan konfigurasi baru.

Pembuatan subtitle klip memakai decoding berurutan (`batch_size=1`) pada GPU
maupun CPU, dengan konteks dua detik sebelum dan sesudah rentang klip. Ini
menghindari hilangnya satu blok 30 detik ketika hasil batch memiliki satu kata
yang gagal disejajarkan. Timestamp keluaran tetap dibatasi rentang klip dan
filter ucapan yang tidak meyakinkan tetap berlaku. Versi pemulihan subtitle
adalah `clip-speech-v4`; hasil lama perlu dibuat ulang melalui **Dari audio**.
Transkripsi video penuh tetap mengikuti konfigurasi batch server.

## Terjemahan subtitle Inggris ke Indonesia

Di editor klip, panel **Subtitle** atau **Timeline**, pilih **Terjemahkan**
lalu **Mulai terjemahkan**. Jika subtitle belum ada, gunakan **Dari audio**
dengan bahasa **English** dahulu. Simpan edit sebelum memulai terjemahan.
DeepSeek menerjemahkan teks dari revisi tersimpan; waktu setiap cue, batas
klip, transkrip sumber dan audio asli dipertahankan. Fitur ini tidak melakukan dubbing.

Tinjau teks Inggris dan Indonesia, pilih **Terapkan terjemahan ke draft**,
koreksi bila perlu, lalu **Simpan** dan ekspor MP4/SRT. Hasil AI tidak langsung
menimpa subtitle tersimpan. Usulan dari revisi lama atau ketika draft masih
berubah tidak bisa diterapkan. Subtitle terjemahan memakai mode kalimat;
template Podcast dialihkan ke Minimal karena timestamp kata sumber berbahasa
Inggris tidak berlaku untuk urutan kata Indonesia. Gaya lain tetap dipertahankan.

Memakai konfigurasi DeepSeek yang sudah ada dan kuota API penyedia. Proses
berjalan di antrean ringan, mendukung batal/coba lagi, dan mencatat penggunaan
AI per kelompok cue. Teks dibatasi 100.000 karakter per permintaan. Pemeriksaan:
`test_subtitle_translation.py`, `test_subtitle_translation_api.py`, dan
`subtitle-translation.spec.ts`.

## Efek subtitle

Jika muncul peringatan teks terlalu panjang, pilih **Sesuaikan subtitle** pada
panel Subtitle, Gaya subtitle, atau dialog ekspor. Tinjau usulan lalu pilih
**Terapkan penyesuaian** dan **Simpan**. Ukuran otomatis diaktifkan; cue yang
masih tidak muat dipecah tanpa membuang teks. Pemisahan memakai timing kata
asli jika cocok. Untuk terjemahan atau teks manual tanpa timing kata, batas
bagian diperkirakan dalam rentang cue asal dan perlu ditinjau di timeline.
Timing perkiraan tidak dipakai untuk highlight Podcast; gunakan mode kalimat.

Di editor klip, buka **Tampilan → Gaya subtitle**. Preset **Sinematik** memakai
fade halus, **Gaming impact** memakai teks tebal dengan pop masuk, dan
**Komedi pop** memakai teks pink dengan gerak geser. Pada **Warna & efek**,
ubah animasi serta durasinya (100–500 ms), warna, outline, bayangan dan kapital.
Mode kalimat atau kata per kata tetap dapat dipilih; kata per kata memerlukan
timestamp ucapan yang tersedia. Simpan revisi lalu ekspor MP4 untuk menerapkan
efek. File SRT tetap berisi teks/waktu tanpa animasi.

### Remotion

Pada **Tampilan → Gaya subtitle → Renderer**, pilih **Remotion**, lalu template
**Minimal**, **Gaming Punch**, atau **Sinematik**. Minimal mengikuti pengaturan
animasi dasar; Gaming Punch memakai gerak masuk spring; Sinematik memakai
fade dan gerak halus. Warna, font, outline, posisi, serta mode kalimat/kata tetap
mengikuti gaya subtitle. Simpan perubahan sebelum mengekspor.

Preview dan ekspor memakai komposisi React yang sama di `services/remotion`.
FFmpeg menyiapkan framing, trim, dan audio; Remotion merender animasi subtitle,
judul pembuka/penutup, transisi, dan zoom di atas video tersebut. Audio asli lalu
digabung kembali tanpa enkode ulang.
Pilihan **Standar** tetap memakai FFmpeg dan menjadi default klip lama.
Efek intro/outro memakai awal/akhir rentang klip yang ada, sehingga durasi dan
audio tidak bertambah. Zoom memakai waktu relatif terhadap klip, dengan pusat
dan kekuatan yang dapat diatur. Transisi masuk/keluar memengaruhi gambar video.
Atur semuanya melalui **Tampilan → Efek video**. Buka tab **Timeline** untuk
menggeser atau mengubah durasi subtitle/zoom, menyunting teks, dan mengubah
batas video. Tombol panah menggeser blok 0,1 detik (Shift: 1 detik); kolom angka
tersedia untuk waktu yang presisi. Setelah trim, zoom tetap mengikuti momen
sumber yang sama; bagian di luar rentang baru dilepas.
Timeline digunakan untuk mengatur klip yang sedang diedit, subtitle, dan efek;
penggabungan beberapa klip/proyek menjadi satu video belum tersedia.
Ekspor Remotion memerlukan proses render tambahan.

Docker build menyertakan bundle preview, komposisi, font, dan Chrome Headless
Shell. Tidak ada unduhan browser atau panggilan AI ketika ekspor Remotion berjalan.
Untuk pengembangan native, jalankan dari root repository:

```sh
npm --prefix services/remotion ci
npm --prefix services/remotion run build
npm --prefix services/remotion run browser:install
```

Salin `services/remotion/dist/player.js` ke `apps/web/public/remotion/player.js`
sebelum menjalankan Nuxt. Arahkan `REMOTION_SCRIPT_PATH` ke path absolut
`services/remotion/render.mjs`; `REMOTION_NODE_PATH` dapat diatur jika Node tidak
ada pada PATH. Set `REMOTION_BROWSER_EXECUTABLE` ke executable Chrome Headless
Shell hasil instalasi di `services/remotion/node_modules/.remotion`.
Ulangi build dan salin bundle serta `dist/THIRD-PARTY-NOTICES.txt` ketika komposisi berubah.
Remotion memiliki ketentuan lisensi tersendiri; lihat
[lisensi resmi Remotion](https://www.remotion.pro/license) untuk penggunaan tim.

## Thumbnail dari video

Di halaman proyek, pilih **Buat thumbnail** di bawah video sumber, atau **Thumbnail**
pada hasil ekspor. Pilih waktu/frame, edit judul, gaya, posisi dan ukuran teks,
lalu pilih **Unduh JPG**. Format tersedia: YouTube 1280 × 720, vertikal 720 × 1280,
dan persegi 1080 × 1080. Opsi **Tampilkan seluruh frame** mempertahankan seluruh
gambar dengan latar gelap; tanpa opsi itu, gambar dipotong dari tengah.

Preview dan JPG dibuat di browser dari video yang dapat diputar. Hasil diunduh
ke perangkat, belum disimpan sebagai aset proyek. Tidak memerlukan API AI.
Teks panjang otomatis dibungkus dan diperkecil agar tetap berada dalam gambar.
Preset **Pop 3D**, **Gradasi**, dan **Neon** menyediakan efek teks dengan empat
palet warna. Pilih font Display tebal atau Modern, serta opsi huruf kapital.
Gaya klasik kuning, putih, dan panel gelap tetap tersedia. Semua efek ikut
dirender ke JPG yang diunduh.

## Menjalankan dengan Docker Compose

Prasyarat: Docker Engine/Desktop dengan Linux containers dan Compose v2, Python
3.10+ untuk generator `.env`, koneksi internet saat mengunduh image/dependensi
dan model pertama kali. Seluruh layanan aplikasi hanya dipublikasikan melalui
`127.0.0.1:8080`; PostgreSQL/Redis tidak dipublikasikan ke host.

Jalankan dari root repository:

```sh
python scripts/init_env.py
docker compose build
docker compose up -d postgres redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.cli create-user
docker compose run --rm api python -m app.cli download-model
docker compose up -d
```

Buka **http://localhost:8080**. CLI meminta email dan password minimal 12 karakter
secara interaktif. Tidak ada registrasi publik. `download-model` menggunakan
Whisper multilingual `small`, CPU/int8 dan menyimpan cache di named volume;
langkah ini dapat dilewati bila hanya menggunakan klip manual. Menjalankan
migrasi berulang aman. Backup dahulu sebelum migrasi pada instalasi berisi data.

`.env` dibuat dengan password PostgreSQL acak dan tidak ditimpa bila sudah ada.
Jangan menggunakan placeholder `.env.example` sebagai password. Jika port
berubah, sesuaikan `APP_PORT` **dan** `APP_ORIGIN` agar CSRF tetap cocok. Jika
dipasang di balik HTTPS, gunakan origin HTTPS dan `COOKIE_SECURE=true`.

### Instalasi Windows lokal dengan data di drive E:

Image, volume database/media/model dan disk WSL berada di `E:\Docker\wsl`;
swap WSL juga diarahkan ke sana melalui `%USERPROFILE%\.wslconfig`.
Cadangan disk sebelum pemindahan disimpan di
`E:\Docker\migration-backup\wsl-before-20261102`.
Docker Desktop masih terdaftar di `C:\Program Files\Docker\Docker`.
Salinan file aplikasi di `E:\Docker\Desktop` sudah diverifikasi, tetapi belum
diaktifkan karena Windows menolak penggantian folder instalasi asal.
Konfigurasi/log kecil tetap mengikuti direktori profil Windows.
Jangan memindahkan atau menghapus file VHDX saat aktif.

Instalasi lokal ini memakai **http://localhost:8081** karena port 8080 digunakan
Apache Laragon. `.env` menetapkan `APP_PORT=8081` dan
`APP_ORIGIN=http://localhost:8081`; contoh instalasi baru tetap memakai 8080.

Paket `services/backend/app/media` dibangun kembali untuk validasi/preview video,
render MP4/SRT, layout gaming, pelacakan wajah/pembicara, dan impor URL publik.
`.gitignore` hanya mengabaikan `/media/` di root agar source paket ikut Git.
Database sudah dimigrasikan, akun lokal sudah dibuat, dan model Whisper `small`
sudah tersedia di cache. Setelah mengubah kode backend, bangun ulang image
dengan `docker compose build api`, lalu jalankan `docker compose up -d`.

Setelah restart Windows, buka Docker Desktop, lalu jalankan `docker compose up -d`
dari repository ini. Terminal yang sudah terbuka sebelum instalasi perlu dibuka
ulang agar PATH baru terbaca. Kredensial bootstrap lokal tersedia di
`.runtime/admin-login.txt` (diabaikan Git); gunakan CLI `reset-password` untuk
mengganti kata sandi. Rekomendasi DeepSeek memerlukan key sendiri di `.env`.

Untuk rekomendasi, isi `DEEPSEEK_API_KEY` di `.env` backend secara lokal lalu
recreate layanan backend:

```sh
docker compose up -d --force-recreate api worker-heavy worker-light dispatcher scheduler
```

Model default `deepseek-flash` diverifikasi dari
[dokumentasi DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) pada
1 November 2026. Model dan base URL dapat diubah. Tanpa key, upload, transkripsi,
klip manual, dan render tetap tersedia; analisis menampilkan error konfigurasi.
Jangan menaruh key di frontend, source code, atau chat. Biaya ditampilkan sebagai
token karena tarif uang belum dikonfigurasi.

## Menggunakan workspace

Story Studio tersedia di `/studio`: masukkan naskah atau tabel storyboard, susun
adegan dengan DeepSeek, lalu buka **Produksi** untuk membuat gambar, suara narator,
dan subtitle dari audio. Tinjau usulan, terapkan ke draft, simpan, lalu ekspor
MP4/SRT. Media yang sudah dipilih tetap dipakai; penggantian dilakukan per adegan.
Subtitle bertimestamp dapat diedit, dan durasi produksi diperpanjang bila diperlukan
agar ucapan selesai, dalam batas 30 detik per adegan dan 3 menit per video.

Gambar dan suara kini mengutamakan model lokal, tanpa biaya API: Stable Diffusion
untuk gambar, penerjemah arahan Indonesia–Inggris lokal, dan Pocket TTS untuk dua
suara Indonesia. Pilihan suara dasar Inggris memakai eSpeak NG. Jalankan
`powershell -File scripts/setup_story_local.ps1` untuk memasang model dan runtime
Docker GPU. Model tersimpan di `.runtime/story-models`, bukan di image atau Git.
Tidak ada fallback otomatis ke cloud. DeepSeek tetap opsional untuk tombol naskah
dan gaya AI; impor tabel/paragraf dapat dipakai tanpa AI berbayar. Konfigurasi,
batas kualitas, lisensi model dan pilihan cloud ada di
[panduan Story Studio](services/remotion/STORYBOARD.md).

Publikasi dan kalender tersedia melalui **Kalender** atau **Jadwalkan** pada hasil
ekspor. Koneksi YouTube, Instagram, dan TikTok dikelola melalui **Pengaturan →
Koneksi akun**. Draft mendukung ketiga platform; pengiriman otomatis memerlukan
koneksi OAuth dan kesiapan API masing-masing platform. Ikuti
[panduan koneksi dan kalender](docs/SOCIAL-PUBLISHING.md). TikTok memiliki batasan
audit/penggunaan untuk aplikasi lokal pribadi; kalender tidak melewati aturan itu.

Pada **Pengaturan → Batas pemrosesan**, ubah batas durasi sumber (1–720 menit),
ukuran file (hingga 64 GiB), dan durasi maksimum klip (5–600 detik). Default
instalasi tetap 60 menit, 2 GiB, dan 180 detik. Pengaturan disimpan per akun dan
berlaku untuk upload maupun impor URL. Job menyimpan batas saat dibuat;
percobaan ulang memakai batas terbaru. Menurunkan batas tidak menghapus klip lama.

Workspace mengikuti tinggi layar. Kontrol preview, trim, simpan, dan ekspor
tetap terlihat; daftar klip, transkrip, dan ekspor panjang bergulir di panelnya.
Di ponsel, gunakan tab **Preview / Alat editor**. Pengaturan tampilan dibagi
menjadi **Framing / Gaya subtitle**; gaming memiliki **Area sumber / Susunan panel**.

1. Masuk, buat proyek, lalu pilih **File perangkat** atau **URL video**.
   Untuk URL, masukkan tautan satu video publik dan pilih **Impor video**.
   Tunggu unduhan dan validasi selesai; setelah masuk antrean, halaman boleh ditutup.
2. Untuk alur tanpa AI, pilih **Klip manual**, tentukan durasi (default 5–180 detik), lalu
   edit subtitle sendiri. Untuk transkripsi, pilih bahasa dan **Transkripsi
   saja**; **Buat kandidat** menjalankan transkripsi lalu analisis jika perlu.
3. Di editor, ubah trim, crop/letterbox, dan cue. Pada tab **Tampilan**, pilih
   **Pelacakan frame → Ikuti wajah** atau **Ikuti pembicara (perkiraan)** untuk
   crop bergerak. Klik **Analisis preview**, tunggu selesai, lalu putar atau geser
   video untuk memeriksa gerakan sebelum ekspor. Analisis bisa memakai draft
   yang belum disimpan; **Simpan** tetap menghasilkan revisi baru.
4. Ekspor revisi tersimpan ke 720×1280 atau 1080×1920. Hasil lama tetap tersedia.
   Tab Ekspor menyediakan MP4, SRT, serta preview render final.
5. Hapus proyek melalui dialog bernama. Akses dicabut segera; worker membatalkan
   pemrosesan aktif lalu membersihkan file dan teks proyek.

Impor URL memakai `yt-dlp` dan mendukung MP4 langsung, YouTube, serta situs
yang didukung extractor seperti TikTok dan Instagram. Dukungan bukan jaminan
setiap URL dapat diunduh: sumber dapat membatasi akses berdasarkan login, lokasi,
anti-bot, atau format. Video privat, DRM, playlist/profil dan siaran langsung
tidak didukung. Tidak ada pengambilan cookie browser. Gunakan video yang Anda
miliki atau boleh gunakan. Batas default tetap 2 GiB, 60 menit dan 3840×2160;
unduhan secara default dibatasi hingga 1080p jika tersedia (`IMPORT_MAX_HEIGHT`).
H.264 diprioritaskan pada tingkat resolusi yang sama untuk mengurangi waktu
decode dan kebutuhan preview tambahan. Sumber tetap divalidasi penuh; bila
perlu preview, validasi decode dilakukan sekaligus dengan pembuatan preview.
Untuk mempertahankan lebih banyak detail dari sumber 4K, ubah
`IMPORT_MAX_HEIGHT=2160`; unduhan dan pemrosesan akan membutuhkan lebih banyak
waktu serta ruang. Perubahan ini berlaku pada impor baru.

URL hanya menerima HTTP/HTTPS publik pada port80/443. Resolver dan koneksi
unduhan memblokir IP lokal/private termasuk redirect dan DNS rebinding.
FFmpeg dibatasi pada file hasil unduhan lokal; proses downloader tidak menerima
API key atau kredensial database. URL dengan query token tidak ditampilkan di
respons job/log aplikasi dan dihapus dari data job ketika proyek dihapus.
Unduhan gagal/dibatalkan dibersihkan dan dapat dicoba lagi melalui kartu pekerjaan.
Docker menyertakan FFmpeg, Node dan EJS dari lockfile. Modul impor yang dibangun
kembali memakai FFmpeg melalui path absolut dan menerapkan opsi input lokal
pada merger/fixup yt-dlp. Runtime JavaScript eksternal belum diaktifkan kembali;
video YouTube yang mewajibkan challenge tersebut masih dapat gagal diimpor.

Render menggunakan video asli dan decode/re-encode. Preview CSS mendekati crop
dan subtitle; file hasil render adalah acuan font wrapping dan timing.
Preview editor mengikuti jalur pelacakan setelah **Analisis preview** selesai,
termasuk saat pause/seek. Analisis hanya memindai durasi klip terpilih. **Ikuti
wajah** mempertahankan satu wajah selama masih terlihat. **Ikuti pembicara
(perkiraan)** memakai YuNet dan model audiovisual Light-ASD lokal untuk menilai
kecocokan audio dengan urutan gambar setiap wajah, lalu berpindah ketika bukti
cukup konsisten. Ini bukan identifikasi orang atau diarization suara. Ucapan
tumpang tindih, wajah kecil/tertutup, audio tidak sinkron, atau pembicara di luar
frame dapat membuat pilihan keliru; periksa preview dan hasil final.
Jika tidak ada wajah, posisi manual digunakan dan alasannya ditampilkan.
Kegagalan model/proses pada analisis preview ditampilkan sebagai pekerjaan gagal
yang dapat dicoba lagi; render yang memakai fallback menyebutkan alasannya.
Jika sumber, batas klip,
mode atau posisi cadangan berubah, analisis lama tidak dipakai untuk draft itu;
jalankan **Analisis preview** lagi. Perubahan judul/subtitle tidak membatalkan
analisis. Jalur yang sesuai disimpan dan dipakai ulang saat ekspor, sehingga
tidak perlu memindai wajah lagi. Klip lama tetap manual sampai opsi pelacakan
dipilih; preview tidak membuat revisi ataupun MP4 baru. Perubahan model atau
algoritma juga mengganti signature analisis agar jalur lama tidak dipakai sebagai
hasil versi baru. Riwayat ekspor lama tetap tersedia dengan metadata aslinya.
Model wajah dan pembicara dibundel; inferensi menggunakan ONNX Runtime CPU,
tanpa Torch atau panggilan API untuk audio/video. Lisensi MIT, provenance,
checksum dan cara mereproduksi ekspor model dijelaskan di
[dokumentasi model](services/backend/models/README.md).
Subtitle berasal dari ucapan/cue yang disunting, bukan ringkasan judul AI.
Di **Tampilan → Gaya subtitle**, tersedia preset Klasik, Bold putih, Kuning,
Neon, Kotak pop, dan Minimal, serta warna teks/latar/outline, ketebalan outline,
bayangan, tebal, miring, dan kapital. Ini preset statis bergaya editor video;
belum ada animasi atau highlight kata per kata. Gaya berlaku pada preview dan
MP4 burn-in; teks SRT tetap asli.

Pada **Teks muncul**, pilih **Kata per kata mengikuti suara** untuk menampilkan
kata hanya selama timestamp ucapannya, termasuk jeda tanpa teks. Mode ini
memakai timestamp kata pada versi transkrip yang terhubung ke klip, berlaku
pada preview dan ekspor. Token ASR yang membentuk satu kata digabung berdasarkan
teks yang cocok. Jika timestamp tidak tersedia, berdurasi nol, atau teks telah
diubah sehingga tidak cocok, cue ditandai dan ekspor mode ini ditolak; pilih
**Kalimat lengkap** atau gunakan teks transkrip yang cocok. Timing tidak ditebak
dengan membagi rata durasi kalimat. SRT tetap berisi cue lengkap.

Menggeser ukuran teks menonaktifkan pengecilan otomatis: ukuran yang dipilih
benar-benar dipakai, dengan pembungkusan maksimal empat baris. Aktifkan
**Kecilkan otomatis agar muat dua baris** untuk perilaku sebelumnya; ukuran
efektif cue ditampilkan. Cue terlalu panjang ditolak saat ekspor dengan pesan
untuk memecah atau memendekkan teks. Draft koreksi tetap
tersimpan. Pemecahan otomatis transkrip hanya memakai word timestamps yang
tersedia, tanpa mengarang waktu kata.
Resize tidak meningkatkan detail sumber. CPU-only tidak menjanjikan kecepatan
tertentu; catat hasil benchmark pada perangkat yang akan dipakai.

### Klip gaming dengan facecam

Untuk video yang sudah memuat facecam dan gameplay dalam satu sumber, buka
editor klip lalu pilih **Tampilan → Mode video → Gaming (facecam + gameplay)**.
Pilih **Area facecam**, gunakan preset sudut lalu geser/ubah ukuran kotak agar
sesuai webcam kreator. **Area gameplay** dapat memakai seluruh video atau area
yang dipilih. Kotak juga dapat diatur melalui angka persentase dan keyboard.

Facecam ditampilkan di atas, gameplay di bawah. Tinggi panel facecam dapat
diatur 15–45%. Gameplay memakai **Tampilkan seluruh area** secara default untuk
mempertahankan HUD dan konteks; **Isi panel (crop)** memperbesar gambar dengan
memotong tepinya. Preview langsung berubah saat mengatur area, pause, atau seek,
tanpa pekerjaan analisis baru. Kedua panel berasal dari satu pemutar, sehingga
audio dan waktu tetap sinkron. Simpan pengaturan sebelum ekspor.

Ini adalah layout untuk sumber yang sudah digabung, bukan penggabungan dua file
terpisah atau deteksi otomatis momen intens dalam game. Pemilihan klip AI masih
berdasarkan transkrip; batas klip dapat disunting manual. Facecam asli mungkin
tetap terlihat di area gameplay, dan gambar permainan yang sudah tertutup
facecam pada sumber tidak tersedia untuk dipulihkan melalui crop.

### Akselerasi transkripsi NVIDIA

GPU NVIDIA yang dapat diakses Docker/WSL2 bisa memakai worker CUDA terpisah:

```sh
docker compose -f compose.yml -f compose.gpu.yml build
docker compose -f compose.yml -f compose.gpu.yml up -d
```

Image GPU menyertakan CUDA 12/cuDNN 9 untuk faster-whisper. Mode `auto` memilih
CUDA/float16 dengan batch 8; bila gagal, worker mencoba CPU/int8 satu kali dan
mencatat alasan serta perangkat yang benar-benar digunakan pada metadata job.
Model tetap `small` multilingual dan beam 5. Hanya satu pekerjaan berat berjalan
sekaligus untuk menjaga penggunaan VRAM. Override GPU memberi worker 4 inti CPU.
Instalasi CPU dapat tetap memakai `compose.yml` saja.

Instalasi Windows lokal saat ini memakai CPU dengan `compose.yml` saja.
Override GPU di atas digunakan pada host dengan NVIDIA/CUDA yang tersedia
untuk Docker. File dan cache Docker lokal berada di drive E:.

## Perintah pemeliharaan

```sh
docker compose logs --tail=100 api worker-heavy worker-light dispatcher scheduler
docker compose run --rm api python -m app.cli reset-password --email editor@example.com
docker compose stop
docker compose up -d
```

Reset password mencabut sesi lama. `stop` mempertahankan volume. Jangan menjalankan
`docker compose down -v` kecuali memang bermaksud menghapus seluruh database,
video, dan model cache. Backup pemulihan harus mencakup database **dan** volume
media yang konsisten; cache model dapat diunduh ulang.

Antrean dan lease disimpan di PostgreSQL. Dispatcher mengirim transactional
outbox; scheduler memulihkan lease kedaluwarsa dan pengiriman broker yang hilang.
Heavy worker menggunakan concurrency/prefetch 1. Timeout, lease, batas upaya,
upload, disk reserve, serta TTL ada di `.env.example`. Pembatalan subprocess
bersifat kooperatif: heartbeat default 15 detik, polling proses 0,2 detik, lalu
SIGTERM dan SIGKILL setelah grace 3 detik jika diperlukan. Request provider
yang sedang berjalan dapat menunggu timeout dan tetap dikenai biaya.

Upload terputus diulang dari awal. Upload yang proses API-nya mati dipulihkan
oleh cleanup setelah TTL 24 jam. Scratch attempt terminal dibersihkan setelah
24 jam, sumber/hasil resmi tidak dihapus otomatis. Bila disk hampir penuh,
hapus proyek yang tidak dibutuhkan melalui aplikasi atau tambah ruang.

## Pengembangan dan pengujian

Backend memerlukan Python 3.11–3.13; local QA menggunakan Python 3.12. Frontend
dipin ke Node 24.15.0 untuk build. Dependency lengkap tersimpan di
`services/backend/uv.lock` dan `apps/web/package-lock.json`.

```sh
cd services/backend
uv sync --frozen --extra transcription
uv run --extra transcription pytest ../../tests -q
cd ../../apps/web
npm ci
npm run typecheck
npm run build
```

Tes media membutuhkan FFmpeg + FFprobe dengan libx264/libass pada PATH, atau
variabel `FFMPEG_PATH`/`FFPROBE_PATH`. Tes default menggunakan database SQLite
terisolasi. Untuk menguji locking PostgreSQL, buat database uji yang namanya
berakhir `_test`, lalu set `CLIPPER_TEST_DATABASE_URL`; suite menolak URL lain.
Jangan arahkan pengujian ke database produksi. Semua provider terkontrol hanya
berada pada test suite; konfigurasi normal tidak mengganti provider dengan mock.

Jika menjalankan backend langsung tanpa Docker, set `DATABASE_URL`, `REDIS_URL`,
`MEDIA_ROOT`, `WHISPER_DOWNLOAD_ROOT`, dan `SUBTITLE_FONT_PATH` ke lokasi lokal.
Default `/data/...` dan `/app/fonts/...` ditujukan untuk container. Untuk font,
gunakan path absolut `services/backend/fonts/NotoSans-Regular.ttf`. Jalankan
API dari `services/backend` agar modul `app` dan `alembic.ini` ditemukan.
Untuk pelacakan di luar Docker, arahkan `TRACKING_MODEL_PATH` ke file
`services/backend/models/face_detection_yunet_2023mar.onnx` dan
`SPEAKER_MODEL_PATH` ke `services/backend/models/light_asd_talkset.onnx`
yang dibundel. Gunakan path absolut untuk keduanya.
Nuxt development memakai `http://localhost:3000` dan proxy API lokal port8000;
sesuaikan `APP_ORIGIN=http://localhost:3000` pada backend. Development server
sendiri tidak menjalankan dispatcher, scheduler, atau Celery worker.

`redis==6.4.0` dan `av==16.1.0` sengaja dipin karena perubahan protokol default
Redis client dan signature PyAV versi lebih baru tidak kompatibel dengan jalur
Kombu/faster-whisper yang digunakan. Upgrade dependensi memerlukan uji antrean
dan decode audio, bukan hanya keberhasilan instalasi.

Smoke HTTP memakai layanan API, dispatcher, broker, worker, dan database yang
benar-benar berjalan. Setelah membuat akun uji khusus:

```sh
python scripts/make_fixture.py
# Set CLIPPER_SMOKE_EMAIL dan CLIPPER_SMOKE_PASSWORD lewat environment lokal.
# Opsional: CLIPPER_SMOKE_URL, default http://localhost:8080.
cd services/backend
uv run python ../../scripts/smoke_api.py
```

Smoke membuat proyek pola sintetis, mempertahankannya untuk review, dan menulis
`.artifacts/acceptance.mp4`, `.artifacts/acceptance.srt`, serta laporan JSON.
File tersebut diabaikan Git. Fixture tidak menggunakan video pribadi. Pengujian
UI/browser dan pilot berbeda dari smoke API; lihat progres untuk batas aktual.

Smoke transkripsi audio nyata menggunakan MP4 pendek milik Anda/berizin (5–180
detik), environment akun smoke yang sama, dan model yang sudah di-cache:

```sh
cd services/backend
uv run --extra transcription python ../../scripts/smoke_transcription.py /path/speech.mp4 --language id
```

Suite browser membutuhkan server web/API/worker yang aktif dan hasil smoke
API `.artifacts/smoke-report.json`:

```sh
cd tests/e2e
npm ci
npx playwright install chromium
# Set CLIPPER_E2E_EMAIL, CLIPPER_E2E_PASSWORD untuk akun uji yang sama.
# CLIPPER_E2E_URL=http://localhost:8080 untuk Compose, default localhost:3000.
npm test
```

Dua tes empty-state memerlukan akun uji kedua tanpa proyek melalui CLI, dengan
`CLIPPER_E2E_EMPTY_EMAIL` dan `CLIPPER_E2E_EMPTY_PASSWORD`; tanpa keduanya tes
tersebut ditandai skip. Suite utama menciptakan proyek/klip uji dan tidak memakai
provider palsu. Screenshot disimpan di `.artifacts/ui/` untuk review manual.

## Privasi dan batas MVP

Transkripsi berlangsung di server instalasi ini. Rekomendasi mengirim teks dan
ID segmen ke DeepSeek, bukan audio/video. Kebijakan retensi provider berlaku
untuk teks yang sudah dikirim; penghapusan proyek lokal tidak menjamin penghapusan
di provider. Semua media privat dan download memeriksa sesi serta ownership.

Satu instalasi/satu host dengan shared volume. Pelacakan wajah/pembicara lokal
dan impor URL tersedia sebagai perluasan setelah PRD awal. Tidak ada
diarization suara, subtitle karaoke, posting sosial, billing, atau S3.
Tidak ada skor atau janji viral. Kualitas editorial dan koreksi subtitle tetap
memerlukan review manusia. Tiga video pilot milik pengguna belum disediakan.

Rincian: [arsitektur](docs/ARCHITECTURE.md), [kontrak API](docs/API.md),
[PRD](docs/PRD.md), [hasil dan backlog](docs/PROGRESS.md).
