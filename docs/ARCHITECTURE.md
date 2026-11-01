# Arsitektur implementasi

## Layanan dan aliran data

Caddy satu origin meneruskan `/api/v1/*` ke FastAPI dan route lain ke Nuxt.
Nuxt adalah workspace client-side (`ssr: false`) dengan autentikasi cookie;
tidak ada logika bisnis dalam Nitro. Production menggunakan PostgreSQL,
SQLAlchemy, Alembic, Celery, dan Redis. SQLite hanya untuk tes terisolasi.

Sumber, preview proxy, MP4/SRT hasil, dan scratch berada di `media-data` privat.
`LocalStorage` memvalidasi key, menolak traversal/symlink, dan melakukan rename
atomik. Video tidak dimuat seluruhnya ke RAM saat upload. Content endpoint
memakai FileResponse berotorisasi dengan Range/HEAD dan `private, no-store`.

Selama transfer, Asset berstatus uploading; upload juga memeriksa tombstone
secara berkala agar penghapusan proyek menghentikan transfer. Upload lengkap
menghasilkan Asset pending + job validate. Worker FFprobe memeriksa
container, codec, audio, ukuran, dimensi, rotasi, SAR, durasi; FFmpeg mencoba
decode seluruh media sebelum file ditandai siap. FFprobe/FFmpeg membatasi
protokol ke file/pipe dan demuxer input ke MOV/MP4, sehingga file upload yang
menyamar sebagai playlist tidak dapat memicu pengambilan URL. Sumber yang
memerlukan proxy dipersiapkan menjadi H.264/AAC. Klip
manual bisa dibuat segera setelah validasi tanpa bergantung pada AI.

## Sesi dan data

Password Argon2id; token sesi random hanya disimpan sebagai hash SHA-256 di DB.
Cookie HttpOnly/SameSite=Lax, Secure untuk HTTPS. Mutasi memerlukan CSRF cookie,
header, hash yang terkait sesi, dan pemeriksaan Origin. Login memakai rate-limit
persisten PostgreSQL dengan bucket akun/peer serta advisory lock agar percobaan
paralel tidak melewati batas. API Compose tidak mempercayai header proxy dari
client: bucket peer berada pada koneksi gateway, sehingga juga menjadi batas
bersama instalasi. Akun/reset hanya dari CLI; reset mencabut sesi.

Ownership selalu diturunkan dari Project.owner_id pada project, transcript,
clip, job, export, dan asset. UUID tidak dianggap bukti izin. Respons error
berisi `code`, `message`, `correlation_id`; data privat/trace tidak dikirim ke UI.

Tabel mencakup User, Session, LoginAttempt, Project, Asset, Transcript,
TranscriptSegment, Clip, ClipRevision, SubtitleCue, Export, Job, JobRequest,
JobAttempt, OutboxEvent, ProviderUsage. Transcript dan revision bersifat
immutable melalui API; save membuat baris baru. `expected_revision` melindungi
perubahan tab usang dengan HTTP409. Cue lokal klip menggunakan integer ms.

## Antrean, idempotency, dan recovery

Pembuatan Job dan OutboxEvent berada dalam satu transaksi. Fingerprint meliputi
input, konfigurasi, revisi, dan versi pipeline; ID export random dikecualikan.
JobRequest menyimpan setiap alias idempotency key setelah deduplikasi. Mengirim
key sama dengan parameter berbeda ditolak. Worker claim memakai row lock;
attempt dan lease membatasi publikasi worker lama.

Dispatcher menandai outbox terkirim sesudah broker menerima. Pengiriman ganda
tetap mungkin dan diharapkan; claim mencegah hasil resmi ganda. Reconciler
memulihkan lease kedaluwarsa sampai batas attempt dan mengirim ulang job queued
yang lama setelah broker kehilangan pesan. Kegagalan render tidak merusak
transkrip/kandidat. Retry render menggunakan snapshot yang sama.

Heavy queue: import_url, validate, preview, transcribe, render. Light queue:
analyze, delete_assets. Whisper dijalankan sebagai subprocess terpisah supaya dapat
dihentikan. FFmpeg memakai argument array dan process group, bukan shell.
Pada Linux, helper subprocess memasang parent-death signal sebelum exec supaya
proses media ikut berhenti jika proses worker induknya mati. Jalur Linux ini
tetap memerlukan smoke test pada deployment; host QA awal memakai Windows.
Heartbeat juga memeriksa tombstone; publikasi ulang memeriksa status/attempt
dan kepemilikan proyek dalam transaksi. Cancellation tidak dilabeli selesai
sebelum subprocess berhenti; lease worker yang hilang ditangani reconciler.

Deletion menandai tombstone dan mencabut akses lebih dahulu, membatalkan job,
lalu menghapus aset serta transkrip/revisi. Tombstone job/usage tetap tersedia
untuk audit terbatas tanpa isi video/teks. Operasi filesystem dan transaksi DB
tidak atomik bersama: nama output deterministik, pemeriksaan attempt, retry,
dan cleanup orphan menutup crash window secara bertahap.

## Media dan AI

FFmpeg menormalkan SAR dan autorotation, lalu fill/crop atau fit/letterbox solid.
Crop `x,y` dalam [0,1] mengatur proporsi ruang overflow, setara CSS
`object-position`. Output 720×1280/1080×1920, 30fps, H.264 yuv420p, AAC,
faststart. Decode/re-encode menghindari trim yang bergantung keyframe.

Impor memprioritaskan format hingga 1080p dan H.264 pada tingkat resolusi yang
sama. Full decode validation hanya sekali: ke null untuk sumber yang langsung
dapat diputar browser, atau bersamaan dengan pembuatan preview bila diperlukan.
Preview tetap divalidasi codec, durasi, SAR, rotasi dan frame rate sebelum ready.

Tracking opsional berjalan pada klip terpilih saja, memakai preview yang sudah
tersedia untuk menghindari decode analisis 4K. Subprocess YuNet memindai sekitar
6 fps pada maksimal 640 piksel dan mengasosiasikan bounding box lokal tanpa
identitas. Mode `face` mempertahankan target yang terlihat. Mode `speaker`
menyiapkan video 25 fps dan PCM16 mono 16 kHz; model Light-ASD TalkSet menilai
audio bersama urutan crop wajah melalui ONNX Runtime CPU (dua thread).
Crop mengikuti median13, padding, resize dan grayscale model; MFCC13 dihitung
dengan NumPy sesuai parameter acuan. Decode dilakukan secara streaming dengan
jendela 100 frame dan overlap 50 frame; tidak menyimpan seluruh video di RAM
atau membuat berkas crop wajah. Tail pendek dipad untuk inferensi dan prediksi
padding dibuang. Track yang terlalu singkat tidak diberi skor buatan. Bila
wajah terdeteksi tetapi seluruh track terlalu singkat, metadata mencatat nol
observasi berskor dan menampilkan alasan framing mengikuti wajah yang tersedia.

Softmax dua logit memberi skor pembicara 0–1, bukan ukuran akurasi terkalibrasi.
Selector menghaluskan skor, memerlukan bukti konsisten dan jeda minimum sebelum
berpindah, serta mempertahankan target ketika ucapan tumpang tindih ambigu.
Pergantian adegan mereset asosiasi. Tidak ada embedding identitas atau pengenalan
suara. FFmpeg sendcmd menerapkan jalur
crop saat render dari sumber asli. Fallback memakai posisi manual dan mencatat
alasannya; berkas perantara video/audio pelacakan segera dibersihkan.

Job `track_preview` menyediakan keyframe sebelum ekspor tanpa mutasi revisi.
Identitas cache dibatasi proyek dan memuat sumber/proxy/checksum, rentang,
crop, SHA YuNet/Light-ASD serta versi algoritma. `algorithm_signature` mewakili
konfigurasi/model aktif dan juga dikirim pada respons klip agar editor menolak
hasil versi lama. Worker memeriksa ulang identitas dan lease
sebelum mempublikasikan hasil. Renderer memakai cache yang sesuai atau memindai
ulang bila tidak ada. Job gagal atau hasil malformed tidak menjadi cache valid.
Frontend menerapkan interpolasi jalur yang sama pada CSS object-position,
dengan requestVideoFrameCallback dan fallback requestAnimationFrame. Perubahan
input menaikkan generasi request; respons lama tidak boleh mengganti draft baru.
Polling berhenti saat halaman tersembunyi atau editor ditutup. Jalur tersimpan
dipakai kembali oleh ekspor dengan snapshot revisi tersimpan.

ASS/libass memakai font Noto Sans berlisensi SIL OFL di `services/backend/fonts`.
Teks di-escape dan filter menggunakan nama file internal tetap. SRT selalu
tersedia, termasuk ketika burn-in dimatikan. Cue di-clamp ke durasi output.
Hasil sementara diperiksa FFprobe sebelum status ready dan rename final.

Whisper multilingual `small`/CPU/int8/VAD/word timestamps adalah baseline.
Override Docker GPU menyertakan CUDA 12/cuDNN 9. Mode auto memakai CUDA/float16
dengan batch 8 bila tersedia; CPU memakai int8/batch 1. Kegagalan CUDA pada auto
dicoba ulang sekali di CPU dengan sisa timeout, dan perangkat aktual serta
alasannya disimpan pada metadata. Heavy concurrency tetap 1.
Versi transkrip baru tidak mengganti rujukan klip lama. Hasil tanpa segmen
ditandai no_speech dan tidak masuk selector. DeepSeek menerima segmen teks
ber-ID, chunk dengan overlap, JSON terstruktur tervalidasi Pydantic. Timestamp
berasal dari database, bukan model. Validasi durasi/ID/urutan, deduplikasi IoU,
retry terbatas/backoff, dan usage per attempt dijalankan di backend.

## UI

Warm light theme dari PRD: canvas `#F5F5F2`, surface putih, teks `#202420`,
muted `#626963`, border `#D9DDD7`, accent `#355D78`, danger `#A33434`.
System font, Lucide, komponen aplikasi custom, tanpa Nuxt UI. Daftar memakai
baris/tabel; editor memusatkan preview/trim dan panel subtitle/tampilan.
Dialog custom menangani delete, konflik, dan perubahan belum tersimpan.
Polling hanya saat ada pekerjaan aktif dan berhenti ketika tab tersembunyi.

Layout gaming menyimpan dua persegi panjang dalam `crop_json.gaming`: facecam
dan gameplay. Koordinat mengacu pada display sumber tegak dengan SAR1. Satu
elemen video menjadi sumber audio dan frame untuk canvas preview serta pemilih
area, sehingga tidak ada dua pemutar yang harus disinkronkan. Perubahan area
atau tinggi panel langsung digambar ulang, termasuk ketika paused/seek.

Renderer gaming memakai satu decode sumber, normalisasi display, `split`, crop
tiap area, scale/pad, lalu `vstack`. Fill melakukan crop sumber sebelum scale
agar area yang sangat sempit tidak membuat intermediate frame berukuran besar.
Fit mempertahankan seluruh area yang dipilih. Preview dan FFmpeg berbagi aturan
pembulatan batas source, tinggi panel genap, serta padding. Subtitle dibakar
setelah kedua panel digabung; audio dipetakan satu kali. Job gaming memasukkan
versi layout ke fingerprint dan melewati analisis/pencarian cache pelacakan.
Mode ini tidak mengubah pemilih momen AI yang masih memakai transkrip.

## Reproduksibilitas

Dependency aplikasi memakai exact pins dan lockfile. Image Compose/Dockerfile
memakai versi + digest manifest yang diverifikasi dari Docker Hub pada
1 November2026. FFmpeg di image backend berasal dari apt Debian bookworm;
paket OS apt bukan snapshot terpisah, sehingga build berikutnya dapat menerima
patch distro. Local QA native Windows berbeda dari deployment Linux Compose;
hasil uji dan batas verifikasi dicatat eksplisit di PROGRESS.

Light-ASD dibundel sebagai ONNX 4,1 MB dari bobot TalkSet upstream berlisensi
MIT. `scripts/export_speaker_model.py` memverifikasi checksum source/bobot pada
commit tertentu dan menguji parity Torch/ONNX pada 25, 50 dan 100 frame.
Torch hanya diperlukan di lingkungan ekspor model pengembangan. Runtime
memakai ONNX Runtime; SciPy dan python_speech_features hanya acuan tes opsional.
Manifest, lisensi dan petunjuk reproduksi ada di
[services/backend/models](../services/backend/models/README.md).
