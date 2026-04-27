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
import time
import json
from typing import Optional


def new_cmd(command: list | str) -> str:
    if isinstance(command, str):
        command = command.split()
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout + result.stderr


def get_local_containers() -> list[str]:
    result = subprocess.run(
        ["lxc", "list", "--format", "json"], capture_output=True, text=True
    )
    containers = json.loads(result.stdout)
    return [c["name"] for c in containers if c["status"] == "Running"]


def is_local_cont(cont: str) -> bool:
    return cont in get_local_containers()


def lxc_exec(cont: str, bash_cmd: str) -> str:
    """Run a bash command inside a local container."""
    result = subprocess.run(
        ["lxc", "exec", cont, "--", "bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def get_server_ip(server_cont: str) -> str:
    host_id = server_cont.split("-")[-1]
    return f"10.0.200.{host_id}"


def cleanup_container(cont: str):
    print(f"  Cleaning {cont}...")
    lxc_exec(
        cont,
        (
            "pkill -f flower-supernode 2>/dev/null; "
            "pkill -f flower-superexec 2>/dev/null; "
            "pkill -f flower-superlink 2>/dev/null; "
            "rm -rf /root/.flwr/apps/ /root/.flwr/superlink/; "
            "echo cleaned"
        ),
    )


def start_superlink(server_cont: str):
    print(f"Starting SuperLink on {server_cont}...")
    lxc_exec(
        server_cont,
        (
            "cd fl_app && source venv/bin/activate && "
            "nohup flower-superlink --insecure "
            "> /tmp/superlink.log 2>&1 &"
        ),
    )
    time.sleep(3)
    check = lxc_exec(server_cont, "pgrep -f flower-superlink && echo UP || echo FAILED")
    if "UP" not in check:
        raise RuntimeError(f"SuperLink failed to start on {server_cont}.")
    print(f"SuperLink running.")


def start_supernode(cont: str, server_ip: str, partition_id: int, num_partitions: int):
    print(f"  {cont} → partition-id={partition_id}")
    lxc_exec(
        cont,
        (
            f"cd fl_app && source venv/bin/activate && "
            f"nohup flower-supernode "
            f"--insecure "
            f"--superlink {server_ip}:9092 "
            f"--node-config 'partition-id={partition_id} num-partitions={num_partitions}' "
            f"> /tmp/supernode_{cont}.log 2>&1 &"
        ),
    )


def wait_for_nodes(server_cont: str, expected: int, timeout: int = 180) -> bool:
    """Poll SuperLink log until all expected nodes activate."""
    print(f"\nWaiting for {expected} nodes (timeout={timeout}s)...")
    start = time.time()
    count = 0
    while time.time() - start < timeout:
        result = lxc_exec(
            server_cont,
            "grep -c 'ActivateNode' /tmp/superlink.log 2>/dev/null || echo 0",
        )
        try:
            count = int(result.strip().split("\n")[-1])
        except ValueError:
            count = 0
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] {count}/{expected} nodes activated", end="\r")
        if count >= expected:
            print(f"\n  All {expected} nodes ready after {elapsed}s.")
            return True
        time.sleep(5)
    print(f"\n  TIMEOUT: only {count}/{expected} nodes connected.")
    return False


def collect_logs(local_clients: list):
    print("\n=== Supernode Logs ===")
    for cont in local_clients:
        print(f"\n--- {cont} ---")
        print(
            lxc_exec(
                cont, f"tail -20 /tmp/supernode_{cont}.log 2>/dev/null || echo 'no log'"
            )
        )


def start_fed_training(
    containers: list,  # ALL containers across both hosts
    server_cont: str,  # must be local to the host running flwr run
    pyproject_path: str = ".",
    node_ready_timeout: int = 180,
    role: str = "auto",  # "server_host" | "client_host" | "auto"
):
    """
    Two-host federated learning launcher.

    Run this function on BOTH hosts with identical arguments.
    Each instance automatically handles only its local containers.

    The host that owns server_cont also runs `flwr run`.
    Partition IDs are assigned from the globally sorted list so both
    hosts always agree on the assignment.

    Args:
        containers:          Complete list of ALL containers (both hosts)
        server_cont:         SuperLink container name
        pyproject_path:      Path for flwr run
        node_ready_timeout:  Seconds to wait before giving up
        role:                Force role or let it auto-detect
    """

    # ── Derive stable partition assignments from full sorted list ─────────────
    # Both host instances receive identical container list and sort it the same
    # way, so partition IDs are always consistent regardless of which host runs.
    all_containers = sorted(containers)
    clients = [c for c in all_containers if c != server_cont]
    num_partitions = len(clients)
    partition_map = {cont: i for i, cont in enumerate(clients)}
    server_ip = get_server_ip(server_cont)

    # ── Determine this host's role ────────────────────────────────────────────
    local_conts = get_local_containers()
    is_server_host = server_cont in local_conts
    my_clients = [c for c in clients if c in local_conts]

    print(f"{'='*50}")
    print(f"Role:        {'SERVER HOST' if is_server_host else 'CLIENT HOST'}")
    print(f"Server:      {server_cont} ({server_ip})")
    print(f"All clients: {clients}")
    print(f"My clients:  {my_clients}")
    print(f"Partitions:  { {c: partition_map[c] for c in my_clients} }")
    print(f"{'='*50}\n")

    # ── Clean local containers ────────────────────────────────────────────────
    print("=== Cleaning local containers ===")
    clean_targets = ([server_cont] if is_server_host else []) + my_clients
    for cont in clean_targets:
        cleanup_container(cont)

    # ── Server host: start SuperLink ─────────────────────────────────────────
    if is_server_host:
        print(f"\n=== Starting SuperLink ===")
        start_superlink(server_cont)

    # ── All hosts: start local SuperNodes ────────────────────────────────────
    if my_clients:
        print(f"\n=== Starting local SuperNodes ===")
        for cont in my_clients:
            start_supernode(cont, server_ip, partition_map[cont], num_partitions)
    else:
        print("No local client containers to start.")

    # ── Server host: wait for ALL nodes, then run ─────────────────────────────
    if is_server_host:
        all_ready = wait_for_nodes(server_cont, num_partitions, node_ready_timeout)

        if not all_ready:
            collect_logs(my_clients)
            raise RuntimeError(
                f"Not all nodes connected. "
                f"Check that the client host has also called start_fed_training()."
            )

        print(f"\n=== Starting flwr run ===")
        lxc_exec(
            server_cont,
            (
                f"cd fl_app && source venv/bin/activate && "
                f"flwr run {pyproject_path} local-deployment --stream "
                f"> /tmp/flwr_run.log 2>&1 &"
            ),
        )

        print("Streaming log (Ctrl+C to detach):")
        print("-" * 60)
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
            print(
                f"\nDetached. Monitor: lxc exec {server_cont} -- tail -f /tmp/flwr_run.log"
            )

    else:
        # Client host just waits so the process doesn't exit
        print(f"\nClient host ready. Waiting for training to complete...")
        print("(Ctrl+C to stop supernodes on this host)")
        try:
            while True:
                time.sleep(30)
                # Optionally print local supernode status
                for cont in my_clients:
                    alive = lxc_exec(
                        cont, "pgrep -f flower-supernode && echo alive || echo dead"
                    )
                    if "dead" in alive:
                        print(f"WARNING: supernode on {cont} has died, restarting...")
                        start_supernode(
                            cont, server_ip, partition_map[cont], num_partitions
                        )
        except KeyboardInterrupt:
            print("\nStopping local supernodes...")
            for cont in my_clients:
                lxc_exec(cont, "pkill -f flower-supernode 2>/dev/null")


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
