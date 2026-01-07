from utils import *
from containers import *
from bridges import *
from ports import *
from datetime import datetime
from app import *

x = (
    "Excellent M.Sc. degree in Computer Science, Physics or Engineering​\n"
    "Strong motivation to conduct research in generative artificial intelligence in engineering​\n"
    "Interest in multi-objective optimization and machine learning\n"
)

dictio = [
    {"id": 1, "name": "System A", "items": ["br0", "br1", "br2"]},
    {"id": 2, "name": "System B", "items": ["br5"]},
]

# a = get_iface_data("172.24.165.10")
# print(a)
# print(type(a))

out = """
wnouicer24@ICT-PW0J1NWE:~/thesis/lxd-ovs-scripts$ sudo lxc exec cont-2 -- sudo i
perf3 -c 10.0.200.1
Connecting to host 10.0.200.1, port 5201
[  5] local 10.0.200.2 port 35178 connected to 10.0.200.1 port 5201
[ ID] Interval           Transfer     Bitrate         Retr  Cwnd
[  5]   0.00-1.01   sec  5.63 GBytes  48.0 Gbits/sec    2   2.66 MBytes
[  5]   1.01-2.01   sec  5.14 GBytes  44.2 Gbits/sec    0   2.68 MBytes
[  5]   2.01-3.02   sec  5.35 GBytes  45.5 Gbits/sec    0   2.69 MBytes
[  5]   3.02-4.03   sec  5.27 GBytes  44.5 Gbits/sec    0   2.70 MBytes
[  5]   4.03-5.02   sec  5.24 GBytes  45.6 Gbits/sec    0   2.72 MBytes
[  5]   5.02-6.01   sec  5.16 GBytes  44.9 Gbits/sec    2   2.72 MBytes
[  5]   6.01-7.02   sec  5.54 GBytes  46.8 Gbits/sec   46   2.73 MBytes
[  5]   7.02-8.01   sec  5.44 GBytes  47.3 Gbits/sec    1   2.73 MBytes
[  5]   8.01-9.01   sec  5.52 GBytes  47.7 Gbits/sec    0   2.75 MBytes
[  5]   9.01-10.00  sec  5.38 GBytes  46.3 Gbits/sec    0   2.75 MBytes
- - - - - - - - - - - - - - - - - - - - - - - - -
[ ID] Interval           Transfer     Bitrate         Retr
[  5]   0.00-10.00  sec  53.8 GBytes  46.2 Gbits/sec   51             sender
[  5]   0.00-10.00  sec  53.8 GBytes  46.2 Gbits/sec                  receiver

iperf Done.
wnouicer24@ICT-PW0J1NWE:~/thesis/lxd-ovs-scripts$
"""

x = get_vxlan_options("vxlan-1-5")
print(x)
