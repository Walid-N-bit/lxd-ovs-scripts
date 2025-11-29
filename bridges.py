"""
for later use:
sudo ovs-vsctl get qos c89c4937-de5e-4f6f-96e4-d98001f4f1d6 other_config:max-rate

"""

from utils import *
from typing import Literal

CONTROLLER = "tcp:10.0.1.5:6653"
QOS = "@newquos"
QUEUE = "@newq-"
VSCTL = "sudo ovs-vsctl"
PROTOCOLS = "OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13"

# ===== helper functions ===== #


def get_qos_id(port: str):
    """
    return QoS object attached to given OVS port name.
    """
    return cmd(f"{VSCTL} get port {port} qos")


# ===== command functions ===== #
# functions that return executable commands as strings #


def create_ovs_br_cmd(br: str, controller: str = CONTROLLER):
    """
    creates new ovs bridge with a given controller
    """
    input = f"{VSCTL} add-br {br} -- set-controller {br} {controller} \
    -- set bridge {br} protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13"   # protocols may be changed here if needed
    return input


def manage_ovs_port_cmd(br: str, port: str, mode: Literal["add", "set", "del"]):
    """
    creates, modifies, deletes a port for a given ovs bridge
    """
    input = ""
    if mode == "set":
        input = f"{VSCTL} {mode} port {br} {port}"
    else:
        input = f"{VSCTL} {mode}-port {br} {port}"

    return input


def add_vxlan(br: str, port: str, rmt_ip: str, key: str = "flow", dst_port: int = 4789):
    """
    return command string for creating a vxlan between two hosts for given bridge.
    naming schema: vxlan-<host_a_id>-<host_b_id>
    """
    port_cmd = manage_ovs_port_cmd(br, port=port, mode="add")
    input = f"{port_cmd} -- set interface {port} type=vxlan options:remote_ip={rmt_ip} options:key={key} options:dst_port={dst_port}"
    return input


def create_qos(port: str, default_rate: int):
    """
    creates new QoS object with a set default rate-limit for an ovs port.
    """
    input = f"{VSCTL} set port {port} qos={QOS} -- --id={QOS} create qos type=linux-htb other-config:max-rate={default_rate}"
    return input


def create_queues(queue_rates: list[int], qos: str = QOS):
    """
    create queues for a given QoS object.
    queues are numbered in the QoS by list order. (0, 1, 2, ...)
    """
    in_1 = []
    in_2 = []
    for i, rate in enumerate(queue_rates):
        in_1.append(f"queues:{i}=@{i}")
        in_2.append(f"--id=@{i} create queue other-config:max-rate={rate}")

    in_1_join = " ".join(in_1)
    in_2_join = " -- ".join(in_2)

    return f"{VSCTL} set qos {qos} {in_1_join} -- {in_2_join}"


def add_queue_of(br: str, in_port: int, queue: str):
    """
    add queue to openflow table.
    """
    input = f"sudo ovs-ofctl add-flow {br} in_port={in_port},actions=set_queue:{queue},normal"
    return input

# ===== execution functions ===== #
####### functions that execute and create data objects #######


def create_brs_for_vm(vm_name: str, controller: str = "", br_nbr: int = 1):
    """
    create bridges for a VM.
    naming schema: br-<host_id>-<bridge_id>
        host_id: unique to every host in the network. the right-most number in IPv4
        bridge_id: 0, 1, 2, ...
    """
    data = {}
    input = ""
    brs = []  # bridges to be created in the vm
    host_id = get_host_id(mode="vm", vm=vm_name)

    for i in range(br_nbr):
        brs.append(f"br-{host_id}-{i}")

    for br in brs:
        # send command to create bridge in VM from host machine
        disp_msg = f"Creating OVS Bridge {br} in {vm_name} ... "
        print(disp_msg)
        if controller != "":
            input = create_ovs_br_cmd(br=br, controller=controller)
        else:
            input = create_ovs_br_cmd(br=br)

        br_out = lxc_cmd(vm_name, command=input)
        save_logs([disp_msg, br_out])

    check = lxc_cmd(vm_name, f"{VSCTL} show")
    data = {}
    print(check)
    save_logs([check])


def create_vxlans():
    """
    creates two vxlans, one for each end.
    get ipv4 of both ends, create a vxlan with th same name (for clarity) on both bridges.
    """

    pass
