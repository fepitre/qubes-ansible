import subprocess
import uuid
import json
import pytest

from conftest import PLUGIN_PATH


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy", "ansible_proxy_strategy_legacy"],
)
@pytest.mark.parametrize(
    "target_host",
    ["localhost", "dom0"],
)
def test_create_and_destroy_vm(run_playbook, request, target_host):
    name = f"test-vm-{uuid.uuid4().hex[:6]}"
    request.node.mark_vm_created(name)

    playbook = [
        {
            "hosts": target_host,
            "tasks": [
                {
                    "name": "Create AppVM",
                    "qubesos": {
                        "name": name,
                        "command": "create",
                        "vmtype": "AppVM",
                    },
                },
                {
                    "name": "Start AppVM",
                    "qubesos": {
                        "name": name,
                        "command": "start",
                    },
                },
                {
                    "name": "Destroy AppVM",
                    "qubesos": {"name": name, "command": "destroy"},
                },
                {
                    "name": "Remove AppVM",
                    "qubesos": {"name": name, "command": "remove"},
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    # Playbook should run successfully
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy", "ansible_proxy_strategy_legacy"],
)
@pytest.mark.parametrize(
    "target_host",
    ["localhost", "dom0"],
)
def test_properties_and_tags_playbook(run_playbook, request, target_host):
    name = f"test-vm-{uuid.uuid4().hex[:6]}"
    request.node.mark_vm_created(name)

    playbook = [
        {
            "hosts": target_host,
            "tasks": [
                {
                    "name": "Create VM with properties",
                    "qubesos": {
                        "name": name,
                        "state": "present",
                        "properties": {"autostart": True, "memory": 128},
                        "tags": ["tag1", "tag2"],
                    },
                },
                {
                    "name": "Validate VM state",
                    "qubesos": {"name": name, "command": "status"},
                },
                {
                    "name": "Cleanup",
                    "qubesos": {"name": name, "state": "absent"},
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr

    # Ensure properties and tags were applied
    run_output = json.loads(result.stdout)
    assert run_output["plays"][0]["tasks"][1]["hosts"][target_host][
        "changed"
    ], result.stdout
    assert {"tag1", "tag2"} == set(
        run_output["plays"][0]["tasks"][1]["hosts"][target_host].get(
            "Tags updated", []
        )
    ), result.stdout


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy", "ansible_proxy_strategy_legacy"],
)
@pytest.mark.parametrize(
    "target_host",
    ["localhost", "dom0"],
)
def test_inventory_playbook(run_playbook, tmp_path, qubes, target_host):
    # Generate inventory via playbook
    playbook = [
        {
            "hosts": target_host,
            "tasks": [
                {
                    "name": "Create inventory",
                    "qubesos": {"command": "createinventory"},
                }
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr

    # Check inventory file exists
    inv_file = tmp_path / "inventory"
    assert inv_file.exists()
    content = inv_file.read_text()

    # Should contain at least one VM entry under [appvms]
    assert "[appvms]" in content

    # Compare with qubes.domains data
    for vm in qubes.domains.values():
        if vm.name != "dom0" and vm.klass == "AppVM":
            assert vm.name in content


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy", "ansible_proxy_strategy_legacy"],
)
def test_vm_connection(vm, run_playbook, ansible_config):
    play_attrs = {
        "hosts": vm.name,
        "gather_facts": False,
        "connection": "qubes",
    }

    default_user_playbook = [
        {
            **play_attrs,
            "tasks": [
                {
                    "name": "Default VM user is 'user'",
                    "ansible.builtin.command": "whoami",
                    "register": "default_result",
                    "failed_when": "default_result.stdout != 'user'",
                },
            ],
        },
    ]

    default_user_result = run_playbook(default_user_playbook, vms=[vm.name])
    assert default_user_result.returncode == 0, default_user_result.stdout

    connect_user_playbook = [
        {
            **play_attrs,
            "remote_user": "user",
            "tasks": [
                {
                    "name": "VM user with 'remote_user: user' is 'user'",
                    "ansible.builtin.command": "whoami",
                    "register": "user_result",
                    "failed_when": "user_result.stdout != 'user'",
                },
            ],
        },
    ]

    connect_user_result = run_playbook(connect_user_playbook, vms=[vm.name])
    assert connect_user_result.returncode == 0, connect_user_result.stdout

    connect_root_playbook = [
        {
            **play_attrs,
            "remote_user": "root",
            "tasks": [
                {
                    "name": "VM user with 'remote_user: root' is 'root'",
                    "ansible.builtin.command": "whoami",
                    "register": "root_result",
                    "failed_when": "root_result.stdout != 'root'",
                },
            ],
        },
    ]

    connect_root_result = run_playbook(connect_root_playbook, vms=[vm.name])
    assert connect_root_result.returncode == 0, connect_root_result.stdout

    become_playbook = [
        {
            **play_attrs,
            "become": True,
            "tasks": [
                {
                    "name": "VM user with 'become: true' is 'root'",
                    "ansible.builtin.command": "whoami",
                    "register": "become_result",
                    "failed_when": "become_result.stdout != 'root'",
                },
            ],
        },
    ]

    become_result = run_playbook(become_playbook, vms=[vm.name])
    assert become_result.returncode == 0, become_result.returncode

    invalid_user = "somebody"
    invalid_user_playbook = [
        {
            **play_attrs,
            "remote_user": invalid_user,
            "tasks": [
                {
                    "name": "No-op",
                    "ansible.builtin.command": "true",
                },
            ],
        },
    ]

    invalid_user_result = run_playbook(invalid_user_playbook, vms=[vm.name])
    assert invalid_user_result.returncode == 2, invalid_user_result.stdout

    if ansible_config == "ansible_linear_strategy":
        invalid_user_output = json.loads(invalid_user_result.stdout)
        assert (
            invalid_user_output["plays"][0]["tasks"][0]["hosts"][vm.name]["msg"]
            == f'Invalid value "{invalid_user}" for configuration option "plugin_type: connection plugin: qubes setting: remote_user ", valid values are: user, root'
        ), invalid_user_result.stdout
    else:
        assert (
            f'Invalid value \\"{invalid_user}\\" for configuration option \\"plugin_type: connection plugin: qubes setting: remote_user \\", valid values are: user, root'
            in invalid_user_result.stdout
        )


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy", "ansible_proxy_strategy_legacy"],
)
def test_minimalvm_connection(minimalvm, run_playbook, ansible_config):
    play_attrs = {
        "hosts": minimalvm.name,
        "gather_facts": False,
        "connection": "qubes",
    }

    default_user_playbook = [
        {
            **play_attrs,
            "tasks": [
                {
                    "name": "Default minimal VM user is 'user'",
                    "ansible.builtin.command": "whoami",
                    "register": "default_result",
                    "failed_when": "default_result.stdout != 'user'",
                },
            ],
        },
    ]

    default_user_result = run_playbook(
        default_user_playbook, vms=[minimalvm.name]
    )
    assert default_user_result.returncode == 0, default_user_result.stdout

    connect_user_playbook = [
        {
            **play_attrs,
            "remote_user": "user",
            "tasks": [
                {
                    "name": "Minimal VM user with 'remote_user: user' is 'user'",
                    "ansible.builtin.command": "whoami",
                    "register": "user_result",
                    "failed_when": "user_result.stdout != 'user'",
                },
            ],
        },
    ]

    connect_user_result = run_playbook(
        connect_user_playbook, vms=[minimalvm.name]
    )
    assert connect_user_result.returncode == 0, connect_user_result.stdout

    connect_root_playbook = [
        {
            **play_attrs,
            "remote_user": "root",
            "tasks": [
                {
                    "name": "Minimal VM user with 'remote_user: root' is 'root'",
                    "ansible.builtin.command": "whoami",
                    "register": "root_result",
                    "failed_when": "root_result.stdout != 'root'",
                },
            ],
        },
    ]

    connect_root_result = run_playbook(
        connect_root_playbook, vms=[minimalvm.name]
    )
    assert connect_root_result.returncode == 0, connect_root_result.stdout

    become_playbook = [
        {
            **play_attrs,
            "become": True,
            "tasks": [
                {
                    "name": "No-op",
                    "ansible.builtin.command": "true",
                },
            ],
        },
    ]

    become_result = run_playbook(become_playbook, vms=[minimalvm.name])
    # Playbook should fail because "become" isn't possibile on unmodified minimal vms.
    assert become_result.returncode == 2, become_result.stdout

    if ansible_config == "ansible_linear_strategy":
        become_output = json.loads(become_result.stdout)
        become_module_result = become_output["plays"][0]["tasks"][0]["hosts"][
            minimalvm.name
        ]
        assert become_module_result["failed"], become_result.stdout
        assert become_module_result["rc"] == 1, become_result.stdout
        assert (
            become_module_result["module_stderr"].rstrip()
            == "sudo: a password is required"
        ), become_result.stdout
    else:
        assert "sudo: a password is required" in become_result.stdout


def test_ansible_doc_qubesos_module():

    cmd = ["ansible-doc", "-M", str(PLUGIN_PATH), "qubesos"]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert (
        result.returncode == 0
    ), f"ansible-doc failed with stderr: {result.stderr}"

    # Should contain expected module information
    assert (
        "> QUBESOS" in result.stdout
    ), "Documentation should mention the module name"


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy", "ansible_proxy_strategy_legacy"],
)
def test_state_absent_when_vm_does_not_exist(run_playbook):
    playbook = [
        {
            "hosts": "localhost",
            "tasks": [
                {
                    "name": "Ensure VM doesn't exist",
                    "qubesos": {"state": "absent", "name": "not_existing_vm"},
                }
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert not output["plays"][0]["tasks"][1]["hosts"]["localhost"]["changed"]


@pytest.mark.parametrize(
    "ansible_config",
    [
        "ansible_linear_strategy",
    ],
)
def test_devices_assignment(
    vm, run_playbook, latest_net_ports, ansible_config, qubes
):
    port = latest_net_ports[0]

    default_user_playbook = [
        {
            "hosts": vm.name,
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Assign PCI device",
                    "qubesos": {
                        "name": vm.name,
                        "state": "present",
                        "devices": {
                            "strategy": "strict",
                            "items": [port],
                        },
                    },
                },
            ],
        },
    ]

    res = run_playbook(default_user_playbook, vms=[vm.name])
    assert res.returncode == 0, res.stdout

    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vm.name].devices["pci"].get_assigned_devices()
    ports_assigned = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in assigned
    ]
    assert ports_assigned == [port]
