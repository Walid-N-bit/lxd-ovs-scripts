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


# tmux helper function
def send_keys(pane: int, keys: str, session: str = ""):
    """
    execute command on a specified tmux pane

    :param session: tmux session name
    :type session: str
    :param pane: pane number
    :type pane: int
    :param keys: command(s) to execute
    :type keys: str
    :return: tmux command output
    :rtype: list[str]
    """
    o1 = cmd(["tmux", "send-keys", "-t", f"{session}:0.{pane}", keys])
    o2 = cmd(["tmux", "send-keys", "-t", f"{session}:0.{pane}", "C-m"])
    return o1, o2


def bordered_print(text: str):
    print(f"\n{'='*len(text)}=")
    print(f" {text}")
    print(f"{'='*len(text)}=\n")


def start_fed_training(containers: list, server_cont: str, pyproject_path: str = "."):
    """
    create tmux session and panes for each client/server process. Start flwr application.

    :param containers: container names
    :type containers: list
    :param server_cont: server container name
    :type server_cont: str
    :param pyproject_path: relative flwr configuration file path
    :type pyproject_path: str
    """

    def init_cont(container: str, pane: int, session: str = ""):
        """
        initiate container dir and virtual environment

        :param container: container name
        :type container: str
        :param pane: tmux pane number
        :type pane: int
        :param session: tmux session
        :type session: str
        """

        cont_commands = [
            f"lxc shell {container}",
            "cd fl_app",
            "source venv/bin/activate",
        ]
        for c in cont_commands:
            out = send_keys(pane, c, session)
            print(out)

    # shelved for later
    # def check_supernodes_connect() -> bool:
    #     return

    # Process steps:
    #   1. separate local and remote containers
    all_local_conts = get_container_names()
    local_clients = [cont for cont in containers if cont in all_local_conts]
    if server_cont in local_clients:
        local_clients.remove(server_cont)
    remote_clients = [cont for cont in containers if cont not in all_local_conts]
    all_clients = sorted(local_clients + remote_clients)
    clients_info = {
        cont: {"supernode-id": i, "pane": 0} for i, cont in enumerate(all_clients)
    }

    #   2. determine if current host is local or remote
    is_server_local = server_cont in all_local_conts

    #   3. get server ip address
    id = server_cont.split("-")[-1]
    server_ip = f"10.0.200.{id}"

    print(f"\n{server_ip = }\n")

    #   4. create tmux session
    bordered_print("starting new session")
    session_name = "fl_session"
    cmd(["tmux", "new", "-d", "-s", session_name])

    #   5. create panes in tmux session for local containers
    #       (two for server, one for each client)

    # pair of client and their pane in th session (server gets 0)
    bordered_print("Creating panes")
    if is_server_local:
        for i, cont in enumerate(local_clients, 1):
            cmd(["tmux", "split-window", "-t", session_name, "-h"])
            clients_info[cont].update({"pane": i})
    else:
        for i, cont in enumerate(local_clients):
            cmd(["tmux", "split-window", "-t", session_name, "-h"])
            clients_info[cont].update({"pane": i})
    cmd(["tmux", "select-layout", "tiled"])

    #   6. initiate clients env
    bordered_print("Initializing containers venvs")
    for cont in clients_info:
        pane = clients_info.get(cont).get("pane")
        try:
            init_cont(cont, pane, session_name)
        except Exception as e:
            print(f"ERROR: {e}")
        print(f"{cont} done")

    #   7. launch superlink if server is local
    bordered_print("Starting Server SuperLink")
    superlink_command = "flower-superlink --insecure"
    if is_server_local:
        send_keys(0, superlink_command, session_name)
    time.sleep(3)

    #   8. launch supernodes in local containers
    bordered_print("Starting SuperNodes")
    for cont in clients_info:
        sn_id = clients_info.get(cont).get("supernode-id")
        pane = clients_info.get(cont).get("pane")
        supernode_command = f"flower-supernode --insecure --superlink {server_ip}:9092 --clientappio-api-address {server_ip}:9094 --node-config 'partition-id={sn_id} num-partitions={len(all_clients)}'"
        out = send_keys(pane, supernode_command, session_name)
        print(out)

    #   9. check if all clients (local and remote) have connected
    # while True:
    #     pass

    #   10. run flwr app
    if is_server_local:
        cmd(["tmux", "split-window", "-t", session_name, "-h"])
        cmd(["tmux", "select-layout", "tiled"])
        extra_pane = len(local_clients) + 1
        init_cont(server_cont, extra_pane, session_name)
        out = send_keys(
            extra_pane,
            f"flwr run {pyproject_path} --insecure --superlink {server_ip}:9093 --stream",
            session_name,
        )


# def start_fed_training(containers: list, server_cont: str, pyproject_path: str = "."):
#     containers = sorted(containers)

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
