#!/bin/bash

# Enable strict mode for better error handling
set -euo pipefail
IFS=$'\n\t'

# Enable job control
set -m

# Function to start a client
start_a_client() {
    local join_port=$1

    echo "Starting client with --join 127.0.0.1:${join_port}"
    # Start the node with --join and pipe its output to sed for prefixing
    # Run in a subshell to capture the PID of the 'poetry run' process
    poetry run python3 example_cli.py --join 127.0.0.1:${join_port} --submit "Swarm1"    
}

# Start client with --join
start_a_client "5000" 

