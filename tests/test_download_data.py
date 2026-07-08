import os
import pandas as pd
from unittest.mock import patch
from scripts.download_data import download_data

def test_synthetic_fallback():
    # Mock requests.get to simulate network failure
    with patch("requests.get", side_effect=Exception("Network error")):
        download_data()
        
    csv_path = "data/processed/trajectories_synthetic.csv"
    assert os.path.exists(csv_path)
    
    df = pd.read_csv(csv_path)
    assert len(df) >= 50
    expected_cols = ["vehicle_id", "mode", "time_s", "x_m", "y_m", "speed_mps"]
    for c in expected_cols:
        assert c in df.columns
