import numpy as np

class Junction:
    def __init__(self, junction_id: str, incoming_roads: list, outgoing_roads: list, turn_proportions: dict):
        """
        Represents an intersection point in the network where roads meet.
        
        Args:
            junction_id: Unique identifier for the junction.
            incoming_roads: List of incoming road IDs.
            outgoing_roads: List of outgoing road IDs.
            turn_proportions: Dictionary mapping incoming_road_id -> dict of {outgoing_road_id: probability}.
                              Must sum to 1.0 per incoming road.
        """
        self.junction_id = junction_id
        self.incoming_roads = list(incoming_roads)
        self.outgoing_roads = list(outgoing_roads)
        self.turn_proportions = turn_proportions
        
        self.validate_proportions()

    def validate_proportions(self):
        """
        Validates that turn proportions are configured for all incoming roads
        and that they sum to 1.0 (within float tolerance) for each.
        Also verifies that outgoing roads specified are valid.
        """
        for road_id in self.incoming_roads:
            if road_id not in self.turn_proportions:
                raise ValueError(f"Junction {self.junction_id}: Missing turn proportions for incoming road {road_id}")
            
            proportions = self.turn_proportions[road_id]
            total = sum(proportions.values())
            if not np.isclose(total, 1.0, atol=1e-6):
                raise ValueError(f"Junction {self.junction_id}: Proportions for incoming road {road_id} sum to {total}, must sum to 1.0")
            
            for out_id in proportions.keys():
                if out_id not in self.outgoing_roads:
                    raise ValueError(f"Junction {self.junction_id}: Outgoing road {out_id} in proportions is not in outgoing_roads list")

    def decide_exit_road(self, incoming_road_id: str, rng: np.random.Generator) -> str:
        """
        Decides the outgoing road for a car coming from incoming_road_id using the configured turn proportions.
        """
        if incoming_road_id not in self.turn_proportions:
            raise ValueError(f"Junction {self.junction_id}: No turn proportions configured for incoming road {incoming_road_id}")
        
        proportions = self.turn_proportions[incoming_road_id]
        roads = list(proportions.keys())
        probabilities = list(proportions.values())
        
        # Perform weighted random choice
        return rng.choice(roads, p=probabilities)

def decide_exit_road(incoming_road_id: str, turn_proportions: dict, rng: np.random.Generator) -> str:
    """
    Decides the outgoing road for a car coming from incoming_road_id using the provided turn proportions.
    Used as a helper or standalone function.
    """
    if incoming_road_id not in turn_proportions:
        raise ValueError(f"No turn proportions configured for incoming road {incoming_road_id}")
    
    proportions = turn_proportions[incoming_road_id]
    roads = list(proportions.keys())
    probabilities = list(proportions.values())
    
    # Perform weighted random choice
    return rng.choice(roads, p=probabilities)
