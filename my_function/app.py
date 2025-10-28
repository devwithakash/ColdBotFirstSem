# my_function/app.py
import time
from flask import Flask

app = Flask(__name__)

# This is the "work"
EXECUTION_TIME = 2 

@app.route("/", methods=["POST"])
def execute_function():
    # Simulate work, just like in our simulation
    time.sleep(EXECUTION_TIME)
    return {"message": "Function executed successfully!"}, 200

if __name__ == "__main__":
    # Run inside the container on port 5000
    app.run(host="0.0.0.0", port=5000)