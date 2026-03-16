"""
This module is designed to run this application: https://github.com/Walid-N-bit/fl_app.git

"""

from utils import cmd, get_host_id


def start_fed_training(containers: list, server_cont: str):
    """
    create tmux panes and send commands to each to start the federated learning process
    """
    # create session
    cmd("tmux")
    # start server
    id = get_host_id("vm", server_cont)
    server_ip = f"10.0.200.{id}"
    cmd("flower-superlink --insecure")

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
            cmd(f"tmux send-keys '{c}' C-m", shell=True)

    # start trining
    cmd("tmux split-window -h 'flwr run . local-deployment --stream'", shell=True)
