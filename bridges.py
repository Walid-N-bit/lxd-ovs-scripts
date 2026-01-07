"""
for later use:
sudo ovs-vsctl get qos c89c4937-de5e-4f6f-96e4-d98001f4f1d6 other_config:max-rate

"""

from utils import *
from typing import Literal

CONTROLLER = "tcp:10.0.1.5:6653"

VSCTL = "sudo ovs-vsctl"
PROTOCOLS = "OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13"

# ===== helper functions ===== #


def get_port_qos(port: str):
    """
    return QoS object attached to given OVS port name.
    """
    return cmd(f"{VSCTL} get port {port} qos")


def get_ovs_brs():
    """
    return a list of ove bridges installed on the host.

    :return: list of ovs bridges
    :rtype: list[str]
    """
    input = f"{VSCTL} list-br"
    output = cmd(input)
    out_lines = output.splitlines()
    return out_lines


# ===== command functions ===== #
# functions that return executable commands as strings #


def create_ovs_br_cmd(br: str, controller: str = CONTROLLER):
    """
    creates new ovs bridge with a given controller
    """
    input = f"{VSCTL} add-br {br} -- set-controller {br} {controller} \
    -- set bridge {br} protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13"  # protocols may be changed here if needed
    return input


# ===== execution functions ===== #
####### functions that execute and create data objects #######


def create_brs_for_vm(vm_name: str, br_nbr: int, controller: str = ""):
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


def create_brs_in_host(hostname: str, br_nbr: int, controller: str = ""):
    """
    create OVS bridges in a host machine.
    naming schema: br-<host_id>-<bridge_id>
        host_id: unique to every host in the network. the right-most number in IPv4
        bridge_id: 0, 1, 2, ...
    """
    data = {}
    input = ""
    brs = []  # bridges to be created in the vm
    host_id = get_host_id(mode="local")

    for i in range(br_nbr):
        brs.append(f"br-{host_id}-{i}")

    for br in brs:
        # send command to create bridge in VM from host machine
        disp_msg = f"Creating OVS Bridge {br} in {hostname} ... "
        print(disp_msg)
        if controller != "":
            input = create_ovs_br_cmd(br=br, controller=controller)
        else:
            input = create_ovs_br_cmd(br=br)

        br_out = cmd(input)
        save_logs([disp_msg, br_out])

    check = cmd(f"{VSCTL} show")
    print(check)
    save_logs([check])
