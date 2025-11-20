import pytest
from unittest.mock import patch
from bridges import (
    vsctl_input,
    get_qos_id,
    create_ovs_br,
    manage_port,
    create_vxlan,
    create_qos,
    create_queues,
    QOS,
)

# ===========================
#   vsctl_input()
# ===========================


def test_vsctl_input_single():
    commands = ["add-br br0"]
    expected = ["sudo ovs-vsctl", "add-br br0", "--"]
    assert vsctl_input(commands) == expected


def test_vsctl_input_multiple():
    commands = ["add-br br0", "set-controller br0 tcp:1.2.3.4:6653"]
    out = vsctl_input(commands)

    assert out[0] == "sudo ovs-vsctl"
    assert out[1] == "add-br br0"
    assert out[2] == "--"
    assert out[3] == "set-controller br0 tcp:1.2.3.4:6653"
    assert out[4] == "--"


# ===========================
#   get_qos_id()
# ===========================


@patch("bridges.cmd")
def test_get_qos_id(mock_cmd):
    mock_cmd.return_value = "qos123"
    assert get_qos_id("eth0") == "qos123"
    mock_cmd.assert_called_once_with("sudo ovs-vsctl get port eth0 qos")


# ===========================
#   create_ovs_br()
# ===========================


def test_create_ovs_br():
    out = create_ovs_br("br1", "tcp:10.0.0.1:6653")
    assert out == "add-br br1 -- set-controller br1 tcp:10.0.0.1:6653"


# ===========================
#   manage_port()
# ===========================


def test_manage_port_add():
    assert manage_port("br0", "eth1", "add") == "add-port br0 eth1"


def test_manage_port_set():
    assert manage_port("br0", "eth1", "set") == "set port br0 eth1"


def test_manage_port_delete():
    assert manage_port("br0", "eth1", "del") == "del-port br0 eth1"


# ===========================
#   create_vxlan()
# ===========================


def test_create_vxlan():
    out = create_vxlan("br0", "vx0", "10.0.0.9", key="flow", dst_port=4789)

    # manage_port() should generate:
    assert "add-port br0 vx0" in out
    assert "type=vxlan" in out
    assert "options:remote_ip=10.0.0.9" in out
    assert "options:key=flow" in out
    assert "options:dst_port=4789" in out


# ===========================
#   create_qos()
# ===========================


def test_create_qos():
    out = create_qos("eth2", 100000)
    assert f"set port eth2 qos={QOS}" in out
    assert f"--id={QOS} create qos" in out
    assert "other-config:max-rate=100000" in out


# ===========================
#   create_queues()
# ===========================


def test_create_queues():
    out = create_queues([10000, 20000, 30000])
    parts = out.split(" -- ")

    assert len(parts) == 6  # one per queue

    assert "queues:0=@0" in parts[0]
    assert "other-config:max-rate=10000" in parts[1]

    assert "queues:1=@1" in parts[2]
    assert "other-config:max-rate=20000" in parts[3]

    assert "queues:2=@2" in parts[4]
    assert "other-config:max-rate=30000" in parts[5]
