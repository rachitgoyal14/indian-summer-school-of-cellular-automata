import os
import requests
import pandas as pd
import numpy as np
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def download_data():
    """
    Attempt to download Kanagaraj trajectory data or generate synthetic data as fallback.
    """
    setup_logging()
    
    os.makedirs("data/processed", exist_ok=True)
    
    urls = [
        "https://toledo.net.technion.ac.il/files/2014/10/ChennaiTrajectoryData2.45-3.00PM.xlsx",
        "https://toledo.net.technion.ac.il/files/2014/10/ChennaiTrajectoryData3.00-3.15PM.xlsx"
    ]
    
    success = False
    
    for url in urls:
        try:
            logging.info(f"Attempting to download {url}")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            raw_path = "data/raw/temp.xlsx"
            os.makedirs("data/raw", exist_ok=True)
            with open(raw_path, 'wb') as f:
                f.write(response.content)
            
            logging.info("Download successful, processing data...")
            df = pd.read_excel(raw_path)
            
            # The column names might vary, so we map them correctly
            # We want: vehicle_id, mode, time_s, x_m, y_m, speed_mps
            
            # Exact mapping for Kanagaraj dataset
            col_map = {
                'Vehicle Number': 'vehicle_id',
                'Vehicle Type': 'mode',
                'Time (sec)': 'time_s',
                'Long Distance (m)': 'x_m',
                'Lat Distance (m)': 'y_m',
                'Long Speed (m/sec)': 'speed_mps'
            }
            
            df.rename(columns=col_map, inplace=True)
            
            required_cols = ["vehicle_id", "mode", "time_s", "x_m", "y_m", "speed_mps"]
            for c in required_cols:
                if c not in df.columns:
                    logging.warning(f"Column {c} missing from processed data!")
                    df[c] = 0
            
            df = df[required_cols]
            
            # Map Kanagaraj numerical mode to our text modes
            # 1 - Motorcycle (two_wheeler)
            # 2 - Car (car)
            # 3 - Bus (bus)
            # 4 - Truck (bus)
            # 5 - LCV (car or bus, let's map to car)
            # 6 - Auto-Rickshaw (three_wheeler)
            type_mapping = {
                1.0: 'two_wheeler',
                2.0: 'car',
                3.0: 'bus',
                4.0: 'bus',
                5.0: 'car',
                6.0: 'three_wheeler'
            }
            df['mode'] = df['mode'].map(type_mapping).fillna('car')
            
            df.to_csv("data/processed/trajectories_kanagaraj.csv", index=False)
            logging.info("Processed real Kanagaraj data.")
            success = True
            break
        except Exception as e:
            logging.warning(f"Failed to download or process {url}: {e}")
            
    if not success:
        logging.warning("Falling back to generating synthetic trajectory data.")
        generate_synthetic_data()

def generate_synthetic_data():
    """
    Generate synthetic trajectory data for 4 modes on a 200m road.
    """
    np.random.seed(42)
    
    modes = ["two_wheeler", "three_wheeler", "car", "bus"]
    speeds = {
        "two_wheeler": (8, 14),
        "three_wheeler": (6, 11),
        "car": (7, 13),
        "bus": (5, 9)
    }
    
    records = []
    
    for vid in range(1, 201):
        mode = np.random.choice(modes, p=[0.4, 0.2, 0.3, 0.1])
        start_time = np.random.uniform(0, 900)
        speed = np.random.uniform(speeds[mode][0], speeds[mode][1])
        y = np.random.uniform(0, 7) # 7m road width
        
        # simulate passing a 200m road
        duration = 200 / speed
        time_steps = np.arange(start_time, start_time + duration, 1.0)
        
        for t in time_steps:
            x = (t - start_time) * speed
            if x <= 200:
                records.append({
                    "vehicle_id": vid,
                    "mode": mode,
                    "time_s": round(t, 2),
                    "x_m": round(x, 2),
                    "y_m": round(y, 2),
                    "speed_mps": round(speed, 2)
                })
                
    df = pd.DataFrame(records)
    df.sort_values(by=["time_s", "vehicle_id"], inplace=True)
    df.to_csv("data/processed/trajectories_synthetic.csv", index=False)
    logging.info(f"Generated synthetic data: {len(df)} rows.")

if __name__ == "__main__":
    download_data()
