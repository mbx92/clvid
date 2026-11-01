# Progres dan bukti implementasi

Tanggal: **1 November 2026**, timezone pengguna Asia/Makassar.

**Alur inti bekerja dengan media nyata. MVP belum dinyatakan selesai seluruhnya:**
panggilan DeepSeek live dan tiga video pilot pengguna masih belum dilakukan.
Instalasi baru Docker Desktop/WSL2 dan pipeline Linux sudah diuji.
Tidak ada push, PR, atau deploy publik.

## Fitur yang sudah diimplementasikan

- Monorepo Nuxt/Vue/TypeScript/Tailwind v4/Lucide, FastAPI/SQLAlchemy/Alembic,
  PostgreSQL, Celery/Redis, konfigurasi sembilan layanan Compose, lockfile.
- Bootstrap/reset akun CLI, hash Argon2id, sesi server, CSRF, rate-limit login,
  ownership seluruh objek dan file, Range/HEAD privat.
- Proyek, pencarian/filter/pagination, upload streaming/XHR progress, validasi
  media, proxy playback, klip manual, transkrip bertimestamp, pencarian/seek.
- Impor URL publik: pilihan file/URL pada dialog, yt-dlp2026.10.26 + EJS0.8.0
  + Node24, heavy queue, dedupe, cancel/retry, validasi sumber dan proxy yang sama.
  MP4 langsung dan YouTube diuji sampai render; situs lain mengikuti dukungan
  extractor dan batas akses sumber. Tidak memakai cookie browser atau bypass DRM.
- Editor trim/cue/crop/letterbox/style, status simpan, revisi immutable,
  konflik tab lama, dialog perubahan belum tersimpan, shortcut dan keyboard.
- Render H.264/AAC 9:16, 720/1080, 30fps, ASS burn-in opsional, SRT terpisah,
  snapshot revision, riwayat hasil, preview final, download.
- Whisper multilingual small/CPU/int8/VAD, word timestamps, versi transkrip,
  no-speech tanpa kandidat palsu. Cue panjang otomatis dipisah hanya jika word
  timestamp nyata tersedia; koreksi pengguna tidak ditimpa.
- Adapter DeepSeek: JSON/Pydantic, ID segmen, token-budget chunks/overlap,
  deduplikasi, retry terbatas, usage. Belum diverifikasi dengan provider live.
- Outbox, request idempotency, claim/lease/heartbeat, attempt fencing, recovery,
  cancellation subprocess, deletion tombstone, cleanup partial/orphan/scratch.

## Pemeriksaan aktual

| Pemeriksaan | Hasil aktual |
| --- | --- |
| Backend unit/integration pada PostgreSQL 17.11 | Suite 44 tes lulus dalam 26,70 detik; tes tambahan pagination/filter history 1 tes lulus dalam 1,95 detik (45 kasus terverifikasi) |
| Regresi backend terbaru di Docker/Linux | Seluruh 75 tes unit/integration lulus dalam 29,10 detik, termasuk 30 kasus baru URL/SSRF/ownership/dedupe/cleanup/environment secrets; fixture rotasi kompatibel FFmpeg5 dan9 |
| Unit frontend | 7 tes lulus (`npm test`), termasuk pagination lebih dari100 item dan refresh riwayat |
| TypeScript | `npm run typecheck` lulus |
| Build Nuxt production | `npm run build` lulus, 8,51 detik pada pemeriksaan terakhir frontend |
| Playwright Chromium | 8 tes lulus, 25,2 detik pada regresi terakhir setelah pagination |
| Migrasi PostgreSQL | Upgrade dua kali sukses; `alembic check`: tidak ada perubahan schema yang hilang |
| Compose runtime Linux | Fresh install Docker Desktop 4.97.0, Engine 29.9.2, Compose 5.6.1; build, migrasi, bootstrap, Whisper cache, 9 layanan berjalan; API/web/PostgreSQL/Redis healthy |
| Browser terhadap build Docker | Alur upload, keyboard edit, crop, save, render, preview dan download lulus (1 tes, 18,2 detik) |
| Browser impor URL | Form URL pada390/1440px, submit keyboard, unduh, validasi dan playback sumber lulus; screenshot di `.artifacts/ui/url-dialog-*.png` |
| Regresi browser terbaru | Kedua alur URL dan unggah file/edit/render lulus bersama pada build Docker terbaru (2 tes, 16,1 detik) |
| URL live di Docker | MP4 W3Schools dan YouTube `jNQXAC9IVRw` berhasil diimpor, divalidasi, dibuat klip dan diekspor MP4/SRT + HTTP Range; laporan `.artifacts/url-smoke.json` |
| Linux parent-death guard | Proses induk benar-benar menerima SIGKILL; child dihentikan otomatis, lulus |
| HTTP + broker + worker nyata | Upload, validate, manual clip, edit setelah export dimulai, render, download MP4/SRT, byte Range berhasil |
| Worker benar-benar dimatikan | Job render attempt 1 diputus, lease pulih, attempt 2 sukses; hanya satu export resmi |
| Cancellation render aktif | `running -> cancel_requested -> cancelled`, tanpa aset MP4 siap |
| Whisper Indonesia lewat seluruh pipeline HTTP | Upload MP4, Celery, transkrip DB, cue sumber, render dan unduh berhasil |
| Silence lewat seluruh pipeline HTTP | Status no_speech, nol segmen, tidak membuat job analyze |

Uji kill/restart native memakai lease10detik, heartbeat2detik, dan interval
reconciler2detik agar failover dapat diperiksa cepat. Konfigurasi default
deployment tetap lease90/heartbeat15/reconciler15detik.

Tes backend mencakup ownership lintas akun, cookie/CSRF/session expiry/logout,
rate-limit, upload oversize/empty/tombstone saat streaming, HTTP Range, immutable
revision, optimistic conflict, idempotency alias/retry, outbox gagal kirim,
duplicate claim, worker-loss lease, deletion/scratch, validasi selector,
timing subtitle, dan render FFmpeg nyata. Media meliputi rotasi, VFR, SAR2,
crop kiri/kanan dengan sampling warna output, korup/tanpa audio, cancellation,
serta playlist tersamar yang ditolak tanpa request jaringan.

Regresi terakhir: burn-in yang dinonaktifkan kini tidak membangun ASS, sehingga
cue panjang tetap dapat diekspor sebagai SRT tanpa terkena batas layout burn-in.
Teks burn-in yang tak muat pada dua baris terbaca ditolak sebelum job dibuat;
draft tetap tersimpan dan dapat dipisah/disunting.

History ekspor dapat difilter berdasarkan klip di backend dengan ownership
tetap diperiksa. Pagination memastikan hasil lama tidak hilang ketika jumlah
klip/ekspor melampaui satu halaman.

Playwright melakukan **login UI -> upload file -> manual clip -> keyboard edit
subtitle/trim/crop -> save -> export -> preview final -> download SRT**, ditambah
dua tab dengan konflik revisi, focus trap/Escape, dan dialog perubahan belum
tersimpan. Pengukuran DOM memastikan tidak ada overflow horizontal pada 390,
768, 1024, 1440px. Seluruhnya memakai API dan media asli, bukan route mock.

## Media hasil dan review visual

Artefak berikut berada pada workspace lokal dan diabaikan Git:

- `.artifacts/acceptance.mp4`: **7,000 detik**, 720×1280, H.264 yuv420p,
  AAC, SAR1:1, 30fps; `.artifacts/acceptance.srt` berisi teks koreksi.
- `.artifacts/acceptance-frame.png`: crop kanan dan burn-in diperiksa visual.
- `.artifacts/transcription-pipeline/speech-id.mp4` dan `speech-id.srt`:
  output dari audio Indonesia sungguhan, beserta laporan versi/pipeline.
- `.artifacts/recovery-report.json`: worker kill/restart dan pembatalan aktual.
- `.artifacts/ui/`: 22 screenshot enam state: Proyek, detail, editor, dialog
  hapus, empty akun kosong, dan error nyata. Desktop/mobile diperiksa visual;
  editor tablet 768/1024 juga diperiksa.

Review menemukan dan memperbaiki double border pencarian, judul editor
terpotong, ruang kosong berlebih dari grid mobile, serta perbedaan wrapping
subtitle browser/ASS. Preview kini memakai Noto Sans, pembagian dua baris dan
ukuran efektif yang sama. Perbedaan rasterisasi browser/libass tetap mungkin;
preview final selalu tersedia sebagai acuan.

Pemeriksaan bagian8 PRD: tidak ada gradient/glow/neon, emoji/sparkle, hero
marketing, statistik/score palsu, placeholder fitur berbayar, progres timer
palsu, atau dialog `alert/confirm/prompt`. Komponen memakai border/row/panel,
aksen biru kusam, native file chooser, dialog dan combobox custom. Data pada
screenshot berasal dari proyek uji yang benar-benar diproses.

## Benchmark transkripsi terbatas

Mesin: Windows11 x64, AMD Ryzen5 5500, 6 core/12 logical CPU. Python3.12.16,
faster-whisper1.2.1, CTranslate2 4.8.4, PyAV16.1.0, model multilingual `small`,
CPU/int8, `cpu_threads=2`, beam5, VAD dan word timestamps. Model sudah dicache.
Angka ini satu smoke per sampel, bukan SLA atau evaluasi bisnis.

| Sampel | Media | Proses terukur | Hasil |
| --- | --- | --- | --- |
| Suara Inggris, fixture JFK dari repository Whisper | 11,0 detik | 6,62 detik | en, 2 segmen, word timestamps |
| Suara Indonesia, Google FLEURS validation id_id row1 | 7,92 detik | 9,047 detik | id, probabilitas0,98326, 1 segmen660–6780ms |
| Video audio hening sintetis | 8,0 detik | 5,844 detik | 0 segmen; tidak diteruskan ke selector |

Indonesia menunjukkan perbedaan kata `mulai`/`dimulai` terhadap referensi;
tidak ada klaim akurasi berdasarkan satu sampel. FLEURS berlisensi CC-BY-4.0:
[dataset resmi](https://huggingface.co/datasets/google/fleurs). Attribution,
referensi dan konfigurasi disimpan pada
`.artifacts/live-indonesian/attribution.json` serta `smoke-report.json`.
Output turunan memakai visual testsrc sintetis dan audio sampel tersebut.
Fixture Inggris berasal dari [Whisper tests](https://github.com/openai/whisper/tree/main/tests).
Tidak ada media pilot pribadi pengguna yang digunakan.

## Matriks acceptance

| ID | Status dan batas bukti |
| --- | --- |
| AC-01 | Lulus fresh install Docker/WSL2, build, migrasi, akun, model dan startup lokal; seluruh data disk Docker berada di G: |
| AC-02 | Lulus tes API ownership proyek/clip/job/transcript/export/asset lintas akun |
| AC-03 | Lulus valid/korup/oversize/empty/audio-missing dan streaming terputus/tombstone |
| AC-04 | Lulus jalur manual dan transkripsi Indonesia sampai MP4/SRT; selector live belum diuji |
| AC-05 | Lulus DB persistent, refresh/reload browser, actual worker kill/restart; Redis-loss diuji lewat reconciler/dispatch tests |
| AC-06 | Lulus adapter tests terkontrol untuk invalid ID/JSON/empty/dedupe; bukan provider live |
| AC-07 | Lulus selisih <=100ms pada fixture trim; smoke7detik tepat7,000 |
| AC-08 | Lulus cue clamp/koreksi/SRT/burn-in dan inspeksi frame |
| AC-09 | Lulus crop pixel alignment, rotasi, VFR, SAR, letterbox |
| AC-10 | Lulus snapshot revisi lama saat edit; UI menunjukkan revisi hasil dan konflik |
| AC-11 | Lulus retry render/idempotent retry tanpa mengulang transcript |
| AC-12 | Lulus duplicate claim/request/fingerprint; recovery hanya satu hasil resmi |
| AC-13 | Lulus penghentian proses dan cancellation aktif native; Linux parent-death guard juga diuji dengan SIGKILL pada induk |
| AC-14 | Lulus tombstone, pembatalan publication, file/transcript/scratch cleanup, stream upload saat delete |
| AC-15 | Secret backend-only; settings/usage tak mengembalikan key; tidak ada key nyata dalam source atau frontend |
| AC-16 | Lulus dialog custom focus trap/Escape dan konflik dua tab |
| AC-17 | Lulus 390/768/1024/1440px DOM dan review screenshot |
| AC-18 | Lulus inti upload/edit/save/export dengan keyboard; native file chooser memakai Playwright file input |
| AC-19 | Enam state desktop/mobile diperiksa; perbaikan recapture selesai |
| AC-20 | Tidak ada data/progress/hasil AI palsu; gap live dan pilot dicatat di sini |

## Keterbatasan dan pekerjaan tersisa

1. **Docker Linux kini terverifikasi pada WSL2.** PostgreSQL17.11, Redis7.4.8,
   Celery prefork dan FFmpeg5.1.9 berhasil menjalankan smoke upload/manual/render,
   HTTP Range, transkripsi Indonesia sampai MP4/SRT (transkripsi+queue 9,16 detik),
   cleanup proyek uji, serta alur browser. Setelah penambahan URL, suite backend
   diperluas menjadi75 tes dan seluruhnya lulus di Docker; suite8 browser lengkap
   sebelumnya dijalankan native, alur upload dan URL diuji terpisah di Docker.
   Runtime web sempat gagal karena dependency tracing menghilangkan file:
   penanganan ENOENT diperbaiki, workaround dibatasi ke Windows, dan healthcheck
   web ditambahkan. Build Docker setelah perbaikan berjalan dan browser lulus.
2. Integrasi DeepSeek dan schema/adapter terkontrol sudah diuji. Audit percepatan
   di bawah tidak menjalankan analisis provider tambahan. Kualitas rekomendasi
   dan biaya uang belum menjadi bagian dari pengukuran ini.
3. **Pilot tiga video pengguna belum tersedia.** Belum diukur median penghematan
   30%, kandidat layak, koreksi manusia, atau kualitas dua pembicara/noise.
4. Npm audit frontend saat implementasi: 2 low, 12 moderate pada dependensi
   transitif; nol high/critical. Review pembaruan kompatibel sebelum produksi;
   tidak dilakukan downgrade Nuxt paksa.
5. Preview editor tetap pendekatan untuk rasterisasi font. Setelah analisis,
   preview dan ekspor dapat mengikuti wajah atau perkiraan pembicara; tidak ada
   diarization suara atau jaminan pemilihan pembicara pada ucapan tumpang tindih.
   Tidak ada pricing monetary yang dikarang.
6. Upload/resume parsial belum didukung; pemulihan API mati mengikuti TTL24jam.
   Provider yang sudah menerima request dapat tetap mengenakan biaya walaupun
   pengguna membatalkan. Delete lokal bukan permintaan delete ke provider.
7. Impor URL bukan jaminan setiap situs/video bisa diunduh. TikTok/Instagram
   belum diuji live pada host ini; login/anti-bot/geoblock dapat menolak sumber.
   Playlist, profil, live, URL private/local dan port selain80/443 ditolak.
   Extractor menggunakan HTTP/HLS/DASH native Python; format yang membutuhkan
   downloader eksternal/impersonation tidak diaktifkan. Saat situs berubah,
   pembaruan yt-dlp/EJS perlu diuji kembali dan dipatok pada lockfile.

## Percepatan dan pelacakan frame, 1 November 2026

Audit pekerjaan pengguna menemukan sumber 26 menit 25,8 detik, 3840×2160 AV1,
1,22 GB. Impor beserta validasi/preview berlangsung 75 menit 39,7 detik;
transkripsi 7 menit 14,6 detik; analisis 2 menit 2,8 detik. Antrean kurang dari
2 detik dan tidak ada retry. Durasi setiap tahap impor tidak dicatat saat itu,
sehingga bagian unduhan, validasi dan preview tidak bisa dipisahkan secara pasti.

Perubahan:

- Impor memilih hingga 1080p bila tersedia dan memprioritaskan H.264 pada tingkat
  resolusi yang sama. Opsi 2160p tetap dapat dikonfigurasi untuk detail lebih tinggi.
- Sumber yang perlu preview hanya menjalani satu decode penuh, sambil membuat
  preview 1280 piksel. Validasi paket rusak dan metadata hasil tetap wajib.
- Worker lokal menggunakan 4 inti CPU dan NVIDIA RTX 4060 8 GB. Transkripsi
  memilih CUDA/float16, batch 8, model small multilingual, beam 5; fallback CPU
  dan perangkat aktual dicatat pada hasil pekerjaan. Image CPU tetap tersedia.
- Pelacakan wajah YuNet berjalan lokal pada durasi klip terpilih. Crop bergerak
  dengan smoothing dan reset adegan. Versi awal perkiraan pembicara memakai
  gerak mulut serta aktivitas audio; jalur ini telah diganti oleh Light-ASD
  audiovisual pada pembaruan di bawah. Wajah pada poster juga bisa terdeteksi;
  belum ada jaminan akurasi pemilihan pembicara atau diarization suara.
- Editor menyediakan mode manual, mengikuti wajah, atau perkiraan pembicara.
  Implementasi awal menampilkan posisi manual; pembaruan preview di bawah
  menambahkan gerakan sebelum ekspor. Membuka klip lama tidak mengubah revisinya. Kartu pekerjaan
  menampilkan waktu aktual, bukan ETA buatan.

Pengukuran sampel audio yang sama (60,004 detik, tanpa unduhan model):

| Konfigurasi | Total load + transkripsi |
| --- | ---: |
| CPU 2 inti, int8, batch 1 | 42,901 detik |
| CPU 4 inti, int8, batch 1 | 20,101 detik |
| RTX 4060, float16, batch 8 | 4,487 detik |

Wrapper aplikasi dengan `device=auto` juga terverifikasi memakai CUDA,
tanpa fallback, selama 4,861 detik termasuk subprocess. Hasil CPU memiliki
167 kata dan GPU 166 kata; benchmark ini mengukur kecepatan, bukan membuktikan
kualitas transkripsi identik. Bukti tanpa teks transkrip ada pada
`.artifacts/performance/`.

Sampel video pengguna 60 detik: analisis wajah 16,719 detik, dan render lengkap
720×1280 termasuk analisis 23,937 detik. Wajah ditemukan pada 349/360 frame sampel.
Ini cakupan deteksi, bukan akurasi pembicara. Tidak ada pergantian pembicara
dalam hasil sampel; contact sheet diperiksa dan wajah tetap di dalam crop.
Artefak: `.artifacts/tracking-user-render/`.

Suite backend terbaru: **109 tes lulus** pada SQLite/FFmpeg Windows (37,22 detik)
dan PostgreSQL terisolasi/FFmpeg Linux (40,57 detik). Termasuk perubahan crop
nyata melalui FFmpeg, cancellation, fallback model, revisi immutable, metadata
hasil, pemilihan format downloader, decode tunggal, serta penolakan paket rusak
dan preview yang tidak konsisten.

Dua tes browser nyata pada Docker terbaru lulus dalam 13,0 detik. Mode wajah
menemukan wajah pada 36/36 frame sampel klip 6 detik, menyimpan 37 keyframe,
dan mengekspor MP4 tanpa fallback. Revisi lama tetap identik setelah editor
dibuka. Screenshot 390/1440 piksel dan video hasil diperiksa; bukti terdapat
pada `.artifacts/tracking-browser-report.json` dan `.artifacts/ui/tracking-*.png`.

Ekspor tambahan pada stack aktif menggabungkan mode speaker dengan subtitle
burn-in: klip 6,000 detik selesai dirender dalam 4,748 detik, 720×1280 H.264/AAC.
Wajah ditemukan pada 36/36 sampel tanpa fallback. Inspeksi frame memastikan
subtitle dua baris terlihat pada detik 2 dan hilang pada detik 5,5 setelah cue
berakhir di detik 5. Bukti: `.artifacts/tracking-with-subtitles/`.

Uji ulang URL video pengguna sepanjang 26 menit 25,8 detik pada proyek QA:

| Tahap | Pekerjaan lama | Setelah perbaikan |
| --- | ---: | ---: |
| Impor, validasi dan preview | 4.539,7 detik | 153,642 detik |
| Transkripsi | 434,6 detik | 26,498 detik |

Waktu yang terlihat dari klien termasuk antrean/polling adalah 154,86 dan
28,14 detik, total sekitar 3 menit 3 detik sampai transkrip siap. Sumber baru
1920×1080 H.264/AAC, 560.570.570 byte, langsung dipakai sebagai preview. Durasi
sumber sama persis dengan impor lama. Runtime transkripsi tercatat CUDA/float16,
batch 8, beam 5, tanpa fallback, menghasilkan 61 segmen. Tidak ada panggilan
analisis DeepSeek baru pada pengukuran ini.

Perbandingan ini mencakup perubahan sumber 4K AV1 menjadi 1080p H.264, decode
tunggal, batas CPU, dan GPU; bukan benchmark GPU saja atau jaminan waktu semua
URL. Kondisi jaringan antarpercobaan juga tidak dikendalikan. Bukti job aktual
tanpa URL maupun teks transkrip: `.artifacts/performance/full-video.json`.
Worker yang diterapkan dicocokkan hash-nya dengan delapan modul produksi yang
diuji; model tracking dibundel. Semua layanan Docker sehat setelah pembaruan.

## Preview pelacakan sebelum ekspor, 1 November 2026

Editor kini menyediakan **Analisis preview** untuk mode wajah/pembicara. Analisis
draft tidak menyimpan revisi atau membuat ekspor. Setelah siap, object-position
video mengikuti keyframe saat playback dan seek, dengan perpindahan adegan yang
sama seperti FFmpeg. Subtitle tetap dilapis pada waktu klip yang sesuai.

Cache dicocokkan dengan proyek, sumber/proxy/checksum, batas klip, crop, SHA model
dan versi algoritma. Perubahan framing atau rentang membatalkan hasil lokal;
perubahan judul/subtitle tidak. Respons terlambat serta polling sebelum aksi
retry/cancel tidak dapat menimpa state baru. Job bersama tidak dibatalkan hanya
karena draft berubah. Ekspor revisi yang cocok memakai ulang keyframe yang sudah
dipreview dan mencatat `analysis_reused`.

Pemeriksaan backend pada image Docker terbaru: **182 tes lulus** dengan database
PostgreSQL khusus pengujian dan FFmpeg Linux (62,55 detik). Mencakup cache lintas
revisi dalam proyek yang sama, ownership/CSRF, rentang durasi, cancellation,
lease, sumber/model/proxy berubah selama analisis, hasil sah tanpa wajah,
penolakan keyframe rusak, dan penghapusan input/hasil cache bersama proyek.
Uji FFmpeg nyata membandingkan gerakan halus, hard cut, serta burn-in subtitle
ketika pelacak dilarang dipanggil ulang. Frontend: **23 tes unit** dan typecheck
lulus; callback video dibersihkan saat pause, tab tersembunyi dan unmount.

Dua tes browser nyata pada stack yang diterapkan lulus dalam 23,8 detik.
Analisis draft berjalan tanpa menyimpan revisi atau membuat ekspor; preview
bergerak sesuai keyframe pada pause/seek/playback, berhenti pada batas klip,
dan kembali ke posisi manual di luar rentang. Respons POST nyata sengaja
ditunda sampai mode berubah; hasil lama berhasil ditolak. Rentang dan posisi
cadangan yang berubah juga menonaktifkan analisis lama.

Pada klip sampel 6 detik, analisis membutuhkan 2,505 detik dan render memakai
cache 2,521 detik. Setelah save/reload, permintaan mengembalikan ID job yang sama
tanpa menambah attempt. Ekspor memiliki `analysis_reused=true` dan keyframe yang
identik dengan preview. Screenshot desktop 1440px/mobile 390px telah diperiksa;
bukti terdapat pada `.artifacts/tracking-preview/`. Akun dan proyek QA
dibersihkan setelah pengujian, termasuk seluruh input/hasil job preview.

## Pembicara audiovisual Light-ASD, 1 November 2026

Keluhan crop yang menetap pada satu orang ditelusuri ke dua hal berbeda:
mode **Ikuti wajah** memang mempertahankan satu target, sedangkan pemilihan
pembicara versi awal terlalu bergantung pada perubahan piksel mulut dan aktivitas
audio. Mode **Ikuti pembicara (perkiraan)** kini memakai Light-ASD TalkSet lokal
untuk menilai audio bersama urutan crop tiap wajah, lalu selector menunggu bukti
konsisten sebelum handoff. Mode/revisi pengguna tidak diubah otomatis.

Model ONNX 4,1 MB dibundel dari source/bobot upstream berlisensi MIT. Script
`scripts/export_speaker_model.py` memverifikasi commit/checksum dan membandingkan
Torch dengan ONNX pada 25/50/100 frame; galat absolut maksimal 3,34×10⁻⁶.
Runtime memakai ONNX Runtime CPU dua thread tanpa Torch. MFCC NumPy diperiksa
terhadap python_speech_features0.6/SciPy1.17.1, termasuk silence, DC dan PCM acak;
crop dibandingkan per-piksel dengan praproses acuan. **10 tes scorer lulus**
pada lingkungan parity; vektor acuan tetap diuji tanpa dependensi tes opsional.
Lihat [provenance dan reproduksi model](../services/backend/models/README.md).

Pengukuran lokal sebelum acceptance deployment akhir:

| Sampel | Inferensi Light-ASD saja | Skor observasi wajah | Handoff selector |
| --- | ---: | ---: | ---: |
| Potongan 43,760 detik | 15,297 detik | 526 | 3 |
| Potongan 60 detik | 17,359 detik | 698 | 3 |

Pada sampel 43,760 detik, fokus berpindah pada sekitar 16,48; 32,32; dan 35,16
detik. Ini bukti jalur model/selector bergerak pada sampel yang diperiksa,
bukan evaluasi akurasi umum atau jaminan durasi proses. Waktu tabel tidak
mencakup persiapan media, deteksi wajah, render, maupun antrean. Kedua potongan
berasal dari video yang sama; tidak menggantikan pilot tiga video. Laporan
angka dan keyframe: `.artifacts/speaker-diagnostics/asd43/` dan `asd60/`.

Review independen menemukan kasus bukti challenger yang tertahan oleh jeda
minimum kemudian memicu handoff ketika audio sudah diam. Selector diperbaiki
agar kondisi audiovisual saat ini tetap wajib terpenuhi; regresi silence dan
pembalikan skor ikut diuji. Suite tracking/selector terkait: **24 tes lulus**.
Track wajah terlalu singkat tidak diberi probabilitas buatan; bila seluruh
track demikian, metadata mencatat `speaker_scored_frames:0` dan peringatan
bahwa framing mengikuti wajah yang tersedia. Score0–1 bukan
akurasi terkalibrasi, identitas orang, atau diarization audio.

Versi analisis berubah ke `tracking-preview-2`, metode speaker ke
`yunet-light-asd-v1`. Identitas cache mencakup SHA kedua model dan signature
algoritma; hasil metode lama tetap menjadi riwayat aslinya, bukan cache untuk
metode baru. API mengirim signature aktif agar editor dapat menolak analisis
yang tidak sesuai versi.

Acceptance pada Docker lokal selesai setelah build final:

- Backend Linux/PostgreSQL: **218 lulus, 1 dilewati**; pemeriksaan terarah pada
  image final: **33 lulus, 1 dilewati**. Skip hanya pembanding MFCC opsional
  `python_speech_features`; vektor referensi yang dibundel tetap diuji.
- Frontend: **26 tes lulus**, typecheck dan build lulus.
- Browser nyata: **3 tes lulus**, termasuk preview dua pembicara, respons
  analisis terlambat, seek/playback, invalidasi pengaturan, dan reuse saat export.
- Cuplikan QA 43,76 detik: analisis **20,309 detik**, export **9,801 detik**;
  terdeteksi **3 perpindahan**, dan keyframe export identik dengan preview.
  Screenshot browser pada detik 5/23/34/40 menunjukkan kanan/kiri/kanan/kiri.
  Bukti: `.artifacts/speaker-switching/report.json` dan `speaker-export.mp4`.
- Preview klip pengguna yang bermasalah dihitung ulang dengan model final:
  **3 perpindahan dalam 20,759 detik**, revisi tersimpan tetap 3. Cache cocok
  dengan sumber dan pengaturan aktif sehingga dapat langsung dimuat di editor.

Sembilan layanan Docker berjalan; health ready HTTP200 dan satu perangkat CUDA
tetap tersedia untuk transkripsi. Proyek serta akses akun QA sementara sudah
dibersihkan. Tidak ada pekerjaan aktif pada pemeriksaan akhir. Waktu di atas
adalah hasil pada satu mesin/sumber uji, bukan jaminan untuk semua video.

## Layout gaming satu sumber

Mode **Gaming (facecam + gameplay)** ditambahkan untuk video yang facecam-nya
sudah menyatu dengan permainan. Dua area sumber dapat diatur melalui preset,
drag/resize, keyboard, dan angka persentase. Facecam di panel atas dengan tinggi
15–45%; gameplay di bawah, default fit untuk menjaga HUD. Kedua panel memakai
satu video/audio decoder. Preview berubah langsung saat mengatur area, pause,
seek, dan playback, tanpa job analisis atau simpan otomatis.

Crop gaming tervalidasi, tersimpan dalam revisi, dan diekspor lewat FFmpeg
split/crop/scale/pad/vstack. Fill melakukan crop sebelum scale agar area sempit
tidak membuat frame intermediate besar. Subtitle diterapkan pada komposisi
akhir; audio sumber dipetakan satu kali. Sumber berotasi/SAR berbeda diuji.
Versi `gaming-layout-1` masuk identitas job; mode podcast tetap menggunakan
jalur dan cache analisisnya. Tidak ada migrasi database atau model AI tambahan.

Validasi pada stack Docker lokal:

- **286 tes backend lulus, 1 dilewati** (pembanding MFCC opsional), PostgreSQL
  `clipper_test` terisolasi; tidak memakai database produksi untuk fixture.
- **33 tes frontend**, typecheck dan build lulus.
- **2 tes browser nyata lulus**, meliputi preview/playback/seek, perubahan area
  tanpa simpan/job, drag, resize keyboard, perubahan tinggi saat paused,
  save/reload, tampilan desktop/mobile, dan export revisi tersimpan.
- Fixture sintetis 960×540 memakai area kreator dan penanda HUD pada sudut.
  MP4 720×1280 mempertahankan semua penanda; selisih kanal RGB browser/export
  maksimal 3/255 pada empat titik ukur. Tepat satu stream audio. Render klip
  enam detik tercatat 1,482 detik pada mesin uji.

Bukti lokal: `.artifacts/gaming/report.json`, `desktop.png`, `mobile.png`,
`preview.png`, `export-frame.png`, dan `gaming-export.mp4`. Pengujian ini
memverifikasi layout, bukan kemampuan mendeteksi momen seru dari aksi game.
Pemilihan klip AI tetap berdasarkan transkrip. Proyek dan akses akun QA
sementara dibersihkan setelah pemeriksaan; layanan Docker dibiarkan berjalan.

## Mengulang pemeriksaan

### Subtitle kata per kata (1 November 2026)

- Pilihan tampilan kalimat atau kata per kata memakai `TranscriptSegment.words_json`
  dari versi transkrip yang dipatok revisi; tidak memakai estimasi pembagian waktu.
  Preview mengikuti frame clock saat play/pause/seek, dan ASS menampilkan event
  kata dengan jeda kosong. Token ASR dapat digabung dengan pencocokan teks persis.
- Cue tanpa timestamp cocok ditandai; ekspor ditolak dengan pesan tindakan.
  Koreksi draft tetap bisa disimpan dan mode kalimat/SRT tidak berubah.
- Pengujian mencakup timestamp tidak merata, jeda, trim, token gabungan, teks
  berubah, ownership, transkrip versi baru, preview setelah reload/seek/playback,
  serta ekspor MP4 nyata. Frame pada 0.6/1.1/1.6 detik menunjukkan kata pertama,
  jeda kosong, dan kata kedua. Bukti di `.artifacts/word-subtitles/`.

### Ukuran dan styling subtitle (1 November 2026)

- Penyebab slider tampak tidak berubah adalah auto-fit yang membatasi ukuran
  efektif. Slider kini memakai ukuran persis dan mematikan auto-fit; pilihan
  otomatis tetap tersedia dengan indikator ukuran efektif cue. Mode manual
  membungkus hingga empat baris dan menolak cue berlebih sebelum ekspor.
- Enam preset statis, warna teks/outline/latar, tebal/miring/kapital, outline
  dan bayangan tersimpan dalam revisi serta diterapkan di preview dan libass.
  Teks sumber dan SRT tidak diubah oleh kapitalisasi tampilan.
- Browser nyata memverifikasi rasio ukuran 100/24, penyimpanan/reload gaya,
  layout laptop/ponsel tanpa scroll panel, dan MP4 720p dengan gaya baru.
  Screenshot dan frame ekspor diperiksa di `.artifacts/subtitle-styles/`.
- Validasi akhir: 307 tes backend lulus / 1 opsional dilewati, 34 tes web
  lulus, typecheck/build lulus, dan 4 tes browser subtitle/workspace/gaming
  lulus. Data QA dibersihkan setelah pemeriksaan.

### Pengaturan batas akun dan workspace kompak (1 November 2026)

Perbaikan susulan: impor/validasi yang sudah mencapai batas percobaan dapat
dicoba sekali lagi setelah batas durasi/ukuran penyebab kegagalan dinaikkan.
Job lama tanpa snapshot didukung, nomor percobaan tetap berurutan, perubahan
yang tidak relevan tidak membuka retry, dan batas sama tidak bisa dipakai
untuk retry tanpa akhir. Regresi mencakup API, service, isolasi pemilik,
idempotensi, snapshot lama/baru, serta kegagalan jaringan yang tidak terkait.

- Pengaturan menyimpan batas durasi sumber, ukuran file, dan durasi klip per
  akun. Rentang maksimum 12 jam, 64 GiB, dan 10 menit; default tetap 1 jam,
  2 GiB, dan 3 menit. Upload/impor dan kandidat/manual memakai batas akun.
- Migrasi aditif `51ad8d802001` menambah pengaturan dan snapshot batas pada job.
  Job aktif mempertahankan snapshot; retry mengambil batas terbaru. Penurunan
  batas tidak menghapus klip lama atau menghalangi penyuntingan durasinya semula.
- Workspace mengikuti tinggi layar; alat framing/subtitle dan area/susunan
  gaming dipisah tab. Ponsel memilih preview atau alat; daftar panjang tetap
  dapat digulir dalam panel tanpa menggeser seluruh halaman.
- Validasi: 298 tes backend lulus, 1 opsional dilewati; 33 tes web lulus,
  typecheck/build lulus. Tes mencakup isolasi akun, CSRF, snapshot/retry,
  migrasi data lama, render 181 detik, dan tracking hingga batas baru.
- Tiga tes browser nyata memeriksa penyimpanan pengaturan, layout laptop
  1366×768 / ponsel 390×844, serta preview, crop interaktif, simpan dan ekspor
  gaming. Bukti visual di `.artifacts/workspace-settings/`.

### Kalender dan publikasi YouTube, Instagram Reels, TikTok (1 November 2026)

- Menu Kalender dan tombol Jadwalkan pada hasil ekspor: draft, edit, pembatalan,
  preview MP4, status publikasi, serta WITA/WIB/WIT/UTC. Jadwal terikat ke file
  ekspor yang dipilih dan memerlukan persetujuan pengguna sebelum dikirim.
- Koneksi akun dan panduan callback berada di **Pengaturan → Koneksi akun**;
  Kalender hanya memilih tujuan yang sudah terhubung dan mengatur jadwal.
- OAuth resmi, token terenkripsi, state sekali pakai terikat sesi, isolasi akun,
  dan migrasi aditif `72bc19010001`. Layanan `publisher` menyimpan progres upload
  dan tidak mengulangi unggahan yang hasilnya tidak pasti secara otomatis.
- Adapter YouTube resumable, Instagram Reels container/publish dengan media
  bertanda tangan dan profil AAC, serta TikTok FILE_UPLOAD/status. TikTok Direct
  Post dinonaktifkan secara default; kelayakan aplikasi dan persetujuan TikTok
  tetap diperlukan. Tidak ada akun sosial atau kredensial developer bawaan.
- Panduan pemula di `docs/SOCIAL-PUBLISHING.md`, dimulai dari Google Cloud dan
  OAuth YouTube localhost. Instagram memerlukan akun profesional, Facebook Page,
  dan akses HTTPS publik yang harus dikonfigurasi terpisah.
- Validasi akhir: 324 tes backend lulus / 1 opsional dilewati, 36 tes web lulus,
  typecheck/build lulus, serta 4 tes browser kalender/workspace/gaming lulus.
  Uji browser memakai ekspor MP4 nyata dan draft tiga platform; mencakup edit,
  batal, pergeseran tanggal WITA ke WIB, disclosure TikTok, dan layout ponsel.
  Bukti visual tersedia di `.artifacts/calendar/`. Profil audio Instagram juga
  diuji dengan FFmpeg lokal.
- Database lokal dicadangkan sebelum migrasi dan 10 layanan Docker diperbarui.
  Pengujian API sosial menggunakan respons simulasi; belum ada upload nyata
  karena pengguna belum memiliki aplikasi developer dan belum menghubungkan
  akun. Jadwal dan upload nyata baru dapat diuji setelah setup tersebut selesai.

### Seluruh halaman desktop tanpa scroll (1 November 2026)

- Pustaka proyek, detail proyek, editor klip, kalender, pengaturan, dan login
  mengikuti tinggi viewport desktop. Daftar proyek menggunakan pagination server;
  kandidat, transkrip, cue subtitle, ekspor, pekerjaan, dan agenda menggunakan
  pagination panel. Konten yang belum dimuat tetap dapat diambil melalui tombol
  muat berikutnya. Pengaturan dipisah empat tab.
- Kalender dan agenda ditampilkan berdampingan. Koneksi akun memakai tab khusus
  di Pengaturan; form jadwal dipisah Video & jadwal / Opsi publikasi. Urutan agenda
  tetap stabil setelah perubahan status dengan waktu publikasi yang sama.
- Form dialog dan kontrol panel menyesuaikan ruang vertikal. Dropdown memakai
  lapisan terpisah agar tidak terpotong, termasuk saat panel menyesuaikan ukuran.
  Tampilan ponsel tetap responsif dan daftar panjang tetap dapat digulir.
- Validasi: typecheck/build dan 36 tes web lulus. Enam tes browser mencakup layout
  seluruh halaman pada 1280×720, 1366×768, dan 1920×1080; tombol dalam viewport;
  pagination data panjang; kalender tiga platform; koneksi akun di pengaturan; preview/crop
  gaming; serta penyimpanan dan ekspor gaya subtitle. Bukti visual tersedia di
  `.artifacts/desktop-layout/`. Tidak ada perubahan backend atau migrasi database.

### Dropdown custom di seluruh aplikasi (1 November 2026)

- Seluruh elemen select native diganti AppSelect, termasuk zona waktu, hasil
  ekspor, platform, akun, privasi, dan audiens di kalender. Editor, gaming,
  subtitle, resolusi ekspor, bahasa, serta filter proyek memakai komponen sama.
- Dropdown memiliki pencarian dan pagination untuk pilihan panjang, penanda
  pilihan aktif, placeholder, opsi nonaktif, navigasi keyboard, dan Escape yang
  menutup dropdown tanpa menutup dialog. Popup tetap berada dalam viewport dan
  tidak terpotong panel; halaman desktop tetap tanpa scroll.
- Pemilihan privasi TikTok tetap eksplisit; opsi yang dilarang untuk disclosure
  tertentu tidak dapat dipilih dengan pointer maupun keyboard. Form memeriksa
  hasil ekspor sebelum menyimpan atau menjadwalkan.
- Penyimpanan ekspor tidak diubah: volume Docker `clipper_media-data`, terpasang
  di `/data/media`, memakai key `projects/<project_id>/<uuid>.mp4` dan `.srt`.
  Tombol Unduh MP4/SRT menyalin hasil ke lokasi download browser pengguna.
- Typecheck/build dan 36 tes web lulus. Pengujian browser mencakup kalender,
  pencarian 20 opsi, pagination, keyboard, opsi disabled, fokus dialog, viewport
  desktop/ponsel, serta regresi editor dan render. Bukti dropdown ada di
  `.artifacts/custom-select/`. Respons akun sosial pada uji dropdown disimulasikan
  di browser; tidak ada koneksi atau publikasi akun nyata.

### Pagination mengikuti ruang panel (1 November 2026)

- DesktopPager menghitung kapasitas dari tinggi panel dan ukuran baris yang
  benar-benar dirender. Batas tetap 1–3 item dihapus dari subtitle, kandidat,
  transkrip, ekspor, agenda, pekerjaan, dan riwayat pemakaian. Baris kandidat
  dan ekspor dirapatkan tanpa mengecilkan ukuran teks.
- Daftar proyek juga menghitung page_size permintaan server dari ruang tabel.
  Respons lama diabaikan jika ukuran layar/filter berubah saat request berjalan.
  Resize mempertahankan item acuan dalam halaman; penghapusan item membatasi
  nomor halaman agar tetap valid. Ponsel mempertahankan tampilan daftar normal.
- Pengujian aktual menunjukkan 4 cue subtitle pada tinggi 768 px dan 6 pada
  1080 px; daftar proyek memuat 6 baris pada 1366×768. Jumlah bergantung pada
  tinggi baris, pesan, dan ruang panel, bukan angka tetap.
- Typecheck/build, 36 tes web, dan 8 tes browser lulus. Uji ekspor menelusuri
  20 item tanpa duplikasi/terlewat, memeriksa ruang tersisa lebih kecil dari
  satu baris, serta resize dengan lebih banyak baris di layar tinggi. Tidak ada
  perubahan backend, database, atau lokasi media.

### Scroll hanya pada panel konten desktop (1 November 2026)

- Menggantikan pagination adaptif di atas: kandidat, transkrip, subtitle,
  ekspor, pekerjaan, agenda, dan riwayat pemakaian kini memakai ScrollList.
  Seluruh item yang sudah dimuat tersedia dalam panel yang dapat digulir;
  tombol muat berikutnya tetap mengambil halaman data tambahan dari server.
- Sidebar, preview, playback, toolbar, tombol Simpan/Ekspor, dan kalender
  tetap berada di tempat. Daftar proyek memakai area scroll dengan header
  tabel tetap terlihat dan pagination server 20 proyek per halaman.
- Panel mendukung scroll mouse dan keyboard. Batas posisi panel juga menahan
  label aksesibilitas subtitle agar fokus ke cue terakhir tidak memperbesar
  dokumen. Tampilan ponsel mempertahankan perilaku scroll responsif.
- Typecheck/build dan 36 tes web lulus. Delapan tes browser mencakup regresi
  editor, gaming, subtitle, pengaturan, kalender, dropdown, layout desktop,
  serta scroll ekspor/agenda. Uji layout terakhir memeriksa cue terakhir tetap
  dapat diedit, preview tidak bergeser, resize, dan viewport ponsel. Bukti
  visual ada di `.artifacts/desktop-layout/`. Tidak ada perubahan backend,
  migrasi database, atau penyimpanan media.

Lihat README untuk setup. Variabel testing harus menunjuk akun/database uji,
bukan data pengguna. `scripts/smoke_api.py` dan `scripts/smoke_transcription.py`
menyediakan smoke yang dapat dijalankan ulang. Suite browser ada di `tests/e2e`
dengan lockfile terpisah; petunjuk menjalankannya di README.

Seluruh source dan artefak tersedia lokal. Tidak ada Git repository awal dan
tidak dibuat commit/push/deploy publik. Layanan QA native sementara sudah
dihentikan. Instalasi Docker lokal dibiarkan berjalan untuk pengguna; proyek
smoke sudah dibersihkan dan kredensial/sesi QA dicabut. Bukti di `.artifacts`
dan cache alat di `.tools` serta `.runtime` tetap lokal dan diabaikan Git.
