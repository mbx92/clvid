# Model pelacakan lokal

File di direktori ini dibundel ke image backend. Pelacakan tidak mengunduh
model saat pengguna menekan **Analisis preview**. Model hanya dipakai pada
klip terpilih, maksimal 180 detik; tidak mengenali identitas orang.

| Model | Penggunaan | Provenance dan lisensi |
| --- | --- | --- |
| `face_detection_yunet_2023mar.onnx` | Bounding box dan landmark wajah | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), [manifest](YUNET-SOURCE.json), [MIT](YUNET-LICENSE.txt) |
| `light_asd_talkset.onnx` | Skor pembicara dari audio dan urutan gambar wajah | [Light-ASD](https://github.com/Junhua-Liao/Light-ASD/tree/ed38c232de5efe0261dbd68627c0ade7cdfe14eb), [manifest ekspor](light_asd_talkset.json), [MIT](LICENSE-Light-ASD.txt) |

Light-ASD berasal dari `weight/finetuning_TalkSet.model` pada commit
`ed38c232de5efe0261dbd68627c0ade7cdfe14eb`. File ONNX berukuran 4.105.980 byte;
SHA-256 yang dibundel adalah
`1d2426dd8f50ded8fb43c342af4f35785cdea61815b5b803cf4a153bc544fa18`.
Manifest mencatat checksum bobot asli, versi alat, bentuk tensor, dan hasil
perbandingan numerik. Pertahankan berkas lisensi saat mendistribusikan model.

## Inferensi dan batas hasil

Runtime menggunakan ONNX Runtime 1.31.1 pada CPU dengan dua thread, tanpa Torch
atau pemuatan pickle. Input model adalah audio MFCC float32 `[1,4T,13]` dan
video grayscale float32 `[1,T,112,112]` pada rentang 0–255. Output `[T,2]`
berupa logit; skor pembicara dihitung sebagai `sigmoid(logit1-logit0)`.
Angka tersebut merupakan skor model, bukan persentase akurasi atau identitas.

Praproses mengikuti [implementasi evaluasi upstream](https://github.com/Junhua-Liao/Light-ASD/blob/ed38c232de5efe0261dbd68627c0ade7cdfe14eb/Columbia_test.py):
video 25 fps, crop wajah dengan median13, padding 110, resize 224, pusat 112,
dan audio PCM16 mono 16 kHz. MFCC memakai 13 koefisien, jendela 25 ms/langkah
10 ms, 26 filter, FFT512, preemphasis 0,97, lifter22, rectangular window dan
log-energy. Implementasi NumPy diperiksa terhadap python_speech_features0.6;
SciPy/python_speech_features bukan dependensi runtime.

Selector memerlukan bukti yang konsisten sebelum handoff. Wajah tertutup/kecil,
audio tidak sinkron, suara di luar frame, dan ucapan bersamaan tetap dapat
menghasilkan pilihan yang keliru. Mode **Ikuti wajah** tetap tersedia untuk
mempertahankan satu wajah; tinjau preview bergerak dan MP4 akhir.

## Mereproduksi ONNX

Jalankan dari root repository dalam virtual environment pengembangan terpisah.
Lingkungan yang dipakai untuk ekspor tercatat sebagai Python3.12,
Torch2.10.0+cpu, ONNX1.20.1, ONNX Runtime1.31.1, NumPy2.4.3.
Contoh setelah mengaktifkan virtual environment tersebut:

```sh
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install onnx==1.20.1 onnxruntime==1.31.1 numpy==2.4.3
python scripts/export_speaker_model.py --variant talkset --output .artifacts/light_asd_reproduced.onnx
```

[Script ekspor](../../../scripts/export_speaker_model.py) mengunduh source dan
bobot ke `.tools/light-asd-upstream`, dipatok ke commit dan checksum sebelum
diimpor/dimuat. Bobot dibaca dengan `weights_only=True`. Penggantian pooling
yang ekuivalen diuji terhadap keluaran asli, lalu hasil ONNX dibandingkan dengan
Torch untuk T=25,50,100. Ekspor juga menjalankan ONNX checker dan menulis manifest
JSON di samping output. Hasil acuan memiliki selisih absolut maksimal
3,34×10⁻⁶; verifikasi parity kembali jika versi alat berubah.

Normal deployment cukup memakai model yang dibundel. Jika mengganti bobot,
pertahankan kontrak tensor, manifest dan lisensinya; set `SPEAKER_MODEL_PATH`
dan rebuild/recreate layanan yang menggunakan model. Signature cache meliputi
SHA kedua model serta versi algoritma, sehingga hasil analisis sebelumnya tidak
dianggap sebagai hasil model baru. Berkas MP4 lama tetap hasil versi aslinya.
