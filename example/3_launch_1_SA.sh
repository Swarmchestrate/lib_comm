#!/bin/bash

# Enable strict mode for better error handling
set -euo pipefail
IFS=$'\n\t'

# Enable job control
set -m

# Function to start a client
start_a_SA() {
    local listen_port=$1
    local join_port=$2

    echo "Starting client with --join 127.0.0.1:${join_port}"
    # Start the node with --join and pipe its output to sed for prefixing
    # Run in a subshell to capture the PID of the 'poetry run' process
    poetry run python3 example_sa.py --listen 127.0.0.1:${listen_port} --join 127.0.0.1:${join_port} --appid "Swarm1"    
}

# Start client with --join
start_a_SA "5003" "5002" 

