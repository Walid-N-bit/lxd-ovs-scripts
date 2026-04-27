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
    result = subprocess.run(
        ["lxc", "exec", cont, "--", "bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def get_server_ip(server_cont: str) -> str:
    return f"10.0.200.{server_cont.split('-')[-1]}"


# ── tmux helpers ──────────────────────────────────────────────────────────────

SESSION = "fl_training"


def tmux(cmd_str: str) -> str:
    return new_cmd(f"tmux {cmd_str}")


def tmux_new_session():
    # Kill existing session if present to start clean
    new_cmd(f"tmux kill-session -t {SESSION} 2>/dev/null")
    time.sleep(0.5)
    new_cmd(f"tmux new-session -d -s {SESSION} -x 220 -y 50")
    print(f"tmux session '{SESSION}' created.")


def tmux_new_pane() -> str:
    """Split a new pane and return its id."""
    result = subprocess.run(
        ["tmux", "split-window", "-t", SESSION, "-h", "-P", "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def tmux_send(pane_id: str, keys: str):
    new_cmd(["tmux", "send-keys", "-t", pane_id, keys, "C-m"])


def tmux_run_in_cont(pane_id: str, cont: str, command: str):
    """Open a container shell in a pane and run a command."""
    tmux_send(pane_id, f"lxc exec {cont} -- bash")
    time.sleep(0.5)
    tmux_send(pane_id, "cd fl_app && source venv/bin/activate")
    time.sleep(0.3)
    tmux_send(pane_id, command)


def tmux_tile():
    new_cmd(f"tmux select-layout -t {SESSION} tiled")


# ── Core operations ───────────────────────────────────────────────────────────


def cleanup_container(cont: str):
    print(f"  Cleaning {cont}...")
    lxc_exec(
        cont,
        (
            "pkill -9 -f flower-supernode 2>/dev/null; "
            "pkill -9 -f flower-superexec 2>/dev/null; "
            "pkill -9 -f flower-superlink 2>/dev/null; "
            "sleep 2; "  # wait for ports to release
            "rm -rf /root/.flwr/apps/ /root/.flwr/superlink/; "
            "echo cleaned"
        ),
    )


def start_superlink_tmux(server_cont: str, pane_id: str):
    """Start SuperLink in a visible tmux pane."""
    print(f"  Starting SuperLink in pane {pane_id}...")
    tmux_run_in_cont(
        pane_id,
        server_cont,
        "FLWR_LOG_LEVEL=DEBUG flower-superlink --insecure 2>&1 | tee /tmp/superlink.log",
    )
    time.sleep(3)
    # Verify it actually started
    check = lxc_exec(server_cont, "pgrep -f flower-superlink && echo UP || echo FAILED")
    if "UP" not in check:
        raise RuntimeError(f"SuperLink failed to start on {server_cont}.")
    print(f"  SuperLink running.")


def start_supernode_tmux(
    cont: str, server_ip: str, partition_id: int, num_partitions: int, pane_id: str
):
    """Start a local SuperNode in a visible tmux pane."""
    print(f"  {cont} → partition-id={partition_id} (tmux pane {pane_id})")
    tmux_run_in_cont(
        pane_id,
        cont,
        f"flower-supernode --insecure "
        f"--superlink {server_ip}:9092 "
        f"--node-config 'partition-id={partition_id} num-partitions={num_partitions}' "
        f"2>&1 | tee /tmp/supernode_{cont}.log",
    )


def start_supernode_background(
    cont: str, server_ip: str, partition_id: int, num_partitions: int
):
    """
    Start a remote SuperNode in a detached tmux session inside the container.
    - Survives launcher exit and Ctrl+C
    - Can be attached to later with:
      lxc exec <cont> -- tmux attach -t supernode
    """
    print(
        f"  {cont} → partition-id={partition_id} " f"(detached tmux inside container)"
    )

    supernode_cmd = (
        f"cd fl_app && source venv/bin/activate && "
        f"flower-supernode "
        f"--insecure "
        f"--superlink {server_ip}:9092 "
        f"--node-config 'partition-id={partition_id} num-partitions={num_partitions}' "
        f"2>&1 | tee /tmp/supernode_{cont}.log"
    )

    # Kill any existing supernode tmux session first
    lxc_exec(cont, "tmux kill-session -t supernode 2>/dev/null; sleep 0.5")

    # Start a new detached tmux session inside the container running the supernode
    lxc_exec(
        cont,
        (f"tmux new-session -d -s supernode " f"-x 200 -y 50 " f"'{supernode_cmd}'"),
    )


def wait_for_nodes(
    server_cont: str, expected: int, has_remote: bool = False, timeout: int = 180
) -> bool:
    print(f"\nWaiting for {expected} nodes to connect (timeout={timeout}s)...")
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
        print(f"  [{elapsed}s] {count}/{expected} nodes connected", end="\r")

        if count >= expected:
            print(f"\n  All {expected} nodes connected after {elapsed}s.")
            if has_remote:
                # Remote nodes need extra time to load venv + ClientApp after connecting
                print(f"  Giving remote nodes 15s to finish loading ClientApp...")
                for i in range(15, 0, -1):
                    print(f"  Starting in {i}s...  ", end="\r")
                    time.sleep(1)
                print()
            return True

        time.sleep(5)

    print(f"\n  TIMEOUT: only {count}/{expected} nodes connected.")
    return False


def collect_logs(clients: list):
    print("\n=== Supernode Logs ===")
    for cont in clients:
        print(f"\n--- {cont} ---")
        print(
            lxc_exec(
                cont, f"tail -20 /tmp/supernode_{cont}.log 2>/dev/null || echo 'no log'"
            )
        )


# ── Main launcher ─────────────────────────────────────────────────────────────


def start_fed_training(
    containers: list,
    server_cont: str,
    pyproject_path: str = ".",
    node_ready_timeout: int = 180,
):
    """
    Federated learning launcher with tmux visibility for local containers.

    Run on BOTH hosts with identical arguments.
    - Server host: opens tmux panes for all local containers + flwr run pane
    - Client host: opens tmux panes for local containers, remote ones run in background
    - Partition IDs derived from globally sorted list — consistent across both hosts
    """

    all_containers = sorted(containers)
    clients = [c for c in all_containers if c != server_cont]
    num_partitions = len(clients)
    partition_map = {cont: i for i, cont in enumerate(clients)}
    server_ip = get_server_ip(server_cont)

    local_conts = get_local_containers()
    is_server_host = server_cont in local_conts
    my_local_clients = [c for c in clients if c in local_conts]
    my_remote_clients = [c for c in clients if c not in local_conts]

    print(f"{'='*55}")
    print(f"Role:           {'SERVER HOST' if is_server_host else 'CLIENT HOST'}")
    print(f"Server:         {server_cont} ({server_ip})")
    print(f"Local clients:  {my_local_clients}")
    print(f"Remote clients: {my_remote_clients}")
    print(
        f"Partition map:  { {c: partition_map[c] for c in my_local_clients + my_remote_clients} }"
    )
    print(f"{'='*55}\n")

    # ── 1. Clean ──────────────────────────────────────────────────────────────
    print("=== Cleaning stale state ===")
    clean_targets = (
        ([server_cont] if is_server_host else []) + my_local_clients + my_remote_clients
    )
    for cont in clean_targets:
        cleanup_container(cont)

    # ── 2. Set up tmux session ────────────────────────────────────────────────
    print(f"\n=== Setting up tmux session '{SESSION}' ===")
    tmux_new_session()

    # Track pane IDs — first pane already exists after new-session
    result = subprocess.run(
        ["tmux", "list-panes", "-t", SESSION, "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    pane_ids = [result.stdout.strip()]  # first pane

    # Create one pane per local container that needs one
    local_conts_needing_pane = (
        [server_cont] if is_server_host else []
    ) + my_local_clients
    # First pane goes to server (or first client if not server host)
    # Remaining panes are split
    for _ in range(len(local_conts_needing_pane) - 1):
        pane_id = tmux_new_pane()
        pane_ids.append(pane_id)
        time.sleep(0.2)

    # Add one more pane for flwr run on server host
    if is_server_host:
        run_pane = tmux_new_pane()
        time.sleep(0.2)
    else:
        run_pane = None

    tmux_tile()
    time.sleep(0.5)

    # ── 3. Start SuperLink in first pane (server host only) ───────────────────
    pane_cursor = 0
    if is_server_host:
        print(f"\n=== Starting SuperLink ===")
        start_superlink_tmux(server_cont, pane_ids[pane_cursor])
        pane_cursor += 1

    # ── 4. Start local SuperNodes in tmux panes ───────────────────────────────
    if my_local_clients:
        print(f"\n=== Starting local SuperNodes (tmux) ===")
        for cont in my_local_clients:
            start_supernode_tmux(
                cont,
                server_ip,
                partition_map[cont],
                num_partitions,
                pane_ids[pane_cursor],
            )
            pane_cursor += 1
            time.sleep(0.5)

    # ── 5. Start remote SuperNodes in background ──────────────────────────────
    if my_remote_clients:
        print(f"\n=== Starting remote SuperNodes (background) ===")
        for cont in my_remote_clients:
            start_supernode_background(
                cont, server_ip, partition_map[cont], num_partitions
            )

    # ── 6. Server host: wait then run ─────────────────────────────────────────
    if is_server_host:
        # all_ready = wait_for_nodes(server_cont, num_partitions, node_ready_timeout)
        all_ready = wait_for_nodes(
            server_cont,
            num_partitions,
            has_remote=len(my_remote_clients) > 0,
            timeout=node_ready_timeout,
        )

        if not all_ready:
            collect_logs(my_local_clients + my_remote_clients)
            raise RuntimeError(
                "Not all nodes connected in time. "
                "Ensure the client host has also called start_fed_training()."
            )

        print(f"\n=== Starting flwr run ===")
        tmux_run_in_cont(
            run_pane,
            server_cont,
            f"flwr run {pyproject_path} local-deployment --stream 2>&1 | tee /tmp/flwr_run.log",
        )
        tmux_tile()
        print(f"\nTraining started.")
        print(f"Attach to tmux session to watch:  tmux attach -t {SESSION}")

    else:
        # Client host: keep supernodes alive, restart if they die
        print(f"\nClient host ready.")
        print(f"Attach to watch:  tmux attach -t {SESSION}")
        for cont in my_local_clients:
            print(f"  lxc exec {cont} -- tmux attach -t supernode")
        print(f"\nTerminal is free. Training is running.")


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
