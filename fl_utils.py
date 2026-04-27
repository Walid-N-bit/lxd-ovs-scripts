"""
This module is designed to run this application: https://github.com/Walid-N-bit/fl_app.git

"""

from utils import cmd, get_host_id
from containers import get_container_names
import pandas as pd
import time

TRAIN_DATA = "compressed_images_wheat/train.csv"
TEST_DATA = "compressed_images_wheat/test.csv"
PARTITIONING = "compressed_images_wheat/data_partition.json"
DATA_DIR = "compressed_images_wheat"

import subprocess
import json
from typing import Optional


def new_cmd(command: list | str) -> str:
    if isinstance(command, str):
        command = command.split()
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout + result.stderr


def get_container_names() -> list[str]:
    """Return names of containers on the local LXD host."""
    result = subprocess.run(
        ["lxc", "list", "--format", "json"], capture_output=True, text=True
    )
    containers = json.loads(result.stdout)
    return [c["name"] for c in containers if c["status"] == "Running"]


def get_host_id(prefix: str, cont_name: str) -> str:
    """Extract numeric ID from container name e.g. cont-140 → 140."""
    return cont_name.split("-")[-1]


def is_local_cont(cont: str) -> bool:
    return cont in get_container_names()


def get_server_ip(server_cont: str) -> str:
    host_id = get_host_id("vm", server_cont)
    return f"10.0.200.{host_id}"


def cleanup_container(cont: str):
    """Kill stale flower processes and clear FAB cache."""
    print(f"  Cleaning {cont}...")
    lxc_target = cont if is_local_cont(cont) else f"remote:{cont}"
    new_cmd(
        [
            "lxc",
            "exec",
            lxc_target,
            "--",
            "bash",
            "-c",
            "pkill -f flower-supernode 2>/dev/null; "
            "pkill -f flower-superexec 2>/dev/null; "
            "pkill -f flower-superlink 2>/dev/null; "
            "rm -rf /root/.flwr/apps/ "
            "/root/.flwr/superlink/ "  # remove if accidentally created
            "; echo done",
        ]
    )


def start_supernode(cont: str, server_ip: str, partition_id: int, num_partitions: int):
    """
    Start a supernode on any container — local or remote — using lxc exec.
    This is reliable regardless of which host machine runs this script.
    """
    lxc_target = cont if is_local_cont(cont) else f"remote:{cont}"

    # Build the supernode command
    supernode_cmd = (
        f"cd fl_app && source venv/bin/activate && "
        f"nohup flower-supernode "
        f"--insecure "
        f"--superlink {server_ip}:9092 "
        f"--node-config 'partition-id={partition_id} num-partitions={num_partitions}' "
        f"> /tmp/supernode_{cont}.log 2>&1 &"
    )

    result = new_cmd(["lxc", "exec", lxc_target, "--", "bash", "-c", supernode_cmd])
    print(f"  Started supernode on {cont} (partition {partition_id}/{num_partitions})")
    return result


def wait_for_nodes(server_cont: str, expected: int, timeout: int = 120) -> bool:
    """
    Poll SuperLink log until all expected nodes have activated.
    Returns True if all nodes ready, False if timeout.
    """
    print(f"\nWaiting for {expected} nodes to connect (timeout={timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        result = new_cmd(
            [
                "lxc",
                "exec",
                server_cont,
                "--",
                "bash",
                "-c",
                "grep -c 'ActivateNode' /tmp/superlink.log 2>/dev/null || echo 0",
            ]
        )
        try:
            count = int(result.strip().split("\n")[-1])
        except ValueError:
            count = 0

        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Nodes activated: {count}/{expected}", end="\r")

        if count >= expected:
            print(f"\n  All {expected} nodes connected after {elapsed}s.")
            return True
        time.sleep(5)

    print(f"\n  TIMEOUT: Only {count}/{expected} nodes connected after {timeout}s.")
    return False


def get_node_logs(containers: list, server_cont: str):
    """Print supernode logs for debugging after a failed round."""
    print("\n=== Node Status Report ===")
    for cont in containers:
        if cont == server_cont:
            continue
        lxc_target = cont if is_local_cont(cont) else f"remote:{cont}"
        print(f"\n--- {cont} ---")
        result = cmd(
            [
                "lxc",
                "exec",
                lxc_target,
                "--",
                "bash",
                "-c",
                f"tail -20 /tmp/supernode_{cont}.log 2>/dev/null || echo 'no log found'",
            ]
        )
        print(result)


def start_fed_training(
    containers: list,
    server_cont: str,
    pyproject_path: str = ".",
    lxc_remote_name: str = "remote",  # name of remote LXD remote, set via `lxc remote add`
    node_ready_timeout: int = 120,
):
    """
    Robust federated learning launcher.

    Works correctly across two LXD hosts. Uses lxc exec for all container
    operations instead of tmux shell, ensuring remote containers are started.

    Args:
        containers:          All participating containers (local + remote)
        server_cont:         Name of the SuperLink container
        pyproject_path:      Path to pass to `flwr run`
        lxc_remote_name:     Name of the remote LXD host as configured in `lxc remote`
        node_ready_timeout:  Seconds to wait for all nodes before aborting
    """

    containers = sorted(containers)
    clients = [c for c in containers if c != server_cont]
    num_partitions = len(clients)
    server_ip = get_server_ip(server_cont)

    print(f"Server:      {server_cont} ({server_ip})")
    print(f"Clients:     {clients}")
    print(f"Partitions:  {num_partitions}")
    print(f"Remote name: {lxc_remote_name}\n")

    # ── Step 1: Clean all containers ─────────────────────────────────────────
    print("=== Cleaning stale state ===")
    all_targets = [server_cont] + clients
    for cont in all_targets:
        cleanup_container(cont)

    # ── Step 2: Start SuperLink ───────────────────────────────────────────────
    print(f"\n=== Starting SuperLink on {server_cont} ===")
    if not is_local_cont(server_cont):
        raise RuntimeError(
            f"Server container '{server_cont}' must be local to the machine "
            f"running flwr run. Run this script from the host that owns {server_cont}."
        )

    new_cmd(
        [
            "lxc",
            "exec",
            server_cont,
            "--",
            "bash",
            "-c",
            "cd fl_app && source venv/bin/activate && "
            "nohup flower-superlink --insecure "
            "> /tmp/superlink.log 2>&1 &",
        ]
    )
    time.sleep(3)

    # Verify SuperLink is up
    check = new_cmd(
        [
            "lxc",
            "exec",
            server_cont,
            "--",
            "bash",
            "-c",
            "pgrep -f flower-superlink && echo UP || echo FAILED",
        ]
    )
    if "FAILED" in check:
        raise RuntimeError("SuperLink failed to start. Check /tmp/superlink.log")
    print(f"SuperLink running on {server_ip}:9092")

    # ── Step 3: Start all SuperNodes ─────────────────────────────────────────
    print(f"\n=== Starting {num_partitions} SuperNodes ===")
    for i, cont in enumerate(clients):
        start_supernode(cont, server_ip, i, num_partitions)

    # ── Step 4: Wait for all nodes to connect ────────────────────────────────
    all_connected = wait_for_nodes(server_cont, num_partitions, node_ready_timeout)

    if not all_connected:
        print("\nNot all nodes connected. Collecting logs for diagnosis...")
        get_node_logs(clients, server_cont)
        raise RuntimeError(f"Aborting: not all nodes connected. " f"Check logs above.")

    # ── Step 5: Launch training ───────────────────────────────────────────────
    print(f"\n=== Starting federated run ===")
    new_cmd(
        [
            "lxc",
            "exec",
            server_cont,
            "--",
            "bash",
            "-c",
            f"cd fl_app && source venv/bin/activate && "
            f"flwr run {pyproject_path} local-deployment --stream "
            f">> /tmp/flwr_run.log 2>&1 &",
        ]
    )

    print(f"Training started. Streaming logs from {server_cont}:")
    print("-" * 60)

    # Stream the run log
    try:
        proc = subprocess.Popen(
            [
                "lxc",
                "exec",
                server_cont,
                "--",
                "bash",
                "-c",
                "tail -f /tmp/flwr_run.log",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        for line in proc.stdout:
            print(line, end="")
    except KeyboardInterrupt:
        print("\nLog streaming stopped (training continues in background).")


# def start_fed_training(containers: list, server_cont: str, pyproject_path: str = "."):
#     """
#     create tmux panes and send commands to each to start the federated learning process
#     """

#     containers = sorted(containers)

#     def send_keys(keys: str):
#         return ["tmux", "send-keys", keys, "C-m"]

#     def is_local_cont(cont: str) -> bool:
#         local_conts = get_container_names()
#         if cont in local_conts:
#             return True
#         else:
#             return False

#     # create session
#     sess_out = cmd("tmux new -d")

#     print(sess_out)
#     # start server
#     if is_local_cont(server_cont):
#         id = get_host_id("vm", server_cont)
#         server_ip = f"10.0.200.{id}"
#         cmd(send_keys(f"lxc shell {server_cont}"))
#         cmd(send_keys("cd fl_app ; source venv/bin/activate"))
#         cmd(send_keys("FLWR_LOG_LEVEL=DEBUG flower-superlink --insecure"))
#     else:
#         id = server_cont[5:]
#         server_ip = f"10.0.200.{id}"

#     # start clients
#     clients = containers.copy()
#     if server_cont in clients:
#         clients.remove(server_cont)
#     nbr_parts = len(clients)

#     print(f"\n{clients = }")
#     print(f"{server_ip = }\n")

#     for i, cont in enumerate(clients):
#         if is_local_cont(cont):
#             commands = [
#                 f"lxc shell {cont}",
#                 "cd fl_app ; source venv/bin/activate",
#                 f"flower-supernode --insecure --superlink {server_ip}:9092 --node-config 'partition-id={i} num-partitions={nbr_parts}'",
#             ]
#             cmd("tmux split-window -h")
#             for c in commands:
#                 cmd(send_keys(c))
#     time.sleep(10)
#     # start trining
#     if is_local_cont(server_cont):
#         cmd(["tmux", "split-window", "-h"])
#         cmd(send_keys(f"lxc shell {server_cont}"))
#         cmd(send_keys("cd fl_app ; source venv/bin/activate"))
#         cmd(send_keys(f"flwr run {pyproject_path} local-deployment --stream"))

#     # to adjust panes
#     cmd("tmux select-layout tiled")


# def start_fed_training(containers: list, server_cont: str, pyproject_path: str = "."):
#     containers = sorted(containers)

#     def send_keys(pane: int, keys: str):
#         return ["tmux", "send-keys", "-t", f"0.{pane}", keys, "C-m"]

#     def is_local_cont(cont: str) -> bool:
#         local_conts = get_container_names()
#         if cont in local_conts:
#             return True
#         else:
#             return False

#     # Create session
#     cmd("tmux new-session -d -s fl")

#     pane = 0  # track pane index

#     # Start server in pane 0
#     if is_local_cont(server_cont):
#         id = get_host_id("vm", server_cont)
#         server_ip = f"10.0.200.{id}"
#         cmd(send_keys(pane, f"lxc shell {server_cont}"))
#         cmd(send_keys(pane, "cd fl_app ; source venv/bin/activate"))
#         cmd(send_keys(pane, "flower-superlink --insecure"))
#     else:
#         id = server_cont[5:]
#         server_ip = f"10.0.200.{id}"

#     # Start clients, each in their own pane
#     clients = [c for c in containers if c != server_cont]
#     nbr_parts = len(clients)
#     for i, cont in enumerate(clients):
#         pane += 1
#         cmd(["tmux", "split-window", "-t", "fl", "-h"])
#         if is_local_cont(cont):
#             cmd(send_keys(pane, f"lxc shell {cont}"))
#             cmd(send_keys(pane, "cd fl_app ; source venv/bin/activate"))
#             cmd(
#                 send_keys(
#                     pane,
#                     f"flower-supernode --insecure --superlink {server_ip}:9092 "
#                     f"--node-config 'partition-id={i} num-partitions={nbr_parts}'",
#                 )
#             )

#     # Start flwr run in a new pane
#     if is_local_cont(server_cont):
#         pane += 1
#         cmd(["tmux", "split-window", "-t", "fl", "-h"])
#         cmd(send_keys(pane, f"lxc shell {server_cont}"))
#         cmd(send_keys(pane, "cd fl_app ; source venv/bin/activate"))
#         cmd(send_keys(pane, f"flwr run {pyproject_path} local-deployment --stream"))


def save_original_toml(container: str):
    cont_in = "scp /root/fl_app/pyproject.toml /root/data/pyproject_original.toml"
    out = cmd(f"lxc exec {container} -- bash -c '{cont_in}'", shell=True)
    print(out)


def save_modified_toml(container: str):
    cont_in = "scp /root/fl_app/pyproject.toml /root/data/pyproject_copy.toml"
    out = cmd(f"lxc exec {container} -- bash -c '{cont_in}'", shell=True)
    print(out)


def reset_toml(container):
    cont_in = "scp /root/data/pyproject_original.toml /root/fl_app/pyproject.toml"
    out = cmd(f"lxc exec {container} -- bash -c '{cont_in}'", shell=True)
    print(out)


def restore_modified_tol(container):
    cont_in = "scp /root/data/pyproject_copy.toml /root/fl_app/pyproject.toml"
    out = cmd(f"lxc exec {container} -- bash -c '{cont_in}'", shell=True)
    print(out)


def update_nodes(containers: list, server: str = ""):
    """
    perform git pull and update local repos on clients and server nodes.

    :param containers: list of container names
    :type containers: list
    :param server: server container name
    :type server: str
    """
    if server:
        save_modified_toml(server)
        reset_toml(server)
    for cont in containers:
        out = cmd(f"lxc exec {cont} -- git -C fl_app pull")
        print(out)

    if server:
        restore_modified_tol(server)


def partition_data(containers: list, parts_nbr: int, server_cont: str) -> dict:
    """
    Docstring for partition_data

    :param containers: Description
    :type containers: list
    :return: Description
    :rtype: dict
    """
    import random, json

    def create_parts(nodes: list, classes: list) -> list[list]:
        result = []
        for _ in range(len(nodes)):
            local_part = random.sample(classes, parts_nbr)
            result.append(local_part)
        return result

    def included_classes(class_parts: list[list]) -> set:
        all_classes = []
        for part in class_parts:
            all_classes.extend(part)
        return set(all_classes)

    if server_cont in containers:
        containers.remove(server_cont)
    else:
        pass
    global_train = pd.read_csv(TRAIN_DATA)
    # global_test = pd.read_csv(TEST_DATA)
    global_classes = sorted(global_train["class_name"].unique())

    partitions = create_parts(containers, global_classes)

    while included_classes(partitions) != set(global_classes):
        # print(f"included set: {included_classes(partitions)}")
        # print(f"global set: {global_classes}")
        partitions = create_parts(containers, global_classes)

    container_data_partition = {}
    for i, cont in enumerate(containers):
        container_data_partition.update({f"{cont}": partitions[i]})

    with open(PARTITIONING, "w") as f:
        json.dump(container_data_partition, f)

    return container_data_partition


def save_partitioned_csv(partition_info: dict, path: str = DATA_DIR):
    """
    create training and testing csv files for each container.

    :param partition_info: dictionary describing classes used in each container
    :type partition_info: dict
    """
    global_train = pd.read_csv(TRAIN_DATA, index_col=0)
    global_test = pd.read_csv(TEST_DATA, index_col=0)
    for cont in partition_info:
        local_train = global_train[
            global_train["class_name"].isin(partition_info[cont])
        ]
        local_test = global_test[global_test["class_name"].isin(partition_info[cont])]
        local_train.to_csv(f"{path}/{cont}_train.csv", index=False)
        local_test.to_csv(f"{path}/{cont}_test.csv", index=False)


def replace_col_strings(path: str, col: str, old: str, new: str):
    """
    replace strings in all rows of a col with another string

    :param path: file path
    :type path: str
    :param col: column name
    :type col: str
    :param old: old string text
    :type old: str
    :param new: new string text
    :type new: str
    """

    """
    execute the following to use this function:

    files = glob("compressed_images_wheat/cont-*.csv")
    for f in files:
        replace_col_strings(
            f,
            "path",
            "compressed_images_wheat",
            "/root/data",
        )
    """
    df = pd.read_csv(path)
    df[col] = df[col].replace(old, new, regex=True)
    df.to_csv(path, index=False)
