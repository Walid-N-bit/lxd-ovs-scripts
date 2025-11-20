from containers import *
from utils import *
from bridges import *


def define_bridges(vm_list: list[str], br_nbr: int):
    """
    setup bridges fr each VM.
    naming schema: br-<host_id>-<bridge_id>
        host_id: unique to every host in the network. the right-most number in IPv4
        bridge_id: 0, 1, 2, ...
    """
    input = ""
    brs = []
    
    for vm in vm_list:
        pass
    pass


def define_containers():
    pass


def main():
    pass


if __name__ == "__main__":
    pass
