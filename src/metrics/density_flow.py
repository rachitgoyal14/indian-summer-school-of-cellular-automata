import pandas as pd

def flow_density_from_log(df: pd.DataFrame, road_length_cells: int, cell_length_m: float, window_s: int, measurement_point_offset: int = 50) -> pd.DataFrame:
    """
    Computes density and flow from a simulation log.
    density (veh/km) = (avg number of vehicles on road in window) / (road length in km)
    flow (veh/hr) = (vehicles that crossed a fixed measurement point in window) x (3600/window_s)
    """
    if df.empty:
        return pd.DataFrame(columns=["window_start", "window_end", "density_veh_per_km", "flow_veh_per_hr"])
        
    road_length_km = (road_length_cells * cell_length_m) / 1000.0
    measurement_point_cells = road_length_cells - measurement_point_offset # measure far enough from end to catch high-speed vehicles
    
    max_time = df['time_s'].max()
    windows = list(range(0, int(max_time) + 1, window_s))
    
    results = []
    
    for i in range(len(windows) - 1):
        w_start = windows[i]
        w_end = windows[i+1]
        
        # Vehicles in this time window
        mask = (df['time_s'] >= w_start) & (df['time_s'] < w_end)
        df_window = df[mask]
        
        if df_window.empty:
            density = 0.0
            flow = 0.0
        else:
            # Density: avg vehicles per second / road_length_km
            # count total vehicle records in this window / window length = avg vehicles
            avg_vehicles = len(df_window) / float(window_s)
            density = avg_vehicles / road_length_km
            
            # Flow: count unique vehicles that cross measurement point
            # To cross measurement point in this window, the vehicle must be before it at start of step
            # and past it at end of step. We can just count vehicles whose position_cells is >= measurement_point
            # and who were previously < measurement_point, or just look at max position in window vs min.
            # Simpler: count vehicles that reach or exceed measurement_point in this window, but only count them once.
            
            crossed_vehicles = set()
            for vid, group in df_window.groupby('vehicle_id'):
                # Check if it was ever >= measurement point
                if group['position_cells'].max() >= measurement_point_cells:
                    # check if its FIRST appearance in this window was < measurement point?
                    # Or just check if the exact crossing happened here.
                    # Best: check if any step has position >= measurement_point and (position - speed) < measurement_point
                    crossings = group[(group['position_cells'] >= measurement_point_cells) & 
                                      (group['position_cells'] - group['speed_cells_per_step'] < measurement_point_cells)]
                    if not crossings.empty:
                        crossed_vehicles.add(vid)
                        
            flow = len(crossed_vehicles) * (3600.0 / window_s)
            
        results.append({
            "window_start": w_start,
            "window_end": w_end,
            "density_veh_per_km": density,
            "flow_veh_per_hr": flow
        })
        
    return pd.DataFrame(results)
