# Azure Synapse Analytics — Medallion Pipeline (Bronze → Silver → Gold)

Folder ini berisi PySpark notebook untuk transformasi **Bronze → Silver → Gold** di Azure Synapse Analytics menggunakan ADLS Gen2 (`georisk`).

## Isi Folder
1. **`bronze_to_silver.ipynb`**: Membersihkan, menstandardisasi tipe data, melakukan **concat (`unionByName`) + deduplikasi** untuk 5 sumber data (`firms`, `magma`, `air_quality`, `weather`, `mcd_burned_scar`) ke container **`silver`**.
2. **`silver_to_gold.ipynb`**: Membaca 5 dataset dari container **`silver`** dan menghasilkan 4 tabel siap pakai di container **`gold`**:
   - `gold/dashboard_air_quality_weather/` — Kualitas udara + cuaca per jam per kota (dengan `aqi_category` & `is_latest_reading`)
   - `gold/dashboard_volcano_status/` — Status aktivitas gunung api terkini (dengan `level_rank` 1–4 & `is_high_alert`)
   - `gold/dashboard_fire_hotspots/` — Hotspot FIRMS diperkaya intensitas FRP & irisan spasial tile MODIS MCD64A1 Burned Scar
   - `gold/ml_karhutla_features/` — Feature store harian per `(location, date)` untuk ML prediksi karhutla (cuaca, kualitas udara, histori burned scar, hotspot radius 50 km, fitur lag, dan target label `t+1`)

## Cara Merangkai di Azure Synapse Studio
1. Pastikan container **`silver`** dan **`gold`** sudah dibuat di Storage Account **`georisk`**.
2. Import `bronze_to_silver.ipynb` dan `silver_to_gold.ipynb` di menu **Develop → `+` → Import**.
3. Di Synapse Pipeline (`pl_bronze_to_silver`):
   - Aktivitas 1 (Notebook): `bronze_to_silver` (kirim parameter `run_slot`).
   - Aktivitas 2 (Notebook): `silver_to_gold`, hubungkan garis **Success (hijau)** dari Aktivitas 1 ke Aktivitas 2.
4. Klik **Publish all**.
5. Setiap kali GitHub Actions selesai mengunggah Bronze, pipeline Synapse otomatis menjalankan **Bronze → Silver → Gold** secara berurutan!
