#!/bin/bash

# --- CONFIG ---
BASE_URL="http://127.0.0.1:8080"
REQUESTS_PER_BURST=5 # Fixed number of requests in each burst (as requested)

# --- 1. VALIDATE INPUT ---
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Error: Missing arguments."
    echo "Usage: ./run_experiment.sh <strategy> <experiment_num> <num_bursts>"
    echo "Example: ./run_experiment.sh lru 1 10"
    exit 1
fi

STRATEGY=$1
EXP_NUM=$2
NUM_BURSTS=$3
TOTAL_REQUESTS=$(( $NUM_BURSTS * $REQUESTS_PER_BURST ))

# Validate strategy
if [ "$STRATEGY" != "lru" ] && [ "$STRATEGY" != "mru" ]; then
    echo "Error: Invalid strategy '$STRATEGY'. Must be 'lru' or 'mru'."
    exit 1
fi

RESULT_DIR="results" # New directory name as requested
OUTPUT_FILE="${RESULT_DIR}/exp${EXP_NUM}_${STRATEGY}.json"

# --- CHECK FOR JQ (REQUIRED) ---
if ! command -v jq &> /dev/null
then
    echo "Error: 'jq' is not installed."
    echo "This script requires jq to save JSON logs."
    echo "Please install it (e.g., sudo apt-get install jq) and try again."
    exit 1
fi

# --- FUNCTIONS ---

# Function to save the FINAL stats to a file
save_final_stats() {
    STRATEGY_UPPER=$(echo "$STRATEGY" | tr '[:lower:]' '[:upper:]')
    echo
    echo "--- FINAL SCHEDULER STATS ($STRATEGY_UPPER) ---"
    
    # Fetch stats from the server
    STATS_JSON=$(curl -s "${BASE_URL}/stats")
    
    if [ -z "$STATS_JSON" ]; then
        echo "Error: Failed to fetch stats from scheduler."
        return
    fi

    # Print stats to terminal (using jq)
    echo "$STATS_JSON" | jq .

    # Save the final JSON object to the file
    echo "$STATS_JSON" > "$OUTPUT_FILE"
    
    echo "----------------------------------------------"
    echo "Saved final stats to $OUTPUT_FILE"
}

# Function to reset stats
reset_stats() {
    echo
    echo "--- RESETTING SCHEDULER STATS ---"
    curl -s -X POST "${BASE_URL}/stats/reset"
    echo
}

# Function to set the strategy
set_strategy() {
    STRATEGY_UPPER=$(echo "$STRATEGY" | tr '[:lower:]' '[:upper:]')
    echo
    echo "--- SETTING SCHEDULER STRATEGY to ${STRATEGY_UPPER} ---"
    curl -s -X POST "${BASE_URL}/set_strategy" -H "Content-Type: application/json" -d "{\"strategy\":\"${STRATEGY}\"}"
    echo
}

# --- SCRIPT START ---
echo "=========================================="
echo " FaaS Advanced Comparison Test"
echo " Experiment: $EXP_NUM"
echo " Strategy:   $STRATEGY"
echo "=========================================="
echo "Scheduler running at $BASE_URL"
echo "Make sure scheduler.py is running!"
echo

# Create result directory if it doesn't exist
mkdir -p $RESULT_DIR

# --- 1. GENERATE THE RANDOM WORKLOAD ---
echo "--- Generating a random workload of $TOTAL_REQUESTS requests... ---"
echo "($NUM_BURSTS bursts of $REQUESTS_PER_BURST requests each)"

# These arrays will store the workload
declare -a BURST_FUNCS
declare -a SLEEP_TIMES

FUNCTIONS=("function-a" "function-b" "function-c")

for i in $(seq 1 $NUM_BURSTS)
do
    BURST_FUNCS[$i]=${FUNCTIONS[$RANDOM % ${#FUNCTIONS[@]}]}
    SLEEP_TIMES[$i]=$(shuf -i 3-10 -n 1)
done

echo "Workload generated. Starting test..."

# --- 2. RUN THE TEST ---
set_strategy "$STRATEGY"
reset_stats

STRATEGY_UPPER=$(echo "$STRATEGY" | tr '[:lower:]' '[:upper:]')

echo
echo "--- STARTING $STRATEGY_UPPER TEST ---"
for i in $(seq 1 $NUM_BURSTS)
do
    TARGET_FUNC=${BURST_FUNCS[$i]}
    SLEEP_TIME=${SLEEP_TIMES[$i]}
    
    echo "Burst $i/$NUM_BURSTS ($STRATEGY_UPPER): Sending $REQUESTS_PER_BURST requests to $TARGET_FUNC..."
    
    for j in $(seq 1 $REQUESTS_PER_BURST)
    do
        # -s (silent) and -o /dev/null (discard output) for a cleaner log
        curl -s -o /dev/null "${BASE_URL}/invoke/$TARGET_FUNC" &
    done
    
    if [ $i -lt $NUM_BURSTS ]; then
        echo "Burst sent. Sleeping for $SLEEP_TIME seconds..."
        sleep $SLEEP_TIME
    fi
done

echo
echo "$STRATEGY_UPPER test complete. Waiting for final jobs to finish..."
wait
save_final_stats "$STRATEGY" "$OUTPUT_FILE"


# --- FINAL RESULTS ---
echo
echo "=========================================="
echo " All tests finished."
echo " Total requests sent: $TOTAL_REQUESTS"
echo "=========================================="
echo
echo "Results saved to: $OUTPUT_FILE"