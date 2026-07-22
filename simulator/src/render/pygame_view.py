import os
import time
import numpy as np
import pygame
from PIL import Image, ImageDraw, ImageFont
from src.core.network import Road, Network
from src.core.junction import Junction
from src.network.grid_builder import build_grid_network

# Colors
COLOR_BG = (18, 18, 24)           # Dark slate blue
COLOR_ROAD_BG = (35, 35, 45)      # Medium grey/blue
COLOR_CAR = (0, 230, 115)         # Vibrant neon green
COLOR_TEXT = (230, 230, 240)      # Off-white
COLOR_HUD_BG = (30, 30, 40)       # Dark panel bg
COLOR_GRID = (50, 50, 65)         # Subtle grid lines
COLOR_HIGHLIGHT = (255, 102, 102) # Soft neon red/orange for active markers
COLOR_JUNCTION = (0, 153, 255)    # Cool neon blue for junctions

# PIL Font Cache & Renderer
_font_cache = {}

def get_pil_font(size, bold=False):
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    
    font_paths = [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "Courier New.ttf"
    ]
    if bold:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ] + font_paths
        
    font = None
    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:
                pass
                
    if font is None:
        font = ImageFont.load_default()
        
    _font_cache[key] = font
    return font

def render_text_to_surface(text, color, bg_color=None, size=16, bold=False):
    font = get_pil_font(size, bold)
    bbox = font.getbbox(text)
    
    if bbox is None:
        w, h = 10, 10
    else:
        w = max(1, bbox[2] - bbox[0])
        h = max(1, bbox[3] - bbox[1])
        
    w += 4
    h += 4
    
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0) if bg_color is None else bg_color + (255,))
    draw = ImageDraw.Draw(img)
    draw.text((2, 2 - (bbox[1] if bbox else 0)), text, fill=color + (255,), font=font)
    
    raw_data = img.tobytes("raw", "RGBA")
    surf = pygame.image.fromstring(raw_data, img.size, "RGBA")
    return surf

class SimulatorApp:
    def __init__(self, road_length=1000, target_density=0.3, steps_per_second=10, case=1):
        pygame.init()
        pygame.display.set_caption(f"Rule 184 Traffic Simulator - Case {case}")
        
        self.width = 1200
        self.height = 600
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        
        # Simulation parameters
        self.road_length = road_length
        self.target_density = target_density
        self.steps_per_second = steps_per_second
        self.case = case
        self.paused = False
        self.step_count = 0
        self.rng = np.random.default_rng(42)
        
        # Camera / Zoom / Pan
        self.cell_width = 8.0  # Zoom factor
        self.camera_x = 0.0
        self.camera_y = 0.0
        
        # Interaction state
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.camera_start_x = 0
        self.camera_start_y = 0
        
        # Setup network
        self.network = Network()
        self.setup_network()
        self.reset_sim()
        
        # Timing
        self.last_sim_step_time = pygame.time.get_ticks()
        self.running = True
        
    def setup_network(self):
        self.network = Network()
        spacing = 250.0
        
        if self.case == 1:
            # Case 1: Original one-way periodic road
            road = Road("Road_A", length=self.road_length, start_coord=(100.0, 300.0), end_coord=(1100.0, 300.0), periodic=True)
            self.network.add_road(road)
            
        elif self.case == 2:
            # Case 2: Two-way no interaction (independent horizontal periodic roads)
            road_e = Road("Road_East", length=self.road_length // 2, start_coord=(100.0, 280.0), end_coord=(1100.0, 280.0), periodic=True)
            road_w = Road("Road_West", length=self.road_length // 2, start_coord=(1100.0, 320.0), end_coord=(100.0, 320.0), periodic=True)
            self.network.add_road(road_e)
            self.network.add_road(road_w)
            
        elif self.case == 3:
            # Case 3: Two-way with left/right turns (T-junction J1 at center 600, 300)
            # Incoming roads
            road_e1 = Road("Road_E1", length=30, start_coord=(100.0, 300.0), end_coord=(600.0, 300.0))
            road_w2 = Road("Road_W2", length=30, start_coord=(1100.0, 300.0), end_coord=(600.0, 300.0))
            road_n2 = Road("Road_N2", length=20, start_coord=(600.0, 50.0), end_coord=(600.0, 300.0))
            
            # Outgoing roads
            road_w1 = Road("Road_W1", length=30, start_coord=(600.0, 300.0), end_coord=(100.0, 300.0))
            road_e2 = Road("Road_E2", length=30, start_coord=(600.0, 300.0), end_coord=(1100.0, 300.0))
            road_n1 = Road("Road_N1", length=20, start_coord=(600.0, 300.0), end_coord=(600.0, 50.0))
            
            self.network.add_road(road_e1)
            self.network.add_road(road_w2)
            self.network.add_road(road_n2)
            self.network.add_road(road_w1)
            self.network.add_road(road_e2)
            self.network.add_road(road_n1)
            
            # Central Junction
            j1 = Junction("J1", ["Road_E1", "Road_W2", "Road_N2"], ["Road_E2", "Road_W1", "Road_N1"], {
                "Road_E1": {"Road_E2": 0.7, "Road_N1": 0.3},
                "Road_W2": {"Road_W1": 0.7, "Road_N1": 0.3},
                "Road_N2": {"Road_E2": 0.5, "Road_W1": 0.5}
            })
            self.network.add_junction(j1)
            
            # Boundary U-turn junctions to conserve cars
            j_e_wrap = Junction("J_E_wrap", ["Road_E2"], ["Road_W2"], {"Road_E2": {"Road_W2": 1.0}})
            j_w_wrap = Junction("J_W_wrap", ["Road_W1"], ["Road_E1"], {"Road_W1": {"Road_E1": 1.0}})
            j_n_wrap = Junction("J_N_wrap", ["Road_N1"], ["Road_N2"], {"Road_N1": {"Road_N2": 1.0}})
            
            self.network.add_junction(j_e_wrap)
            self.network.add_junction(j_w_wrap)
            self.network.add_junction(j_n_wrap)
            
        elif self.case == 4:
            # Case 4: 4-way intersection (Junction J1 at 600, 300)
            road_e1 = Road("Road_E1", length=30, start_coord=(100.0, 300.0), end_coord=(600.0, 300.0))
            road_w2 = Road("Road_W2", length=30, start_coord=(1100.0, 300.0), end_coord=(600.0, 300.0))
            road_n2 = Road("Road_N2", length=20, start_coord=(600.0, 50.0), end_coord=(600.0, 300.0))
            road_s1 = Road("Road_S1", length=20, start_coord=(600.0, 550.0), end_coord=(600.0, 300.0))
            
            road_w1 = Road("Road_W1", length=30, start_coord=(600.0, 300.0), end_coord=(100.0, 300.0))
            road_e2 = Road("Road_E2", length=30, start_coord=(600.0, 300.0), end_coord=(1100.0, 300.0))
            road_n1 = Road("Road_N1", length=20, start_coord=(600.0, 300.0), end_coord=(600.0, 50.0))
            road_s2 = Road("Road_S2", length=20, start_coord=(600.0, 300.0), end_coord=(600.0, 550.0))
            
            self.network.add_road(road_e1)
            self.network.add_road(road_w2)
            self.network.add_road(road_n2)
            self.network.add_road(road_s1)
            self.network.add_road(road_w1)
            self.network.add_road(road_e2)
            self.network.add_road(road_n1)
            self.network.add_road(road_s2)
            
            j1 = Junction("J1", ["Road_E1", "Road_W2", "Road_N2", "Road_S1"], ["Road_E2", "Road_W1", "Road_N1", "Road_S2"], {
                "Road_E1": {"Road_E2": 0.7, "Road_N1": 0.15, "Road_S2": 0.15},
                "Road_W2": {"Road_W1": 0.7, "Road_S2": 0.15, "Road_N1": 0.15},
                "Road_S1": {"Road_S2": 0.7, "Road_E2": 0.15, "Road_W1": 0.15},
                "Road_N2": {"Road_N1": 0.7, "Road_W1": 0.15, "Road_E2": 0.15}
            })
            self.network.add_junction(j1)
            
            j_e_wrap = Junction("J_E_wrap", ["Road_E2"], ["Road_W2"], {"Road_E2": {"Road_W2": 1.0}})
            j_w_wrap = Junction("J_W_wrap", ["Road_W1"], ["Road_E1"], {"Road_W1": {"Road_E1": 1.0}})
            j_n_wrap = Junction("J_N_wrap", ["Road_N1"], ["Road_N2"], {"Road_N1": {"Road_N2": 1.0}})
            j_s_wrap = Junction("J_s_wrap", ["Road_S2"], ["Road_S1"], {"Road_S2": {"Road_S1": 1.0}})
            
            self.network.add_junction(j_e_wrap)
            self.network.add_junction(j_w_wrap)
            self.network.add_junction(j_n_wrap)
            self.network.add_junction(j_s_wrap)
            
        elif self.case == 5:
            # Case 5: Connected multi-junction grid network (3x3 grid)
            self.network = build_grid_network(rows=3, cols=3, segment_length_cells=30, periodic=True, spacing=spacing)
            
        # Center camera automatically
        x_coords = []
        y_coords = []
        for road in self.network.roads.values():
            if road.start_coord is not None and road.end_coord is not None:
                # Check for wrap-around roads in Case 5 to avoid biasing the camera center
                dist = np.hypot(road.end_coord[0] - road.start_coord[0], road.end_coord[1] - road.start_coord[1])
                if dist < 1.5 * spacing:
                    x_coords.extend([road.start_coord[0], road.end_coord[0]])
                    y_coords.extend([road.start_coord[1], road.end_coord[1]])
                    
        if x_coords and y_coords:
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)
            center_x = (min_x + max_x) / 2.0
            center_y = (min_y + max_y) / 2.0
            self.cell_width = 8.0
            self.camera_x = center_x * self.cell_width - self.width / 2.0
            self.camera_y = center_y * self.cell_width - self.height / 2.0
        else:
            self.cell_width = 8.0
            self.camera_x = 0.0
            self.camera_y = 0.0

    def reset_sim(self):
        for road in self.network.roads.values():
            road.initialize_density(self.target_density, self.rng)
        self.actual_density = self.network.get_average_density()
        self.measured_flow = 0.0
        self.step_count = 0
        
    def step_sim(self):
        total_cells = sum(road.length for road in self.network.roads.values())
        if total_cells > 0:
            num_moves = self.network.step(self.rng)
            self.measured_flow = num_moves / total_cells
        else:
            self.network.step(self.rng)
            self.measured_flow = 0.0
        self.actual_density = self.network.get_average_density()
        self.step_count += 1
        
    def draw_text(self, text, x, y, color, size=16, bold=False):
        surf = render_text_to_surface(text, color, size=size, bold=bold)
        self.screen.blit(surf, (x, y))
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.VIDEORESIZE:
                self.width, self.height = event.size
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left click drag
                    self.dragging = True
                    self.drag_start_x = event.pos[0]
                    self.drag_start_y = event.pos[1]
                    self.camera_start_x = self.camera_x
                    self.camera_start_y = self.camera_y
                elif event.button == 4: # Scroll Up -> Zoom In
                    self.zoom(1.2, event.pos[0], event.pos[1])
                elif event.button == 5: # Scroll Down -> Zoom Out
                    self.zoom(1.0 / 1.2, event.pos[0], event.pos[1])
                    
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False
                    
            elif event.type == pygame.MOUSEMOTION:
                if self.dragging:
                    dx = event.pos[0] - self.drag_start_x
                    dy = event.pos[1] - self.drag_start_y
                    self.camera_x = self.camera_start_x - dx
                    self.camera_y = self.camera_start_y - dy
                    
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_s: # Step once when paused
                    if self.paused:
                        self.step_sim()
                elif event.key == pygame.K_r:
                    self.reset_sim()
                elif event.key == pygame.K_UP:
                    self.target_density = min(1.0, self.target_density + 0.05)
                elif event.key == pygame.K_DOWN:
                    self.target_density = max(0.0, self.target_density - 0.05)
                elif event.key == pygame.K_RIGHT: # Pan right
                    self.camera_x += 50
                elif event.key == pygame.K_LEFT: # Pan left
                    self.camera_x -= 50
                elif event.key == pygame.K_EQUALS: # Zoom in
                    self.zoom(1.2, self.width / 2.0, self.height / 2.0)
                elif event.key == pygame.K_MINUS: # Zoom out
                    self.zoom(1.0 / 1.2, self.width / 2.0, self.height / 2.0)
                elif event.key == pygame.K_RIGHTBRACKET: # Increase simulation speed
                    self.steps_per_second = min(100, self.steps_per_second + 2)
                elif event.key == pygame.K_LEFTBRACKET: # Decrease simulation speed
                    self.steps_per_second = max(1, self.steps_per_second - 2)

    def zoom(self, factor, focus_x, focus_y):
        old_zoom = self.cell_width
        new_zoom = max(1.0, min(100.0, old_zoom * factor))
        
        # Calculate cursor position in world space
        x_world = (focus_x + self.camera_x) / old_zoom
        y_world = (focus_y + self.camera_y) / old_zoom
        
        self.cell_width = new_zoom
        self.camera_x = x_world * self.cell_width - focus_x
        self.camera_y = y_world * self.cell_width - focus_y
        
    def get_visible_bounds(self):
        # Return bounding box in world space that is currently visible
        x_min = self.camera_x / self.cell_width
        y_min = self.camera_y / self.cell_width
        x_max = (self.camera_x + self.width) / self.cell_width
        y_max = (self.camera_y + self.height) / self.cell_width
        return x_min, x_max, y_min, y_max

    def update(self):
        if not self.paused:
            now = pygame.time.get_ticks()
            ms_per_step = 1000.0 / self.steps_per_second
            if now - self.last_sim_step_time >= ms_per_step:
                self.step_sim()
                self.last_sim_step_time = now

    def draw(self):
        self.screen.fill(COLOR_BG)
        
        x_min, x_max, y_min, y_max = self.get_visible_bounds()
        zoom = self.cell_width
        
        # We define a road thickness (width of road segment in world coords)
        road_thickness = 14.0
        
        # Helper to compute queue length
        def get_queue_length(road_state):
            q = 0
            for cell in reversed(road_state):
                if cell == 1:
                    q += 1
                else:
                    break
            return q
            
        # Draw roads
        for road_id, road in self.network.roads.items():
            if road.start_coord is None or road.end_coord is None:
                continue
                
            x1, y1 = road.start_coord
            x2, y2 = road.end_coord
            
            # Check for grid wrap-around roads in Case 5 (skip drawing long toroidal lines)
            dist = np.hypot(x2 - x1, y2 - y1)
            if self.case == 5 and dist > 350.0:
                continue
                
            dx = x2 - x1
            dy = y2 - y1
            
            # Unit direction and normal vector
            ux = dx / dist
            uy = dy / dist
            nx = -uy
            ny = ux
            
            # Shift lanes slightly to the right of direction of travel to draw two-way side-by-side
            offset_dist = 6.0
            x1_shifted = x1 + offset_dist * nx
            y1_shifted = y1 + offset_dist * ny
            x2_shifted = x2 + offset_dist * nx
            y2_shifted = y2 + offset_dist * ny
            
            # Draw road background line
            screen_start = (x1_shifted * zoom - self.camera_x, y1_shifted * zoom - self.camera_y)
            screen_end = (x2_shifted * zoom - self.camera_x, y2_shifted * zoom - self.camera_y)
            
            # Draw thick road line
            pygame.draw.line(self.screen, COLOR_ROAD_BG, screen_start, screen_end, int(road_thickness * zoom / 8.0 + 2))
            
            # Draw cells
            cell_size_world = dist / road.length
            
            for i in range(road.length):
                # Center of cell i
                cx = x1_shifted + (i + 0.5) * cell_size_world * ux
                cy = y1_shifted + (i + 0.5) * cell_size_world * uy
                
                # Check if visible
                if not (x_min - 20 <= cx <= x_max + 20 and y_min - 20 <= cy <= y_max + 20):
                    continue
                    
                # Corners of the cell
                w = cell_size_world
                h = road_thickness * 0.8
                
                p1 = (cx - 0.5 * w * ux - 0.5 * h * nx, cy - 0.5 * w * uy - 0.5 * h * ny)
                p2 = (cx + 0.5 * w * ux - 0.5 * h * nx, cy + 0.5 * w * uy - 0.5 * h * ny)
                p3 = (cx + 0.5 * w * ux + 0.5 * h * nx, cy + 0.5 * w * uy + 0.5 * h * ny)
                p4 = (cx - 0.5 * w * ux + 0.5 * h * nx, cy - 0.5 * w * uy + 0.5 * h * ny)
                
                screen_pts = [
                    (p * zoom - self.camera_x, q * zoom - self.camera_y)
                    for (p, q) in [p1, p2, p3, p4]
                ]
                
                if road.state[i] == 1:
                    pygame.draw.polygon(self.screen, COLOR_CAR, screen_pts)
                else:
                    if zoom > 4.0:
                        # Draw thin boundary outline for cell
                        pygame.draw.polygon(self.screen, COLOR_GRID, screen_pts, 1)
                        
            # Draw lane boundaries
            screen_edge1_start = ((x1_shifted - 0.5 * road_thickness * nx) * zoom - self.camera_x,
                                  (y1_shifted - 0.5 * road_thickness * ny) * zoom - self.camera_y)
            screen_edge1_end = ((x2_shifted - 0.5 * road_thickness * nx) * zoom - self.camera_x,
                                (y2_shifted - 0.5 * road_thickness * ny) * zoom - self.camera_y)
            screen_edge2_start = ((x1_shifted + 0.5 * road_thickness * nx) * zoom - self.camera_x,
                                  (y1_shifted + 0.5 * road_thickness * ny) * zoom - self.camera_y)
            screen_edge2_end = ((x2_shifted + 0.5 * road_thickness * nx) * zoom - self.camera_x,
                                (y2_shifted + 0.5 * road_thickness * ny) * zoom - self.camera_y)
            pygame.draw.line(self.screen, COLOR_TEXT, screen_edge1_start, screen_edge1_end, 1)
            pygame.draw.line(self.screen, COLOR_TEXT, screen_edge2_start, screen_edge2_end, 1)

        # Draw junctions
        for j_id, j in self.network.junctions.items():
            # Estimate junction coordinate from incoming roads
            coords = []
            for r_in_id in j.incoming_roads:
                r_in = self.network.roads.get(r_in_id)
                if r_in is not None and r_in.end_coord is not None:
                    coords.append(r_in.end_coord)
            for r_out_id in j.outgoing_roads:
                r_out = self.network.roads.get(r_out_id)
                if r_out is not None and r_out.start_coord is not None:
                    coords.append(r_out.start_coord)
                    
            if not coords:
                continue
                
            jx, jy = np.mean(coords, axis=0)
            
            # Skip drawing boundary wrap junctions to avoid visual clutter
            if "wrap" in j_id:
                continue
                
            # Circle marker for real junctions
            screen_j = (jx * zoom - self.camera_x, jy * zoom - self.camera_y)
            radius = max(6, int(road_thickness * zoom / 8.0 + 3))
            
            pygame.draw.circle(self.screen, COLOR_JUNCTION, screen_j, radius)
            pygame.draw.circle(self.screen, COLOR_TEXT, screen_j, radius, 1)
            
            # Label
            if zoom > 4.0:
                self.draw_text(j_id, screen_j[0] - 10, screen_j[1] - radius - 15, COLOR_TEXT, size=12, bold=True)
                
        # Draw UI Panels
        self.draw_hud()
        
        pygame.display.flip()

    def draw_hud(self):
        # Status Bar Panel (Top)
        hud_height = 95
        pygame.draw.rect(self.screen, COLOR_HUD_BG, (0, 0, self.width, hud_height))
        pygame.draw.line(self.screen, COLOR_TEXT, (0, hud_height), (self.width, hud_height), 1)
        
        # Text positioning
        y_offset = 8
        spacing = 18
        
        # Case Title
        case_titles = {
            1: "Case 1: One-Way Road",
            2: "Case 2: Two-Way No Interaction",
            3: "Case 3: T-Junction turns",
            4: "Case 4: 4-Way Intersection",
            5: "Case 5: 3x3 Grid Network"
        }
        title = case_titles.get(self.case, f"Case {self.case}: Custom Configuration")
        self.draw_text(title, 20, y_offset, COLOR_TEXT, size=20, bold=True)
        
        # Playback status
        status_str = "PAUSED" if self.paused else "RUNNING"
        status_color = COLOR_HIGHLIGHT if self.paused else COLOR_CAR
        self.draw_text(f"[{status_str}] Speed: {self.steps_per_second} steps/sec", 20, y_offset + 28, status_color, size=15, bold=True)
        
        # Metrics Column 1
        col_x = 420
        self.draw_text(f"Step: {self.step_count}", col_x, y_offset, COLOR_TEXT, size=14)
        self.draw_text(f"Target Density: {self.target_density:.2f}", col_x, y_offset + spacing, COLOR_TEXT, size=14)
        self.draw_text(f"Actual Density: {self.actual_density:.4f}", col_x, y_offset + 2 * spacing, COLOR_TEXT, size=14)
        
        # Metrics Column 2
        col_x_2 = 640
        self.draw_text(f"Measured Flow: {self.measured_flow:.4f}", col_x_2, y_offset, COLOR_TEXT, size=14)
        self.draw_text(f"Total Roads:   {len(self.network.roads)}", col_x_2, y_offset + spacing, COLOR_TEXT, size=14)
        self.draw_text(f"Total Vehicles: {self.network.get_total_cars()}", col_x_2, y_offset + 2 * spacing, COLOR_TEXT, size=14)

        # Metrics Column 3: Junction Queues & Road densities (Scrollable/Readout)
        col_x_3 = 880
        self.draw_text("Top Queues:", col_x_3, y_offset, COLOR_TEXT, size=13, bold=True)
        
        # Sort roads by queue length
        queues = []
        for r_id, road in self.network.roads.items():
            if "wrap" not in r_id:
                # Count consecutive cars at the end of the road
                q = 0
                for cell in reversed(road.state):
                    if cell == 1:
                        q += 1
                    else:
                        break
                queues.append((r_id, q, np.sum(road.state == 1) / max(1, road.length)))
                
        # Sort by queue length descending, then density descending
        queues.sort(key=lambda x: (-x[1], -x[2]))
        
        for idx, (r_id, q_len, r_density) in enumerate(queues[:3]):
            txt = f"{r_id}: Q={q_len} | d={r_density:.2f}"
            # Truncate road ID if too long
            if len(r_id) > 12:
                r_id_trunc = r_id[:9] + "..."
                txt = f"{r_id_trunc}: Q={q_len} | d={r_density:.2f}"
            self.draw_text(txt, col_x_3, y_offset + (idx + 1) * 16, COLOR_HIGHLIGHT if q_len > 3 else COLOR_TEXT, size=12)
            
        # Instruction Panel (Bottom)
        instr_height = 55
        pygame.draw.rect(self.screen, COLOR_HUD_BG, (0, self.height - instr_height, self.width, instr_height))
        pygame.draw.line(self.screen, COLOR_TEXT, (0, self.height - instr_height), (self.width, self.height - instr_height), 1)
        
        help_line1 = "[Space] Pause/Resume  |  [S] Step Once  |  [R] Reset  |  [Up/Down] Target Density"
        help_line2 = "[+/-] Zoom  |  [Scroll Wheel] Zoom  |  [Left/Right/Up/Down or Drag] Pan  |  [ [ / ] ] Sim Speed"
        
        self.draw_text(help_line1, 20, self.height - instr_height + 8, COLOR_TEXT, size=13)
        self.draw_text(help_line2, 20, self.height - instr_height + 28, COLOR_TEXT, size=13)

    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)
        pygame.quit()
