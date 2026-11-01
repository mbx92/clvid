# Kontrak HTTP ringkas

Prefix `/api/v1`. Daftar endpoint dan schema input tersedia melalui OpenAPI
`/api/v1/openapi.json`; bentuk respons utama dijelaskan di bawah.
Semua endpoint workspace memerlukan cookie sesi. Untuk mutasi, ambil
`GET /auth/csrf`, lalu kirim `X-CSRF-Token` dengan cookie yang sama. Login
mengganti token CSRF; simpan token dari respons baru. Logout mencabut sesi.

Kalender sosial: `GET /social/accounts`, `GET /social/exports`,
`GET /social/posts?start=<ISO offset>&end=<ISO offset>` (maksimal 93 hari),
`POST /social/posts`, `PATCH /social/posts/{id}`, serta
`POST /social/posts/{id}/cancel|check|draft`. Input jadwal mencakup export_id,
platform, account_id opsional untuk draft, title, caption, scheduled_at dengan
offset, timezone IANA, status draft/scheduled, options, consent, request_key,
dan expected_version untuk perubahan. Jadwal disimpan UTC dan mengikat ekspor
yang dipilih. Idempotency key tidak boleh dipakai ulang untuk konten berbeda.

Koneksi memakai `POST /social/oauth/{platform}/start`, callback GET sekali pakai,
dan `DELETE /social/accounts/{id}`. Token/secret tidak pernah dikirim ke frontend.
`GET /social/accounts/{id}/creator-info` mengambil opsi TikTok terbaru. Hanya
`GET/HEAD /social/media/{post_id}` yang tidak memerlukan sesi: route ini wajib
memiliki signature/expiry valid, hanya untuk salinan video Instagram pada
publikasi aktif, dan bukan endpoint akses aset umum.

| Operasi | Input/hasil utama |
| --- | --- |
| `GET /auth/csrf` | `{csrf_token}` dan cookie CSRF; dapat memulihkan cookie CSRF yang hilang pada sesi aktif |
| `POST /auth/login` | `{email,password}` → `{id,email,csrf_token}` |
| `GET /auth/me` | `{id,email,csrf_token}` atau HTTP401 |
| `POST /auth/logout` | HTTP204, mencabut sesi dan menghapus cookie |
| `GET /projects` | `search,status,page,page_size` → `{items,total,page,page_size}` |
| `POST /projects` | `{name}` → project |
| `GET /projects/{id}` | project, aset, versi transkrip terbaru, active_jobs, dan riwayat jobs |
| `PATCH /projects/{id}` | `{name}` |
| `POST /projects/{id}/source` | body byte MP4 mentah, bukan multipart; `Content-Type: video/mp4`, opsional `X-Filename` percent-encoded → HTTP202 job |
| `POST /projects/{id}/source-url` | `{url}` HTTP/HTTPS publik → HTTP202 job `import_url`; menerima `Idempotency-Key`, tidak dapat berjalan bersamaan dengan upload/impor sumber lain |
| `POST /projects/{id}/process` | `{language: auto/id/en,count,min_duration_ms,max_duration_ms,analyze,transcribe_again}` → HTTP202 job |
| `GET /projects/{id}/transcripts/{version}` | integer versi atau `latest`; `search,page,page_size`; `{id,version,segments,total,...}` |
| `POST /projects/{id}/clips` | `{title,start_ms,end_ms,transcript_id?,crop_json?,subtitle_style_json?,cues?}` |
| `GET /projects/{id}/clips` | `page,page_size` → `{items,total,page,page_size}` |
| `GET /clips/{id}` | clip dan snapshot revisi aktif, aset sumber/preview, durasi media, `tracking_signatures:{face,speaker}` untuk versi analisis aktif |
| `GET /clips/{id}/subtitle-words` | query `start_ms,end_ms` batas draft; `{source_words:[{word,start_ms,end_ms}]}` dari versi transkrip revisi aktif, waktu absolut sumber |
| `PATCH /clips/{id}` | `{expected_revision,title?,start_ms?,end_ms?,crop_json?,subtitle_style_json?,cues?}` → clip dengan revision baru |
| `POST /clips/{id}/tracking-preview` | `{start_ms,end_ms,crop_json:{mode:"fill",tracking:"face"\|"speaker",x,y}}` → HTTP202 job `track_preview`; menerima draft dan `Idempotency-Key`, tanpa revisi/ekspor baru |
| `POST /clips/{id}/exports` | `{revision,resolution:720/1080}` → HTTP202 job |
| `GET /projects/{id}/exports` | `page,page_size,clip_id?` → `{items,total,page,page_size}`, setiap hasil menyebut revision dan MP4/SRT asset |
| `GET /jobs/{id}` | status, stage, progress nullable (0–1), attempt, timestamps, error |
| `POST /jobs/{id}/retry` | retry tahap yang sama, dibatasi attempts |
| `POST /jobs/{id}/cancel` | HTTP202, queued langsung cancelled; running cancel_requested |
| `DELETE /projects/{id}` | HTTP202 job delete_assets; akses dicabut langsung |
| `GET/HEAD /assets/{id}/content` | private Range/HEAD; `?download=true` attachment |
| `GET /settings`, `GET /usage` | nonsecret configuration, layanan, token/storage |
| `PATCH /settings` | `{max_video_seconds,max_upload_bytes,max_clip_ms}` integer, menyimpan batas akun dan mengembalikan settings |

`PATCH /settings` memerlukan sesi dan CSRF. Rentang: sumber 60–43200 detik,
file 1048576–68719476736 byte, klip 5000–600000 ms; durasi klip tidak boleh
melebihi batas sumber. `GET /settings` mencakup `settings_scope: "account"`,
`editable_ranges`, dan batas efektif. Detail proyek/klip menyertakan
`limits:{min_clip_ms,max_clip_ms}` untuk UI. Klip lama tetap dapat diedit sampai
durasi tersimpannya bila batas akun diturunkan. Job menyimpan snapshot batas
sumber/file; retry job gagal atau dibatalkan mengambil batas akun terbaru.
Jika impor/validasi gagal karena batas durasi atau ukuran dan jumlah percobaan
sudah habis, kenaikan batas yang menyebabkan kegagalan mengizinkan satu retry
manual tambahan. Snapshot diperbarui saat antrean dibuat; batas yang sama tidak
membuka retry berulang, dan nomor/riwayat percobaan tidak direset.

Pembuatan job serta retry/cancel menerima `Idempotency-Key` maksimal128 karakter.
Key yang sama dengan parameter berbeda pada operasi yang sama menghasilkan409.
Job fingerprint sama juga dideduplikasi ketika key berbeda; seluruh alias key
disimpan. Retry dengan key yang sudah dipakai mengembalikan status aktual tanpa
menambah percobaan lagi. Untuk percobaan baru setelah kegagalan berikutnya,
gunakan key baru. Project detail mengandung `source_asset`, `preview_asset`,
`active_jobs`, dan `jobs`; metadata aset berada di field `metadata`.

Daftar proyek memakai default25 item (maksimum100). Klip dan ekspor default100
(maksimum200), segmen transkrip default100 (maksimum1000). Nomor halaman mulai1.
`GET /usage` menghitung token seluruh riwayat pemilik; `items` memuat100 panggilan
terakhir. Tanpa tarif yang dikonfigurasi, `currency_cost` tetap `null`.

Clip memuat `revision` sebagai objek dengan nomor integer `revision`, title,
start/end_ms sumber, cue lokal, dan konfigurasi.
Crop satu panel: `{mode:"fill"|"fit",tracking:"static"|"face"|"speaker",x:0.5,y:0.5}`.
Tracking default `static`; revisi lama yang tidak memiliki field tersebut tetap
manual. Pelacakan hanya aktif pada `fill`; `x,y` menjadi posisi fallback.
Ekspor menjalankan tahap `track_faces` sebelum `render` bila dipilih. Metadata
`mp4_asset.metadata.framing` memuat mode, keyframes, cakupan deteksi,
`fallback_reason` dan `warnings`. `face` mempertahankan satu wajah terlihat;
`speaker` memakai model audiovisual Light-ASD untuk memperkirakan pembicara
aktif, bukan diarization atau identitas seseorang. Metode saat ini
`yunet-face-v1` dan `yunet-light-asd-v1`. Mode speaker juga menyimpan
`speaker_model_sha256`, `speaker_sample_fps:25`, `speaker_switches`,
`speaker_seconds` dan `speaker_scored_frames` (jumlah waktu sampel unik dengan
sedikitnya satu wajah berskor, maksimal `total_frames`). Jumlah switch menghitung handoff yang dipilih selector,
bukan jumlah orang, hard cut adegan, atau bukti akurasi.

Crop gaming memakai satu sumber dengan dua area statis:

```json
{
  "mode": "gaming",
  "tracking": "static",
  "x": 0.5,
  "y": 0.5,
  "gaming": {
    "facecam": { "x": 0.75, "y": 0, "width": 0.25, "height": 0.25 },
    "gameplay": { "x": 0, "y": 0, "width": 1, "height": 1 },
    "facecam_height": 0.28,
    "facecam_fit": "fill",
    "gameplay_fit": "fit"
  }
}
```

Kedua area wajib berada dalam koordinat display sumber yang sudah tegak dan
square-pixel, dinormalisasi 0–1. Lebar/tinggi minimal 0,02; area boleh saling
tumpang tindih. `facecam_height` adalah porsi tinggi output, rentang 0,15–0,45.
Facecam selalu di atas. `fit` menampilkan seluruh area dengan padding; `fill`
memotong tengah area untuk memenuhi panel. Nilai default adalah facecam `fill`,
gameplay `fit`, dan tinggi 0,28. Mode gaming menolak pelacakan wajah/pembicara,
dan konfigurasi `gaming` tidak boleh disertakan pada mode lain. Payload lama
tetap diserialisasi tanpa field gaming tambahan.

Preview gaming dihitung di browser tanpa endpoint analisis. Render hanya
memakai revisi tersimpan; `gaming_layout_version` ikut dalam identitas job.
Metadata framing mencatat `layout:"gaming"`, `method:"gaming-layout-1"`,
konfigurasi area, ukuran display sumber, serta tinggi panel hasil pembulatan.
Tidak ada pelacakan wajah atau deteksi intensitas game pada jalur ini.

Preview tracking menerima batas draft mulai 5 detik hingga batas klip akun (maksimal 600 detik) di dalam sumber yang sudah
ready. Job memakai tahap `track_faces`; setelah berhasil, `result_json` memuat
`tracking_spec` dan `framing`. Spec mencakup ID/checksum sumber dan preview,
batas waktu, crop, versi algoritma/pipeline, sample fps, `model_sha256`,
`speaker_model_sha256` (null untuk face), dan `algorithm_signature`. Signature
harus cocok dengan `clip.tracking_signatures[mode]`, selain input draft.
Versi analisis saat ini `tracking-preview-2`; perubahan algoritma atau bobot
mengganti identitas cache. Permintaan
identik dalam proyek yang sama mengembalikan job yang sama, termasuk setelah
draft disimpan atau dipakai klip lain. Editor harus menolak respons terlambat
yang tidak sesuai draft saat ini, dan tidak otomatis membatalkan job bersama.

Ekspor memakai kembali analisis berhasil dengan spec yang cocok dan mencatat
`mp4_asset.metadata.framing.analysis_reused`. Hasil sah tanpa wajah tetap
berhasil dengan alasan fallback manual. Kegagalan model/proses menjadi job
`failed` dengan `tracking_unavailable`, dapat diulang lewat endpoint retry.
`tracking_input_changed` meminta analisis baru jika sumber/model berubah.
Kegagalan preview tidak membuat proyek gagal; penghapusan proyek membersihkan
input dan hasil analisis dari job.
Style: `{enabled:true,font_size:52,position:"bottom"|"top",background:true,safe_margin:0.15}`.
Field tambahan opsional: `auto_fit:true`, `bold:false`, `italic:false`,
`uppercase:false`, `text_color:"#FFFFFF"`, `outline_color:"#111111"`,
`outline_width:2.5`, `shadow:0`, `background_color:"#000000"`.
Warna wajib `#RRGGBB`; outline dan bayangan 0–8 pada ukuran output1080.
Background memakai kotak dengan opacity tetap; saat aktif outline digantikan
kotak latar. Gaya kapital tidak mengubah cue tersimpan atau teks SRT.
`display_mode:"sentence"|"words"` (default sentence) mengatur tampilan lengkap
atau kata berdasarkan timestamp asli. Respons revisi mencakup `source_words`
read-only untuk rentang klip; endpoint subtitle-words menyediakan rentang draft
setelah trim dengan ownership dan validasi batas yang sama. Worker membentuk
event kata dari versi transkrip yang dipatok revisi. Kata/tanda baca dan
kapitalisasi cue dipertahankan; token transkripsi hanya digabung jika teks
normalisasinya sama persis. Jeda suara tetap kosong. Cue tanpa timing yang cocok
menghasilkan422 `SUBTITLE_WORD_TIMING` sebelum render. Koreksi draft tetap bisa
disimpan. MP4 memakai event kata, SRT tetap memakai cue lengkap.
Font size mengacu output1080 dan diskalakan pada720. Cue:
`{start_ms,end_ms,text}`. Bila `cues` tidak dikirim pada trim, backend memindahkan
cue lama melalui koordinat sumber dan mempertahankan teks koreksi.
Pembuatan klip dari transkrip dapat memecah segmen panjang memakai word timestamps
asli. `auto_fit:true` mempertahankan dua baris dengan ukuran efektif yang
diperkecil bila perlu. `auto_fit:false` memakai ukuran persis dan membungkus
hingga empat baris. Ekspor burn-in memvalidasi batas baris; cue terlalu panjang
menghasilkan422 `SUBTITLE_TOO_LONG` sebelum job dibuat. Draft tidak dihapus.

Error konsisten `{code,message,correlation_id}` tanpa stack trace atau echo
password. Unauthorized401, CSRF403, objek milik orang lain404, konflik409,
ukuran413, validasi422, batas antrean/login429, dan disk507.

Impor URL berjalan di heavy worker dengan tahap `import_url` → `validate` →
`prepare_preview` bila diperlukan. Status proyek awal `importing`, kemudian
`validating` dan `ready`/`failed`. Progress unduh dapat `null` tanpa persentase
buatan. Metadata `source_asset.imported_from_url` berada di objek `metadata`.
Kesalahan URL/situs dilaporkan lewat job tanpa URL mentah atau respons provider.
Hanya URL satu video publik; port80/443, tanpa userinfo, cookie browser, DRM,
siaran langsung atau playlist. Retry impor lama ditolak jika video baru sudah ada.

Job transkripsi yang selesai juga memuat `result_json.runtime`: perangkat dan compute
type aktual, batch size, CPU threads, beam size, waktu model/inference/total,
serta `fallback_reason` bila `auto` beralih ke CPU. Nilai progress berasal dari
timestamp segmen, bukan perkiraan berbasis waktu tunggu.
