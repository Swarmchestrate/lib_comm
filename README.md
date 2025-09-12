# Swarmchestrate communication library

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-%20v1.2+-blue)](https://python-poetry.org/)

## Overview

**SwchP2Pcom** is a Python package for creating a peer to peer network.

---

## Features

- **Lightweight and Flexible**: Minimal configuration required to start a server or join a network.
- **Poetry Integration**: Dependency management and virtual environment handled seamlessly.

---

## Prerequisites

- Python 3.8 or later
- Poetry 1.2 or later

---

## Development

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

## SwchPeer API Documentation

The `SwchPeer` class provides a high-level interface for creating peer-to-peer networks with automatic discovery, message handling, and network resilience features.

### Initialization

```python
from swchp2pcom import SwchPeer

agent = SwchPeer(
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

#### Leaving Networks

**`leave() -> Deferred`**
Gracefully leave the network.

```python
deferred = agent.leave()
deferred.addCallback(lambda _: print("Successfully left network"))
deferred.addErrback(lambda failure: print(f"Leave failed: {failure.getErrorMessage()}"))
```

#### Adding links to peers

**`connect(peer_id: str) -> Deferred`**
Connect to a specific known peer by their ID.

```python
deferred = agent.connect("peer-uuid-123")
deferred.addCallback(lambda protocol: print("Connected to peer"))
```

#### Removing links to peers

**`disconnect(peer_id: str) -> Deferred`**
Disconnect from a specific peer.

```python
deferred = agent.disconnect("peer-uuid-123")
deferred.addCallback(lambda _: print("Successfully disconnected from peer"))
deferred.addErrback(lambda failure: print(f"Disconnection failed: {failure.getErrorMessage()}"))
```

### Messaging

#### Sending Messages

**`send(peer_id: Union[str, List[str]], message_type: str, payload: Dict[str, Any]) -> None`**
Send a targeted message to one or more specific peers.

```python
# Send to a single peer
agent.send("peer-123", "chat", {
    "text": "Hello!",
    "timestamp": time.time()
})

# Send to multiple peers
agent.send(["peer-123", "peer-456", "peer-789"], "notification", {
    "message": "System update available",
    "priority": "high"
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

**`on(event_name: str, listener: Callable) -> SwchPeer`**
Register event listeners with method chaining support.

#### Available Events

**`entered`** - Triggered when the agent successfully enters the network
- **Parameters**: None
- **Handler signature**: `listener()`

```python
def on_entered():
    print("Successfully joined the network!")

agent.on("entered", on_entered)
```

**`left`** - Triggered when the agent successfully leaves the network
- **Parameters**: None
- **Handler signature**: `listener()`

```python
def on_left():
    print("Successfully left the network!")

agent.on("left", on_left)
```

**`peer:connected`** - Triggered when a peer establishes a direct connection to this agent
- **Parameters**: `peer_id` (str) - The ID of the connected peer
- **Handler signature**: `listener(peer_id: str)`

```python
def on_peer_connected(peer_id):
    print(f"Direct connection established with peer: {peer_id}")
    # You can now send messages directly to this peer

agent.on("peer:connected", on_peer_connected)
```

**`peer:disconnected`** - Triggered when a peer disconnects from this agent
- **Parameters**: `peer_id` (str) - The ID of the disconnected peer
- **Handler signature**: `listener(peer_id: str)`

```python
def on_peer_disconnected(peer_id):
    print(f"Lost direct connection with peer: {peer_id}")
    # This peer may still be reachable through other peers

agent.on("peer:disconnected", on_peer_disconnected)
```

**`peer:all_disconnected`** - Triggered when all peers disconnect from this agent (triggers rejoin if enabled)
- **Parameters**: None
- **Handler signature**: `listener()`

```python
def on_all_disconnected():
    print("Lost all connections - isolated from network")
    # If rejoin is enabled, automatic reconnection will start

agent.on("peer:all_disconnected", on_all_disconnected)
```

**`peer:discovered`** - Triggered when a new peer is discovered in the network (may not be directly connected)
- **Parameters**: `peer_id` (str) - The ID of the discovered peer
- **Handler signature**: `listener(peer_id: str)`

```python
def on_peer_discovered(peer_id):
    print(f"New peer discovered in network: {peer_id}")
    metadata = agent.get_peer_metadata(peer_id)
    if metadata:
        print(f"Peer type: {metadata.get('type', 'unknown')}")

agent.on("peer:discovered", on_peer_discovered)
```

**`peer:undiscovered`** - Triggered when a peer leaves the network entirely
- **Parameters**: `peer_id` (str) - The ID of the peer that left
- **Handler signature**: `listener(peer_id: str)`

```python
def on_peer_undiscovered(peer_id):
    print(f"Peer left the network: {peer_id}")
    # This peer is no longer reachable in the network

agent.on("peer:undiscovered", on_peer_undiscovered)
```

**`message`** - Triggered when any message is received
- **Parameters**: `event_data` (dict) - Contains message information
  - `peer_id` (str) - ID of the sender
  - `message_type` (str) - Type of the message
  - `payload` (dict) - The message payload
- **Handler signature**: `listener(event_data: dict)`

```python
def on_message(event_data):
    sender = event_data['peer_id']
    msg_type = event_data['message_type']
    payload = event_data['payload']
    print(f"Received {msg_type} from {sender}: {payload}")

agent.on("message", on_message)
```

**Event Handler Chaining Example**

```python
agent.on("entered", lambda: print("Joined network")) \
     .on("peer:connected", lambda peer_id: print(f"Connected: {peer_id}")) \
     .on("peer:discovered", lambda peer_id: print(f"Discovered: {peer_id}")) \
     .on("message", lambda event: print(f"Message from {event['peer_id']}: {event['message_type']}"))
```

### Peer Discovery

**`find_peers(metadata: Optional[Dict] = None) -> List[str]`**
Search for peers based on metadata criteria.

```python
# Find all peers
all_peers = agent.find_peers()

# Find peers by type
workers = agent.find_peers({"type": "worker"})

# Find peers with multiple criteria
specific_peers = agent.find_peers({
    "universe": "production",
    "type": "coordinator"
})
```

**`get_connected_peers() -> List[str]`**
Get list of currently connected peer IDs.

```python
connected = agent.get_connected_peers()
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
from swchp2pcom import SwchPeer
import time

# Create agent
agent = SwchPeer(
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
- **Email**: benedek.kovacs@sztaki.hun-ren.hu

---

Thank you for using **SwchP2Pcom**! 🎉