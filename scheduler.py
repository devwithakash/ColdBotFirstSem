import docker
import time
import threading
import requests
import queue
import random # NEW: To handle variable execution time
from flask import Flask, request, jsonify
from enum import Enum, auto

# --- 1. Configuration ---

# We'll use LCS, but you can change this to "MRU"
STRATEGY = "LCS" 

# How long an idle container stays alive
WARM_TIME = 20  # 20 seconds

# How long the janitor waits between cleanup cycles
JANITOR_SLEEP = 5


# --- 2. State Management (NOW PER-FUNCTION) ---

class State(Enum):
    IDLE = auto()
    EXECUTING = auto()

# NEW: This is the core of our affinity-based routing.
# Each function gets its own pool, queue, and limit.
FUNCTION_POOLS = {
    "function-a": {
        "pool": {}, # Was WORKER_POOL
        "queue": queue.Queue(), # Was PENDING_REQUESTS
        "limit": 5 # Was MAX_CONTAINERS
    },
    "function-b": {
        "pool": {},
        "queue": queue.Queue(),
        "limit": 3 # Give B a smaller limit for testing
    },
    "function-c": {
        "pool": {},
        "queue": queue.Queue(),
        "limit": 3
    }
}

# We still use one global lock to modify the main FUNCTION_POOLS dict
POOLS_LOCK = threading.Lock()


# --- 3. The Scheduler (Warm/Cold Start Logic) ---

# MODIFIED: Now needs to know *which* pool to check
def get_warm_container(function_name):
    """Finds an idle container for a specific function."""
    
    worker_pool = FUNCTION_POOLS[function_name]["pool"]
    
    # Find all idle containers in this function's pool
    idle_containers = []
    for name, data in worker_pool.items():
        if data["state"] == State.IDLE:
            idle_containers.append((name, data))
    
    if not idle_containers:
        return None # No warm containers for this function
        
    if STRATEGY == "MRU":
        selected = sorted(idle_containers, key=lambda c: c[1]["last_used_time"], reverse=True)[0]
    else: # LCS
        selected = sorted(idle_containers, key=lambda c: c[1]["last_used_time"])[0]
    
    return selected[1]


# MODIFIED: Now needs to know *which* pool to add to
def start_new_container(docker_client, function_name):
    """Starts a new 'faas-function' container (a Cold Start) for a specific function."""
    print(f"COLD START ({function_name}): No warm containers. Starting a new one...")
    
    try:
        # We still use the *same* generic image. The "function" is just a label
        # for our scheduler's routing logic.
        container = docker_client.containers.run(
            "faas-function:latest", 
            detach=True,
            publish_all_ports=True
        )
        
        container.reload()
        host_port = container.ports["5000/tcp"][0]["HostPort"]
        
        print(f"COLD START ({function_name}): New container {container.short_id} running on port {host_port}.")
        
        # Wait for the server inside the container to boot up.
        time.sleep(1) 
        
        container_data = {
            "state": State.EXECUTING,
            "last_used_time": -1,
            "port": host_port,
            "container_obj": container
        }
        
        # Add the new container to the *correct* function's pool
        FUNCTION_POOLS[function_name]["pool"][container.name] = container_data
        return container_data
        
    except Exception as e:
        print(f"Error during cold start ({function_name}): {e}")
        return None


# --- 4. Janitor & Queue Processor (NOW PER-FUNCTION) ---

def run_janitor(docker_client):
    """Runs in a background thread to clean up old containers from ALL pools."""
    print("JANITOR: Starting up...")
    while True:
        with POOLS_LOCK:
            # NEW: Iterate over all defined function pools
            for func_name, pool_config in FUNCTION_POOLS.items():
                worker_pool = pool_config["pool"]
                
                # We copy the keys to avoid changing the dict while iterating
                for container_name in list(worker_pool.keys()):
                    data = worker_pool[container_name]
                    
                    if data["state"] == State.IDLE:
                        expiry_time = data["last_used_time"] + WARM_TIME
                        
                        if time.time() >= expiry_time:
                            print(f"JANITOR ({func_name}): Container {container_name[:12]} expired. Stopping...")
                            try:
                                data["container_obj"].stop()
                                data["container_obj"].remove()
                                del worker_pool[container_name] # Delete from the specific pool
                                print(f"JANITOR ({func_name}): Container {container_name[:12]} removed.")
                            except Exception as e:
                                print(f"JANITOR ({func_name}): Error removing {container_name[:12]}: {e}")
        
        time.sleep(JANITOR_SLEEP)


# MODIFIED: Now needs function_name to find the right queue
def process_queued_request(container_data, function_name):
    """
    This function processes items from a *specific function's* queue.
    """
    
    pool_config = FUNCTION_POOLS[function_name]
    pending_queue = pool_config["queue"]

    try:
        # 1. Check if there is work to do
        # We get the exec_time that was stored in the queue
        exec_time = pending_queue.get_nowait()
    except queue.Empty:
        # 2. Queue is empty. Set container to IDLE and finish.
        with POOLS_LOCK:
            container_data["state"] = State.IDLE
            container_data["last_used_time"] = time.time()
            print(f"QUEUE_PROC ({function_name}): Queue empty. Container {container_data['container_obj'].short_id} now IDLE.")
        return # End this thread's life

    # 3. Queue was NOT empty. Process the request.
    print(f"QUEUE_PROC ({function_name}): Popped request. Assigning to warm container {container_data['container_obj'].short_id}...")
    function_port = container_data["port"]
    function_url = f"http://127.0.0.1:{function_port}/"
    
    try:
        # NEW: Send the specific execution time to the container
        payload = {"exec_time": exec_time}
        requests.post(function_url, json=payload, timeout=5) # Increased timeout
        
        # 4. After finishing, RECURSIVELY call this function
        # This container keeps processing this function's queue.
        process_queued_request(container_data, function_name)
        
    except Exception as e:
        print(f"QUEUE_PROC ({function_name}): Error during queued execution: {e}")
        with POOLS_LOCK:
            container_data["state"] = State.IDLE
            container_data["last_used_time"] = time.time()


# --- 5. The API (The user's entry point) ---

app = Flask(__name__)

# MODIFIED: API now takes the function name in the URL
@app.route("/invoke/<function_name>")
def invoke_function(function_name):
    
    docker_client = docker.from_env()

    # NEW: Dynamic Pool Creation Logic
    # Check if the function is one we know how to handle
    if function_name not in FUNCTION_POOLS:
        # If not, acquire a lock to safely create it
        with POOLS_LOCK:
            # Double-check in case another thread created it
            # while this one was waiting for the lock
            if function_name not in FUNCTION_POOLS:
                print(f"SCHEDULER: First request for '{function_name}'. Dynamically creating new pool...")
                FUNCTION_POOLS[function_name] = {
                    "pool": {},
                    "queue": queue.Queue(),
                    "limit": 5 # Default limit for new functions
                }
    
    # --- From here, the logic proceeds as normal ---
    
    # Get the specific config for this function
    pool_config = FUNCTION_POOLS[function_name]
    worker_pool = pool_config["pool"]
    pending_queue = pool_config["queue"]
    limit = pool_config["limit"]
    
    container_data = None
    
    # NEW: Generate the random execution time *before* the lock
    # This is the "payload" of the request
    exec_time = random.uniform(0.5, 2.0) # 500ms to 2000ms
    
    with POOLS_LOCK:
        # 1. Try to find a warm container in this function's pool
        container_data = get_warm_container(function_name)
        
        if container_data:
            # --- WARM START ---
            print(f"WARM START ({function_name}): Using {STRATEGY} to select container {container_data['container_obj'].short_id}.")
            container_data["state"] = State.EXECUTING
            # Fall through to 'Execute the function' block
        
        else:
            # --- NO WARM CONTAINER ---
            # 2. Check if we can start a new one (check *this function's* limit)
            if len(worker_pool) < limit:
                # --- COLD START ---
                container_data = start_new_container(docker_client, function_name)
                if not container_data:
                    return jsonify({"error": "Cold start failed"}), 500
                # Fall through to 'Execute the function' block
            
            else:
                # --- AT LIMIT, QUEUE REQUEST ---
                print(f"AT LIMIT ({function_name}, {limit}): All containers busy. Queuing request.")
                # NEW: Put the *execution time* on the queue
                pending_queue.put(exec_time) 
                return jsonify({"message": "All workers busy, request queued."}), 202
    
    # --- Execute the function (EITHER WARM OR COLD START) ---
    function_port = container_data["port"]
    function_url = f"http://127.0.0.1:{function_port}/"
    
    try:
        start_exec_time = time.time()
        
        # NEW: Send the execution time in the request body
        payload = {"exec_time": exec_time}
        response = requests.post(function_url, json=payload, timeout=5) # Increased timeout
        
        end_exec_time = time.time()
        
        # --- After execution, CHECK QUEUE ---
        print(f"EXECUTION ({function_name}): Container {container_data['container_obj'].short_id} finished. Checking queue...")
        
        # Start the queue processor in a new thread
        threading.Thread(
            target=process_queued_request, 
            args=(container_data, function_name)
        ).start()
        
        return jsonify({
            "message": "Function executed",
            "function": function_name,
            "container_id": container_data["container_obj"].short_id,
            "execution_time_ms": (end_exec_time - start_exec_time) * 1000
        }), 200
        
    except Exception as e:
        print(f"Error during function execution: {e}")
        with POOLS_LOCK:
            container_data["state"] = State.IDLE
            container_data["last_used_time"] = time.time()
        return jsonify({"error": "Function execution failed"}), 500


# --- 6. Start Everything ---

if __name__ == "__main__":
    print(f"Starting Scheduler Service with {len(FUNCTION_POOLS)} functions defined.")
    
    # Connect to Docker
    client = docker.from_env()
    client.ping() # Test connection
    print("Connected to Docker daemon.")
    
    # Start the Janitor in a separate thread
    janitor_thread = threading.Thread(target=run_janitor, args=(client,), daemon=True)
    janitor_thread.start()
    
    # Start the main API server
    print(f"Starting API server on http://127.0.0.1:8080 with {STRATEGY} strategy.")
    app.run(host="0.0.0.0", port=8080)