"""
this module contains helper functions that perform various small tasks
"""

import os
import csv
import subprocess
import signal
from typing import Callable, Literal
from datetime import datetime
import re
import json


TIME = datetime.now().strftime("%d-%m-%Y_%Hh-%Mm")
DFLT_LOG_PATH = f"logs/{TIME}.txt"
SYS_DATA = "sys_data.json"


def file_exists(path: str):
    """
    create path directory if it doesn't exist.
    check if path file exists or not. return true if exists, false otherwise.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_exists = os.path.exists(path)
    return file_exists


def save_to_csv(path: str, data: list[list], headers: list[str]):
    """
    create new directory if it doesn't exist.
    create file if it doesn't exist.
    append data rows to csv file.
    """
    f_exists = file_exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if not f_exists:
            writer.writerow(headers)
        for row in data:
            writer.writerow(row)


def load_csv_data(path: str):
    """
    read data from csv in path.
    return as list of lists.
    """
    f_exists = file_exists(path)
    data = []
    if f_exists:
        with open(path, "r", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                data.append(row)
            return data
    else:
        return "Specified path does not exist"


def cmd(input: str) -> str:
    """
    take input and run as a command. return output.
    """
    proc = proc = subprocess.Popen(
        input, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, text=True
    )
    out, _ = proc.communicate()
    return out


def timeout_error():
    raise Exception("No output")


def timeout_handler(func: Callable, duration: int = 10):
    """
    timeout functionality for performing tasks.
    """
    print("starting...")
    signal.signal(signal.SIGALRM, timeout_error)
    signal.alarm(duration)
    try:
        func
    except Exception as e:
        print(e)


def parse_output(out: str) -> list[list[str]]:
    """
    take output as lines of string. return as tokenized lists.
    """
    lines = out.splitlines()
    result = []
    for l in lines:
        result.append(l.split())
    return result


def save_logs(output: list, path: str = DFLT_LOG_PATH):
    """
    keep a log of operations' output.
    creates a logs directory, txt file, and appends data.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # file_exists = os.path.exists(path)
    with open(path, "a") as file:
        for line in output:
            file.write(line)
        file.write(
            "\n________________________________________________________________________________________________________________________________________________\n"
        )


def copy_file(src: str, dst: str):
    cmd(f"sudo cp {src} {dst}")


def delete_file(path: str):
    if os.path.exists(path):
        os.remove(path)
    else:
        print(f"Error: {path} does not exist")


def is_installed(package: str):
    """
    return True if Linux package is installed.
    return False otherwise.
    """
    out = cmd(f"sudo {package} --version")
    return not ("command not found" in out.lower())


def lxc_cmd(vm_name: str, command: str):
    """
    execute a command inside a given VM or container from the host.
    """
    input = f"sudo lxc exec {vm_name} -- {command}"
    out = cmd(input)
    return out


def get_host_id(mode: Literal["local", "vm"], vm: str = ""):
    """
    get the id number of a host. The rightmost number in a IPv4.
    e.g.: 10.0.200.42 -> host_id = 42
    must provide a virtual-machine name when using vm mode.
    only works if the interface has the pattern: 10.0.<number>.<number>
    """
    host_id = ""
    out = ""
    if mode == "local":
        out = cmd("hostname -I")
    elif mode == "vm":
        out = lxc_cmd(vm, "hostname -I")

    out_ips = out.split(" ")
    ip_pattern = r"^10\.0\.\d{1,3}\.(\d{1,3})$"
    for ip in out_ips:
        match = re.search(ip_pattern, ip)
        if match:
            host_id = match.group(1)

    return host_id


# ========= json helper functions ========= #

def save_json_file(data: json, path: str = SYS_DATA):
    """
    save data into a json file
    """
    # f_exists = file_exists(path)
    with open(path, "w") as f:
        json.dump(data, f, indent=3)


def read_json_file(path: str = SYS_DATA):
    """
    return data from json file for given path.
    """
    with open(path, "r") as f:
        data = json.load(f)
    return data


def search_json_file(
    key: str,
    value: str | int,
    path: str = SYS_DATA,
):
    """
    find a json item = {key: value} in path
    """
    data = read_json_file(path)
    result = next((item for item in data if item[key] == value), None)
    return result


def edit_json_file(key: str, value: str | int, new_item: dict, path: str = SYS_DATA):
    """
    change a json item in path.
    """
    data = read_json_file(path)
    new_data = []
    for item in data:
        if item[key] == value:
            item = new_item
        new_data.append(item)
    save_json_file(data=new_data, path=path)


def del_json_item(key: str, value: str | int, path: str = SYS_DATA):
    """
    remove an item in json file in path.
    """
    data = read_json_file(path)
    new_data = []
    for item in data:
        if item[key] != value:
            new_data.append(item)
    save_json_file(data=new_data, path=path)


### Note: ssh tunneling from desktop machines to gateway to make http requests is possible!!!
