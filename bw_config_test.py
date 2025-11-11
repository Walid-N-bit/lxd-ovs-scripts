"""
dd if=/dev/zero bs=1000 count=1 | nc localhost 9000
"""

import os
import argparse
import subprocess
import time
import csv
from datetime import datetime
import pandas as pd
import signal
from tabulate import tabulate

INGRESS_RATE = 0  # Kbps
HOST_IP = "10.0.0.1"
DATA_PATH = "ovs_ipr_data"
BANDWIDTH_COLUMNS = [
    "timestamp",
    "host_ip",
    "block_size (bytes)",
    "count",
    "destination_ip",
    "port",
    "duration (s)",
    "throughput (MB/s)",
    "throughput (Mbps)",
    "raw_output",
]

NC_TOUT = 2


def args_fnc():
    parser = argparse.ArgumentParser(description="Automate data collection")
    parser.add_argument(
        "--show", nargs="?", const=True, help="Display the current state of the system"
    )
    parser.add_argument(
        "--test",
        nargs="?",
        const=True,
        help="Perform a bandwidth test by sending packets from src to dst",
    )
    parser.add_argument(
        "--profile",
        nargs="?",
        const=True,
        help="Display available network profiles. Apply a profile",
    )

    args = parser.parse_args()
    return args


########## csv helper functions ##########


def save2csv(path: str, data: list, headers: list[str]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        for row in data:
            writer.writerow(row)


def load_csv_data(path: str):
    file_exists = os.path.exists(path)
    data = []
    if file_exists:
        with open(path, "r", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                data.append(row)
            return data
    else:
        return "Specified path does not exist"


def update_csv(path: str, data: list):
    file_exists = os.path.exists(path)
    if file_exists:
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            for row in writer:
                writer.writerow(row)
    else:
        return "Specified path does not exist"


########## input messages and parser ##########


def input_dd_params():
    """
    request user to input parameters for the dd nc command:
    dd if=/dev/zero bs=<packet_size> count=<pkt_nmbr> | nc <dst_ip> <port>
    the value of <packet_size> is calculated iteratively
    """
    pkt_size = input("Packet size (Bytes): <starting_value> <step_value> <end_value>\n")
    pkt_size = [int(p) for p in pkt_size.split(" ")]
    pkt_nmbr = int(input("Number of packets per request: "))
    dst_ip = input("Destination IPv4: ")
    port = int(input("Port number: "))
    rep = int(input("Repetitions per packet: "))

    return {
        "packet_size": pkt_size,
        "packets_number": pkt_nmbr,
        "dst_ip": dst_ip,
        "port": port,
        "repetitions": rep,
    }

    # return pkt_size, pkt_nmbr, dst_ip, port, rep


def timeout_handler():
    raise Exception("No output")


def get_summary_line(output: str):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(10)
    summary_line = ""
    try:
        for line in output.splitlines():
            if "copied" in line:
                summary_line = line
                return summary_line
    except Exception as e:
        print(e)


def parse_dd_output(output: str):
    """
    take output of dd nc command and return as values
    """
    try:
        parts = output.strip().split(",")
        time_s = float(parts[-2].split()[0])
        mb_s = float(parts[-1].split()[0])
        mbps = mb_s * 8
        return time_s, mb_s, mbps
    except Exception:
        return None, None, None


########## call command and capture output ##########


def cmd(input: str) -> str:
    proc = proc = subprocess.Popen(
        input, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, text=True
    )
    out, _ = proc.communicate()
    return out


########## collect system info ##########


def get_ipv4(device: str) -> str:
    inp = (
        r"ip a show dev "
        + device
        + r" | grep -oP '(?:\b\.?(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){4}' | head -1"
    )
    out = cmd(inp).strip()
    return out


def get_ovs_conf(arg: str):
    """
    calls ovs commands, returns bridges, their interfaces, and their ingress policing policies
    Return:
        data: list[dict]
    """
    vsctl = "sudo ovs-vsctl"
    data = []
    # get all bridges
    brs = cmd(f"{vsctl} list-br").splitlines()
    # get all interfaces per bridge
    for br in brs:
        ifaces = cmd(f"{vsctl} list-ifaces {br}").splitlines()
        for i in ifaces:
            ipr = cmd(f"{vsctl} get interface {i} ingress_policing_rate")
            ipb = cmd(f"{vsctl} get interface {i} ingress_policing_burst")
            data.append(
                {
                    "interface": i,
                    "bridge": br,
                    "ipv4": get_ipv4(i),
                    "ingress_policing_rate": int(ipr),
                    "ingress_policing_burst": int(ipb),
                }
            )
    if arg == True:
        # update the csv data for ovs configuration
        df = pd.DataFrame(data)
        df.to_csv("ovs_config.csv", index=False)
        return data

    elif type(arg) == str:
        row = next((row for row in data if row.get("interface") == arg), None)
        return row


def get_device_ipr_hostname(ip: str):
    """
    look for device with ip passed as param
    return ingress_policing_rate of that device
    """
    ovs_data = get_ovs_conf(True)
    device = next(
        (row.get("interface") for row in ovs_data if row.get("ipv4") == ip), None
    )
    ipr = next(
        (row.get("ingress_policing_rate") for row in ovs_data if row.get("ipv4") == ip),
        None,
    )
    hostname = cmd("hostname").split(".")[0]
    return device, ipr, hostname


########## send dd nc packets ##########


def packet_nbr_msg(packets: list):
    """
    compute the total number of packets to be sent
    input: [start, step, end]
    """
    pkt_nbr = int((packets[2] - packets[0]) / packets[1])
    seconds = pkt_nbr * (NC_TOUT + 1)
    minutes, sec = divmod(seconds, 60)
    h, mins = divmod(minutes, 60)
    print("_____________________________________\n\n")
    print(f"===== Sending {pkt_nbr} packets =====\n\n")
    print(f"______ ETA = {h}h {mins}m {sec}s ______\n\n")


def perform_test(inputs: dict):
    """
    take parameters for the command and iteratively send packets
    dd if=/dev/zero bs=<packet_size> count=<pkt_nmbr> | nc <dst_ip> <port>
    ------------------------------------------
    input:
    {
        "packet_size": [start step end],
        "packets_number": int,
        "dst_ip": str,
        "port": int,
        "repetitions": int,
    }
    """

    start = inputs.get("packet_size")[0]
    step = inputs.get("packet_size")[1]
    end = inputs.get("packet_size")[2] + 1
    count = inputs.get("packets_number")
    dst_ip = inputs.get("dst_ip")
    port = inputs.get("port")
    repetitions = inputs.get("repetitions")
    packet_nbr_msg([start, step, end])

    start_time = datetime.now()

    for size in range(start, end, step):
        for _ in range(repetitions):
            data_row = []
            inp = f"dd if=/dev/zero bs={size} count={count} | nc -q {NC_TOUT} {dst_ip} {port}"
            out = cmd(inp)

            # get the last line in the dd nc output
            summary_line = get_summary_line(out)
            signal.alarm(0)  # cancel timeout alarm

            duration, mb_s, mbps = parse_dd_output(summary_line)

            # save to csv
            data_row.append(
                [
                    datetime.now().isoformat(),
                    HOST_IP,
                    size,
                    count,
                    dst_ip,
                    port,
                    duration,
                    mb_s,
                    mbps,
                    summary_line,
                ]
            )

            path = "/".join(
                [
                    DATA_PATH,
                    f"{get_device_ipr_hostname(HOST_IP)[2]}",
                    f"{get_device_ipr_hostname(HOST_IP)[0]}_ipr_{get_device_ipr_hostname(HOST_IP)[1]}.csv",
                ]
            )
            save2csv(path=path, data=data_row, headers=BANDWIDTH_COLUMNS)

            print(f"-> {size} bytes: {mbps or 'N/A'} Mbps ({summary_line})")
            # time.sleep(1)
    # message at the end
    end_time = datetime.now()
    print(f"\n====== Data saved in {path} ======\n")
    print(f"\n________ Elapsed time: {end_time - start_time} ________\n")


########### profiles ###########


def show_profiles():
    print("under construction")


def save_profile():
    pass


def apply_profile():
    pass


########### main ###########


def main():
    args = args_fnc()
    if args.show:
        conf_data = get_ovs_conf(args.show)
        print(tabulate(conf_data, headers="keys"))
    elif args.test:
        inputs = input_dd_params()
        perform_test(inputs)
    elif args.profile:
        show_profiles()
    else:
        print("you must include at least one positional argument")


if __name__ == "__main__":
    main()
