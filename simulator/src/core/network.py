import numpy as np
from src.core.junction import Junction
from src.core.rule184 import step as rule184_step

class Road:
    def __init__(self, road_id: str, length: int, start_coord=None, end_coord=None, periodic: bool = False):
        """
        Represents a single lane of a road as a 1D cellular automaton.
        
        Args:
            road_id: Unique identifier for the road.
            length: Number of cells in the road.
            start_coord: (x, y) coordinates of the start of the road (for rendering).
            end_coord: (x, y) coordinates of the end of the road (for rendering).
            periodic: If True, behaves as a standalone periodic road (Phase 1/2 style).
        """
        self.road_id = road_id
        self.length = length
        self.state = np.zeros(length, dtype=np.int8)
        self.start_coord = start_coord
        self.end_coord = end_coord
        self.periodic = periodic

    def initialize_density(self, density: float, rng: np.random.Generator):
        """
        Randomly populates the road with vehicles based on a target density.
        """
        if self.length <= 0:
            return
        num_cars = int(round(self.length * density))
        num_cars = max(0, min(num_cars, self.length))
        
        self.state = np.zeros(self.length, dtype=np.int8)
        if num_cars > 0:
            indices = rng.choice(self.length, size=num_cars, replace=False)
            self.state[indices] = 1


class Network:
    def __init__(self):
        """
        Manages the collection of roads and junctions and updates their states.
        """
        self.roads = {}       # road_id -> Road
        self.junctions = {}   # junction_id -> Junction
        
        # Lookups helper dictionaries
        self.road_end_junction = {}    # road_id -> Junction
        self.road_start_junction = {}  # road_id -> Junction

    def add_road(self, road: Road):
        self.roads[road.road_id] = road

    def add_junction(self, junction: Junction):
        self.junctions[junction.junction_id] = junction
        # Update lookup helpers
        for r_in in junction.incoming_roads:
            self.road_end_junction[r_in] = junction
        for r_out in junction.outgoing_roads:
            self.road_start_junction[r_out] = junction

    def step(self, rng: np.random.Generator) -> int:
        """
        Executes one synchronous update step for the entire network.
        Ensures zero collisions at junctions and within roads.
        
        Returns:
            The total number of vehicle movements in this step.
        """
        # Dictionary to store the target outgoing road chosen by cars at the end of incoming roads
        # key: outgoing_road_id -> value: list of incoming_road_ids that want to enter it
        targets = {r_id: [] for r_id in self.roads}
        exits = []  # List of incoming road IDs whose cars exit the network
        
        # 1. Decision phase: for each road ending at a junction, if last cell is occupied, decide target
        for road_id, road in self.roads.items():
            if road.periodic:
                continue
            if road.length > 0 and road.state[-1] == 1:
                j = self.road_end_junction.get(road_id)
                if j is not None:
                    target_road_id = j.decide_exit_road(road_id, rng)
                    if target_road_id is not None:
                        targets[target_road_id].append(road_id)
                    else:
                        exits.append(road_id)
                else:
                    exits.append(road_id)

        # 2. Conflict resolution at junction entry cells
        # will_move_last[r_in] will be True if the car at the last cell of r_in is allowed to move
        will_move_last = {r_id: False for r_id in self.roads}
        
        # Exits always move successfully (exit network)
        for road_id in exits:
            will_move_last[road_id] = True

        for out_road_id, incoming_list in targets.items():
            if not incoming_list:
                continue
            
            out_road = self.roads[out_road_id]
            # Target first cell must be empty at the start of the step
            if out_road.length > 0 and out_road.state[0] == 0:
                # Randomly select exactly one incoming road to cross
                selected_in_road = rng.choice(incoming_list)
                will_move_last[selected_in_road] = True
                
        # 3. Apply updates to all roads synchronously
        new_states = {}
        num_moves = 0
        
        for road_id, road in self.roads.items():
            if road.periodic:
                # Use standard periodic Rule 184 step
                next_state = rule184_step(road.state, periodic=True)
                # Count moves: cars that were at i and next cell was empty
                moves = int(np.sum((road.state == 1) & (np.roll(road.state, -1) == 0)))
                num_moves += moves
                new_states[road_id] = next_state
                continue
            
            L = road.length
            if L == 0:
                new_states[road_id] = road.state
                continue
                
            new_state = np.zeros(L, dtype=np.int8)
            
            # Count internal moves
            if L > 1:
                internal_moves = int(np.sum((road.state[:-1] == 1) & (road.state[1:] == 0)))
                num_moves += internal_moves
            
            # Count junction moves
            if will_move_last.get(road_id, False):
                num_moves += 1
            
            # Update internal cells (indices 1 to L-2)
            if L > 2:
                # Car stays if next cell is occupied, else moves (becomes empty)
                # Empty cell becomes occupied if previous cell has a car
                for i in range(1, L - 1):
                    if road.state[i] == 1:
                        new_state[i] = 1 if road.state[i+1] == 1 else 0
                    else:
                        new_state[i] = 1 if road.state[i-1] == 1 else 0
            
            # Update cell 0 (start of road)
            if L > 1:
                if road.state[0] == 1:
                    # Car stays if cell 1 is occupied
                    new_state[0] = 1 if road.state[1] == 1 else 0
                else:
                    # Empty cell 0 can receive a car from the junction
                    j_start = self.road_start_junction.get(road_id)
                    received_car = False
                    if j_start is not None:
                        # Check if any incoming road to this junction targeted this road and successfully moved
                        for r_in in j_start.incoming_roads:
                            if will_move_last.get(r_in) and road_id in targets and r_in in targets[road_id]:
                                received_car = True
                                break
                    new_state[0] = 1 if received_car else 0
            else:
                # Road of length 1 (cell 0 is also cell L-1)
                # It behaves as a single cell junction transition
                if road.state[0] == 1:
                    new_state[0] = 0 if will_move_last.get(road_id, False) else 1
                else:
                    j_start = self.road_start_junction.get(road_id)
                    received_car = False
                    if j_start is not None:
                        for r_in in j_start.incoming_roads:
                            if will_move_last.get(r_in) and road_id in targets and r_in in targets[road_id]:
                                received_car = True
                                break
                    new_state[0] = 1 if received_car else 0
                    
            # Update cell L-1 (end of road)
            if L > 1:
                if road.state[L-1] == 1:
                    # Car stays if it was NOT allowed to move across the junction
                    new_state[L-1] = 0 if will_move_last.get(road_id, False) else 1
                else:
                    # Empty cell L-1 receives a car if cell L-2 is occupied
                    new_state[L-1] = 1 if road.state[L-2] == 1 else 0
                    
            new_states[road_id] = new_state
            
        # Update states
        for road_id, road in self.roads.items():
            road.state = new_states[road_id]
            
        return num_moves

    def get_total_cars(self) -> int:
        return sum(np.sum(road.state == 1) for road in self.roads.values())

    def get_average_density(self) -> float:
        total_cells = sum(road.length for road in self.roads.values())
        if total_cells == 0:
            return 0.0
        return self.get_total_cars() / total_cells
