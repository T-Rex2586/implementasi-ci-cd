# CI/CD Scraping Data Pipeline — Azure Blob Storage & GitHub Actions

Pipeline ingestion otomatis berbasis Python dengan CI/CD GitHub Actions (scheduler setiap 6 jam) dan penyimpanan terpusat di **Azure Blob Storage / ADLS Gen2** menggunakan autentikasi **OIDC (Microsoft Entra ID Federated Credentials)**.

## Sumber Data (5 Sources)

| No | Key | Sumber Data | Metode Akses | Output |
| --- | --- | --- | --- | --- |
| 1 | `firms` | NASA FIRMS (MODIS & VIIRS Hotspots) | REST API CSV (`FIRMS_API_KEY`) | `data/firms/latest_hotspots.csv` |
| 2 | `magma` | MAGMA Indonesia (PVMBG / Badan Geologi ESDM) | Web Scraper HTML | `data/magma/latest.json` |
| 3 | `air_quality` | Open-Meteo Air Quality API | REST API JSON (tanpa key) | `data/air_quality/latest_air_quality.csv` |
| 4 | `weather` | Open-Meteo Weather API | REST API JSON (tanpa key) | `data/weather/latest_weather.csv` |
| 5 | `mcd_burned_scar` | MODIS MCD64A1 Burned Area / Burned Scar (v6.1) | Microsoft Planetary Computer STAC API (`modis-64A1-061`, tanpa key) | `data/mcd_burned_scar/latest_burned_scar.csv` + `latest_stac_items.json` |

## Menjalankan Secara Lokal

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Isi FIRMS_API_KEY pada file .env
python -m src.main
pytest
```

## Konfigurasi Azure & GitHub

1. **Azure Resource Group & Storage Account** (upgrade ke ADLS Gen2 / Hierarchical Namespace) + buat container `bronze`.
2. **Microsoft Entra ID → App Registration** + tambahkan **Federated Credential** (`GitHub Actions deploying Azure resources`, branch `main`).
3. **IAM Role Assignment** pada Storage Account: tambahkan role **Storage Blob Data Contributor** ke App Registration.
4. **GitHub Repository Variables** (`Settings → Secrets and variables → Actions → Variables`):
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`
   - `AZURE_STORAGE_ACCOUNT` (`georisk`)
   - `AZURE_STORAGE_CONTAINER` (`bronze`)
5. **GitHub Repository Secrets** (`Secrets`):
   - `FIRMS_API_KEY` (MAP_KEY dari NASA FIRMS; sumber lain termasuk `MCD64A1 Burned Scar` tidak memerlukan API key).
