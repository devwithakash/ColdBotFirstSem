# 🧊 FaaS Cold Start Scheduler Simulation

This project is a **Function-as-a-Service (FaaS)** platform simulation built with **Docker** and **Python**.  
It demonstrates and tests different **container scheduling strategies** to mitigate **cold starts**, inspired by the research paper:

> **"LCS: Alleviating Total Cold Start Latency in Serverless Applications with LRU Warm Container Approach."**

---

## 🎯 Objective

The simulation compares two container scheduling strategies:

- **MRU (Most Recently Used)** — A common cost-saving approach that picks the newest idle container.  
- **LCS (Least Recently Used)** — The proposed strategy from the paper, picking the *oldest* idle container to maximize the warm pool.

---

## ⚙️ Components

### 🧩 1. Function Container (`/my_function`)
- A Docker image (`faas-function:latest`) running a simple **Python Flask server**.
- Simulates a serverless “function” by performing a short task (`time.sleep(2)`).

### 🧠 2. Scheduler Service (`scheduler.py`)
- Acts as the **“brain”** of the FaaS platform.
- Runs a **Flask server** on port `8080` to handle incoming requests.
- Manages a **warm pool** of idle containers.
- Decides whether to start a **Cold Start** (new container) or reuse a **Warm Start** (existing container) based on the strategy.
- Includes a **Janitor thread** that periodically removes expired containers after `WARM_TIME`.

---

## 🧰 Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (or Docker Engine)
- Python **3.7+**

---

## 🚀 1. Setup

### 🏗️ Build the Function Container
From the project’s root directory:
```bash
docker build -t faas-function:latest ./my_function
```

---

### 🐍 Set Up the Python Environment
Create and activate a virtual environment for the scheduler.

```bash
# Create the venv
python3 -m venv venv

# Activate it (Linux/macOS)
source venv/bin/activate

# (On Windows)
venv\Scripts\activate
```

---

### 📦 Install Dependencies
```bash
pip install flask docker
```

---

## ▶️ 2. How to Run

### 🧠 Start the Scheduler
Run the scheduler script:
```bash
python3 scheduler.py
```

You should see:
```
Starting Scheduler Service...
Connected to Docker daemon.
JANITOR: Starting up...
Starting API server on http://127.0.0.1:8080 with LCS strategy.
```

---

### 🧪 Test the Lifecycle

#### 🧊 Test 1: Cold Start
```bash
curl http://127.0.0.1:8080/invoke
```
→ A **COLD START** occurs (a new container is created).

#### 🔥 Test 2: Warm Start
Run the same command again before `WARM_TIME` (default 20s) expires:
```bash
curl http://127.0.0.1:8080/invoke
```
→ A **WARM START** occurs (existing container is reused).

#### 🧹 Test 3: Janitor & New Cold Start
Wait for `WARM_TIME (20s) + JANITOR_SLEEP (5s)`, then observe:
- The Janitor stops and removes the expired container.
- Running the curl again triggers a **new Cold Start**.

---

## ⚖️ 3. How to Test: LCS vs MRU

This experiment verifies the difference between the two strategies.

### Step 1: Set Strategy to MRU
Edit `scheduler.py`:
```python
STRATEGY = "MRU"
```
Restart the scheduler:
```bash
python3 scheduler.py
```

---

### Step 2: Run the MRU Test
In a new terminal:
```bash
# Send two requests simultaneously (to create 2 cold starts)
curl http://127.0.0.1:8080/invoke &
curl http://127.0.0.1:8080/invoke &

# Wait for them to finish
echo "Waiting 5 seconds..."
sleep 5

# Send the test request
echo "Sending test request..."
curl http://127.0.0.1:8080/invoke
```

**Observe the logs:**
```
WARM START: Using MRU to select container C2...
```
→ It reuses the *most recently used* container (C2).

---

### Step 3: Set Strategy to LCS
Edit `scheduler.py`:
```python
STRATEGY = "LCS"
```
Restart:
```bash
python3 scheduler.py
```

---

### Step 4: Run the LCS Test
Repeat the same commands as before.

**Observe the logs:**
```
WARM START: Using LCS to select container C1...
```
→ It reuses the *least recently used* container (C1), refreshing it and extending its life — just as the research proposes.

---

## ⚙️ Configuration

You can modify these parameters at the top of `scheduler.py`:

| Variable | Description |
|-----------|-------------|
| `STRATEGY` | `"LCS"` or `"MRU"` — core scheduling logic |
| `WARM_TIME` | Idle time (in seconds) before a container expires |
| `JANITOR_SLEEP` | Interval (in seconds) for the janitor thread to run |

---

## 📈 Expected Behavior Summary

| Action | Description | Outcome |
|--------|--------------|----------|
| First Request | No warm container available | **Cold Start** |
| Subsequent Request (within WARM_TIME) | Warm container reused | **Warm Start** |
| After Expiry | Janitor removes container | **Cold Start (again)** |

---

## 🧩 References
- **Paper:** *LCS: Alleviating Total Cold Start Latency in Serverless Applications with LRU Warm Container Approach*  
- **Technologies:** Python, Flask, Docker

---

## 🧑‍💻 Author
**Akash Sachan**