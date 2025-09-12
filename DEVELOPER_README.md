# Developer README

This document contains information for developers who want to contribute to or modify the SwchP2Pcom library.

## Prerequisites

- Python 3.12 or later
- Poetry 1.2 or later

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

## Development Setup

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

## Contributing

When contributing to this project, please follow the established coding standards and ensure all tests pass before submitting pull requests.
