# Swarmchestrate communication library

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-%20v1.2+-blue)](https://python-poetry.org/)

## Overview

**Swch_comm** is a Python package for creating a peer to peer network.

---

## Features

- **Lightweight and Flexible**: Minimal configuration required to start a server or join a network.
- **Poetry Integration**: Dependency management and virtual environment handled seamlessly.

---

## Prerequisites

- Python 3.8 or later
- Poetry 1.2 or later

---

## Developement

## Installing Poetry

If Poetry is not already installed on your system, follow these steps:

### 1. Install Poetry

Run the official installation script provided by Poetry:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

### 2. Verify Installation

Ensure Poetry is installed correctly by checking its version:

```bash
poetry --version
```

You should see something like:

```
Poetry version 1.x.x
```

---

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Swarmchestrate/lib_comm
   cd lib_comm
   ```

2. Install dependencies using Poetry:

   ```bash
   poetry install
   ```

3. (Optional) Activate the virtual environment:

   ```bash
   poetry shell
   ```

   > Note: Activating the virtual environment is optional. You can still use the package directly by prefacing your commands with `poetry run`, which runs the script within Poetry's managed virtual environment.

4. (Optional) Building the package:

   ```bash
   poetry build
   ```

5. Add new dependencies:

   ```bash
   poetry add <package-name>
   ```

---

## SwchAgent API Documentation

The `SwchAgent` class provides a high-level interface for creating peer-to-peer networks with automatic discovery, message handling, and network resilience features.

### Initialization

```python
from swch_com.swchagent import SwchAgent

agent = SwchAgent(
    peer_id="my-peer-id",           # Optional: Auto-generated if None
    listen_ip="127.0.0.1",          # Optional: IP to listen on
    listen_port=8080,               # Optional: Port to listen on
    public_ip="192.168.1.100",      # Optional: Advertised IP (defaults to listen_ip)
    public_port=8080,               # Optional: Advertised port (defaults to listen_port)
    metadata={"type": "worker"},    # Optional: Peer metadata
    enable_rejoin=True              # Optional: Enable automatic reconnection
)
```

### Network Operations

#### Joining Networks

**`enter(ip: str, port: int) -> Deferred`**
Join an existing peer network by connecting to a known peer.

```python
# Returns a Deferred for asynchronous handling
deferred = agent.enter("192.168.1.100", 8080)
deferred.addCallback(lambda _: print("Successfully joined network"))
deferred.addErrback(lambda failure: print(f"Failed to join: {failure.getErrorMessage()}"))
```

**`connect(peer_id: str) -> Deferred`**
Connect to a specific known peer by their ID.

```python
deferred = agent.connect("peer-uuid-123")
deferred.addCallback(lambda protocol: print("Connected to peer"))
```

#### Leaving Networks

**`disconnect(peer_id: str) -> bool`**
Disconnect from a specific peer.

```python
success = agent.disconnect("peer-uuid-123")
if success:
    print("Disconnection initiated")
```

**`leave() -> Deferred`**
Gracefully leave the network.

```python
deferred = agent.leave()
deferred.addCallback(lambda _: print("Successfully left network"))
```

### Messaging

#### Sending Messages

**`send(peer_id: str, message_type: str, payload: Dict[str, Any]) -> None`**
Send a targeted message to a specific peer.

```python
agent.send("peer-123", "chat", {
    "text": "Hello!",
    "timestamp": time.time()
})
```

**`broadcast(message_type: str, payload: Dict[str, Any]) -> None`**
Send a message to all connected peers.

```python
agent.broadcast("announcement", {
    "message": "Server maintenance in 10 minutes",
    "timestamp": time.time()
})
```

#### Message Handlers

**`register_message_handler(message_type: str, func: Callable) -> None`**
Register a custom handler for specific message types.

```python
def handle_chat(sender_id, message):
    print(f"Chat from {sender_id}: {message['payload']['text']}")

agent.register_message_handler("chat", handle_chat)
```

### Event System

**`on(event_name: str, listener: Callable) -> SwchAgent`**
Register event listeners with method chaining support.

```python
agent.on("peer:connected", lambda peer_id: print(f"Peer {peer_id} connected")) \
     .on("peer:disconnected", lambda peer_id: print(f"Peer {peer_id} disconnected")) \
     .on("peer:discovered", lambda peer_id: print(f"Discovered peer {peer_id}"))
```

#### Available Events

- `entered` - When the agent successfully enters the network
- `left` - When the agent successfully left the network
- `peer:connected` - When a peer establishes a direct connection
- `peer:disconnected` - When a peer disconnects
- `peer:all_disconnected` - When all peers disconnect (triggers rejoin if enabled)
- `peer:discovered` - When a new peer is discovered in the network
- `peer:undiscovered` - When a peer leaves the network
- `message` - When any message is received

### Peer Discovery

**`findPeers(metadata: Optional[Dict] = None) -> List[str]`**
Search for peers based on metadata criteria.

```python
# Find all peers
all_peers = agent.findPeers()

# Find peers by type
workers = agent.findPeers({"type": "worker"})

# Find peers with multiple criteria
specific_peers = agent.findPeers({
    "universe": "production",
    "type": "coordinator"
})
```

**`getConnectedPeers() -> List[str]`**
Get list of currently connected peer IDs.

```python
connected = agent.getConnectedPeers()
print(f"Connected to {len(connected)} peers")
```

**`get_peer_metadata(peer_id: str) -> Optional[Dict[str, Any]]`**
Retrieve metadata for a specific peer.

```python
metadata = agent.get_peer_metadata("peer-123")
if metadata:
    print(f"Peer type: {metadata.get('type', 'unknown')}")
```

### Network Information

**`get_connection_count() -> int`**
Get the current number of active connections.

```python
count = agent.get_connection_count()
print(f"Active connections: {count}")
```

### Rejoin Mechanism

The agent includes automatic network rejoin capabilities for resilience.

**`enable_rejoin() -> None`**
Enable automatic reconnection when all peers disconnect.

```python
agent.enable_rejoin()
```

**`disable_rejoin() -> None`**
Disable automatic reconnection.

```python
agent.disable_rejoin()
```

**`is_rejoin_enabled() -> bool`**
Check if rejoin mechanism is active.

```python
if agent.is_rejoin_enabled():
    print("Auto-rejoin is enabled")
```

**`is_rejoin_in_progress() -> bool`**
Check if a rejoin attempt is currently happening.

```python
if agent.is_rejoin_in_progress():
    print("Currently attempting to rejoin network")
```

### Reactor Control

**`start() -> None`**
Start the Twisted reactor (blocking call).

```python
agent.start()  # Blocks until reactor stops
```

**`stop() -> None`**
Stop the Twisted reactor.

```python
agent.stop()
```

### Complete Example

```python
from swch_com.swchagent import SwchAgent
import time

# Create agent
agent = SwchAgent(
    peer_id="worker-1",
    listen_ip="127.0.0.1",
    listen_port=8081,
    metadata={"type": "worker", "version": "1.0"}
)

# Set up message handler
def handle_task(sender_id, message):
    task = message['payload']['task']
    print(f"Received task from {sender_id}: {task}")
    
    # Send response back
    agent.send(sender_id, "task_result", {
        "task_id": task.get("id"),
        "result": "completed",
        "timestamp": time.time()
    })

agent.register_message_handler("task_request", handle_task)

# Set up event handlers
agent.on("peer:connected", lambda peer_id: print(f"New peer connected: {peer_id}")) \
     .on("peer:discovered", lambda peer_id: print(f"Discovered peer: {peer_id}"))

# Join existing network
try:
    deferred = agent.enter("127.0.0.1", 8080)
    deferred.addCallback(lambda _: print("Successfully joined network"))
    deferred.addErrback(lambda f: print(f"Failed to join: {f.getErrorMessage()}"))
    
    # Start the agent (this blocks)
    agent.start()
    
except KeyboardInterrupt:
    print("Shutting down...")
    leave_deferred = agent.leave()
    leave_deferred.addCallback(lambda _: agent.stop())
```

---

## Contact

For any questions or feedback, feel free to reach out:

- **Email**: jozsef.kovacs@sztaki.hun-ren.hu

---

Thank you for using **swch_comm**! 🎉