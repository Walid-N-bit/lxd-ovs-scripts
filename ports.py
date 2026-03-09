from utils import *

VSCTL = "sudo ovs-vsctl"
QOS = "@newquos"
QUEUE = "@newq-"

QOS_TAGS = "sys_data/qos_tags.json"

# ----------------------- #
# ports related functions #
# ----------------------- #


def get_ports(br: str) -> list[str]:
    """
    get a list of all ports connected to a given OVS bridge

    :param br: OVS bridge name
    :type br: str
    :return: list of ports connected to br
    :rtype: list[str]
    """
    input = f"sudo ovs-vsctl list-ports {br}"
    output = cmd(input).splitlines()
    return output


def get_ifaces(br: str):
    """
    get a list of all interfaces connected to a given OVS bridge

    :param br: OVS bridge name
    :type br: str
    :return: list of interfaces connected to br
    :rtype: list[str]
    """
    input = f"sudo ovs-vsctl list-ifaces {br}"
    output = cmd(input).splitlines()
    return output


# ----------------------- #
# vxlan related functions #
# ----------------------- #


def add_vxlan(
    br: str, port: str, remote_ip: str, key: str = "flow", dst_port: int = 4789
):
    """
    return command string for creating a vxlan between two hosts for given bridge.
    naming schema: vxlan-<host_a_id>-<host_b_id>
    """
    port_cmd = f"{VSCTL} add-port {br} {port}"
    input = f"{port_cmd} -- set interface {port} type=vxlan options:remote_ip={remote_ip} options:key={key} options:dst_port={dst_port}"
    return input


def create_vxlans(br: str, ips: list[str]):
    """
    create vxlans between local and remote hosts.

    :param br: local targeted bridge
    :type br: str
    :param ips: list of
    :type ips: list[str]
    """
    this_host_id = get_host_id(mode="local")
    this_host_ips = get_ipv4s()
    # remove self ipv4
    for ip in this_host_ips:
        if ip in ips:
            ips.remove(ip)

    targets_ids = [(ip, id_from_ipv4(ip)) for ip in ips]
    vxlans = []
    for id in targets_ids:
        name = f"vxlan-{this_host_id}-{id[1]}"
        vxlans.append((name, id[0]))

    for vxlan in vxlans:
        inp = add_vxlan(
            br,
            port=vxlan[0],
            remote_ip=vxlan[1],
        )
        out = cmd(inp)
        print(out)


def get_vxlans() -> list[str]:
    """
    get all vxlans in the host

    :return: list of vxlan interfaces
    :rtype: list[str]
    """
    input = "sudo ovs-vsctl --format=csv --columns=name --no-headings find interface type=vxlan"
    output = cmd(input).splitlines()
    return output


def get_vxlan_options(vxlan: str) -> dict[dict]:
    """
    get options of the given vxlan.
    options include: remote ip, key, destination port.

    :param vxlan: vxlan name
    :type vxlan: str
    :return: options object
    :rtype: dict
    """
    input = f"sudo ovs-vsctl --format=json --pretty --columns=options find interface name={vxlan}"
    # the output here in json format
    output = cmd(input)
    output = json.loads(output)
    options_list = output.get("data", [])[0][0][1]
    options = dict(name=vxlan, options=dict(options_list))
    return options


# --------------------- #
# QoS related functions #
# --------------------- #


def create_qos(port: str, default_rate: int):
    """
    creates new QoS object with a set default rate-limit for an ovs port.
    """
    input = f"{VSCTL} set port {port} qos={QOS} -- --id={QOS} create qos type=linux-htb other-config:max-rate={default_rate}"
    out = cmd(input)
    return out


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

    inp = f"{VSCTL} set qos {qos} {in_1_join} -- {in_2_join}"
    out = cmd(inp)
    return out


# This function is not really useful with ONOS #
def add_queue_of(br: str, in_port: int, queue: str):
    """
    add queue to openflow table.
    """
    input = f"sudo ovs-ofctl add-flow {br} in_port={in_port},actions=set_queue:{queue},normal"
    return input


# -------------------------------------------- #


def get_all_qos() -> list:
    """
    Execute command to get all QoS objects on the host.

    :return: list of all QoS uuids
    :rtype: list
    """
    input = "sudo ovs-vsctl --column=_uuid --format=csv --no-headings list qos"
    output = cmd(input).splitlines()
    return output


def get_qos_queues(qos_id: str, raw_output: bool = False) -> str | list[dict]:
    """
    return the Queues attached to a given QoS object.

    :param qos_id: uuid of a QoS object
    :type qos_id: str
    :param raw_output: return the raw command output
    :type raw_output: bool
    :return: queues attached to the QoS (queue number, queue uuid, max rate)
    :rtype: str | list[dict]
    """
    input = f"sudo ovs-vsctl --format=json --columns=queues list QoS {qos_id}"
    output = cmd(input)
    output_list = json.loads(output).get("data")[0][0][1]
    parsed_output = []
    for item in output_list:
        new_item = dict(
            number=item[0], id=item[1][1], max_rate=get_queue_rate(item[1][1])
        )
        parsed_output.append(new_item)
    if raw_output:
        return output
    else:
        return parsed_output


def get_qos_default_rate(qos_id: str) -> int:
    """
    get the default (max) rate of the selected QoS object.

    :param qos_id: uuid of the QoS object
    :type qos_id: str
    :return: default rate
    :rtype: int
    """
    input = f"sudo ovs-vsctl get QoS {qos_id} other_config:max-rate"
    output = cmd(input).strip()
    return int(output.strip('"'))


def get_qos_ports(qos_id: str) -> list:
    """
    get the OVS ports that use the given QoS object.

    :param qos_id: uuid of the QoS object
    :type qos_id: str
    :return: list of OVS ports
    :rtype: list
    """
    input = f"sudo ovs-vsctl --columns=name --format=csv --no-headings find port qos={qos_id}"
    output = cmd(input).splitlines()
    return output


def tag_qos(qos_id: str):
    """
    add a tag (short description) for the given QoS object.
    save to a json file.

    :param qos_id: uuid of the QoS object
    :type qos_id: str
    """
    tag = input(f"Add a tag to QoS {qos_id}: ").strip() or ""
    item = {"qos_id": qos_id, "tag": tag}
    update_json_file(key="qos_id", value=qos_id, new_item=item, path=QOS_TAGS)


def get_qos_tag(qos_id: str) -> str:
    """
    get the saved tag for a given QoS object.

    :param qos_id: uuid of the QoS object
    :type qos_id: str
    :return: QoS tag
    :rtype: str
    """
    item = search_json_file(key="qos_id", value=qos_id, path=QOS_TAGS) or {}
    return item.get("tag") or ""


def get_queue_rate(queue_id: str):
    """
    get the max rate of a given Queue.

    :param queue_id: uuid of the Queue
    :type queue_id: str
    """
    input = (
        f"sudo ovs-vsctl --format=csv --bare get queue {queue_id} other_config:max-rate"
    )
    output = cmd(input).strip().strip('"')
    return int(output)
