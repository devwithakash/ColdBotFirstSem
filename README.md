# 🚀 FaaS Cold Start Scheduler Simulation

A real-world Docker-based simulation comparing container scheduling strategies:
- **LCS (Least Recently Used)**
- **MRU (Most Recently Used)**

Inspired by the paper:
**"LCS: Alleviating Total Cold Start Latency in Serverless Applications with LRU Warm Container Approach."**

---

## ✨ Features
- LCS & MRU scheduling
- Strategy switching via API
- Affinity scheduling
- Concurrency limits
- Request queuing
- Dynamic warm pools
- Scale-to-zero janitor
- JSON statistics API
- Automated experiment runner
- Graph visualization dashboard

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
- Docker Desktop
- Python 3.7+
- jq

---

## ⚙️ Installation
```bash
git clone <your-repo-url>
cd lcs-docker-project
docker build -t faas-function:latest ./my_function
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ▶️ Run the Simulation

### Terminal 1 → Start Scheduler
```bash
python3 scheduler.py
```

### Terminal 2 → Run Experiment
```bash
chmod +x run_experiment.sh
./run_experiment.sh lru 1 10
./run_experiment.sh mru 1 10
```

---

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

## 🧠 Reference
Paper: *“LCS: Alleviating Total Cold Start Latency in Serverless Applications with LRU Warm Container Approach.”*

---

## 🧾 License
MIT License © 2025
