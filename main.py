import os
import torch
import numpy as np
import pandas as pd
import xarray as xr
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

from model import ThermoclineAwareOceanModel
from data_fetcher import fetch_and_process_recent_data

MODEL_WEIGHTS = "best_thermocline_model.pt"
ZARR_STORE = "recent_data.zarr"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

FEATURE_VARS = ["analysed_sst", "sos", "sla", "u", "v", "uwnd", "vwnd"]
TARGET_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

app_state = {
    "model": None,
    "zarr_data": None
}

class PredictRequest(BaseModel):
    latitude: float
    longitude: float

def sync_daily_data():
    fetch_and_process_recent_data(zarr_store=ZARR_STORE, window_days=10)
    app_state["zarr_data"] = xr.open_zarr(ZARR_STORE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load Model
    model = ThermoclineAwareOceanModel(in_channels=7, n_depths=15, embed_dim=64, temporal_window=7).to(DEVICE)
    if os.path.exists(MODEL_WEIGHTS):
        model.load_state_dict(torch.load(MODEL_WEIGHTS, map_location=DEVICE))
    model.eval()
    app_state["model"] = model

    if not os.path.exists(ZARR_STORE):
        print("Executing initial data sync...")
        sync_daily_data()
    else:
        app_state["zarr_data"] = xr.open_zarr(ZARR_STORE)

    # Schedule standard daily background updates at 00:00 
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_daily_data, 'cron', hour=0, minute=0)
    scheduler.start()

    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/predict")
async def predict_profile(request: PredictRequest):
    data = app_state["zarr_data"]
    if data is None:
        raise HTTPException(status_code=503, detail="Dataset unavailable or syncing.")

    lats = data.latitude.values
    lons = data.longitude.values
    lat_idx = (np.abs(lats - request.latitude)).argmin()
    lon_idx = (np.abs(lons - request.longitude)).argmin()

    if lat_idx < 2 or lat_idx > len(lats) - 3 or lon_idx < 2 or lon_idx > len(lons) - 3:
        raise HTTPException(status_code=400, detail="Location invalid. Coordinates are too close to dataset boundaries for a 5x5 spatial patch.")

    # Slice specific 7-day 5x5 patch window
    try:
        patch = data.isel(
            time=slice(-7, None),
            latitude=slice(lat_idx - 2, lat_idx + 3),
            longitude=slice(lon_idx - 2, lon_idx + 3)
        ).load()
    except IndexError:
        raise HTTPException(status_code=500, detail="Insufficient temporal records for 7-day window.")

    input_tensor = torch.zeros((1, 7, len(FEATURE_VARS), 5, 5), dtype=torch.float32)
    
    for k, var in enumerate(FEATURE_VARS):
        arr = patch[var].values.astype(np.float32)
        # Re-apply z-score normalization as evaluated during preprocessing logic 
        mean, std = np.nanmean(arr), np.nanstd(arr) + 1e-8
        arr = np.nan_to_num((arr - mean) / std, nan=0.0)
        input_tensor[0, :, k, :, :] = torch.from_numpy(arr)

    input_tensor = input_tensor.to(DEVICE)
    
    # Placeholder climatology tensor (incorporate target_clim array extraction if fully deployed)
    clim_tensor = torch.zeros((1, 15), dtype=torch.float32).to(DEVICE)

    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=(DEVICE.type == "cuda")):
        pred, _, _ = app_state["model"](input_tensor, clim_tensor)

    pred_list = pred[0].cpu().float().numpy().tolist()

    return {
        "target_latitude": float(lats[lat_idx]),
        "target_longitude": float(lons[lon_idx]),
        "timestamp": str(patch.time.values[-1]),
        "temperature_profile": {f"{depth}m": temp for depth, temp in zip(TARGET_DEPTHS, pred_list)}
    }