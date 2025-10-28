import time
from enum import Enum, auto

# --- 1. Constants & Configuration ---

# How long a function takes to run (simulated time units)
EXECUTION_TIME = 2
# How long an idle container stays alive before being released
WARM_TIME = 10
# The function we are testing (for affinity scheduling)
TARGET_FUNCTION = "Function_A"
# How long the simulation will run
SIMULATION_END_TIME = 25

# A simple state machine for our containers
class State(Enum):
    IDLE = auto()
    EXECUTING = auto()
    RELEASED = auto()

# --- 2. Core Class Definitions ---

class Request:
    """A simple object to represent an incoming function request."""
    def __init__(self, arrival_time, function_id):
        self.arrival_time = arrival_time
        self.function_id = function_id

class Container:
    """Represents a single function container on a worker."""
    def __init__(self, function_id, creation_time):
        self.function_id = function_id
        self.state = State.EXECUTING
        # When will this container finish its current job?
        self.execution_end_time = creation_time + EXECUTION_TIME
        # When did this container *last become idle*? This is the key.
        self.last_used_time = -1 # Not idle yet
        print(f"    [t={creation_time}] \U0001F9CA COLD START: New container created. Finishes at t={self.execution_end_time}.")

    def execute(self, current_time):
        """Assigns a new job to this idle container (a warm start)."""
        self.state = State.EXECUTING
        self.execution_end_time = current_time + EXECUTION_TIME
        self.last_used_time = -1 # No longer idle
        print(f"    [t={current_time}] \U0001F525 WARM START: Reusing container. Finishes at t={self.execution_end_time}.")

    def update(self, current_time):
        """Runs on every tick of the clock to update the container's state."""
        
        # First, check if an idle container should be released
        if self.state == State.IDLE:
            # Release if 'current_time' is at or beyond the expiration time
            if current_time >= self.last_used_time + WARM_TIME:
                self.state = State.RELEASED
                print(f"    [t={current_time}] \U0001F4A8 RELEASED: Container expired (last_used={self.last_used_time} + WARM_TIME={WARM_TIME}).")
                return False # Signal to the worker to remove this container

        # Second, check if an executing container has finished
        if self.state == State.EXECUTING and current_time == self.execution_end_time:
            self.state = State.IDLE
            self.last_used_time = current_time # This is the crucial timestamp
            print(f"    [t={current_time}] \U0001F7E2 IDLE: Container finished job. last_used_time={self.last_used_time}")
        
        return True # Signal to the worker to keep this container

# --- 3. The Main Simulation ---

def run_simulation(strategy, requests_template):
    """
    Runs the entire serverless simulation for a given strategy ("MRU" or "LCS").
    """
    print(f"\n{'='*20} \n\U0001F3C1 STARTING SIMULATION: {strategy} Strategy \U0001F3C1 \n{'='*20}")
    
    # This list represents our Worker Node's container pool
    worker_pool = []
    # Create a fresh copy of the requests for this run
    requests_queue = sorted([req for req in requests_template], key=lambda r: r.arrival_time)
    total_cold_starts = 0

    # The main clock loop
    for clock in range(SIMULATION_END_TIME):
        print(f"--- t={clock} ---")
        
        # 1. Update all containers in the pool
        # We iterate over a copy [:] so we can safely remove items
        for container in worker_pool[:]:
            keep = container.update(clock)
            if not keep:
                worker_pool.remove(container) # Container was released
        
        # 2. Process arriving requests for this time unit
        # We use a while loop in case multiple requests arrive at the same time
        while requests_queue and requests_queue[0].arrival_time == clock:
            request = requests_queue.pop(0)
            print(f"  [t={clock}] \U0001F4E8 REQUEST: Received for {request.function_id}.")
            
            # Find available warm containers
            # (Affinity is implicit: we only look in this one worker_pool)
            warm_containers = [
                c for c in worker_pool 
                if c.function_id == request.function_id and c.state == State.IDLE
            ]
            
            if not warm_containers:
                # --- CASE 1: COLD START ---
                total_cold_starts += 1
                new_container = Container(request.function_id, clock)
                worker_pool.append(new_container)
            else:
                # --- CASE 2: WARM START ---
                print(f"    Found {len(warm_containers)} warm container(s).")
                
                selected_container = None
                if strategy == "MRU":
                    # MRU: Sort by last_used_time DESCENDING, pick the first
                    selected_container = sorted(warm_containers, key=lambda c: c.last_used_time, reverse=True)[0]
                else: # LCS
                    # LCS: Sort by last_used_time ASCENDING, pick the first
                    selected_container = sorted(warm_containers, key=lambda c: c.last_used_time)[0]
                
                print(f"    {strategy} selected container (last_used_time={selected_container.last_used_time}).")
                selected_container.execute(clock)

        # Optional: Add a small delay to make the simulation watchable
        # time.sleep(0.1)

    print(f"\n--- \U0001F3C1 Simulation End ({strategy}) ---")
    print(f"Total Cold Starts: {total_cold_starts}")
    print("="*40)
    return total_cold_starts

# --- 4. Run and Compare ---

if __name__ == "__main__":
    
    # This specific request stream is designed to show the difference.
    # WARM_TIME = 10, EXEC_TIME = 2
    # - t=1: CS 1 -> C1 created. Becomes idle at t=3. (Expires at t=3+10=13)
    # - t=2: CS 2 -> C2 created. Becomes idle at t=4. (Expires at t=4+10=14)
    #
    # - t=12: Request arrives.
    #   - MRU: Picks C2 (idle@4). C2 becomes idle at t=14.
    #   - LCS: Picks C1 (idle@3). C1 becomes idle at t=14.
    #
    # - t=13: Request arrives.
    #   - MRU Run: At t=13, C1 expires (13 >= 3+10). Pool is empty. -> COLD START 3
    #   - LCS Run: At t=13, C1 is busy. C2 (idle@4) is checked. (13 >= 4+10) is FALSE. -> WARM START
    
    REQUEST_STREAM = [
        Request(1, TARGET_FUNCTION),
        Request(2, TARGET_FUNCTION),
        Request(12, TARGET_FUNCTION),
        Request(13, TARGET_FUNCTION),
    ]
    
    mru_starts = run_simulation("MRU", REQUEST_STREAM)
    lcs_starts = run_simulation("LCS", REQUEST_STREAM)
    
    print("\n--- \U0001F4C8 Final Comparison ---")
    print(f"MRU (Most Recently Used) Total Cold Starts: {mru_starts}")
    print(f"LCS (Least Recently Used) Total Cold Starts: {lcs_starts}")
    
    if mru_starts > lcs_starts:
        improvement = (mru_starts - lcs_starts) / mru_starts * 100
        print(f"\n\U0001F44D LCS (the paper's approach) performed {improvement:.0f}% better.")
    else:
        print("\n\U0001F914 This scenario did not show a difference. Try adjusting WARM_TIME or request times.")