from containers import *
from utils import *
from bridges import *


def create_brs_for_vm(vm_name: str, controller: str = "", br_nbr: int = 1):
    """
    create bridges for a VM.
    naming schema: br-<host_id>-<bridge_id>
        host_id: unique to every host in the network. the right-most number in IPv4
        bridge_id: 0, 1, 2, ...
    """
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
    print(check)
    save_logs([check])


def create_conts_for_br(vm: str, br: str, cont_ids: list, vlan: int):
    """
    create LXD containers for an ovs bridge.
    naming scheme: cont-<cont_id>
    """
    # in each loop create a new temp profile for a container id
    for id in cont_ids:
        prfl_name = edit_yaml(host_id=id, vlan_id=vlan, ovs_br=br)
        cont_out = create_container(name=f"cont-{id}", profile=prfl_name)
        check = list_conts(vm=vm)
        print(check)
        save_logs([cont_out])


def create_vxlans():
    """
    creates two vxlans, one for each end.
    get ipv4 of both ends, create a vxlan with th same name (for clarity) on both bridges.
    """
    
    pass


def args_func():
    
    pass

def main():

    pass


if __name__ == "__main__":
    pass
