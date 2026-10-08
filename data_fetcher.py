import subprocess
import sys
import datetime
import glob
from pathlib import Path
import xarray as xr
import numpy as np

LAT_MIN, LAT_MAX = 5, 30
LON_MIN, LON_MAX = 45, 105
TARGET_LAT = np.arange(5, 30.25, 0.25)
TARGET_LON = np.arange(45, 105.25, 0.25)

CMEMS_DATASETS = {
    "sst": {
        "dataset_id": "METOFFICE-GLO-SST-L4-REP-OBS-SST",
        "variables": ["analysed_sst"],
        "out_name": "SST_recent.nc",
    },
    "sss": {
        "dataset_id": "cmems_obs-mob_glo_phy-sss_nrt_multi_P1D",
        "variables": ["sos"],
        "out_name": "SSS_recent.nc",
    },
    "ssh": {
        "dataset_id": "c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D",
        "variables": ["sla"],
        "out_name": "SSH_recent.nc",
    },
}

PODAAC_DATASETS = {
    "oscar": {
        "short_name": "OSCAR_L4_OC_FINAL_V2.0",
        "out_dir": "oscar_recent",
    },
    "ccmp": {
        "short_name": "CCMP_WINDS_10M6HR_L4_V3.1",
        "out_dir": "ccmp_recent",
    },
}

def run(cmd):
    result = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr, shell=False)
    if result.returncode != 0:
        print(f"WARNING: command exited with code {result.returncode}", file=sys.stderr)

def fetch_and_process_recent_data(outdir="./data", zarr_store="recent_data.zarr", window_days=10):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    end_date = datetime.datetime.utcnow().date()
    start_date = end_date - datetime.timedelta(days=window_days)
    start_str, end_str = str(start_date), str(end_date)
    
    # Download CMEMS
    for key, cfg in CMEMS_DATASETS.items():
        cmd = [
            "copernicusmarine", "subset",
            "--dataset-id", cfg["dataset_id"],
            "--start-datetime", f"{start_str}T00:00:00",
            "--end-datetime", f"{end_str}T23:59:59",
            "--minimum-longitude", str(LON_MIN),
            "--maximum-longitude", str(LON_MAX),
            "--minimum-latitude", str(LAT_MIN),
            "--maximum-latitude", str(LAT_MAX),
            "--output-filename", cfg["out_name"],
            "--output-directory", str(outdir),
            "--force-download"
        ]
        for var in cfg["variables"]:
            cmd += ["--variable", var]
        run(cmd)

    # Download PODAAC
    for key, cfg in PODAAC_DATASETS.items():
        target_dir = outdir / cfg["out_dir"]
        target_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "podaac-data-downloader",
            "-c", cfg["short_name"],
            "-d", str(target_dir),
            "--start-date", f"{start_str}T00:00:00Z",
            "--end-date", f"{end_str}T23:59:59Z",
            "-b", f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
            "-e", ".nc",
        ]
        run(cmd)

    # Regrid and merge components as configured in final_fast.ipynb
    try:
        ds_sst = xr.open_dataset(outdir / CMEMS_DATASETS["sst"]["out_name"])
        ds_sss = xr.open_dataset(outdir / CMEMS_DATASETS["sss"]["out_name"]).squeeze("depth", drop=True, errors='ignore')
        ds_ssh = xr.open_dataset(outdir / CMEMS_DATASETS["ssh"]["out_name"])
        
        oscar_files = glob.glob(str(outdir / PODAAC_DATASETS["oscar"]["out_dir"] / "*.nc"))
        ds_oscar = xr.open_mfdataset(oscar_files, combine="nested", concat_dim="time")
        ds_oscar = ds_oscar.assign_coords(latitude=ds_oscar['lat'], longitude=ds_oscar['lon']).drop_vars(['lat', 'lon'], errors='ignore')
        ds_oscar = ds_oscar.sel(latitude=slice(LAT_MIN, LAT_MAX), longitude=slice(LON_MIN, LON_MAX))
        ds_oscar = ds_oscar.convert_calendar("standard", use_cftime=False)
        
        ccmp_files = glob.glob(str(outdir / PODAAC_DATASETS["ccmp"]["out_dir"] / "*.nc"))
        ds_ccmp = xr.open_mfdataset(ccmp_files, combine="nested", concat_dim="time")
        ds_ccmp = ds_ccmp.sel(latitude=slice(LAT_MIN, LAT_MAX), longitude=slice(LON_MIN, LON_MAX)).resample(time="1D").mean()

        # Interpolate variables to 0.25 degree target resolution
        ds_sst_regrid = ds_sst.interp(lat=TARGET_LAT, lon=TARGET_LON, method="linear").rename({'lat': 'latitude', 'lon': 'longitude'})
        ds_sss_regrid = ds_sss.interp(latitude=TARGET_LAT, longitude=TARGET_LON, method="linear")
        ds_ssh_regrid = ds_ssh.interp(latitude=TARGET_LAT, longitude=TARGET_LON, method="linear")
        ds_oscar_regrid = ds_oscar.interp(latitude=TARGET_LAT, longitude=TARGET_LON, method="linear")
        ds_ccmp_regrid = ds_ccmp.interp(latitude=TARGET_LAT, longitude=TARGET_LON, method="linear")

        for ds in [ds_sst_regrid, ds_sss_regrid, ds_ssh_regrid, ds_oscar_regrid, ds_ccmp_regrid]:
            ds["time"] = ds["time"].dt.floor("D")

        ds_final = xr.merge([
            ds_sst_regrid[['analysed_sst']], 
            ds_sss_regrid[['sos']], 
            ds_ssh_regrid[['sla']],
            ds_oscar_regrid[['u', 'v']], 
            ds_ccmp_regrid[['uwnd', 'vwnd']]
        ], join="inner")
        
        ds_final = ds_final.chunk({"time": 1, "latitude": -1, "longitude": -1})
        ds_final.to_zarr(zarr_store, mode="w")
        print(f"Daily regridded store successfully constructed at {zarr_store}")
        
    except Exception as e:
        print(f"Data Processing/Regridding Failure: {e}")

if __name__ == "__main__":
    fetch_and_process_recent_data()