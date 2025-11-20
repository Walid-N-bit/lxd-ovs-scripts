"""
for later use:
sudo ovs-vsctl get qos c89c4937-de5e-4f6f-96e4-d98001f4f1d6 other_config:max-rate

"""

from utils import *
from typing import Literal

CONTROLLER = "tcp:10.0.1.5:6653"
QOS = "@newquos"
QUEUE = "@newq-"


def vsctl_input(commands: list[str]):
    """
    build the full input command for ovs-vsctl
    """
    input = ["sudo ovs-vsctl"]
    for c in commands:
        input.append(c)
        input.append("--")

    return input


# ===== helper functions ===== #

def get_qos_id(iface: str):
    return cmd(f"sudo ovs-vsctl get port {iface} qos")


# ===== command functions ===== #


def create_ovs_br(br: str, controler: str = CONTROLLER):
    """
    creates new ovs bridge with a given controller
    """
    input = f"add-br {br} -- set-controller {br} {controler}"
    return input


def manage_port(br: str, iface: str, mode: Literal["add", "set", "del"]):
    """
    creates, modifies, deletes a port for a given ovs bridge
    """
    input = ""
    if mode == "set":
        input = f"{mode} port {br} {iface}"
    else:
        input = f"{mode}-port {br} {iface}"

    return input


def create_vxlan(
    br: str, iface: str, rmt_ip: str, key: str = "flow", dst_port: int = 4789
):
    """
    create a new vxlan port to the given ovs bridge
    """
    port_cmd = manage_port(br, iface=iface, mode="add")
    input = f"{port_cmd} -- set interface {iface} type=vxlan options:remote_ip={rmt_ip} options:key={key} options:dst_port={dst_port}"
    return input


def create_qos(iface: str, default_rate: int):
    """
    creates new QoS object.
    meant to be used inline while creating queues!
    """
    input = f"set port {iface} qos={QOS} -- --id={QOS} create qos type=linux-htb other-config:max-rate={default_rate}"
    return input


def create_queues(queue_rates: list[int], qos: str = QOS):
    """
    create queues for a given qos.
    """
    input = []
    for i, rate in enumerate(queue_rates):
        input.append(
            f"queues:{i}=@{i} -- --id=@{i} create queue other-config:max-rate={rate}"
        )
    return " -- ".join(input)


def add_queue_of(br: str, in_port: int, queue: str):
    """
    add queue to openflow table.
    execute command.
    """
    input = f"sudo ovs-ofctl add-flow {br} in_port={in_port},actions=set_queue:{queue},normal"
    out = cmd(input)
    return out
