#!/bin/bash

# A test script for the FaaS Affinity Scheduler
# Make sure scheduler.py is running in another terminal!

# Set the base URL for the scheduler
BASE_URL="http://127.0.0.1:8080/invoke"

echo "=========================================="
echo " FaaS Scheduler Test Script"
echo "=========================================="
echo "Scheduler running at $BASE_URL"
echo "Make sure scheduler.py is running!"
echo "Press [Enter] to start Test 1..."
read

# --- Test 1: Simple Cold vs. Warm Start ---
echo
echo "--- Test 1: Simple Cold vs. Warm Start (function-a) ---"
echo "Sending 1st request to function-a (expecting COLD START)..."
curl "${BASE_URL}/function-a"
echo
echo
echo "Waiting 2 seconds..."
sleep 2

echo "Sending 2nd request to function-a (expecting WARM START)..."
curl "${BASE_URL}/function-a"
echo
echo
echo "Test 1 Complete. Check logs."
echo "Press [Enter] to start Test 2..."
read

# --- Test 2: Concurrency & Queuing ---
echo
echo "--- Test 2: Concurrency & Queuing (function-b, limit 3) ---"
echo "Sending 5 requests to function-b simultaneously..."
echo "(Check scheduler logs for 3 COLD STARTs and 2 QUEUED messages)"

# Send 5 requests in the background
curl "${BASE_URL}/function-b" &
curl "${BASE_URL}/function-b" &
curl "${BASE_URL}/function-b" &
curl "${BASE_URL}/function-b" &
curl "${BASE_URL}/function-b" &

echo "Waiting for all background requests to finish..."
wait
echo
echo "Test 2 Complete. All 5 requests handled."
echo "Check scheduler logs to see the queue being processed."
echo "Press [Enter] to start Test 3..."
read

# --- Test 3: Affinity Test ---
echo
echo "--- Test 3: Affinity (function-a vs function-c) ---"
echo "Sending 4 requests to 'function-a' (limit 5)"
echo "AND 4 requests to 'function-c' (limit 3) simultaneously..."
echo "(Check logs: 'a' should have 4 COLD STARTs, 'c' should have 3 COLD STARTs + 1 QUEUED)"

# Burst for function-a (limit 5)
curl "${BASE_URL}/function-a" &
curl "${BASE_URL}/function-a" &
curl "${BASE_URL}/function-a" &
curl "${BASE_URL}/function-a" &

# Burst for function-c (limit 3)
curl "${BASE_URL}/function-c" &
curl "${BASE_URL}/function-c" &
curl "${BASE_URL}/function-c" &
curl "${BASE_URL}/function-c" &

echo "Waiting for all 8 requests to complete..."
wait
echo
echo "Test 3 Complete. Check logs for separate pool activity."
echo "Press [Enter] to start Test 4..."
read

# --- Test 4: Dynamic Pool Creation ---
echo
echo "--- Test 4: Dynamic Pool Creation (function-z) ---"
echo "Sending request to a new, unknown function: 'function-z'..."
curl "${BASE_URL}/function-z"
echo
echo
echo "Test 4 Complete. (Check logs for 'Dynamically creating new pool' message)"
echo
echo "=========================================="
echo " All tests finished."
echo "=========================================="