# FaaS Cold Start Scheduler Simulation

This project is a **practical, real-world simulation** of a Function-as-a-Service (FaaS) platform built with **Docker and Python**.  
It demonstrates and tests different **container scheduling strategies** to mitigate cold starts, inspired by the research paper  
**"LCS: Alleviating Total Cold Start Latency in Serverless Applications with LRU Warm Container Approach."**

---

## 🚀 Features

- **LCS (Least Recently Used)**: The proposed strategy that maximizes the warm pool by reusing the oldest idle container.
- **MRU (Most Recently Used)**: A cost-efficient strategy that picks the newest idle container.
- **Strategy Switching:** Change scheduling strategies dynamically via an API endpoint.
- **Affinity Scheduling:** Separate container pools per function (e.g., `function-a`, `function-b`).
- **Concurrency Limits:** Configurable max concurrent containers per function.
- **Request Queuing:** Requests beyond concurrency limit are queued, not dropped.
- **Dynamic Pool Creation:** Unknown functions create new pools automatically.
- **Scale-to-Zero (Janitor):** Idle containers are removed automatically after `WARM_TIME` seconds.
- **Statistics API:** `/stats` endpoint provides detailed JSON metrics (cold/warm starts, queues, etc.).

---
## 📁 Project Structure
```
.
├── my_function/
│   ├── app.py
│   └── Dockerfile
├── results/
│   ├── exp1_lru.json
│   └── exp1_mru.json
├── scheduler.py
├── run_experiment.sh
├── results.html
├── requirements.txt
└── README.md
```


---

## 🧩 Prerequisites

- **Docker Desktop** (or Docker Engine)
- **Python 3.7+**
- **jq** (for JSON processing)

**Install jq:**  
- Ubuntu/Debian → `sudo apt-get install jq`  
- macOS → `brew install jq`

---

## ⚙️ Setup & Installation

### 1️⃣ Clone the repository
```bash
git clone <your-repo-url>
cd coldBootFirstSem
```

### 2️⃣ Build the function container
```bash
docker build -t faas-function:latest ./my_function
```

### 3️⃣ Set up Python environment
```bash
python3 -m venv venv
source venv/bin/activate  # (Windows: venv\Scripts\activate)
```

### 4️⃣ Install dependencies
```bash
pip install -r requirements.txt
```

---

## ▶️ How to Run the Simulation

The simulation needs **two terminals**.

### 🖥️ Terminal 1: Start the Scheduler
```bash
python3 scheduler.py
```
Expected Output:
```
Starting Scheduler Service...
Connected to Docker daemon.
JANITOR: Starting up...
Starting API server on http://127.0.0.1:8080 .
```

### 🧪 Terminal 2: Run the Test Script
Make it executable once:
```bash
chmod +x run_experiment.sh
```

### Run
```bash
./run_experiment.sh <strategy> <exp_no> <size/5>
```

#### Run with LCS:
```bash
./run_experiment.sh lru 1 10
```

#### Run with MRU:
```bash
./run_experiment.sh mru 1 10
```

Each test runs 4 workloads and outputs stats to JSON (`results/<exp_no>_<strategy>.json`).

---

## 📊 Understanding the Output

Example (Test 3 - Affinity Test):

**LCS (Least Recently Used):**
```json
{
  "total_cold_starts": 5,
  "total_warm_starts": 3,
  "total_requests_queued": 0
}
```

**MRU (Most Recently Used):**
```json
{
  "total_cold_starts": 6,
  "total_warm_starts": 1,
  "total_requests_queued": 1
}
```

## 📊 Visualization Dashboard
Run:
```bash
python3 -m http.server 8000
```
Open:
```
http://localhost:8000/results.html
```

---

📈 **Analysis:** LCS results in fewer cold starts (5 vs. 6) and higher warm reuse (3 vs. 1).

---

## ⚙️ Configuration

Edit constants in `scheduler.py`:

| Variable | Description |
|-----------|-------------|
| `WARM_TIME` | Idle time (seconds) before a container is stopped |
| `JANITOR_SLEEP` | Interval for Janitor checks |
| `FUNCTION_POOLS` | Default concurrency per function |

---

## 🧠 Reference

**Paper:** *"LCS: Alleviating Total Cold Start Latency in Serverless Applications with LRU Warm Container Approach."*  
This simulation implements and compares that scheduling logic in a real Docker-based setup.

---

## 🧾 License

MIT License © 2025