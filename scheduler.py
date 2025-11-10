import docker
import time
import threading
import requests
import queue
import random
from flask import Flask, request, jsonify
from enum import Enum, auto

# --- 1. Configuration ---

# DEFAULT STRATEGY (can be changed by API)
STRATEGY = "LCS" 
STRATEGY_LOCK = threading.Lock() # Lock for changing the strategy

WARM_TIME = 20  # 20 seconds
JANITOR_SLEEP = 5

# --- 2. State Management (NOW PER-FUNCTION) ---

class State(Enum):
    IDLE = auto()
    EXECUTING = auto()

FUNCTION_POOLS = {
    "function-a": {
        "pool": {},
        "queue": queue.Queue(),
        "limit": 5
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
POOLS_LOCK = threading.Lock()

# Statistics Tracking
STATS = {
    "total_requests_received": 0,
    "total_requests_executed": 0,
    "total_cold_starts": 0,
    "total_warm_starts": 0,
    "total_requests_queued": 0,
    "total_limit_reached": 0,
    "functions": {}
}
STATS_LOCK = threading.Lock() 

def initialize_function_stats(function_name):
    if function_name not in STATS["functions"]:
        STATS["functions"][function_name] = {
            "requests_received": 0,
            "requests_executed": 0,
            "cold_starts": 0,
            "warm_starts": 0,
            "requests_queued": 0,
            "limit_reached": 0
        }

# --- 3. The Scheduler (Warm/Cold Start Logic) ---

def get_warm_container(function_name):
    """Finds an idle container for a specific function."""
    
    worker_pool = FUNCTION_POOLS[function_name]["pool"]
    
    idle_containers = []
    for name, data in worker_pool.items():
        if data["state"] == State.IDLE:
            idle_containers.append((name, data))
    
    if not idle_containers:
        return None
    
    # --- STRATEGY IS CHECKED HERE ---
    with STRATEGY_LOCK:
        current_strategy = STRATEGY
        
    if current_strategy == "MRU":
        selected = sorted(idle_containers, key=lambda c: c[1]["last_used_time"], reverse=True)[0]
    else: # LCS
        selected = sorted(idle_containers, key=lambda c: c[1]["last_used_time"])[0]
    
    return selected[1]


def start_new_container(docker_client, function_name):
    """Starts a new 'faas-function' container (a Cold Start) for a specific function."""
    print(f"COLD START ({function_name}): No warm containers. Starting a new one...")
    
    container = None
    
    try:
        container = docker_client.containers.run(
            "faas-function:latest", 
            detach=True,
            publish_all_ports=True
        )
        
        container.reload()
        host_port = container.ports["5000/tcp"][0]["HostPort"]
        
        print(f"COLD START ({function_name}): New container {container.short_id} running on port {host_port}. Waiting for health check...")
        
        start_poll = time.time()
        max_wait = 5
        health_check_url = f"http://127.0.0.1:{host_port}/" # Use root path for health
        
        while True:
            try:
                # Send a GET request for the health check
                requests.get(health_check_url, timeout=0.1)
                print(f"COLD START ({function_name}): Health check passed. Container is ready.")
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if time.time() - start_poll > max_wait:
                    raise Exception(f"Container {container.short_id} failed to boot in {max_wait}s.")
                time.sleep(0.1)

        container_data = {
            "state": State.EXECUTING,
            "last_used_time": -1,
            "port": host_port,
            "container_obj": container
        }
        
        FUNCTION_POOLS[function_name]["pool"][container.name] = container_data
        return container_data
        
    except Exception as e:
        print(f"Error during cold start ({function_name}): {e}")
        if container:
            try:
                container.stop()
                container.remove()
            except:
                pass
        return None


# --- 4. Janitor & Queue Processor (NOW PER-FUNCTION) ---

def run_janitor(docker_client):
    """Runs in a background thread to clean up old containers from ALL pools."""
    print("JANITOR: Starting up...")
    while True:
        with POOLS_LOCK:
            for func_name, pool_config in FUNCTION_POOLS.items():
                worker_pool = pool_config["pool"]
                
                for container_name in list(worker_pool.keys()):
                    if container_name not in worker_pool:
                        continue
                        
                    data = worker_pool[container_name]
                    
                    if data["state"] == State.IDLE:
                        expiry_time = data["last_used_time"] + WARM_TIME
                        
                        if time.time() >= expiry_time:
                            print(f"JANITOR ({func_name}): Container {container_name[:12]} expired. Stopping...")
                            try:
                                data["container_obj"].stop()
                                data["container_obj"].remove()
                                del worker_pool[container_name]
                                print(f"JANITOR ({func_name}): Container {container_name[:12]} removed.")
                            except Exception as e:
                                print(f"JANITOR ({func_name}): Error removing {container_name[:12]}: {e}")
        
        time.sleep(JANITOR_SLEEP)


def process_queued_request(container_data, function_name):
    """
    This function processes items from a *specific function's* queue.
    """
    
    if function_name not in FUNCTION_POOLS:
        return 
        
    pool_config = FUNCTION_POOLS[function_name]
    pending_queue = pool_config["queue"]

    try:
        exec_time = pending_queue.get_nowait()
    except queue.Empty:
        with POOLS_LOCK:
            if container_data["container_obj"].name in pool_config["pool"]:
                container_data["state"] = State.IDLE
                container_data["last_used_time"] = time.time()
                print(f"QUEUE_PROC ({function_name}): Queue empty. Container {container_data['container_obj'].short_id} now IDLE.")
        return

    print(f"QUEUE_PROC ({function_name}): Popped request. Assigning to warm container {container_data['container_obj'].short_id}...")
    function_port = container_data["port"]
    function_url = f"http://127.0.0.1:{function_port}/"
    
    try:
        payload = {"exec_time": exec_time}
        requests.post(function_url, json=payload, timeout=5)
        
        with STATS_LOCK:
            STATS["total_requests_executed"] += 1
            STATS["functions"][function_name]["requests_executed"] += 1
        
        process_queued_request(container_data, function_name)
        
    except Exception as e:
        print(f"QUEUE_PROC ({function_name}): Error during queued execution: {e}")
        with POOLS_LOCK:
            if container_data["container_obj"].name in pool_config["pool"]:
                container_data["state"] = State.IDLE
                container_data["last_used_time"] = time.time()


# --- 5. The API (The user's entry point) ---

app = Flask(__name__)

@app.route("/invoke/<function_name>")
def invoke_function(function_name):
    
    docker_client = docker.from_env()

    with POOLS_LOCK:
        if function_name not in FUNCTION_POOLS:
            print(f"SCHEDULER: First request for '{function_name}'. Dynamically creating new pool...")
            FUNCTION_POOLS[function_name] = {
                "pool": {},
                "queue": queue.Queue(),
                "limit": 5 # Default limit
            }
            with STATS_LOCK:
                initialize_function_stats(function_name)
    
    with STATS_LOCK:
        initialize_function_stats(function_name) # Ensure stats exist just in case
        STATS["total_requests_received"] += 1
        STATS["functions"][function_name]["requests_received"] += 1

    
    pool_config = FUNCTION_POOLS[function_name]
    worker_pool = pool_config["pool"]
    pending_queue = pool_config["queue"]
    limit = pool_config["limit"]
    
    container_data = None
    exec_time = random.uniform(0.5, 2.0)
    
    with POOLS_LOCK:
        container_data = get_warm_container(function_name)
        
        if container_data:
            # --- WARM START ---
            with STRATEGY_LOCK:
                current_strategy = STRATEGY
            print(f"WARM START ({function_name}): Using {current_strategy} to select container {container_data['container_obj'].short_id}.")
            container_data["state"] = State.EXECUTING
            
            with STATS_LOCK:
                STATS["total_warm_starts"] += 1
                STATS["functions"][function_name]["warm_starts"] += 1
        
        else:
            # --- NO WARM CONTAINER ---
            if len(worker_pool) < limit:
                # --- COLD START ---
                container_data = start_new_container(docker_client, function_name)
                if not container_data:
                    return jsonify({"error": "Cold start failed"}), 500
                
                with STATS_LOCK:
                    STATS["total_cold_starts"] += 1
                    STATS["functions"][function_name]["cold_starts"] += 1
            
            else:
                # --- AT LIMIT, QUEUE REQUEST ---
                print(f"AT LIMIT ({function_name}, {limit}): All containers busy. Queuing request.")
                pending_queue.put(exec_time)
                
                with STATS_LOCK:
                    STATS["total_requests_queued"] += 1
                    STATS["total_limit_reached"] += 1
                    STATS["functions"][function_name]["requests_queued"] += 1
                    STATS["functions"][function_name]["limit_reached"] += 1
                    
                return jsonify({"message": "All workers busy, request queued."}), 202
    
    # --- Execute the function (EITHER WARM OR COLD START) ---
    function_port = container_data["port"]
    function_url = f"http://127.0.0.1:{function_port}/"
    
    try:
        start_exec_time = time.time()
        payload = {"exec_time": exec_time}
        response = requests.post(function_url, json=payload, timeout=5)
        end_exec_time = time.time()
        
        with STATS_LOCK:
            STATS["total_requests_executed"] += 1
            STATS["functions"][function_name]["requests_executed"] += 1

        print(f"EXECUTION ({function_name}): Container {container_data['container_obj'].short_id} finished. Checking queue...")
        
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
            if function_name in FUNCTION_POOLS and container_data["container_obj"].name in FUNCTION_POOLS[function_name]["pool"]:
                container_data["state"] = State.IDLE
                container_data["last_used_time"] = time.time()
        return jsonify({"error": "Function execution failed"}), 500

# --- 6. Statistics & Strategy Endpoints ---

@app.route("/stats")
def get_stats():
    """Returns a JSON object with all current execution statistics."""
    with STATS_LOCK:
        return jsonify(STATS)

@app.route("/stats/reset", methods=["POST"])
def reset_stats():
    """Resets all statistics to zero."""
    global STATS
    with STATS_LOCK:
        STATS = {
            "total_requests_received": 0,
            "total_requests_executed": 0,
            "total_cold_starts": 0,
            "total_warm_starts": 0,
            "total_requests_queued": 0,
            "total_limit_reached": 0,
            "functions": {}
        }
        with POOLS_LOCK:
            for func_name in FUNCTION_POOLS.keys():
                initialize_function_stats(func_name)
                
    print("--- STATS RESET ---")
    return jsonify({"message": "Stats reset successfully."})

# --- NEW: API ENDPOINT TO SET STRATEGY ---
@app.route("/set_strategy", methods=["POST"])
def set_strategy():
    """Sets the global scheduling strategy (LCS or MRU)."""
    global STRATEGY
    data = request.get_json()
    
    if not data or "strategy" not in data:
        return jsonify({"error": "Missing 'strategy' in JSON body"}), 400
        
    new_strategy = data["strategy"].upper()
    
    if new_strategy in ["LCS", "MRU"]:
        with STRATEGY_LOCK:
            STRATEGY = new_strategy
        print(f"--- STRATEGY SET TO {STRATEGY} ---")
        return jsonify({"message": f"Strategy set to {STRATEGY}"}), 200
    else:
        return jsonify({"error": "Invalid strategy. Must be 'LCS' or 'MRU'."}), 400


# --- 7. Start Everything ---

if __name__ == "__main__":
    print(f"Starting Scheduler Service with {len(FUNCTION_POOLS)} functions defined.")
    
    with STATS_LOCK:
        for func_name in FUNCTION_POOLS.keys():
            initialize_function_stats(func_name)
    
    client = docker.from_env()
    client.ping()
    print("Connected to Docker daemon.")
    
    janitor_thread = threading.Thread(target=run_janitor, args=(client,), daemon=True)
    janitor_thread.start()
    
    print(f"Starting API server on http://127.0.0.1:8080 with {STRATEGY} strategy.")
    app.run(host="0.0.0.0", port=8080)