# Wind Energy Forecasting

The repository is now segregated at the root into:

- `frontend/` for the Next.js user interface
- `backend/` for the FastAPI app, ML pipeline, data, and saved artifacts

The main user experience is now a date-based 7-day forecast flow:

- search for a city or location
- choose a forecast start date
- fetch hourly weather from Open-Meteo
- estimate wind energy for the selected day and the next 6 days

## Project Structure

```text
wind-energy-forecast/
|-- backend/
|   |-- app/
|   |-- data/
|   |-- models/
|   |-- notebooks/
|   |-- plots/
|   |-- src/
|   |-- requirements.txt
|   `-- wind_dataset.zip
|-- frontend/
|   |-- app/
|   |-- components/
|   |-- lib/
|   |-- package.json
|   `-- tsconfig.json
`-- README.md
```

## Backend Setup

Create a Python environment and install backend dependencies:

```bash
python -m venv backend/.venv
backend/.venv/Scripts/activate
pip install -r backend/requirements.txt
```

For lightweight production deployment on Render, use the runtime-only dependency set instead of the training stack:

```bash
pip install -r backend/requirements-render.txt
```

Run the FastAPI backend from the repository root:

```bash
uvicorn backend.app.main:app --reload
```

The backend serves the API on `http://127.0.0.1:8000` by default.

### Render Deployment

Render can deploy this backend from the repository root with:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

The repository also includes `.python-version` pinned to `3.11.11` so Render uses a TensorFlow-compatible Python line instead of the default `3.14.x`.

If you only need the deployed forecast API, `requirements.txt` points to `backend/requirements-render.txt`, which excludes TensorFlow and other training-only packages because the saved production model currently uses the random forest artifact.

### Backend Environment

The frontend calls the backend from another origin, so the API enables local Next.js CORS origins by default:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

To override them in PowerShell:

```powershell
$env:CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
uvicorn backend.app.main:app --reload
```

## Frontend Setup

Start the Next.js frontend in a second terminal:

```bash
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

The default frontend API target is:

```text
http://127.0.0.1:8000
```

If needed, change `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`.

## API Endpoints

- `GET /`
- `GET /docs`
- `GET /health`
- `GET /model-info`
- `GET /locations/search?q=<city>`
- `POST /forecast`
- `GET /demo-window`
- `POST /predict`

`/forecast` is the primary UI path. `/predict` remains available for raw model compatibility.

## Train the Models

Run training from the repository root:

```bash
python -m backend.src.train --data backend/data/wind_data.csv
```

Artifacts are saved into `backend/models/`.

## Evaluate the Models

```bash
python -m backend.src.evaluate --data backend/data/wind_data.csv
```

Plots are written into `backend/plots/`.

## Predict from Python

```python
from backend.src.predict import predict_wind_energy

recent_rows = [
    {
        "wind_speed": 9.8,
        "wind_direction": 120,
        "temperature": 22.4,
        "pressure": 1012.3,
        "timestamp": "2026-04-08 10:00:00",
        "power_output": 410.2
    }
]

result = predict_wind_energy(recent_rows)
print(result)
```

## Predict from the Command Line

```bash
python -m backend.src.predict --input backend/data/recent_history.json
```
