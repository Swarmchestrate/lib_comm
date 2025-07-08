# Swarmchestrate communication library

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-%20v1.2+-blue)](https://python-poetry.org/)

## Overview

**Project Name** is a Python package for creating a peer to peer network.

---

## Features

- **Lightweight and Flexible**: Minimal configuration required to start a server or join a network.
- **Easy to Use**: Simple CLI for quick setup.
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

## Example Usage

The package provides example scripts to demonstrate peer-to-peer communication:
- `example_ra.py` - Resource Agent (RA) implementation
- `example_cli.py` - Client implementation 

### Starting Resource Agents

Use the provided `launch_RAs.sh` script to start multiple Resource Agents:

```bash
./launch_RAs.sh
```

This script will:
- Start 2 Resource Agents by default
- First RA listens on port 5000
- Second RA connects to the first one and listens on port 5001

#### Manual RA Launch

To manually start a Resource Agent:

```bash
# First RA
poetry run python3 example_ra.py --listen 127.0.0.1:5000 --public 127.0.0.1:5000

# Additional RA joining the network
poetry run python3 example_ra.py --listen 127.0.0.1:5001 --public 127.0.0.1:5001 --join 127.0.0.1:5000
```

Options for `example_ra.py`:
- `--listen <ip:port>`: Local address to listen on
- `--public <ip:port>`: Public address for other peers to connect to
- `--join <ip:port>`: (Optional) Address of existing RA to join

### Starting a Client

Use the provided `launch_client.sh` script to start a client that connects to an RA:

```bash
./launch_client.sh
```

This connects to the RA running on port 5000 by default.

#### Manual Client Launch

To manually start a client:

```bash
poetry run python3 example_cli.py --join 127.0.0.1:5000
```

Options for `example_cli.py`:
- `--join <ip:port>`: Address of RA to connect to

---

## Contact

For any questions or feedback, feel free to reach out:

- **Email**: jozsef.kovacs@sztaki.hun-ren.hu

---

Thank you for using **swch_comm**! 🎉