# Azure Synapse Analytics — Bronze to Silver

Folder ini berisi PySpark notebook untuk transformasi **Bronze → Silver** di Azure Synapse Analytics menggunakan ADLS Gen2 (`georisk`).

## Isi Folder
- `bronze_to_silver.ipynb`: Notebook PySpark untuk 5 sumber data (`firms`, `magma`, `air_quality`, `weather`, dan `mcd_burned_scar`).
  - Setiap sumber disimpan sebagai dataset Parquet tersendiri di `abfss://silver@georisk.dfs.core.windows.net/<source>/`.
  - Menggunakan pola **concat (`unionByName`) + deduplikasi** berdasarkan primary key masing-masing sumber (`item_id` untuk `mcd_burned_scar`), dan penulisan aman via folder staging sementara.

## Cara Import ke Azure Synapse Studio
1. Buat container **`silver`** di Storage Account **`georisk`**.
2. Buka **Synapse Studio → Develop → `+` → Import**, lalu pilih file `synapse/bronze_to_silver.ipynb`.
3. Attach ke **Apache Spark Pool** (mis. ukuran `Small`, auto-pause `5–15 menit`).
4. *(Opsional untuk trigger otomatis dari GitHub Actions)*:
   - Masuk ke **Integrate → `+` → Pipeline** (beri nama mis. `pl_bronze_to_silver`).
   - Tambahkan parameter pipeline `run_slot` (String, default kosong).
   - Drag aktivitas **Notebook** → pilih `bronze_to_silver` → pada **Base parameters**, kirim `run_slot` = `@pipeline().parameters.run_slot`.
   - Klik **Publish all**.
   - Di **Manage → Access control**, berikan role **Synapse Contributor** (atau **Synapse Artifact User**) ke App Registration `georisk-github-actions`.
