"""
Phase 4 Combined View: All 4 legs trajectories in global 2D junction box coordinates.
Uses actual arc cells (cx, cy) from get_junction_cells — NOT derived from raw pos_past.
Highlights 1 left-turn and 1 right-turn individual vehicle with annotated paths.
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from src.core.config import load_config
from src.sim.sim_loop import run_full_intersection
from src.intersection.intersection import Intersection

config = load_config('configs/intersection_default.yaml')
rng = np.random.default_rng(42)
mode_mix = {'car': 0.267, 'two_wheeler': 0.546, 'three_wheeler': 0.151, 'bus': 0.036}
df = run_full_intersection(config, 1200, 520, mode_mix, rng)

inter = Intersection(config, 1200, 520, mode_mix, rng)
stop_line  = inter.legs[0].stop_line_position_cells
box_size   = inter.box_size      # 20 cells
W          = box_size // 2       # 10 cells
cell_len   = config['grid']['cell_length_m']  # 0.5 m
cell_wid   = config['grid']['cell_width_m']   # 0.7 m
mode_params = config['mode_params']

# Box physical dims
box_w_m = box_size * cell_wid   # 14 m
box_h_m = box_size * cell_len   # 10 m

df['pos_past'] = df['position_cells'] - stop_line

# ── Build arc-cell records ──────────────────────────────────────────────────
# For every (t, vehicle_id) row where pos_past >= 0, compute the FRONT cell
# position using get_junction_cells and record the centroid as (gx, gy).
records = []
for _, row in df[df['pos_past'] >= 0].iterrows():
    leg_id = int(row['leg_origin'])
    pp     = int(row['pos_past'])
    lat    = int(row['lateral_position_cells'])
    turn   = row['turn']
    mode   = row['mode']
    v_len  = mode_params[mode]['length_cells']
    v_wid  = mode_params[mode]['width_cells']
    # Use just the FRONT cell (pos_past_stop = pp, l=0)
    front_cells = inter.get_junction_cells(leg_id, lat, turn, pp, 1, v_wid)
    # Keep only in-box cells
    front_cells = [(cx, cy) for (cx, cy) in front_cells
                   if 0 <= cx < box_size and 0 <= cy < box_size]
    if not front_cells:
        continue
    cx_mean = np.mean([c[0] for c in front_cells])
    cy_mean = np.mean([c[1] for c in front_cells])
    # Convert box cell to meters: cell (cx, cy) -> (cx*cell_wid, cy*cell_len)
    records.append({
        'time_s':    row['time_s'],
        'vehicle_id': int(row['vehicle_id']),
        'leg_origin': leg_id,
        'turn':       turn,
        'gx':         cx_mean * cell_wid,
        'gy':         cy_mean * cell_len,
        'pos_past':   pp,
    })

arc_df = pd.DataFrame(records)
print(f"Arc records: {len(arc_df)}, unique vehicles: {arc_df['vehicle_id'].nunique()}")

# ── Find highlight vehicles: ones that transited cleanly (short dwell) ──────
def find_clean(turn_type, max_steps=8, min_steps=2):
    cands = arc_df[arc_df['turn'] == turn_type]
    cnts  = cands.groupby('vehicle_id').size()
    good  = cnts[(cnts >= min_steps) & (cnts <= max_steps)].sort_values().index.tolist()
    # Prefer a vehicle with clear spatial movement (std gx + std gy > 0.5m)
    for v in good:
        vdf = cands[cands['vehicle_id'] == v]
        spread = vdf['gx'].std() + vdf['gy'].std()
        if spread > 0.3:
            return v
    return good[0] if good else None

v_left  = find_clean('left',  8)
v_right = find_clean('right', 8)
v_str   = find_clean('straight', 10, 5)
print(f"Highlights: left=v{v_left}, right=v{v_right}, straight=v{v_str}")
for vid in [v_left, v_right, v_str]:
    if vid is None: continue
    vdf = arc_df[arc_df['vehicle_id']==vid].sort_values('time_s')
    print(f"  v{vid} ({vdf.iloc[0]['turn']}, leg{vdf.iloc[0]['leg_origin']}): "
          f"gx {vdf['gx'].min():.1f}→{vdf['gx'].max():.1f} m, "
          f"gy {vdf['gy'].min():.1f}→{vdf['gy'].max():.1f} m")

# ── Plot ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 11))
fig.patch.set_facecolor('#0d1117')
ax.set_facecolor('#141b26')

# Junction box
box_rect = plt.Rectangle((0, 0), box_w_m, box_h_m,
                          linewidth=2, edgecolor='#4a9eff',
                          facecolor='#1a2440', zorder=0)
ax.add_patch(box_rect)
# Mid-lines
ax.axvline(W * cell_wid, color='#4a9eff', alpha=0.18, lw=0.8, ls='--')
ax.axhline(W * cell_len, color='#4a9eff', alpha=0.18, lw=0.8, ls='--')

leg_colors = {0: '#e06c75', 1: '#98c379', 2: '#61afef', 3: '#e5c07b'}
leg_labels = {
    0: 'Leg 0 (N→S)',
    1: 'Leg 1 (E→W)',
    2: 'Leg 2 (S→N)',
    3: 'Leg 3 (W→E)',
}

hl_ids = {v_left, v_right, v_str} - {None}

# Background: all non-highlight vehicles, FULL opacity (alpha=0.45), larger dots
for lid, gdf in arc_df[~arc_df['vehicle_id'].isin(hl_ids)].groupby('leg_origin'):
    ax.scatter(gdf['gx'], gdf['gy'],
               c=leg_colors[lid], alpha=0.35, s=14,
               zorder=2, rasterized=True, linewidths=0)

# Highlighted vehicles
hl_cfg = [
    (v_left,  'left',     '#f9e47a', 'Left-turn',  2.8, 'D', 60),
    (v_right, 'right',    '#ff6b9d', 'Right-turn', 2.8, 'o', 60),
    (v_str,   'straight', '#b0ddff', 'Straight',   2.0, 's', 45),
]
for vid, ttype, color, lbl, lw, mk, ms in hl_cfg:
    if vid is None:
        print(f"  !! no {ttype} highlight vehicle found")
        continue
    vdf = arc_df[arc_df['vehicle_id'] == vid].sort_values('time_s')
    if len(vdf) < 2: continue
    ax.plot(vdf['gx'], vdf['gy'], '-', color=color, lw=lw, zorder=7, alpha=0.95,
            label=f'{lbl}  v{vid}')
    ax.scatter(vdf['gx'], vdf['gy'], c=color, s=ms, zorder=8,
               marker=mk, edgecolors='white', linewidths=0.6)
    # Direction arrow at midpoint
    n = len(vdf)
    if n >= 3:
        m = n // 2
        dx = float(vdf['gx'].iloc[m] - vdf['gx'].iloc[m-1])
        dy = float(vdf['gy'].iloc[m] - vdf['gy'].iloc[m-1])
        if abs(dx) + abs(dy) > 0.05:
            ax.annotate('', xy=(vdf['gx'].iloc[m], vdf['gy'].iloc[m]),
                        xytext=(vdf['gx'].iloc[m-1], vdf['gy'].iloc[m-1]),
                        arrowprops=dict(arrowstyle='->', color=color, lw=2.2))
    # Entry / exit labels (single each, no duplicates)
    entry = vdf.iloc[0]
    ex    = vdf.iloc[-1]
    
    # Custom offsets for entry vs exit
    ax.annotate(
        f"v{vid} entry",
        xy=(entry['gx'], entry['gy']),
        xytext=(-35, 12), textcoords='offset points',
        fontsize=8, color=color, fontweight='bold',
        arrowprops=dict(arrowstyle='->', color=color, lw=0.8),
        bbox=dict(boxstyle='round,pad=0.2', fc='#0d1117', ec=color, alpha=0.9),
        zorder=10,
    )
    ax.annotate(
        f"v{vid} exit",
        xy=(ex['gx'], ex['gy']),
        xytext=(15, -12), textcoords='offset points',
        fontsize=8, color=color, fontweight='bold',
        arrowprops=dict(arrowstyle='->', color=color, lw=0.8),
        bbox=dict(boxstyle='round,pad=0.2', fc='#0d1117', ec=color, alpha=0.9),
        zorder=10,
    )

# ── Leg entry arrows & labels (outside box) ─────────────────────────────────
arrow_kw = dict(arrowstyle='->', lw=2)
ofs = 1.5   # metres outside box
# Leg 0: enters from top (N→S), x≈ east half mid
x0 = (W + 2) * cell_wid
ax.annotate('', xy=(x0, box_h_m), xytext=(x0, box_h_m + ofs),
            arrowprops=dict(**arrow_kw, color=leg_colors[0]))
ax.text(x0, box_h_m + ofs + 0.25, leg_labels[0],
        color=leg_colors[0], ha='center', fontsize=9, fontweight='bold')

# Leg 2: enters from bottom (S→N), x≈ west half mid
x2 = 2 * cell_wid
ax.annotate('', xy=(x2, 0), xytext=(x2, -ofs),
            arrowprops=dict(**arrow_kw, color=leg_colors[2]))
ax.text(x2, -ofs - 0.35, leg_labels[2],
        color=leg_colors[2], ha='center', fontsize=9, fontweight='bold')

# Leg 1: enters from right (E→W), y≈ north half mid
y1 = (W + 2) * cell_len
ax.annotate('', xy=(box_w_m, y1), xytext=(box_w_m + ofs, y1),
            arrowprops=dict(**arrow_kw, color=leg_colors[1]))
ax.text(box_w_m + ofs + 0.2, y1, leg_labels[1],
        color=leg_colors[1], va='center', fontsize=9, fontweight='bold')

# Leg 3: enters from left (W→E), y≈ south half mid
y3 = 2 * cell_len
ax.annotate('', xy=(0, y3), xytext=(-ofs, y3),
            arrowprops=dict(**arrow_kw, color=leg_colors[3]))
ax.text(-ofs - 0.2, y3, leg_labels[3],
        color=leg_colors[3], va='center', ha='right', fontsize=9, fontweight='bold')

# ── Legends ──────────────────────────────────────────────────────────────────
hl_legend = ax.legend(loc='upper right', fontsize=9, title='Highlighted vehicles',
                      facecolor='#1a2440', edgecolor='#4a9eff',
                      labelcolor='#cdd6f4', title_fontsize=8)
hl_legend.get_title().set_color('#8ca8d0')
ax.add_artist(hl_legend)

leg_patches = [mpatches.Patch(color=c, label=leg_labels[i])
               for i, c in leg_colors.items()]
ax.legend(handles=leg_patches, loc='lower right', fontsize=9,
          facecolor='#1a2440', edgecolor='#4a9eff',
          labelcolor='#cdd6f4', title_fontsize=8)

# ── Axis ─────────────────────────────────────────────────────────────────────
margin_x = 3.5
margin_y = 2.5
ax.set_xlim(-margin_x, box_w_m + margin_x + 2)
ax.set_ylim(-margin_y, box_h_m + margin_y + 0.5)

ax.set_xlabel('Box cell X → East  (m,  0 = West wall)', color='#cdd6f4', fontsize=10)
ax.set_ylabel('Box cell Y → North  (m,  0 = South wall)', color='#cdd6f4', fontsize=10)
ax.tick_params(colors='#7a8ba8', labelsize=9)
for sp in ax.spines.values():
    sp.set_color('#4a9eff'); sp.set_alpha(0.35)

# Grid lines to mark box walls
for xv in [0, box_w_m]:
    ax.axvline(xv, color='#4a9eff', lw=1.2, alpha=0.5)
for yv in [0, box_h_m]:
    ax.axhline(yv, color='#4a9eff', lw=1.2, alpha=0.5)

ax.set_title(
    'Phase 4 — 4-Leg Intersection: All Trajectories in Junction-Box Cell Coordinates\n'
    'Plotted via get_junction_cells() arc centroids  |  Full opacity  |  Highlighted: 1 left-turn, 1 right-turn',
    color='#cdd6f4', fontsize=12, pad=12)

plt.tight_layout()
out = 'figures/phase4_combined_view.png'
plt.savefig(out, dpi=160, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"Saved → {out}")
