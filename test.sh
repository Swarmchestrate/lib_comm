#!/bin/bash

# Enable strict mode for better error handling
set -euo pipefail
IFS=$'\n\t'

# Enable job control
set -m

# Configuration
BASE_PORT=5000          # Starting port number
NUM_NODES=5             # Number of nodes to start
SLEEP_TIME=2            # Time to wait between starting nodes (in seconds)

# Array to keep track of started ports
PORTS=()

# Function to check if a port is free
is_port_free() {
    local port=$1
    if lsof -i TCP:${port} >/dev/null 2>&1; then
        return 1  # Port is in use
    else
        return 0  # Port is free
    fi
}

# Function to terminate all nodes
terminate_nodes() {
    echo ""
    echo "Terminating all nodes..."
    # Send SIGTERM to the entire process group
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

# Function to start a node
start_node() {
    local node_num=$1
    local port=$2
    local join_port=$3

    # Check if the port is free
    if ! is_port_free "${port}"; then
        echo "Error: Port ${port} is already in use. Exiting."
        terminate_nodes
    fi

    if [ -z "${join_port}" ]; then
        echo "Starting node${node_num} on port ${port} without --join"
        # Start the node and pipe its output to sed for prefixing
        # Run in a subshell to capture the PID of the 'poetry run' process
        ( poetry run python3 example.py --listen 127.0.0.1:${port} --public 127.0.0.1:${port} 2>&1 ) | \
            sed "s/^/node${node_num}: /" &
    else
        echo "Starting node${node_num} on port ${port} with --join 127.0.0.1:${join_port}"
        # Start the node with --join and pipe its output to sed for prefixing
        # Run in a subshell to capture the PID of the 'poetry run' process
        ( poetry run python3 example.py --listen 127.0.0.1:${port} --public 127.0.0.1:${port} --join 127.0.0.1:${join_port} 2>&1 ) | \
            sed "s/^/node${node_num}: /" &
    fi
}

# Trap SIGINT and SIGTERM to gracefully shut down nodes
trap terminate_nodes SIGINT SIGTERM

# Start the first node without --join
FIRST_PORT=$BASE_PORT
PORTS+=("${FIRST_PORT}")
start_node 1 "${FIRST_PORT}" ""  # Pass an empty string as the third argument
sleep "${SLEEP_TIME}"

# Start subsequent nodes with --join to the latest node
for ((i=2; i<=NUM_NODES; i++)); do
    CURRENT_PORT=$((BASE_PORT + i - 1))
    PORTS+=("${CURRENT_PORT}")

    # Get the latest port to join
    LATEST_INDEX=$((i - 2))  # Zero-based index
    LATEST_PORT=${PORTS[${LATEST_INDEX}]}

    start_node "${i}" "${CURRENT_PORT}" "${LATEST_PORT}"
    sleep "${SLEEP_TIME}"
done

echo "All ${NUM_NODES} nodes have been started."

# Wait for all background processes to finish
wait
