"""
this module creates LXD containers
"""

from utils import *

DFLT_SERVER = "ubuntu"
DFLT_IMAGE = "24.04"
DFLT_PROFILE = "default_profile.yaml"

# ===== command functions ===== #
# functions that return executable commands as strings #


def create_container(
    name: str, profile: str = "", server: str = DFLT_SERVER, image: str = DFLT_IMAGE
):
    """
    creates one LXD container using input params.
    profile must contain the final settings values for the container.
    """
    # input = f"sudo lxc init {server}:{image} {name}"
    input = f"sudo lxc launch {server}:{image} {name}"
    if profile != "":
        # input = f"sudo lxc init {server}:{image} {name} < {profile}"
        input = f"sudo lxc launch {server}:{image} {name} < {profile}"
    print(f"\nCreating container {name}... ")
    output = cmd(input)
    print(f"\nFinished")
    return output


def create_temp_profile(file: str):
    copy_file(file, f"temp_{file}")
    return f"temp_{file}"


def edit_yaml(
    host_id: int,
    vlan_id: int,
    ovs_br: str,
    path: str = DFLT_PROFILE,
):
    """
    modify contents of a yaml file.
    create a temporary .yaml profile using the passed params.
    """
    profile = create_temp_profile(path)

    # check if yq is installed, install if it isn't
    is_yq = is_installed("yq")
    if not is_yq:
        print(
            f"yq is not installed. It will now be installed in order to edit {profile}.\n"
        )
        output = cmd("sudo apt install -y yq")
        print(output)

    # get user.network-config from profile, edit it for the requested host and vlan
    config = cmd(f"sudo yq '.config.\"user.network-config\"' {profile}")
    new_config = (
        config.replace("eth1_host", f"{host_id}")
        .replace("vlan_iface", f"vlan{vlan_id}")
        .replace("vlan_id", f"{vlan_id}")
        .replace("vlan_host", f"{host_id}")
    )
    print(f"Creating profile for 10.0.{vlan_id}.{host_id}...", end=" ")
    # inp1 = f"sudo yq -i -Y '.config.\"user.network-config\"={new_config}' {profile}"
    inp1 = [
        "sudo",
        "yq",
        "-i",
        "-Y",
        f'.config.\"user.network-config\"={new_config}',
        f"{profile}",
    ]
    out1 = cmd(inp1)
    # change the value for the bridge
    # inp2 = f"sudo yq -i -Y '.devices.eth0.parent=\"{ovs_br}\"' {profile}"
    inp2 = ["sudo", "yq", "-i", "-Y", f'.devices.eth0.parent=\"{ovs_br}\"', f"{profile}"]
    out2 = cmd(inp2)
    if len(out1) > 0 or len(out2) > 0:
        print(out1)
        print(out2)
        return 0
    else:
        print(f"\n{profile} for host {host_id} vlan{vlan_id} successfully created")
        return profile


def list_conts_in_vm(vm: str):
    """
    return list of lxc containers in a host and their IP addresses.
    """
    out = lxc_cmd(vm_name=vm, command="sudo lxc list")
    return out


def list_conts():
    """
    return list of lxc containers in a host and their IP addresses.
    """
    headers = ["name", "status", "ipv4", "ipv6", "type", "snapshot"]
    raw_output = cmd("sudo lxc list -f csv")

    print(raw_output)


# ===== execution functions ===== #
####### functions that execute and create data objects #######


def create_conts_for_br(
    br: str,
    cont_ids: list,
    vlan: int,
    vm: str = "",
):
    """
    create LXD containers for an ovs bridge.
    naming scheme: cont-<cont_id>
    """
    # in each loop create a new temp profile for a container id
    for id in cont_ids:
        prfl_name = edit_yaml(host_id=id, vlan_id=vlan, ovs_br=br)
        cont_out = create_container(name=f"cont-{id}", profile=prfl_name)

    check = ""
    if vm != "":
        check = list_conts_in_vm(vm=vm)
    else:
        check = list_conts()

    print(check)
    save_logs([cont_out])
