from containers import *
from utils import *
from bridges import *
from ports import *
from measurements import *
import argparse
import re
import yaml
from pathlib import Path

HOSTS_DATA = "sys_data/hosts.json"
BRIDGES_DATA = "sys_data/bridges.json"
CONTAINERS_DATA = "sys_data/containers.json"
QOS_DATA = "sys_data/qos.json"
VXLAN_DATA = "sys_data/vxlans.json"

MEASUREMENTS = "measurements_data"

FL_REPO = ""


def args_func():
    parser = argparse.ArgumentParser(
        description="Automate data collection and network creation"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="test code",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Check interfaces on the host and stores data in a file.",
    )
    parser.add_argument(
        "--build",
        choices=["bridges", "containers", "vxlans", "qos", "queues"],
        help="Build the network.",
    )
    parser.add_argument(
        "--deploy", action="store_true", help="Deploy ML app in all containers"
    )

    args = parser.parse_args()
    return args


def update_host_data():
    """
    get data about the host. update hosts.json
    see data schema in schemas/host.schema.json
    """
    hostname = get_hostname()
    ips = get_ipv4s()
    ifaces = []
    for ip in ips:
        output = get_iface_data(ip)
        iface_data = {
            "iface": output.get("ifname"),
            "ipv4": ip,
            "vlan": output.get("linkinfo", {}).get("info_data", {}).get("id"),
            "mtu": output.get("mtu"),
        }
        ifaces.append(iface_data)

    item = {"hostname": hostname, "ifaces": ifaces}
    update_json_file(key="hostname", value=hostname, new_item=item, path=HOSTS_DATA)


def update_brs_data():
    """
    return a dict object containing ovs bridges info.
    :return: ovs brs data
    :rtype: dict
    """
    hostname = get_hostname()
    bridges = get_ovs_brs()
    for br in bridges:
        item = {
            "br_name": br,
            "hostname": hostname,
            "controller": CONTROLLER,
        }
        update_json_file(key="br_name", value=br, new_item=item, path=BRIDGES_DATA)


def update_container_data():
    """
    get info about containers then update their data.

    :return: Description
    :rtype: Literal[True]
    """
    container_names = cmd("sudo lxc list --format=csv -c n").splitlines()
    data = []
    for cont in container_names:
        out = cmd(f"sudo lxc config show {cont}")
        yaml_data = yaml.safe_load(out)
        # the output of this is str
        user_config = yaml_data.get("config").get("user.network-config")
        user_devices = yaml_data.get("devices")
        # must be converted to yaml
        user_config_yaml = yaml.safe_load(user_config)

        # container name = cont
        br_name = user_devices.get("eth0", {}).get("parent", {})
        ovs_port = yaml_data.get("config").get("volatile.eth0.host_name", "")
        ifaces = []
        vlan = user_config_yaml.get("vlans")
        vlan_name = [key for key in vlan.keys()][0]
        vlan_ip_addr = vlan.get(vlan_name).get("addresses", [])
        vlan_id = vlan.get(vlan_name).get("id")
        ifaces.append({vlan_name: {"id": vlan_id, "addresses": vlan_ip_addr}})

        ethernets = user_config_yaml.get("ethernets").keys()
        for eth in ethernets:
            addr = user_config_yaml.get("ethernets").get(eth).get("addresses", [])
            ifaces.append({eth: {"addresses": addr}})

        item = {
            "container": cont,
            "interfaces": ifaces,
            "bridge": br_name,
            "ovs_port": ovs_port,
        }
        update_json_file(
            key="container", value=cont, new_item=item, path=CONTAINERS_DATA
        )


def update_vxlan_data():
    """
    get info about VXLANs then update their data.

    :return: Description
    :rtype: Literal[True]
    """
    all_vxlans = get_vxlans()
    bridges = get_ovs_brs()
    vxlan_data = []

    for br in bridges:
        ifaces = get_ifaces(br)
        for iface in ifaces:
            if iface in all_vxlans:
                hostname = get_hostname()
                host_ips = get_ipv4s()
                options = get_vxlan_options(iface).get("options")
                item = dict(
                    vxlan=iface,
                    host=dict(name=hostname, addresses=host_ips),
                    remote_host=options.get("remote_ip"),
                )
                vxlan_data.append(item)

    add_to_json_file(path=VXLAN_DATA, new_items=vxlan_data)


def update_qos_data():
    """
    get QoS objects in the host and save their data in a json file.

    :return: Description
    :rtype: Literal[True]
    """
    new_data = []
    qos_objs = get_all_qos()
    for qos in qos_objs:
        item = dict(
            qos_id=qos,
            tag=get_qos_tag(qos),
            default_rate=get_qos_default_rate(qos_id=qos),
            ports=get_qos_ports(qos),
            queues=get_qos_queues(qos),
        )
        new_data.append(item)
    add_to_json_file(new_items=new_data, path=QOS_DATA)


def is_vlan_ip(vlan: str | int, ip: str):
    """
    check if an IPv4 address follows the pattern: 10.0.<vlan>.<number>

    :param vlan: vlan id
    :type vlan: str|int
    :param ip: ip address to check
    :type ip: str
    :return: if the ip matches the desired pattern
    :rtype: bool
    """
    pattern = rf"^10\.0\.{vlan}\.(\d{{1,3}})$"
    match = re.search(pattern, ip)
    if match:
        return True
    else:
        return False


def net_hosts_ips(vlan: str | int):
    """
    get the IPv4s of host machines for a given vlan id

    :param vlan: vlan id
    :type vlan: str | int
    :return: IPv4s of all host machines
    :rtype: list[str]
    """
    hosts_data = read_json_file(path=HOSTS_DATA)
    data = []
    for item in hosts_data:
        ifaces = item.get("ifaces")
        for iface in ifaces:
            ip = iface.get("ipv4")
            if is_vlan_ip(vlan, ip):
                data.append(ip)
    return data


def save_sys_data():
    """
    get system info and save it to appropriate json files
    """
    update_host_data()
    update_brs_data()
    update_container_data()
    update_vxlan_data()
    update_qos_data()


def is_yes(message: str):
    """
    return True or False for a y or n answer.

    :param message: message text
    :type message: str
    """
    answer = input(f"{message} [y/n]? ")
    if answer == "y":
        return True
    elif answer == "n":
        return False
    else:
        print("Only type y for 'yes' or n for 'no'.\n")
        is_yes()


def run_test():
    """
    Run a network test between two containers then safe the data to a csv file.
    """
    _, client_out = run_iperf_test(server="cont-1", client="cont-2")
    parsed_data = parse_iperf(client_out)
    save_to_csv(
        path=f"{MEASUREMENTS}/{TIME}.csv", data=parsed_data, headers=DATA_FIELDS
    )


def get_container_names() -> list[str]:
    """
    return a list of container names in the host

    :return: container names
    :rtype: list[str]
    """
    data = read_json_file(CONTAINERS_DATA)
    containers = [item.get("container") for item in data]
    return containers


def clone_to_container(name: str):
    """
    download a repo into a container

    :param name: container name
    :type name: str
    """
    input = f"sudo lxc exec {name} -- git clone {FL_REPO} ."
    output = cmd(input)
    return output

def install_pip(name:str):
    input = f"sudo lxc exec {name} -- python -m ensurepip --upgrade"
    output = cmd(input)
    return output

def install_requirements(name:str):
    input = f"sudo lxc exec {name} -- pip install -r requirements.txt"
    output = cmd(input)
    return output


def init_cont_app(name: str):
    out = cmd(f"sudo lxc exec {name} -- bash install_python.sh")


def main():
    args = args_func()

    if args.test:
        pass

    if args.scan:
        save_sys_data()

    if args.build:
        match args.build:
            case "bridges":
                nbr_of_brs = int(
                    input("\nNumber of bridges to create (Default = 1): ").strip()
                    or "1"
                )
                controller = (
                    input(f"\nController (Default = {CONTROLLER}): ").strip()
                    or CONTROLLER
                )
                hostname = get_hostname()
                create_brs_in_host(
                    hostname=hostname, br_nbr=nbr_of_brs, controller=controller
                )
            case "containers":
                conts_ids_str = input(
                    "\nProvide a list of container IDs to use (e.g.: 1,2,3,...): "
                ).strip()
                cont_ids_tokens = conts_ids_str.split(",")
                cont_ids_int = [int(id.strip()) for id in cont_ids_tokens]
                target_br = input("\nOVS bridge that connects containers: ").strip()
                vlan = input("\nVLAN: ").strip()
                create_conts_for_br(br=target_br, cont_ids=cont_ids_int, vlan=vlan)

            case "vxlans":
                vlan = input("\nProvide the network VLAN: ").strip()
                ovs_br = input("\nProvide OVS bridge: ").strip()
                net_ips = net_hosts_ips(vlan)
                create_vxlans(br=ovs_br, ips=net_ips)

            case "qos":
                port = input("\nProvide the egress port: ").strip()
                default_rate = input("\nDefault traffic rate (bps): ").strip()
                create_qos(port, default_rate)

            case "queues":
                q_rates = input(
                    "\nProvide queue rates in bps (e.g.: 10000000,20000000,...): "
                ).strip()
                q_rates = q_rates.split(",")
                qos = input("\nProvide QoS ID: ").strip()
                create_queues(q_rates, qos)
    if args.deploy:
        conts = get_container_names()
        for cont in conts:
            clone_to_container(cont)
            install_pip(cont)
            install_requirements(cont)


if __name__ == "__main__":
    main()
