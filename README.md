# Swarmchestrate

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-%20v1.0+-blue)](https://python-poetry.org/)

## Overview

**Project Name** is a Python package ...

---

## Features

- **Lightweight and Flexible**: Minimal configuration required to start a server or join a network.
- **Easy to Use**: Simple CLI for quick setup.
- **Poetry Integration**: Dependency management and virtual environment handled seamlessly.

---

## Prerequisites

- Python 3.8 or later
- Poetry 1.0 or later

---

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

### 3. Configure Poetry (Optional)

Set Poetry to create virtual environments inside your project directory (optional but recommended):

```bash
poetry config virtualenvs.in-project true
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

---

## Usage

The package provides an example script `example.py` to demonstrate its functionality. The script can be used to start a server or join an existing network.

### Command Syntax

```bash
poetry run python3 example.py --listen <ip:port> --join <ip:port>
```

### Options

- `--listen <ip:port>`: Starts the server and listens for incoming connections.
- `--join <ip:port>`: Joins an existing network at the specified IP and port.

### Example 1: Start a Server

To start a server listening on `127.0.0.1:8080`:

```bash
poetry run python3 example.py --listen 127.0.0.1:8080
```

### Example 2: Join a Network

To join a network on `192.168.1.10:8080`:

```bash
poetry run python3 example.py --join 192.168.1.10:8080
```

---

## Development

1. Install dependencies:

   ```bash
   poetry install
   ```

2. Run tests:

   ```bash
   poetry run pytest
   ```

3. Add new dependencies:

   ```bash
   poetry add <package-name>
   ```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

---

## Contact

For any questions or feedback, feel free to reach out:

- **Email**: your.email@example.com
- **GitHub**: [yourusername](https://github.com/yourusername)

---

Thank you for using **Swarmchestrate**! 🎉