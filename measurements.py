from utils import *
from typing import Literal
import re
import asyncio
import time

DATA_FIELDS = (
    "start_time",
    "end_time",
    "transfer_amount",
    "transfer_unit",
    "bitrate_value",
    "bitrate_unit",
    "retransmits",
    "congestion_window_value",
    "congestion_window_unit",
)
SESSION = "test_session"


def iperf(mode: Literal["client", "server"], ip: str = "", port: str | int = ""):
    """
    construct iPerf command and return it as a string.

    :param mode: mode of execution
    :type mode: Literal["client", "server"]
    :param port: port for the test. Defaults to 5201 when not assigned.
    :type port: str | int
    :param ip: ip address of the server host.
    :type ip: str
    """
    match mode:
        case "client":
            mode = "-c"

        case "server":
            mode = "-s"

    command = f"sudo iperf3 {mode} {ip} {port}".strip()
    return command


def parse_iperf(iperf_out: str) -> list[tuple]:
    """
    parse the output of an iPerf command.

    :param iperf_out: raw output of an iPerf command
    :type iperf_out: str
    :return: parsed data according to DATA_FIELDS
    :rtype: list[tuple]
    """
    iperf_out = iperf_out.splitlines()
    data = []
    data_pattern = r"\[\s*\d+\]\s+(\d+\.\d+)-(\d+\.\d+)\s+sec\s+([\d.]+)\s+([KMGT]?)Bytes\s+([\d.]+)\s+([KMGT]?)bits/sec\s+(\d+)\s+([\d.]+)\s+([KMGT]?)Bytes"
    for line in iperf_out:
        match = re.search(data_pattern, line)
        if match:
            # --------------------------#
            # match.groups() is a tuple #
            # --------------------------#
            data.append(match.groups())
    return data


def tmux_create_panes():
    """
    create a new tmux session.
    split a window into two panes.
    detach session -> return to terminal.
    """
    cmd(f"tmux new-session -d -n {SESSION}")
    cmd("tmux split-window -v")
    cmd("tmux detach")


def tmux_run_command(pane: int, command: str):
    """
    execute a command on a selected tmux pane.

    :param pane: tmux pane number
    :type pane: int
    :param command: command to be executed on the pane.
    :type command: str
    """
    cmd(f"tmux select-pane -t {pane}")
    cmd(f"tmux send-keys 'clear' Enter")
    input = f"tmux send-keys '{command}' enter"
    output = cmd(input)
    # if there's an error, print it
    if len(output) > 0:
        print(output)


def tmux_capture(pane: int, lines: int):
    """
    capture the output from a selected pane and return it as string.

    :param pane: tmux pane number
    :type pane: int
    :param lines: number of lines captured in the selected pane
    :type lines: int
    """
    input = f"tmux select-pane -t {pane} ; tmux capture-pane -t 1 -p -S -{lines}"
    output = cmd(input)
    return output


def iperf_in_container(container: str):
    """
    check if iPerf is installed in the selected LXD container.
    print messages for each case.

    :param container: container name
    :type container: str
    """
    iperf_is_installed = is_installed(package="iperf3", vm=container)
    if not iperf_is_installed:
        print(
            f"Please install the iPerf tool on {container}.\nCommand: sudo apt install iperf3\n"
        )
        return
    else:
        print(f"iPerf installed on {container}")


def run_iperf_in_container(pane: int, command: str, lines: int = 20, delay: int = 0):
    """
    run shell command in a selected tmux pane.

    :param pane: tmux pane number
    :type pane: int
    :param command: command to be executed
    :type command: str
    :param lines: number of output lines to be captured
    :type lines: int
    :param delay: time delay in seconds between execution and output capture
    :type delay: int
    """
    tmux_run_command(pane, command)
    time.sleep(delay)

    output = tmux_capture(pane, lines)
    return output


def run_iperf_test(client: str, server: str, port: str | int = "") -> list[tuple]:

    iperf_in_container(container=server)
    iperf_in_container(container=client)

    server_id = get_host_id(mode="vm", vm=server)
    server_ip = f"10.0.200.{server_id}"

    server_input = f"sudo lxc exec {server} -- {iperf(mode="server", port=port)}"
    client_input = (
        f"sudo lxc exec {client} -- {iperf(mode="client", ip=server_ip, port=port)}"
    )

    timeout = 12

    tmux_create_panes()
    # pane 0 will be used for the server
    # pane 1 will be used for the client
    print("Starting server")
    server_output = run_iperf_in_container(pane=0, command=server_input)

    print("Starting client")
    client_output = run_iperf_in_container(pane=1, command=client_input, delay=timeout)

    cmd("tmux kill-server")

    return server_output, client_output
