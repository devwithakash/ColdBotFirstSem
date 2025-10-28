# scheduler.py
import docker
import time
import threading
import requests
from flask import Flask
from enum import Enum, auto

# --- 1. Configuration ---

# We'll use LCS, but you can change this to "MRU"
STRATEGY = "LCS" 

# How long an idle container stays alive
WARM_TIME = 20  # 20 seconds

# How long the janitor waits between cleanup cycles
JANITOR_SLEEP = 5


# --- 2. State Management ---

class State(Enum):
    IDLE = auto()
    EXECUTING = auto()

# This is our "worker_pool" from the simulation,
# but now it tracks real Docker containers.
#
# Format:
# "container_name": {
#   "state": State.IDLE,
#   "last_used_time": 123456.789,
#   "port": 32768, # The host port
#   "container_obj": <Docker Container Object>
# }
WORKER_POOL = {}

# We use a Lock to prevent race conditions
# (e.g., janitor cleaning a container while it's being assigned)
POOL_LOCK = threading.Lock()


# --- 3. The Scheduler (Warm/Cold Start Logic) ---

def get_warm_container():
    """Finds an idle container using the chosen strategy."""

    # Find all idle containers
    idle_containers = []
    for name, data in WORKER_POOL.items():
        if data["state"] == State.IDLE:
            idle_containers.append((name, data))

    if not idle_containers:
        return None # No warm containers

    if STRATEGY == "MRU":
        # MRU: Sort by last_used_time DESCENDING (newest first)
        selected = sorted(idle_containers, key=lambda c: c[1]["last_used_time"], reverse=True)[0]
    else: # LCS
        # LCS: Sort by last_used_time ASCENDING (oldest first)
        selected = sorted(idle_containers, key=lambda c: c[1]["last_used_time"])[0]

    # Return the chosen container's data
    return selected[1]


def start_new_container(docker_client):
    """Starts a new 'faas-function' container (a Cold Start)."""
    print(f"COLD START: No warm containers. Starting a new one...")

    try:
        # We use publish_all_ports=True to let Docker pick a random
        # available port on the host to map to port 5000.
        container = docker_client.containers.run(
            "faas-function:latest",
            detach=True,
            publish_all_ports=True
        )

        # We need to inspect the container to find out
        # which host port Docker assigned.
        container.reload()
        host_port = container.ports["5000/tcp"][0]["HostPort"]

        print(f"COLD START: New container {container.short_id} running on port {host_port}.")

        # We must wait a moment for the server inside
        # the container to boot up before we can use it.
        time.sleep(1) # Simple, but not robust.

        # Create the entry for our pool
        container_data = {
            "state": State.EXECUTING,
            "last_used_time": -1,
            "port": host_port,
            "container_obj": container
        }

        # Add to the pool
        WORKER_POOL[container.name] = container_data
        return container_data

    except Exception as e:
        print(f"Error during cold start: {e}")
        return None


# --- 4. The Janitor (Cleans up expired containers) ---

def run_janitor(docker_client):
    """Runs in a background thread to clean up old containers."""
    print("JANITOR: Starting up...")
    while True:
        with POOL_LOCK:
            # We copy the keys to avoid changing the dict while iterating
            for container_name in list(WORKER_POOL.keys()):

                data = WORKER_POOL[container_name]

                if data["state"] == State.IDLE:
                    expiry_time = data["last_used_time"] + WARM_TIME

                    if time.time() >= expiry_time:
                        print(f"JANITOR: Container {container_name[:12]} expired. Stopping...")
                        try:
                            data["container_obj"].stop()
                            data["container_obj"].remove()
                            del WORKER_POOL[container_name]
                            print(f"JANITOR: Container {container_name[:12]} removed.")
                        except Exception as e:
                            print(f"JANITOR: Error removing {container_name[:12]}: {e}")

        # Wait before the next cleanup cycle
        time.sleep(JANITOR_SLEEP)


# --- 5. The API (The user's entry point) ---

app = Flask(__name__)

@app.route("/invoke")
def invoke_function():

    # Connect to the Docker daemon
    docker_client = docker.from_env()

    container = None

    with POOL_LOCK:
        # Try to find a warm container
        container_data = get_warm_container()

        if container_data:
            # --- WARM START ---
            print(f"WARM START: Using {STRATEGY} to select container {container_data['container_obj'].short_id} on port {container_data['port']}.")
            container_data["state"] = State.EXECUTING
            container = container_data
        else:
            # --- COLD START ---
            container = start_new_container(docker_client)
            if not container:
                return {"error": "Cold start failed"}, 500

    # --- Execute the function ---
    # Now that we have a container (warm or cold),
    # send it the HTTP request.
    function_port = container["port"]
    function_url = f"http://127.0.0.1:{function_port}/"

    try:
        start_exec_time = time.time()
        response = requests.post(function_url) # This is the actual execution
        end_exec_time = time.time()

        # --- After execution, mark as IDLE ---
        with POOL_LOCK:
            container["state"] = State.IDLE
            container["last_used_time"] = time.time()
            print(f"EXECUTION: Container {container['container_obj'].short_id} finished. Now IDLE.")

        return {
            "message": "Function executed",
            "container_id": container["container_obj"].short_id,
            "execution_time_ms": (end_exec_time - start_exec_time) * 1000
        }, 200

    except Exception as e:
        # Handle if the container dies
        print(f"Error during function execution: {e}")
        # We'll mark it as idle so the janitor can clean it
        with POOL_LOCK:
            container["state"] = State.IDLE
            container["last_used_time"] = time.time()
        return {"error": "Function execution failed"}, 500


# --- 6. Start Everything ---

if __name__ == "__main__":
    print("Starting Scheduler Service...")

    # Connect to Docker
    client = docker.from_env()
    client.ping() # Test connection
    print("Connected to Docker daemon.")

    # Start the Janitor in a separate thread
    janitor_thread = threading.Thread(target=run_janitor, args=(client,), daemon=True)
    janitor_thread.start()

    # Start the main API server
    # We run this on port 8080
    print(f"Starting API server on http://127.0.0.1:8080 with {STRATEGY} strategy.")
    app.run(host="0.0.0.0", port=8080)