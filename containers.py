"""
this module creates LXD containers
"""

from utils import *
from pathlib import Path

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
    input = f"sudo lxc init {server}:{image} {name}"
    # input = f"sudo lxc launch {server}:{image} {name}"
    if profile != "":
        input = f"sudo lxc init {server}:{image} {name} < {profile}"
        # input = f"sudo lxc launch {server}:{image} {name} < {profile}"
    print(f"\nCreating container {name}... ")
    output = cmd(input, shell=True)
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
) -> dict:
    """
    modify contents of a yaml file.
    create a temporary .yaml profile using the passed params.
    return the name of the profile.
    """
    from ruamel.yaml import YAML

    yaml = YAML()

    lxdbr0_ip = get_iface_ipv4("lxdbr0").split(".")
    lxdbr0_ip = ".".join(lxdbr0_ip[:3])

    profile = create_temp_profile(path)
    # with open(profile, "r") as f:
    #     profile_data = yaml.safe_load(f)
    profile_data = yaml.load(Path(profile))

    config = profile_data["config"]["user.network-config"]
    new_config = (
        config.replace("eth1_host", f"{host_id}")
        .replace("vlan_iface", f"vlan{vlan_id}")
        .replace("vlan_id", f"{vlan_id}")
        .replace("vlan_host", f"{host_id}")
        .replace("lxdbr0_ip", f"{lxdbr0_ip}")
    )
    profile_data["config"]["user.network-config"] = new_config
    profile_data["devices"]["eth0"]["parent"] = ovs_br
    print(f"Creating profile for 10.0.{vlan_id}.{host_id}...", end=" ")
    try:
        # with open(profile, "w") as f:
        #     yaml.dump(profile_data, f)
        yaml.dump(profile_data, Path(profile))
        print("Profile created.")
    except Exception as e:
        raise e

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
