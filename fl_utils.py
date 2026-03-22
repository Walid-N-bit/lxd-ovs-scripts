"""
This module is designed to run this application: https://github.com/Walid-N-bit/fl_app.git

"""

from utils import cmd, get_host_id
import pandas as pd

TRAIN_DATA = "compressed_images_wheat/train.csv"
TEST_DATA = "compressed_images_wheat/test.csv"
PARTITIONING = "compressed_images_wheat/data_partition.json"
DATA_DIR = "compressed_images_wheat"


def start_fed_training(containers: list, server_cont: str):
    """
    create tmux panes and send commands to each to start the federated learning process
    """

    def send_keys(keys: str):
        return ["tmux", "send-keys", keys, "C-m"]

    # create session
    sess_out = cmd("tmux new -d")
    print(sess_out)
    # start server
    id = get_host_id("vm", server_cont)
    server_ip = f"10.0.200.{id}"
    cmd(send_keys(f"lxc shell {server_cont}"))
    cmd(send_keys("cd fl_app ; source venv/bin/activate"))
    cmd(send_keys("flower-superlink --insecure"))

    # start clients
    clients = containers.copy()
    clients.remove(server_cont)
    nbr_parts = len(clients)
    for i, cont in enumerate(clients):
        commands = [
            f"lxc shell {cont}",
            "cd fl_app ; source venv/bin/activate",
            f"flower-supernode --insecure --superlink {server_ip}:9092 --node-config 'partition-id={i} num-partitions={nbr_parts}'",
        ]
        cmd("tmux split-window -h")
        for c in commands:
            cmd(send_keys(c))

    # start trining
    cmd(["tmux", "split-window", "-h"])
    cmd(send_keys(f"lxc shell {server_cont}"))
    cmd(send_keys("cd fl_app ; source venv/bin/activate"))
    cmd(send_keys("flwr run . local-deployment --stream"))


def update_nodes(containers: list):
    for cont in containers:
        out = cmd(f"lxc exec {cont} -- git -C fl_app pull")
        print(out)


def partition_data(containers: list, parts_nbr: int, server_cont:str) -> dict:
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
    
    containers.remove(server_cont)
    global_train = pd.read_csv(TRAIN_DATA)
    # global_test = pd.read_csv(TEST_DATA)
    global_classes = sorted(global_train["class_name"].unique())

    # global_labels_map = {i: k for i, k in enumerate(global_classes)}

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
    create training and testing csv files then copy them to each container.

    :param partition_info: dictionary describing classes used in each container
    :type partition_info: dict
    """
    global_train = pd.read_csv(TRAIN_DATA)
    global_test = pd.read_csv(TEST_DATA)
    for cont in partition_info:
        local_train = global_train[
            global_train["class_name"].isin(partition_info[cont])
        ]
        local_test = global_test[global_test["class_name"].isin(partition_info[cont])]
        local_train.to_csv(f"{path}/{cont}_train.csv")
        local_test.to_csv(f"{path}/{cont}_test.csv")
