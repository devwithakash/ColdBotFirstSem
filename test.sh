#!/bin/bash

# A test script for the FaaS Affinity Scheduler
#
# USAGE:
#   ./test_burst.sh lcs  -> Saves results to test_lru_logs.json
#   ./test_burst.sh mru  -> Saves results to test_mru_logs.json
#
# If no argument is given, it defaults to 'lcs'.

# --- CONFIG ---
BASE_URL="http://127.0.0.1:8080"
LOG_FILE="test.log"

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
OUTPUT_FILE="test_${STRATEGY}_logs.json"


# --- FUNCTIONS ---

# MODIFIED: This function now saves the stats to the OUTPUT_FILE
get_stats_and_save() {
    echo
    echo "--- CURRENT SCHEDULER STATS (from /stats) ---"
    
    # Fetch stats from the server
    STATS_JSON=$(curl -s "${BASE_URL}/stats")
    
    if [ -z "$STATS_JSON" ]; then
        echo "Error: Failed to fetch stats from scheduler."
        return
    fi

    # Print stats to terminal (using jq)
    echo $STATS_JSON | jq .

    # NEW: Append stats to the JSON file
    # This reads the file, adds the new stats object to the array,
    # and writes it back atomically.
    jq --argjson new_stats "$STATS_JSON" '. += [$new_stats]' "$OUTPUT_FILE" > "${OUTPUT_FILE}.tmp" && mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"
    
    echo "----------------------------------------------"
    echo "Saved stats for this test to $OUTPUT_FILE"
}

# Function to grep and summarize test.log
summarize_log() {
    echo
    echo "--- TEST SCRIPT LOG SUMMARY (from curl output) ---"
    
    EXECUTED=$(grep '"message":"Function executed"' $LOG_FILE | wc -l)
    echo "Executed:     $EXECUTED"
    
    QUEUED=$(grep '"message":"All workers busy, request queued."' $LOG_FILE | wc -l)
    echo "Queued:       $QUEUED"

    ERRORS=$(grep '"error":' $LOG_FILE | wc -l)
    echo "Errors:       $ERRORS"
    
    echo "------------------------------------------------"
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
echo " FaaS Scheduler Test Script"
echo "=========================================="
echo "Scheduler running at $BASE_URL"
echo "Make sure scheduler.py is running!"
echo

# --- SET THE STRATEGY ---
echo "--- SETTING SCHEDULER STRATEGY to ${STRATEGY_UPPER} ---"
curl -s -X POST "${BASE_URL}/set_strategy" -H "Content-Type: application/json" -d "{\"strategy\":\"${STRATEGY}\"}"
echo

# --- NEW: Initialize the output file ---
echo "[]" > $OUTPUT_FILE
echo "Saving all test stats to $OUTPUT_FILE"


reset_stats
echo "Press [Enter] to start Test 1..."
read

# --- Test 1: Simple Cold vs. Warm Start ---
echo
echo "--- Test 1: Simple Cold vs. Warm Start (function-a) ---"
echo "Sending 1st request to function-a (expecting COLD START)..."
curl -s "${BASE_URL}/invoke/function-a" >> $LOG_FILE
echo

echo "Waiting 2 seconds..."
sleep 2

echo "Sending 2nd request to function-a (expecting WARM START)..."
curl -s "${BASE_URL}/invoke/function-a" >> $LOG_FILE
echo
echo
echo "--- Test 1 Results ---"
summarize_log 
get_stats_and_save # <-- Use new function
echo "Test 1 Complete. Check logs."

reset_stats
echo "Press [Enter] to start Test 2..."
read

# --- Test 2: Concurrency & Queuing ---
echo
echo "--- Test 2: Concurrency & Queuing (function-b, limit 3) ---"
echo "Sending 5 requests to function-b simultaneously..."
echo "(Check scheduler logs for 3 COLD STARTs and 2 QUEUED messages)"

# Send 5 requests in the background, logging output
curl -s "${BASE_URL}/invoke/function-b" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-b" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-b" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-b" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-b" >> $LOG_FILE &

echo "Waiting for all background requests to finish..."
wait
echo
echo "--- Test 2 Results ---"
summarize_log 
get_stats_and_save # <-- Use new function
echo "Test 2 Complete. All 5 requests handled."
echo "Check scheduler logs to see the queue being processed."

reset_stats
echo "Press [Enter] to start Test 3..."
read

# --- Test 3: Affinity Test ---
echo
echo "--- Test 3: Affinity (function-a vs function-c) ---"
echo "Sending 4 requests to 'function-a' (limit 5)"
echo "AND 4 requests to 'function-c' (limit 3) simultaneously..."
echo "(Check logs: 'a' should have 4 COLD STARTs, 'c' should have 3 COLD STARTs + 1 QUEUED)"

# Burst for function-a (limit 5)
curl -s "${BASE_URL}/invoke/function-a" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-a" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-a" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-a" >> $LOG_FILE &

# Burst for function-c (limit 3)
curl -s "${BASE_URL}/invoke/function-c" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-c" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-c" >> $LOG_FILE &
curl -s "${BASE_URL}/invoke/function-c" >> $LOG_FILE &

echo "Waiting for all 8 requests to complete..."
wait
echo
echo "--- Test 3 Results ---"
summarize_log 
get_stats_and_save # <-- Use new function
echo "Test 3 Complete. Check logs for separate pool activity."

reset_stats
echo "Press [Enter] to start Test 4..."
read

# --- Test 4: Dynamic Pool Creation ---
echo
echo "--- Test 4: Dynamic Pool Creation (function-z) ---"
echo "Sending request to a new, unknown function: 'function-z'..."
curl -s "${BASE_URL}/invoke/function-z" >> $LOG_FILE
echo
echo
echo "--- Test 4 Results ---"
summarize_log 
get_stats_and_save # <-- Use new function
echo "Test 4 Complete. (Check logs for 'Dynamically creating new pool' message)"
echo
echo "=========================================="
echo " All tests finished."
echo "Final results saved to $OUTPUT_FILE"
echo "=========================================="