# Fixture media

Fixture tidak berisi konten pengguna. `scripts/make_fixture.py` membuat pola video
bergerak dan nada 440 Hz menggunakan FFmpeg `lavfi`, tanpa file eksternal.
Gunakan untuk upload, validasi, range, crop, timing, subtitle manual, dan ekspor.
Nada bukan ucapan dan tidak dipakai sebagai bukti akurasi transkripsi.

Video hasil generator diletakkan di `.artifacts/` yang diabaikan Git. Pengujian
media membuat fixture kecil sendiri dalam direktori sementara pytest.

Pilot tiga video milik pengguna tidak tersedia di repository ini dan harus
dilaksanakan terpisah sebelum menyimpulkan manfaat atau kualitas Indonesia.
