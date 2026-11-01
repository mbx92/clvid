# PRD — AI Video Clipper

Versi: 1.0  
Tanggal: 1 November 2026  
Status: spesifikasi MVP untuk implementasi melalui Codex lokal  
Nama kerja: Clipper — boleh diganti tanpa mengubah cakupan  
Bahasa produk: Indonesia

> Dokumen ini adalah spesifikasi pembangunan, bukan laporan fitur yang sudah tersedia. Codex harus mengimplementasikan alur pemrosesan video nyata, menguji hasilnya, dan melaporkan keterbatasan secara jujur.

## 1. Ringkasan produk

Aplikasi web untuk mengubah video podcast, wawancara, dan edukasi menjadi beberapa kandidat klip pendek. Pengguna mengunggah video, memperoleh transkrip dan rekomendasi potongan, meninjau serta mengedit hasil, kemudian mengekspor MP4 vertikal dengan subtitle.

Nilai utama produk adalah mengurangi waktu mencari momen dan melakukan editing berulang. Produk tidak menjanjikan viral, jumlah tayangan, atau penghasilan. Rekomendasi AI membantu keputusan editorial; pengguna menentukan hasil akhir.

MVP ditujukan untuk penggunaan pribadi atau tim kecil pada satu instalasi. Arsitektur menyimpan kepemilikan data per pengguna agar pengembangan berikutnya tidak memerlukan perubahan mendasar.

## 2. Keputusan yang sudah ditetapkan

| Area | Keputusan |
|---|---|
| Frontend | Nuxt, Vue, TypeScript |
| Styling | Tailwind CSS v4; komponen aplikasi custom; tidak memakai Nuxt UI |
| Ikon | Lucide; satu keluarga ikon; tidak memakai emoji |
| Backend | Python FastAPI |
| Database | PostgreSQL; SQLAlchemy dan Alembic |
| Background processing | Celery dengan Redis sebagai broker |
| Transkripsi | faster-whisper lokal; CPU sebagai konfigurasi awal |
| Analisis teks | DeepSeek API; model dan base URL dapat dikonfigurasi |
| Media | FFmpeg dan FFprobe pada worker |
| Storage MVP | Filesystem melalui named volume Docker; backend storage memiliki interface untuk perluasan S3 |
| Deployment | Satu repository, Docker Compose |
| Akses awal | Login; akun awal dibuat melalui CLI lokal; registrasi publik tidak tersedia |
| Input awal | Upload file MP4 dari perangkat |
| Output awal | MP4 H.264/AAC, vertikal 9:16; subtitle burn-in opsional dan file SRT |
| Bahasa awal | Indonesia dan Inggris; opsi deteksi otomatis |

Pin versi dependensi yang kompatibel saat implementasi; sertakan lockfile. Jangan menggunakan tag image `latest` untuk deployment yang ingin direproduksi. Nomor versi patch dan identifier model DeepSeek harus diverifikasi saat implementasi, bukan ditebak dari dokumen ini.

## 3. Pengguna dan pekerjaan utama

### 3.1 Pengguna sasaran

- Kreator dengan video panjang yang ingin membuat konten pendek.
- Editor yang mengerjakan konten podcast atau wawancara secara rutin.
- Pemilik aplikasi yang ingin menguji efisiensi pipeline sebelum mengembangkan produk berlangganan.

### 3.2 User stories

| ID | Kebutuhan |
|---|---|
| US-01 | Saya dapat mengunggah video dan mengetahui apakah file dapat diproses. |
| US-02 | Saya dapat meninggalkan halaman lalu kembali tanpa kehilangan pekerjaan di server. |
| US-03 | Saya dapat membaca transkrip dan melompat ke waktu ucapan. |
| US-04 | Saya mendapat kandidat klip dengan alasan pemilihan yang dapat dipahami. |
| US-05 | Saya dapat mengubah batas klip, subtitle, dan framing sebelum export. |
| US-06 | Saya dapat membuat klip manual meskipun hasil rekomendasi AI kurang sesuai. |
| US-07 | Saya dapat mengunduh hasil atau mengulang tahap yang gagal tanpa mengulang semuanya. |
| US-08 | Saya dapat menghapus proyek beserta seluruh asetnya. |

## 4. Sasaran dan cara mengukur manfaat

### 4.1 Target fungsional

Satu video Indonesia dapat melewati upload, validasi, transkripsi, rekomendasi, review, render, dan download tanpa perpindahan ke aplikasi lain.

### 4.2 Evaluasi pilot

Gunakan sedikitnya tiga video milik pengguna: satu pembicara, dua pembicara, dan audio dengan gangguan ringan. Untuk perbandingan editing manual, gunakan brief serta standar kelayakan yang sama dan catat waktu review, koreksi, serta waktu tunggu secara terpisah.

| Metrik | Definisi | Target awal, bukan jaminan |
|---|---|---|
| Waktu kerja aktif | Waktu memilih, mengoreksi, dan menyiapkan hasil | Median berkurang sedikitnya 30% dibanding workflow manual pada sampel pilot |
| Kandidat layak | Kandidat yang bisa dipakai setelah koreksi ringan / seluruh kandidat | Dicatat dahulu; belum menetapkan klaim akurasi |
| Keberhasilan export | Render yang berhasil / render yang dimulai | Seluruh fixture valid pada acceptance suite berhasil |
| Kualitas subtitle | Kesalahan kata, keterbacaan, dan timing pada sampel | Tidak ada subtitle di luar durasi klip; koreksi teks dapat dilakukan |
| Biaya | Token API, waktu CPU/GPU, ukuran aset per proyek | Terukur; jangan menampilkan estimasi rupiah jika tarif belum dikonfigurasi |

Kecepatan transkripsi tidak ditetapkan sebagai klaim universal. Laporkan perangkat, model, durasi media, dan waktu proses aktual. Satu video sukses tidak cukup untuk menyimpulkan manfaat bisnis.

## 5. Cakupan MVP dan batasannya

### 5.1 Wajib tersedia

1. Login, logout, sesi aman, dan isolasi proyek per pengguna.
2. Daftar proyek, pencarian nama, filter status, dan penghapusan.
3. Upload video, validasi metadata, dan progress upload yang nyata.
4. Antrean persisten, status per tahap, retry, serta cancellation.
5. Transkrip dengan timestamp, pencarian teks, dan navigasi ke waktu video.
6. Rekomendasi kandidat klip menggunakan DeepSeek.
7. Penjelasan singkat mengapa setiap kandidat dipilih.
8. Pembuatan klip manual dari transkrip atau batas waktu.
9. Preview, trim awal/akhir, edit subtitle, dan pengaturan crop manual.
10. Pengaturan subtitle sederhana dan export MP4/SRT.
11. Riwayat export per revisi klip dan download file yang sudah siap.
12. Halaman pengaturan nonrahasia, status layanan, dan informasi pemakaian dasar.

### 5.2 Di luar MVP

- Auto-tracking wajah/pembicara, diarization lanjutan, dan split-screen otomatis.
- Video generatif, avatar, dubbing, voice cloning, dan B-roll otomatis.
- Subtitle karaoke per kata dan motion graphics kompleks.
- Editor multi-track seperti Premiere atau CapCut.
- Import YouTube/TikTok melalui URL dan download media pihak ketiga.
- Auto-publish ke media sosial, penjadwalan posting, serta analitik tayangan.
- Billing, paket berlangganan, marketplace, organisasi, dan kolaborasi realtime.
- Janji atau label persentase “peluang viral”.
- S3/MinIO production adapter, multi-host worker, dan autoscaling.

Jangan membangun fitur tahap berikutnya hanya agar dashboard terlihat penuh. Jangan menambah landing page marketing ke MVP.

## 6. Alur pengguna

### 6.1 Membuat proyek

1. Pengguna login dan membuka halaman Proyek.
2. Memilih “Proyek baru”, memberi nama, lalu mengunggah video.
3. Sistem menampilkan nama file, ukuran, progress transfer, dan tombol batal.
4. Setelah upload lengkap, backend melakukan validasi metadata melalui job.
5. Pengguna memilih bahasa, jumlah kandidat, dan rentang durasi.
6. Pengguna memilih “Buat kandidat”. Sistem menjalankan transkripsi lalu analisis.
7. Kandidat muncul setelah tersedia; pengguna dapat meninjau transkrip terlebih dahulu jika analisis gagal.

### 6.2 Meninjau dan mengedit

1. Buka kandidat dari daftar; preview berpindah ke rentang yang dipilih.
2. Lihat judul internal, timecode, transkrip, serta alasan pemilihan.
3. Ubah in/out dengan input timecode, drag handle, atau tombol “Gunakan posisi sekarang”.
4. Perbaiki teks subtitle dan atur framing video.
5. Pilih “Simpan”. Tampilkan status belum tersimpan, menyimpan, tersimpan, atau gagal secara jelas.
6. Pilih “Ekspor”; export menggunakan snapshot revisi terakhir yang tersimpan.

Judul kandidat adalah nama internal. Jangan otomatis membakarnya menjadi headline pada video. Subtitle menampilkan ucapan, bukan ringkasan yang dibuat model.

### 6.3 Mengunduh dan menghapus

- Export yang selesai memiliki tombol “Unduh MP4” dan “Unduh SRT”.
- Export sebelumnya tetap tersedia ketika revisi baru sedang dirender.
- Penghapusan proyek menggunakan dialog custom yang menyebut nama proyek dan aset yang akan dihapus.
- Selama penghapusan, proyek tidak menerima pekerjaan baru; server membatalkan pekerjaan aktif sebelum membersihkan aset.

## 7. Spesifikasi fungsi

### F-01 — Akun dan sesi

- Bootstrap akun pertama melalui CLI interaktif; tidak ada password bawaan dalam repository.
- Email/username unik dan password di-hash dengan Argon2id.
- Gunakan sesi server-side dengan cookie HttpOnly, SameSite=Lax, dan Secure ketika HTTPS.
- Sediakan perlindungan CSRF untuk operasi mutasi, rate limit login, logout yang mencabut sesi, dan masa berlaku sesi.
- Password recovery MVP melalui CLI lokal; tidak perlu layanan email.
- Setiap query proyek, job, clip, dan asset memeriksa kepemilikan di backend.

### F-02 — Upload dan validasi media

- Default batas: 2 GiB per file, 60 menit per video, dan maksimal 3840×2160 atau orientasi setara. Semua dapat diubah melalui konfigurasi.
- MP4 adalah container yang diterima; kompatibilitas ditentukan FFprobe dan decoder yang tersedia, bukan ekstensi saja.
- Validasi ukuran saat streaming dan metadata setelah upload. Jangan membaca seluruh video ke RAM.
- Tulis ke file sementara dengan nama acak; rename atomik hanya setelah upload selesai.
- Simpan durasi, codec, dimensi, rotation, frame rate, audio stream, dan ukuran.
- Tolak file korup, durasi nol, tidak memiliki audio untuk transkripsi, atau melebihi limit dengan pesan yang spesifik.
- Video tanpa ucapan yang terdeteksi menghasilkan status “Tidak ditemukan ucapan”, bukan kandidat buatan.
- File valid tetapi tidak kompatibel untuk playback browser dibuatkan proxy preview H.264/AAC. Render akhir tetap bersumber dari aset asli.
- Upload terputus harus dapat diulang dari awal dengan pesan jelas; resumable upload belum wajib.
- Bersihkan upload parsial kedaluwarsa dan periksa ruang disk sebelum menerima pekerjaan berat.

### F-03 — Transkripsi

- Default konfigurasi awal: model Whisper multilingual `small`, CPU, komputasi int8. Nilai ini dapat diubah setelah benchmark kualitas Indonesia.
- Simpan segmen, waktu mulai/akhir, serta word timestamps bila tersedia.
- Jangan memakai varian English-only untuk input Indonesia.
- Jalankan VAD yang sesuai dan tangani hasil kosong tanpa melanjutkan analisis AI.
- Transkrip asli disimpan sebagai versi immutable; koreksi subtitle klip tidak mengubah transkrip sumber.
- Jika transkripsi dijalankan ulang, buat versi baru. Klip lama tetap merujuk versi semula.
- Untuk MVP, koreksi dilakukan pada subtitle klip. Editor transkrip sumber menyeluruh bukan syarat rilis.
- Tidak menjanjikan pemisahan pembicara pada audio tumpang tindih.

### F-04 — Rekomendasi klip

- Default permintaan: sampai 5 kandidat dengan durasi sasaran 30–60 detik.
- Jumlah dan rentang durasi dapat diubah; batas editor MVP 5–180 detik.
- Kirim teks dan ID segmen ke DeepSeek, bukan file video/audio.
- Model mengembalikan ID segmen awal/akhir, judul internal, alasan, dan ringkasan topik dalam JSON.
- Timestamp akhir dihitung backend dari segmen asli. Jangan mempercayai timestamp karangan model.
- Beri konteks sebelum/sesudah segmen agar jawaban tidak kehilangan pertanyaan atau kesimpulan.
- Untuk transkrip panjang, chunk berdasarkan anggaran token model dengan overlap segmen; lakukan penggabungan dan deduplikasi hasil lintas chunk.
- Validasi ID, urutan segmen, rentang durasi, keberadaan teks, dan batas media.
- Kandidat yang sangat tumpang tindih, misalnya intersection-over-union waktu >0,7, disaring kecuali ada alasan editorial yang berbeda.
- Jika hanya 2 kandidat valid, tampilkan 2 dengan penjelasan. Jangan membuat 5 kandidat buruk hanya untuk memenuhi jumlah.
- Hindari potongan yang terhenti sebelum kesimpulan atau mengubah makna. Hal ini tetap diperiksa pengguna karena validasi programatis tidak menjamin makna.
- Tidak menampilkan skor viral. Urutan rekomendasi dan alasan editorial sudah cukup.
- Jika AI gagal, pertahankan transkrip dan sediakan retry analisis atau klip manual.

Contoh kontrak semantik respons model:

```json
{
  "clips": [
    {
      "start_segment_id": "seg_0042",
      "end_segment_id": "seg_0050",
      "title": "Kesalahan menentukan harga",
      "reason": "Memuat masalah, contoh, dan kesimpulan yang dapat dipahami sendiri.",
      "topic": "Penetapan harga"
    }
  ]
}
```

Schema harus divalidasi dengan Pydantic. ID di atas hanya contoh dokumentasi, bukan data seed untuk UI.

### F-05 — Editor klip

- Panel utama: preview video, kontrol playback, strip waktu untuk satu rentang klip.
- Panel teks: subtitle cue yang dapat diedit dan waktu cue.
- Panel pengaturan: framing, subtitle, dan output.
- Pengguna dapat membuat klip manual; pilih rentang transkrip atau masukkan waktu.
- Sistem memastikan `0 ≤ start < end ≤ duration` dan menerapkan batas durasi.
- Timestamp internal menggunakan integer milidetik; konversi ke detik hanya pada boundary media/API bila diperlukan.
- Perubahan batas klip memotong/menggeser cue secara deterministik. Jangan diam-diam menghapus koreksi teks; jika regenerasi cue diperlukan, minta keputusan lewat dialog custom.
- Simpan revisi dengan nomor versi. Pembaruan dari tab lama ditolak dengan konflik yang dapat diselesaikan pengguna, bukan menimpa diam-diam.
- Berpindah halaman saat ada perubahan belum tersimpan menampilkan dialog aplikasi. Browser dapat menampilkan peringatan bawaannya untuk penutupan tab/reload jika dipasang `beforeunload`; jangan menjanjikan custom dialog pada tindakan yang dikendalikan browser. MVP boleh mengandalkan indikator tersimpan dan dokumentasi batas ini.
- Shortcut: Space untuk playback ketika fokus di area player; I/O untuk batas masuk/keluar saat fokus editor. Jangan menangkap shortcut saat pengguna mengetik atau berada di dialog.

### F-06 — Framing dan subtitle

- Output 9:16 dengan dua mode: “Isi frame” melalui crop dan “Tampilkan seluruh video” melalui letterbox solid.
- Crop manual menggunakan koordinat ternormalisasi; satu posisi crop berlaku sepanjang klip MVP.
- Tampilan preview dan render harus menggunakan perhitungan aspect ratio, rotation, dan crop yang sama.
- Pilihan subtitle MVP: aktif/nonaktif, ukuran, posisi bawah/atas, serta gaya polos atau dengan latar gelap.
- Default subtitle: putih, outline atau latar gelap untuk kontras, maksimal dua baris; font dibundel dengan lisensi yang sesuai.
- Default safe inset: 10% sisi kiri/kanan dan 15% dari bawah. Ini preset aplikasi, bukan klaim aman untuk semua platform; posisi dapat disesuaikan.
- Cue lokal klip dihitung dari timestamp sumber dikurangi awal klip, lalu di-clamp ke durasi output.
- Memanjangkan teks cue tidak otomatis mengarang timing per kata. MVP menggunakan caption per cue.
- Escape karakter ASS/SRT dan path agar input teks tidak menjadi instruksi filter atau shell.
- Preview browser adalah pendekatan; sediakan preview file render final sebagai acuan authoritative untuk font wrapping dan timing.

### F-07 — Render dan export

- Default export: 1080×1920, 30 fps, H.264 dengan pixel format kompatibel browser, audio AAC, dan faststart.
- Pilihan 720×1280 untuk export lebih ringan.
- Jangan mengeklaim peningkatan detail ketika sumber beresolusi rendah; beri keterangan bahwa video diperbesar.
- Trim dengan decode/re-encode untuk ketepatan batas; stream copy tanpa penyesuaian keyframe tidak memenuhi kebutuhan edit presisi.
- Tangani input variable frame rate, rotation metadata, dan sample aspect ratio.
- Burn-in menggunakan ASS/libass; SRT dapat diunduh terpisah meski burn-in dimatikan.
- Volume audio sumber dipertahankan secara default; musik tambahan dan normalisasi agresif bukan fitur MVP.
- Tulis output sementara, validasi hasil dengan FFprobe, baru tandai export siap.
- Render mengunci snapshot clip revision, style, dan versi pipeline. Edit setelah render dimulai tidak mengubah output yang sedang dikerjakan.
- UI membedakan “Hasil revisi 2” dari “Revisi 3 belum diekspor”.
- Gunakan progress FFmpeg bila tersedia. Tidak boleh memakai timer palsu untuk menunjukkan kemajuan.

### F-08 — Status, retry, dan cancellation

- PostgreSQL adalah sumber status resmi. Redis bukan satu-satunya tempat menyimpan hasil atau riwayat job.
- Job memiliki state `queued`, `running`, `cancel_requested`, `succeeded`, `failed`, atau `cancelled`.
- Stage: `validate`, `prepare_preview`, `transcribe`, `analyze`, `render`, dan `delete_assets`.
- Status proyek merupakan ringkasan; setiap render tetap memiliki status sendiri. Gagalnya satu export tidak membuat seluruh proyek tidak dapat digunakan.
- UI melakukan polling sekitar 3 detik hanya ketika ada job aktif; hentikan polling agresif saat tab tersembunyi.
- Tampilkan tahap, waktu mulai, dan antrean bila diketahui. Gunakan indikator tak tentu ketika persentase tidak dapat dihitung.
- Satu heavy worker, concurrency 1, dan prefetch 1 sebagai konfigurasi CPU awal.
- Analisis API dan cleanup dapat memakai worker ringan terpisah; jangan membiarkan dua transkripsi berat berjalan tanpa batas.
- Timeout, heartbeat, lease, dan batas retry harus eksplisit serta configurable.
- Job yang kehilangan worker tidak boleh selamanya “running”; reconciler memeriksa lease dan menerapkan retry aman atau failure.
- Cancellation bersifat kooperatif. Untuk FFmpeg, hentikan subprocess group secara bertahap; untuk transkripsi, isolasikan proses agar dapat dihentikan. Jangan sekadar mengganti label UI sementara CPU terus bekerja.
- Pembatalan panggilan eksternal tidak menjamin biaya provider berhenti; jangan menjanjikan refund otomatis.

### F-09 — Pengaturan dan penggunaan

- Halaman pengaturan memperlihatkan bahasa default, batas upload, model transkripsi, device, dan status konfigurasi AI.
- Secret DeepSeek hanya melalui environment backend. UI menampilkan “Terkonfigurasi” atau “Belum dikonfigurasi”, tidak mengembalikan key.
- Jangan meminta pengguna menempelkan key ke chat, source code, atau frontend.
- Simpan jumlah token jika provider mengembalikannya, latensi, outcome, dan provider request ID bila tersedia.
- Biaya uang hanya dihitung dari tarif konfigurasi dengan tanggal berlaku; tanpa tarif tampilkan token, bukan angka uang rekaan.
- UI upload menjelaskan singkat: “Transkripsi diproses di server ini. Teks transkrip dikirim ke penyedia AI untuk memilih kandidat.”

## 8. Arah UI dan aturan anti-UI-slop

### 8.1 Karakter visual

Produk harus terasa seperti alat kerja editorial yang tenang, padat secukupnya, dan mudah dipakai berulang kali. Fokus visual berada pada video dan teks, bukan dekorasi tentang AI.

Tema awal: light theme dengan latar abu-abu hangat, permukaan putih, teks gelap, dan satu warna aksen biru kusam. Dark theme bukan syarat MVP.

### 8.2 Design tokens awal

| Token | Nilai awal | Penggunaan |
|---|---|---|
| `--color-canvas` | `#F5F5F2` | Latar aplikasi |
| `--color-surface` | `#FFFFFF` | Panel dan dialog |
| `--color-surface-muted` | `#ECEDE9` | Area sekunder dan hover |
| `--color-text` | `#202420` | Teks utama |
| `--color-text-muted` | `#626963` | Teks sekunder |
| `--color-border` | `#D9DDD7` | Separator dan batas panel |
| `--color-accent` | `#355D78` | Tombol utama, selection, focus |
| `--color-danger` | `#A33434` | Aksi destruktif dan error |
| `--radius-control` | `6px` | Input dan tombol |
| `--radius-panel` | `8px` | Panel dan dialog |

Nilai di atas adalah titik awal desain. Verifikasi kontras WCAG AA pada pasangan warna aktual; jangan menganggap semua kombinasi sudah memenuhi kontras. Gunakan border lebih kuat untuk input bila dibutuhkan.

- Font utama: system sans-serif. Tidak bergantung pada font CDN untuk penggunaan lokal.
- Teks isi 14–16 px; label 12–13 px; judul halaman 24–28 px.
- Timecode dan angka memakai tabular numerals; monospace hanya untuk timecode atau data teknis yang relevan.
- Skala spacing: 4, 8, 12, 16, 24, 32 px.
- Tinggi kontrol desktop sekitar 36–40 px dengan target interaksi yang diperluas bila perlu; perangkat sentuh minimal 44 px.
- Shadow hanya untuk overlay/popover/dialog yang memerlukan pemisahan layer.
- Lucide ukuran 16–20 px, stroke konsisten; ikon menambah informasi atau membantu aksi.

### 8.3 Larangan yang wajib ditaati

1. Tidak memakai gradient ungu-biru, mesh gradient, glassmorphism, glow, atau neon.
2. Tidak memakai emoji, ikon sparkle/magic-wand sebagai dekorasi AI, maskot, atau orb animasi.
3. Tidak membuat hero “Transform your content with AI” di dalam dashboard.
4. Tidak membuat kartu statistik seperti “AI Power”, “Viral Potential”, atau angka dummy untuk memenuhi ruang.
5. Tidak membuat setiap informasi menjadi rounded card terpisah. Gunakan baris, tabel, separator, dan panel jika lebih tepat.
6. Tidak memakai border radius raksasa, tombol pill untuk semua aksi, atau shadow pada setiap elemen.
7. Tidak memasang gradient pada teks, heading berlebihan, label uppercase berjarak lebar, atau slogan abstrak.
8. Tidak menambahkan grafik tanpa data atau alasan kerja yang jelas.
9. Tidak memakai sidebar berisi banyak menu nonaktif, upsell, badge “Pro”, atau fitur palsu.
10. Tidak memakai mock content di mode normal sehingga aplikasi terlihat bekerja padahal backend belum terhubung.
11. Tidak memakai spinner tanpa keterangan untuk pekerjaan panjang atau persentase kemajuan yang dibuat-buat.
12. Tidak memakai `window.alert`, `window.confirm`, atau `window.prompt` untuk alur aplikasi.

### 8.4 Struktur halaman

**Proyek**

- Sidebar desktop ringkas: nama produk, Proyek, Pengaturan, dan akun di bawah.
- Header halaman: “Proyek” di kiri, tombol “Proyek baru” di kanan.
- Baris pencarian serta filter status tepat di atas daftar.
- Desktop menggunakan tabel: thumbnail kecil, nama, durasi, status, waktu diperbarui, dan menu aksi.
- Mobile menggunakan daftar baris bertumpuk, bukan tabel horizontal yang sulit dibaca.
- Empty state: teks pendek “Belum ada proyek” dan satu tombol upload; tanpa ilustrasi dekoratif.

**Detail proyek**

- Breadcrumb, nama proyek, dan status proses.
- Metadata file dan aksi utama diletakkan dekat konteksnya.
- Tab “Kandidat”, “Transkrip”, dan “Ekspor”.
- Kandidat berupa baris dengan thumbnail, durasi, judul, alasan pendek, dan aksi “Tinjau”.
- Tidak ada dashboard KPI di atas daftar kandidat.

**Editor klip**

- Header: kembali ke proyek, nama klip, status simpan, tombol “Simpan”, dan “Ekspor”.
- Desktop lebar: area preview/workspace sekitar 60–65%, panel teks/pengaturan sisanya. Proporsi dapat disesuaikan untuk video vertikal agar tidak menyisakan ruang kosong berlebihan.
- Preview vertikal ditampilkan pada matte gelap netral; area player boleh gelap walaupun aplikasi memakai light theme.
- Kontrol playback dan trim berada dekat preview, bukan tersebar di beberapa kartu.
- Panel kanan menggunakan tab “Subtitle” dan “Tampilan”; transkrip sumber tetap mudah diakses.
- Jangan menjadikan timeline dekoratif dengan waveform palsu. Bila waveform belum dihitung dari audio, gunakan ruler waktu sederhana.

**Ekspor**

- Daftar hasil dengan revisi, resolusi, ukuran, waktu, dan status.
- Tombol download hanya aktif untuk file yang tersedia.
- Hasil gagal menampilkan sebab ringkas dan aksi retry.

**Pengaturan**

- Form terkelompok sederhana untuk default pemrosesan dan status layanan.
- Status teknis lengkap tersedia melalui detail yang dapat dibuka; jangan memenuhi halaman utama dengan log.

### 8.5 Perilaku komponen

- Satu aksi utama yang paling menonjol per konteks. Aksi lain memakai secondary atau text button.
- Icon-only button wajib memiliki accessible name; tooltip tidak menjadi satu-satunya label aksesibilitas.
- Dialog custom memakai focus trap, focus restoration, Escape, label, dan deskripsi yang benar.
- Dialog penghapusan menggunakan tombol jelas: “Batal” dan “Hapus proyek”; jangan “Ya/Tidak”.
- Select/combo box memakai tampilan custom yang konsisten, navigasi keyboard, dan pencarian untuk daftar yang panjang. Boleh memakai primitive headless yang aksesibel; tidak boleh membawa theme UI kit.
- Native file chooser tetap digunakan untuk memilih file; ini bukan dialog konfirmasi aplikasi.
- Validasi form inline. Toast hanya untuk umpan balik tambahan; error penting tetap terlihat di konteks pekerjaan.
- Tidak mengandalkan warna saja untuk membedakan status.
- Animasi singkat maksimal sekitar 150 ms untuk perubahan state; hormati `prefers-reduced-motion`.

### 8.6 Copywriting

| Gunakan | Hindari |
|---|---|
| “Buat kandidat” | “Generate Viral Magic” |
| “Memproses transkrip” | “AI sedang melakukan keajaiban” |
| “3 kandidat tersedia” | “3 video viral siap meledak” |
| “Tinjau klip” | “Unlock your creativity” |
| “Ekspor gagal. Ruang penyimpanan tidak cukup.” | “Oops! Something went wrong.” |

Bahasa harus ringkas, alami, dan spesifik. Istilah “AI” tidak perlu ditempel di setiap tombol.

### 8.7 Responsive dan aksesibilitas

- Uji viewport 1440, 1024, 768, dan 390 px.
- Pada tablet, panel editor dapat ditumpuk atau diganti tab; preview dan tombol utama tetap terlihat.
- Pada mobile, dukung upload, review, koreksi subtitle, trim melalui timecode, render, dan download. Drag timeline presisi tidak wajib.
- Tidak boleh ada overflow halaman horizontal atau tombol tertutup panel sticky.
- Seluruh alur inti dapat dijalankan dengan keyboard; focus indicator terlihat.
- Progress/status job memiliki live-region yang tidak terlalu sering mengganggu screen reader.
- Fitur delete dan retry tetap dapat diakses tanpa hover.

### 8.8 Gerbang review desain

Sebelum menyatakan UI selesai, Codex harus menginspeksi screenshot halaman Proyek, detail, editor, dialog hapus, empty state, dan error state pada desktop serta mobile. Evaluasi daftar larangan di atas satu per satu. Screenshot merupakan bukti review, bukan pengganti pengujian fungsi.

## 9. Arsitektur dan batas tanggung jawab

```mermaid
flowchart TD
    U["Browser"] --> G["Gateway satu origin"]
    G --> W["Nuxt web"]
    G --> A["FastAPI"]
    A --> D["PostgreSQL"]
    A --> R["Redis broker"]
    R --> J["Celery workers"]
    J --> D
    A --> S["Volume media privat"]
    J --> S
    J --> L["DeepSeek API"]
```

- Gateway, misalnya Caddy, mengarahkan `/api/v1/*` ke FastAPI dan route web ke Nuxt.
- Frontend tidak mengakses database, broker, atau filesystem secara langsung.
- Backend Python memiliki domain aplikasi, otorisasi, status job, dan metadata.
- Worker menjalankan FFprobe/FFmpeg, faster-whisper, dan panggilan DeepSeek.
- Semua aturan bisnis tetap di backend Python. Jangan menduplikasi API bisnis ke Nitro hanya karena Nuxt mendukung server routes.
- Worker CPU dapat dipindahkan atau ditambahkan GPU kemudian; MVP menggunakan shared volume pada satu host.
- File media tidak disimpan sebagai blob di PostgreSQL dan tidak dilayani dari public folder Nuxt.
- Jangan memakai FFmpeg.wasm di browser untuk pekerjaan utama MVP.

### 9.1 Keandalan antrean

Gunakan transactional outbox atau mekanisme dispatch persisten ekuivalen: pembuatan job dan catatan dispatch disimpan dalam transaksi database, dispatcher mengirim ke Celery, dan reconciler menangani dispatch yang belum selesai. Jangan mengandalkan commit database lalu publish broker sekali tanpa recovery.

Pengiriman job bersifat at-least-once. Worker menggunakan claim/lease dan idempotency key; pengiriman ganda tidak boleh menggandakan output. Simpan fingerprint input, konfigurasi, versi transkrip, revisi klip, dan versi pipeline.

Retry harus dimulai dari tahap gagal bila output tahap sebelumnya masih valid. Panggilan provider yang timeout dapat sudah diproses provider; deduplikasi internal tidak menjamin biaya API tepat satu kali. Catat attempt secara terpisah.

### 9.2 Struktur repository yang ditargetkan

```text
apps/web/                    Nuxt, komponen, halaman, state UI
services/backend/app/api/    Router dan schema HTTP
services/backend/app/domain/ Model dan aturan aplikasi
services/backend/app/media/  Probe, trim, crop, subtitle, render
services/backend/app/ai/     Transcription dan clip selector adapters
services/backend/app/jobs/   Celery tasks, dispatcher, reconciler
services/backend/app/storage/ Local adapter dan interface storage
services/backend/alembic/    Migrasi database
tests/unit/                 Validasi, timing, ownership, idempotency
tests/integration/          DB, queue, FFmpeg, lifecycle job
tests/e2e/                  Browser flows
tests/fixtures/             Media sintetis/kecil yang boleh didistribusikan
infra/                      Dockerfiles dan gateway config
docs/PRD.md                 Salinan dokumen ini
docs/ARCHITECTURE.md         Keputusan implementasi aktual
docs/PROGRESS.md             Tahap selesai, bukti uji, dan batas yang tersisa
compose.yml
.env.example
README.md
```

File sementara, model cache besar, video pengguna, secret, dan output render tidak boleh masuk git.

## 10. Model data minimum

| Entitas | Field penting |
|---|---|
| User | id, email, password_hash, created_at |
| Session | id/token hash, user_id, expires_at, revoked_at |
| Project | id, owner_id, name, source_asset_id, lifecycle_state, created_at, updated_at |
| Asset | id, project_id, kind, storage_key, bytes, mime, checksum, metadata, state |
| Transcript | id, project_id, version, language, model, config, created_at |
| TranscriptSegment | id, transcript_id, order, start_ms, end_ms, text, words_json |
| Clip | id, project_id, origin, active_revision_id, created_at |
| ClipRevision | id, clip_id, revision, transcript_id, start_ms, end_ms, title, reason, crop_json, subtitle_style_json |
| SubtitleCue | id, clip_revision_id, start_ms, end_ms, text |
| Export | id, clip_revision_id, job_id, config, mp4_asset_id, srt_asset_id, status |
| Job | id, project_id, kind, status, stage, input_fingerprint, attempt, lease_expires_at, progress, error_code, timestamps |
| JobAttempt | id, job_id, attempt, started_at, finished_at, worker_id, outcome, diagnostic_ref |
| OutboxEvent | id, job_id, payload, dispatched_at, attempt |
| ProviderUsage | id, job_attempt_id, provider, model, input_tokens, output_tokens, latency_ms, outcome, request_id |

- Semua waktu sistem UTC; UI memformat sesuai timezone browser.
- Ownership diturunkan dari Project dan diperiksa pada semua akses turunannya.
- Index untuk owner/status/waktu, project FK, dan job lease.
- Foreign key dan unique constraint melindungi revisi, deduplikasi job, serta hubungan aset.
- Penghapusan dibuat bertahap dan idempotent karena transaksi DB tidak bisa sekaligus menghapus filesystem secara atomik.
- Transcript sumber dan ClipRevision immutable setelah dibuat; menyimpan perubahan editor menghasilkan revisi baru dalam transaksi.
- Cue disimpan dalam waktu lokal klip, sedangkan batas ClipRevision memakai waktu sumber.

## 11. Kontrak API minimum

Prefix `/api/v1`. Semua endpoint proyek dan aset memerlukan sesi serta verifikasi ownership. Gunakan pagination untuk daftar dan schema error konsisten.

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/auth/login` | Membuat sesi |
| POST | `/auth/logout` | Mencabut sesi |
| GET | `/auth/me` | Identitas sesi aktif |
| GET/POST | `/projects` | Daftar atau membuat proyek |
| GET/PATCH/DELETE | `/projects/{id}` | Detail, nama, atau meminta penghapusan |
| POST | `/projects/{id}/source` | Streaming upload file sumber |
| POST | `/projects/{id}/process` | Membuat job pipeline |
| GET | `/projects/{id}/transcripts/{version}` | Segmen transkrip dengan pagination |
| GET/POST | `/projects/{id}/clips` | Daftar kandidat atau membuat klip manual |
| GET/PATCH | `/clips/{id}` | Membaca atau membuat revisi baru dengan expected revision |
| POST | `/clips/{id}/exports` | Membuat job render revisi tertentu |
| GET | `/projects/{id}/exports` | Daftar hasil |
| GET | `/jobs/{id}` | State/stage/progress/error |
| POST | `/jobs/{id}/retry` | Retry tahap yang gagal |
| POST | `/jobs/{id}/cancel` | Meminta cancellation |
| GET/HEAD | `/assets/{id}/content` | Streaming/download berotorisasi; mendukung HTTP Range |
| GET | `/settings` | Pengaturan nonrahasia dan capabilities |
| GET | `/usage` | Pemakaian milik pengguna |
| GET | `/health/live` | Liveness tanpa rincian sensitif |
| GET | `/health/ready` | Readiness layanan; lindungi rincian internal |

Job creation mengembalikan HTTP 202 dan job ID. Endpoint mutasi job menerima idempotency key. Konflik revisi menghasilkan 409. Respons error memiliki `code`, pesan untuk pengguna, dan correlation ID; jangan mengirim stack trace atau secret.

File content mendukung seek video melalui byte ranges dan tidak memakai cache publik untuk aset privat. Mengganti UUID di URL tidak boleh membuka file pengguna lain.

## 12. Integritas, keamanan, dan pengelolaan data

- Secret dibaca dari environment backend, tidak menggunakan prefix environment publik Nuxt.
- Gunakan subprocess argument array; jangan menyusun perintah shell dari nama file, subtitle, atau parameter pengguna.
- Storage key dibuat server, bukan path yang dikirim pengguna. Cegah traversal dan akses symlink di luar root.
- Batasi durasi, resolusi, ukuran, jumlah job aktif, CPU, serta timeout proses media.
- Worker berjalan non-root dengan direktori kerja terpisah per job.
- Teks transkrip diperlakukan sebagai data tidak tepercaya, bukan instruksi model. Prompt harus memisahkan instruksi dan transkrip; output tetap divalidasi.
- Jangan menulis full transcript, password, token sesi, atau API key ke log operasional.
- UI tidak membolehkan raw HTML dari subtitle/judul/alasan AI.
- Semua aset persisten bersifat privat; backup harus mencakup metadata dan media bila ingin proyek dapat dipulihkan.
- Hapus file sementara sukses/gagal sesuai TTL; jangan menghapus sumber/hasil jadi otomatis tanpa kebijakan yang terlihat.
- Default sementara: cleanup upload parsial setelah 24 jam dan scratch job setelah 24 jam sejak attempt terminal. Exclude job aktif atau lease yang masih berlaku.
- Penghapusan proyek mencabut akses segera, menandai tombstone, membatalkan job, lalu menghapus aset dengan retry. Worker mengecek tombstone sebelum mempublikasikan hasil baru.
- Data yang telah terkirim ke provider mengikuti kebijakan provider; menghapus proyek lokal tidak menjamin penghapusan di sisi provider. README harus menjelaskan batas ini secara singkat.

## 13. Error dan recovery

| Kondisi | Perilaku yang diwajibkan |
|---|---|
| Key DeepSeek belum ada | Tampilkan konfigurasi belum lengkap; upload, transkripsi, dan klip manual tetap bisa digunakan |
| Key tidak valid | Analisis gagal dengan error konfigurasi; jangan retry terus-menerus |
| Provider rate limit/5xx | Retry terbatas dengan exponential backoff dan jitter |
| JSON kosong/tidak valid | Maksimal retry terbatas, lalu error jelas; jangan membuat kandidat dummy |
| Kandidat berisi ID invalid | Tolak kandidat; jika semua invalid, analisis gagal dengan opsi retry |
| Audio tidak berisi ucapan | Tampilkan hasil kosong dengan penjelasan; tidak memanggil AI selector |
| File korup/codec gagal decode | Gagal validasi atau pemrosesan dengan sebab spesifik |
| Disk tidak cukup | Tolak pekerjaan baru dan hentikan output sementara secara aman |
| Redis restart | Job tersimpan di DB; dispatcher/reconciler memulihkan pengiriman sesuai kebijakan |
| Worker mati | Lease kedaluwarsa dan recovery idempotent; tidak ada render siap yang sebenarnya parsial |
| Render gagal | Kandidat dan edit tetap tersimpan; retry hanya render |
| Pengguna klik export dua kali | Job yang sama untuk idempotency key sama; tidak merender ganda |
| Tab ditutup | Job server tetap berjalan; saat kembali tampilkan state aktual |
| Revisi diedit saat render | Output tetap terikat snapshot lama; UI menandai perbedaan revisi |

## 14. Menjalankan secara lokal

### 14.1 Layanan Compose

`gateway`, `web`, `api`, `worker-heavy`, `worker-light`, `dispatcher`, `scheduler`, `postgres`, dan `redis`. Dispatcher/scheduler boleh berbagi entrypoint backend, tetapi setiap fungsi hanya memiliki satu instance aktif atau dilindungi locking.

Volume persisten: `postgres-data`, `media-data`, dan `whisper-cache`. Volume Redis sesuai kebijakan broker; metadata utama tetap di PostgreSQL.

### 14.2 Konfigurasi minimum

```dotenv
# Placeholder dokumentasi; implementasi menyediakan .env.example lengkap.
APP_ENV=local
APP_ORIGIN=http://localhost:8080
DATABASE_URL=postgresql+psycopg://clipper:CHANGE_ME@postgres:5432/clipper
REDIS_URL=redis://redis:6379/0
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=SET_A_VERIFIED_SUPPORTED_MODEL
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
MEDIA_ROOT=/data/media
MAX_UPLOAD_BYTES=2147483648
MAX_VIDEO_SECONDS=3600
HEAVY_WORKER_CONCURRENCY=1
```

Secret contoh tidak boleh digunakan sebagai kredensial production. README menjelaskan cara membuat secret lokal, menerapkan migrasi, membuat akun, mengunduh model pertama kali, menjalankan Compose, dan membuka aplikasi.

### 14.3 Batas lingkungan

- CPU-only adalah baseline kompatibilitas, bukan janji cepat.
- Profil NVIDIA GPU opsional setelah baseline berfungsi; verifikasi runtime CUDA/CTranslate2 yang kompatibel.
- Jangan mengasumsikan GPU tersedia pada Docker Desktop Mac atau Apple Silicon.
- Download bobot model membutuhkan jaringan pada penggunaan pertama; cache persisten mencegah download berulang.
- Setelah model tersedia, transkripsi dapat berjalan lokal; rekomendasi DeepSeek tetap memerlukan jaringan.
- Video besar memakai ruang untuk sumber, proxy, audio sementara, dan export. Periksa headroom disk berdasarkan ukuran aktual, bukan hanya limit upload.
- Tidak menetapkan kebutuhan minimum RAM atau estimasi menit proses tanpa benchmark pada mesin target.

## 15. Tahapan implementasi untuk Codex

### Tahap 0 — Fondasi dan kontrak

- Periksa repository dan AGENTS.md yang sudah ada; jangan menimpa pekerjaan pengguna.
- Buat struktur monorepo, lockfile, Compose, environment example, database migration, dan bootstrap akun.
- Dokumentasikan API/schema utama dan design tokens.
- Buat shell Proyek, detail, dan editor dengan empty/loading/error states yang nyata. Fixture boleh untuk pengembangan terisolasi, bukan mode aplikasi normal.

**Selesai jika:** stack berjalan lokal, login berfungsi, migrasi dapat diulang aman, dan web terhubung ke API nyata.

### Tahap 1 — Satu alur media tanpa AI

- Upload, FFprobe, storage privat, playback/seek, klip manual, crop, subtitle manual, render, dan download.
- Implementasikan lifecycle job, cleanup dasar, dan revisi export.

**Selesai jika:** file input nyata menghasilkan MP4 yang dapat diputar dengan crop dan durasi benar. Screenshot UI saja tidak memenuhi tahap ini.

### Tahap 2 — Transkripsi lokal

- Integrasikan faster-whisper, versi transkrip, cue subtitle, dan navigasi berdasarkan teks.
- Uji audio kosong, Indonesia, Inggris, dan file dengan rotation/VFR.

**Selesai jika:** klip memiliki subtitle dari transkrip nyata dan cue mengikuti trim.

### Tahap 3 — Pemilihan kandidat

- Integrasikan adapter DeepSeek, chunking, schema validation, deduplikasi, dan usage logging.
- Implementasikan kegagalan konfigurasi/provider tanpa kehilangan pekerjaan.

**Selesai jika:** sedikitnya satu uji nyata dengan API menghasilkan kandidat yang merujuk segmen valid; bila kredensial tidak tersedia, tandai verifikasi live sebagai belum dilakukan.

### Tahap 4 — Kualitas editor dan ketahanan

- Selesaikan dialog custom, combo box, aksesibilitas, responsive, dan pemeriksaan anti-UI-slop.
- Uji konflik revisi, restart worker, dispatch gagal, cancellation, dan deletion saat job aktif.
- Perbaiki preview/render mismatch yang terlihat pada crop, subtitle, dan aspect ratio.

**Selesai jika:** seluruh acceptance wajib lulus atau blocking issue dicatat sebagai belum selesai.

### Tahap 5 — Pilot dan handoff

- Jalankan tiga video pilot dan catat metrik, koreksi manusia, model, serta spesifikasi mesin.
- Lengkapi README, keputusan arsitektur, hasil uji, dan backlog yang nyata.
- Jangan menyebut production-ready hanya karena development server dapat dibuka.

Tahapan merupakan urutan kerja, bukan estimasi jadwal. Jangan membangun billing atau fitur lanjutan sebelum alur inti lolos evaluasi.

## 16. Acceptance criteria wajib

| ID | Pengujian | Kriteria lulus |
|---|---|---|
| AC-01 | Instalasi bersih | README cukup untuk menjalankan stack, migrasi, akun, dan cache model |
| AC-02 | Ownership | Pengguna B tidak dapat membaca/mengubah/download proyek atau aset A |
| AC-03 | Upload | File valid diterima; file korup/oversize ditolak tanpa file siap palsu |
| AC-04 | Pipeline nyata | Upload sampai MP4/SRT berhasil dengan video dan audio asli |
| AC-05 | Job persisten | Refresh browser tidak menghilangkan job; restart worker ditangani tanpa stuck permanen |
| AC-06 | Validasi AI | ID segmen invalid, output kosong, dan format salah ditangani tanpa kandidat dummy |
| AC-07 | Batas klip | Durasi output berbeda maksimal sekitar 100 ms dari target pada fixture valid |
| AC-08 | Subtitle | Tidak ada cue negatif/di luar klip; teks koreksi muncul di SRT dan burn-in |
| AC-09 | Framing | Crop final sesuai koordinat yang disimpan; rotation dan aspect ratio benar |
| AC-10 | Revisi | Edit saat render tidak mengubah snapshot export; UI menunjukkan revisi hasil |
| AC-11 | Retry | Render gagal dapat diulang tanpa mengulang transkripsi dan analisis yang masih valid |
| AC-12 | Deduplikasi | Pengiriman job ganda tidak membuat dua hasil resmi untuk fingerprint sama |
| AC-13 | Cancellation | Pekerjaan berhenti atau mencapai batas pembatalan yang terdokumentasi; UI tidak mengklaim berhenti sebelum proses berhenti |
| AC-14 | Penghapusan | Akses dicabut segera, aset akhirnya terhapus, dan worker tidak memunculkan hasil proyek terhapus |
| AC-15 | Rahasia | Key tidak muncul di bundle frontend, respons API, log, atau repository |
| AC-16 | Dialog | Hapus, retry yang destruktif, dan konflik memakai komponen custom yang aksesibel |
| AC-17 | Responsive | Alur inti dapat dipakai pada 390, 768, 1024, dan 1440 px tanpa overflow halaman |
| AC-18 | Keyboard | Login, upload, pilih klip, edit, simpan, dan export dapat dioperasikan dengan keyboard |
| AC-19 | UI review | Screenshot enam state utama diperiksa; tidak ada pola yang dilarang dalam bagian 8 |
| AC-20 | Hasil jujur | Tidak ada data dummy, score viral, progress palsu, atau klaim tes live yang belum dijalankan |

### Strategi pengujian

- Unit: validasi batas, mapping segmen, chunk merge, cue timing, crop math, revisi, dan izin akses.
- Integration: database migrations, outbox/dispatch, claim job ganda, file Range, FFmpeg output, dan cleanup.
- E2E dengan Playwright: login → upload → klip manual → edit → export → download; jalur AI diuji dengan provider adapter terkontrol di test environment.
- Live smoke: faster-whisper dengan audio nyata dan DeepSeek dengan key dari environment lokal bila tersedia.
- QA visual: layout serta hasil frame render, bukan hanya DOM test.
- Fixtures harus kecil, sintetis atau berizin; tidak mengunggah konten pribadi ke repository.
- Mock provider diperbolehkan dalam test suite yang diberi label. Mode normal tidak boleh diam-diam mengganti AI gagal dengan respons mock.

## 17. Definition of Done dan handoff

MVP selesai ketika alur inti bekerja dengan file nyata, acceptance wajib lulus, hasil UI sudah diinspeksi, dan dokumentasi dapat digunakan pada instalasi lokal baru.

Handoff Codex harus menyertakan:

1. Ringkasan fitur yang benar-benar selesai.
2. Perintah instalasi dan menjalankan aplikasi yang sudah diverifikasi.
3. Konfigurasi yang perlu diisi pengguna, terutama API key dan pilihan model.
4. Perintah pengujian beserta hasil aktual, termasuk tes yang belum dapat dijalankan.
5. Lokasi output contoh serta bukti review crop/subtitle.
6. Keterbatasan dan backlog tanpa menyamarkannya sebagai fitur tersedia.

Tidak perlu membuat PR, push repository, atau deploy ke server publik kecuali diminta. Commit lokal mengikuti instruksi repository dan pengguna. Jangan mengubah stack, menambah layanan berbayar, atau membangun fitur di luar cakupan secara diam-diam.

## 18. Prompt awal untuk Codex lokal

Salin PRD ini ke `docs/PRD.md` pada repository target. Gunakan prompt berikut:

```text
Baca docs/PRD.md sampai selesai dan ikuti AGENTS.md jika tersedia.
Bangun MVP AI Video Clipper sesuai dokumen, mulai dari Tahap 0 dan
lanjutkan bertahap sampai alur inti nyata selesai. Periksa isi repository
sebelum mengubah file dan pertahankan pekerjaan yang sudah ada.

Gunakan Nuxt + TypeScript + Tailwind CSS v4 + Lucide untuk web,
FastAPI + SQLAlchemy/Alembic + PostgreSQL untuk backend,
Celery + Redis untuk job, faster-whisper lokal untuk transkripsi,
DeepSeek API untuk pemilihan kandidat, dan FFmpeg untuk render.
Sediakan Docker Compose serta README lokal yang dapat direproduksi.

Ikuti spesifikasi UI bagian 8: workspace editor yang tenang dan fungsional,
tanpa gradient, glow, kartu statistik dekoratif, emoji, atau Nuxt UI.
Gunakan dialog custom, kontrol yang aksesibel, dan layout responsive.
Jangan membuat aplikasi hanya berupa mockup atau data demo.

Kerjakan satu alur end-to-end lebih dulu: upload, klip manual, render,
download. Setelah itu tambahkan transkripsi dan rekomendasi AI.
Validasi tiap tahap dengan tes yang relevan dan review tampilan browser.
Catat progres aktual di docs/PROGRESS.md.

API key hanya dari environment backend. Jika belum tersedia, lanjutkan
pekerjaan independen dan unit/integration test, lalu laporkan bahwa uji
provider live belum dilakukan. Jangan membuat key, hasil, atau klaim tes.

Gunakan keputusan default PRD untuk detail rutin. Minta klarifikasi hanya
jika ada konflik repository, keputusan destruktif, atau kebutuhan yang
benar-benar memblokir. Jangan berhenti setelah membuat rencana saja.
```

## 19. Rujukan teknis

Rujukan berikut mendukung pemilihan komponen; versi kompatibel tetap harus diverifikasi ketika implementasi.

- faster-whisper: <https://github.com/SYSTRAN/faster-whisper>
- DeepSeek JSON Output: <https://api-docs.deepseek.com/guides/json_mode/>
- FastAPI background tasks dan pertimbangan Celery: <https://fastapi.tiangolo.com/tutorial/background-tasks/>
- Nuxt: <https://nuxt.com/docs>
- Tailwind CSS: <https://tailwindcss.com/docs>
- Celery: <https://docs.celeryq.dev/en/stable/>
- FFmpeg: <https://ffmpeg.org/documentation.html>

Semua target, default limit, dan design token dalam dokumen ini merupakan keputusan produk awal, bukan hasil benchmark atau klaim dari vendor.
