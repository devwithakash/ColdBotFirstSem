#!/bin/bash

# An advanced, randomized stress-test script for the FaaS Affinity Scheduler
#
# USAGE:
#   ./advanced_test.sh lcs  -> Saves results to advanced_lru_logs.json
#   ./advanced_test.sh mru  -> Saves results to advanced_mru_logs.json
#
# If no argument is given, it defaults to 'lcs'.

# --- CONFIG ---
BASE_URL="http://127.0.0.1:8080"
LOG_FILE="advanced_test.log"
NUM_BURSTS=10 # Total number of request bursts
TOTAL_REQUESTS=0

# --- CHECK FOR JQ (REQUIRED) ---
if ! command -v jq &> /dev/null
then
    echo "Error: 'jq' is not installed."
    echo "This script requires jq to save JSON logs."
    echo "Please install it (e.g., sudo apt-get install jq) and try again."
    exit 1
fi

# --- STRATEGY SELECTION ---
DEFAULT_STRATEGY="lcs"
STRATEGY=${1:-$DEFAULT_STRATEGY}
STRATEGY_UPPER=$(echo "$STRATEGY" | tr '[:lower:]' '[:upper:]')

# NEW: Set output file based on strategy
OUTPUT_FILE="advanced_${STRATEGY}_logs.json"


# --- FUNCTIONS ---

# This function saves the FINAL stats to the file
save_final_stats() {
    echo
    echo "--- FINAL SCHEDULER STATS (from /stats) ---"
    
    # Fetch stats from the server
    STATS_JSON=$(curl -s "${BASE_URL}/stats")
    
    if [ -z "$STATS_JSON" ]; then
        echo "Error: Failed to fetch stats from scheduler."
        return
    fi

    # Print stats to terminal (using jq)
    echo $STATS_JSON | jq .

    # NEW: Save the final JSON object to the file
    echo $STATS_JSON > $OUTPUT_FILE
    
    echo "----------------------------------------------"
    echo "Saved final stats to $OUTPUT_FILE"
}

# Function to reset stats
reset_stats() {
    echo
    echo "--- RESETTING SCHEDULER STATS ---"
    curl -s -X POST "${BASE_URL}/stats/reset"
    echo
    # Clear the temporary curl log file
    > $LOG_FILE
}

# --- SCRIPT START ---
echo "=========================================="
echo " FaaS Advanced Stress Test"
echo "=========================================="
echo "Scheduler running at $BASE_URL"
echo "Make sure scheduler.py is running!"
echo

# --- SET THE STRATEGY ---
echo "--- SETTING SCHEDULER STRATEGY to ${STRATEGY_UPPER} ---"
curl -s -X POST "${BASE_URL}/set_strategy" -H "Content-Type: application/json" -d "{\"strategy\":\"${STRATEGY}\"}"
echo

# --- Initialize the output file ---
# This just clears it, we only save at the end
> $OUTPUT_FILE
echo "Will save final results to $OUTPUT_FILE"

# --- Reset stats before starting ---
reset_stats
echo
echo "Press [Enter] to start the advanced test..."
read

# --- MAIN TEST LOOP ---
echo
echo "--- Starting Advanced Test: $NUM_BURSTS random bursts... ---"

# Array of functions to choose from
FUNCTIONS=("function-a" "function-b" "function-c")

for i in $(seq 1 $NUM_BURSTS)
do
    # 1. Get random number of requests for this burst (4-8)
    NUM_TO_SEND=$(shuf -i 4-8 -n 1)
    
    # 2. Get random function to target
    TARGET_FUNC=${FUNCTIONS[$RANDOM % ${#FUNCTIONS[@]}]}
    
    echo
    echo "--- Burst $i/$NUM_BURSTS: Sending $NUM_TO_SEND requests to $TARGET_FUNC ---"
    
    # 3. Send the burst of requests in the background
    for j in $(seq 1 $NUM_TO_SEND)
    do
        curl -s "${BASE_URL}/invoke/$TARGET_FUNC" >> $LOG_FILE &
    done
    
    # 4. Update total request count
    TOTAL_REQUESTS=$((TOTAL_REQUESTS + NUM_TO_SEND))
    
    # 5. Get random sleep time (3-10)
    SLEEP_TIME=$(shuf -i 3-10 -n 1)
    
    # Only sleep if it's not the last burst
    if [ $i -lt $NUM_BURSTS ]; then
        echo "Burst sent. Sleeping for $SLEEP_TIME seconds..."
        sleep $SLEEP_TIME
    fi
done

echo
echo "All bursts complete. Waiting for final jobs to finish..."
wait
echo

# --- FINAL RESULTS ---
echo "=========================================="
echo " All tests finished."
echo " Total requests sent: $TOTAL_REQUESTS"
echo "=========================================="

# 6. Get and save the final, aggregated stats for the *entire* run
save_final_stats

echo
echo "Test complete. Compare $OUTPUT_FILE with the other strategy's log."
```

### How to Use This

1.  **Terminal 1:** Run `scheduler.py` (with the `/set_strategy` and `/stats` endpoints).
    ```bash
    python3 scheduler.py
    ```

2.  **Terminal 2:** Make the new script executable:
    ```bash
    chmod +x advanced_test.sh
    ```

3.  **Run the LCS Test:**
    ```bash
    ./advanced_test.sh lcs
    ```
    Press `[Enter]` and let it run. It will take 1-2 minutes. It will create `advanced_lru_logs.json` with the *total* stats for the entire run.

4.  **Run the MRU Test:**
    ```bash
    ./advanced_test.sh mru