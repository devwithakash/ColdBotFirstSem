import time
from flask import Flask, request

app = Flask(__name__)

@app.route("/", methods=["POST"])
def execute_function():
    # NEW: Get the execution time from the JSON payload
    data = request.get_json()
    # Default to 0.5s if not provided
    exec_time = data.get("exec_time", 0.5) 
    
    # Simulate work
    time.sleep(exec_time)
    
    return {"message": "Function executed successfully!", "exec_time": exec_time}, 200

if __name__ == "__main__":
    # Run inside the container on port 5000
    app.run(host="0.0.0.0", port=5000)
'''```

### 3. Re-Build Your Docker Image

**This is a critical step!** You must rebuild your `faas-function:latest` image so it includes the `app.py` changes.

Run this from your project's root directory:
```bash
docker build -t faas-function:latest ./my_function
```

### 4. How to Test Your Affinity Scheduler

1.  Run the new scheduler: `python3 scheduler.py`
2.  Open a **new terminal**.
3.  Set the limit for `function-b` to **2** in `scheduler.py` for a clear test.
4.  Copy and paste this command block. It will send **4 requests to `function-b`** and **2 requests to `function-a`** all at once.

    ```bash
    # Send 4 requests to function-b (limit 2) and 2 to function-a (limit 5)
    curl http://127.0.0.1:8080/invoke/function-b &
    curl http://127.0.0.1:8080/invoke/function-b &
    curl http://127.0.0.1:8080/invoke/function-b &
    curl http://127.0.0.1:8080/invoke/function-b &
    curl http://127.0.0.1:8080/invoke/function-a &
    curl http://127.0.0.1:8080/invoke/function-a'''