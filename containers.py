"""
this module creates LXD containers
"""

from utils import *

DFLT_SERVER = "ubuntu"
DFLT_IMAGE = "24.04"
DFLT_PROFILE = "default_profile.yaml"


def create_container(
    name: str, profile: str = "", server: str = DFLT_SERVER, image: str = DFLT_IMAGE
):
    """
    creates one LXD container using input params.
    profile must contain the final settings values for the container.
    """
    input = f"sudo lxc init {server}:{image} {name}"
    if profile != "":
        input = f"sudo lxc init {server}:{image} {name} < {profile}"
    print(f"Creating container {name}... ", end=" ")
    output = cmd(input)
    print(f"Finished ✅")
    return output


# def yq_version():
#     yq_v = cmd("sudo yq --version")
#     return "command not found" in yq_v


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
        cmd("sudo apt install yq")

    # get user.network-config from profile, edit it for the requested host and vlan
    config = cmd(f"sudo yq '.config.\"user.network-config\"' {profile}")
    new_config = (
        config.replace("eth1_host", f"{host_id}")
        .replace("vlan_iface", f"vlan{vlan_id}")
        .replace("vlan_id", f"{vlan_id}")
        .replace("vlan_host", f"{host_id}")
        .replace("ovs_br", f"{ovs_br}")
    )
    print(f"Creating profile for 10.0.{vlan_id}.{host_id}...", end=" ")
    out = cmd(f"sudo yq -i -Y '.config.\"user.network-config\"={new_config}' {profile}")
    if len(out) > 0:
        print("out")
        return 0
    else:
        return f"{profile} for host {host_id} vlan{vlan_id} successfully created ✅"

def list_conts(vm:str):
    """
    return list of lxc containers in a host and their IP addresses.
    """
    out = lxc_cmd(vm_name=vm, command="sudo lxc list")
    return out
