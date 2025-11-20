"""
this module contains helper functions that perform various small tasks
"""

import os
import csv
import subprocess
import signal
from typing import Callable
from datetime import datetime


TIME = datetime.now().strftime("%d-%m-%Y_%Hh-%Mm")
DFLT_LOG_PATH = f"logs/{TIME}.txt"


def save_to_csv(path: str, data: list[list], headers: list[str]):
    """
    create new directory if it doesn't exist.
    create file if it doesn't exist.
    append data rows to csv file.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        for row in data:
            writer.writerow(row)


def load_csv_data(path: str):
    """
    read data from csv in path.
    return as list of lists.
    """
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


### Note: ssh tunneling from desktop machines to gateway to make http requests is possible!!!
