
# SDN & Federated Learning Automation Tool

A command-line tool for automating the setup and management of virtualized network infrastructure using OVS (Open vSwitch) and LXC containers, with support for deploying and running Federated Learning (FL) workloads across the network.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Scanning the System](#scanning-the-system)
  - [Building the Network](#building-the-network)
  - [Deploying the FL Application](#deploying-the-fl-application)
  - [Training](#training)
  - [Data Partitioning](#data-partitioning)
  - [Updating Nodes](#updating-nodes)
  - [Resetting Nodes](#resetting-nodes)
- [Data Files](#data-files)
- [Directory Structure](#directory-structure)

---

## Requirements

Before installing, make sure the following are available on your host machine:

- Python 3.10 or higher
- Git
- Open vSwitch (`ovs-vsctl`)
- LXC / LXD
- Nvidia drivers (if using GPU inside containers)
- `iproute2` (for interface scanning)
- `iperf3` (for network testing)

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd <repo-directory>
```

### 2. Create a Python virtual environment

```bash
python3 -m venv venv
```

### 3. Activate the virtual environment

On Linux/macOS:
```bash
source venv/bin/activate
```

On Windows:
```bash
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Prepare system data directories

The tool expects the following directories to exist before running:

```bash
mkdir -p sys_data
mkdir -p measurements_data
```

---

## Configuration

Before using the tool, set the `FL_REPO` variable at the top of `main.py` to point to your Federated Learning application repository:

```python
FL_REPO = "https://github.com/your-org/your-fl-app.git"
```

Also ensure your SDN controller address is defined in the imported `bridges` module (referenced as `CONTROLLER`).

---

## Usage

All commands are run via:

```bash
python main.py [OPTIONS]
```

---

### Scanning the System

Scans the host for network interfaces, OVS bridges, LXC containers, VXLANs, and QoS objects, then saves all discovered data to JSON files under `sys_data/`.

```bash
python main.py --scan
```

This should be run on every host in the network before performing any build steps, so that the tool has an accurate picture of the environment.

---

### Building the Network

Use the `--build` flag with one of the following sub-commands:

#### Bridges

Creates one or more OVS bridges on the current host.

```bash
python main.py --build bridges
```

Prompts:
- Number of bridges to create (default: 1)
- SDN controller address (default: value of `CONTROLLER`)

---

#### Containers

Creates LXC containers and attaches them to a specified OVS bridge with a VLAN.

```bash
python main.py --build containers
```

Prompts:
- A list of container IDs to create (e.g. `1,2,3`)
- The OVS bridge to attach containers to
- The VLAN ID to assign

---

#### VXLANs

Creates VXLAN tunnels between the current host and all other hosts on the same VLAN, using data previously collected by `--scan`.

```bash
python main.py --build vxlans
```

Prompts:
- VLAN ID of the network
- OVS bridge to attach VXLANs to

---

#### QoS

Creates a QoS policy on a given egress port with a configurable default traffic rate.

```bash
python main.py --build qos
```

Prompts:
- Egress port name
- Default traffic rate in bits per second (default: `1000000000` — 1 Gbps)

---

#### Queues

Creates traffic queues with specific rate limits and attaches them to an existing QoS object.

```bash
python main.py --build queues
```

Prompts:
- Comma-separated list of queue rates in bps (e.g. `10000000,20000000,50000000`)
- QoS object ID to attach the queues to

---

### Deploying the FL Application

Clones the FL repository into selected containers and installs all required dependencies, including PyTorch with CUDA support.

```bash
python main.py --deploy
```

Prompts:
- Which containers to deploy to (e.g. `cont-1,cont-2,cont-3`)

The deployment process performs the following steps inside each container:
1. Clones the FL repository
2. Runs `apt update` and `apt upgrade`
3. Installs `git`, `pip`, and `python3-venv`
4. Creates a Python virtual environment in `fl_app/`
5. Installs PyTorch (with CUDA) and all requirements from `requirements.txt`
6. Runs a CUDA availability check
7. Reboots the container

> **Note:** Nvidia driver version is automatically detected from the host and matched inside containers.

---

### Training

Starts a federated learning training run across selected containers.

```bash
python main.py --train
```

Prompts:
- Which container to use as the FL server (default: first container)
- Which containers to use as clients (default: all)

---

### Data Partitioning

Distributes dataset classes across containers to simulate non-IID federated learning conditions.

#### Random partitioning

Pass the number of data classes to randomly distribute:

```bash
python main.py --partition <num_classes>
```

Prompts:
- Which container to exclude (e.g. the server)

#### Partition from config file

Pass `0` to read partition assignments from the existing config file instead:

```bash
python main.py --partition 0
```

After partitioning, CSV file paths are automatically updated to use container-compatible paths (`/root/data`).

---

### Updating Nodes

Pulls the latest code from the remote repository into every container.

```bash
python main.py --update
```

Prompts:
- Server container name (default: first container)

---

### Resetting Nodes

Hard-resets every container to the `main` branch of the remote repository, discarding any local changes.

```bash
python main.py --reset
```

After resetting, `pyproject.toml` is backed up to `/root/data/pyproject_copy.toml` and `/root/data/pyproject_original.toml` on the first container.

---

## Data Files

All system state is stored as JSON in the `sys_data/` directory:

| File | Contents |
|---|---|
| `sys_data/hosts.json` | Host machine interfaces, IPs, VLANs, and MTU values |
| `sys_data/bridges.json` | OVS bridge names, hostnames, and controller info |
| `sys_data/containers.json` | LXC container configs, interfaces, bridges, and OVS ports |
| `sys_data/vxlans.json` | VXLAN interfaces, local host info, and remote IP targets |
| `sys_data/qos.json` | QoS objects, rates, associated ports, and queues |

Network test results are saved as timestamped CSV files in `measurements_data/`.

---

## Directory Structure

```
.
├── main.py                  # Entry point and CLI
├── containers.py            # LXC container management
├── bridges.py               # OVS bridge management
├── ports.py                 # OVS port utilities
├── measurements.py          # iPerf testing and CSV output
├── utils.py                 # General utilities (file I/O, shell commands)
├── fl_utils.py              # Federated learning helpers
├── requirements.txt         # Python dependencies
├── sys_data/                # Auto-generated system state JSON files
├── measurements_data/       # iPerf test result CSVs
└── schemas/                 # JSON schemas for data validation
    └── host.schema.json
```
