import os
import subprocess
import uuid
from typing import List

import pytest
from pathlib import Path

PLUGIN_PATH = Path(__file__).parent / "plugins" / "modules"


@pytest.fixture
def run_playbook(tmp_path):
    """
    Helper to write a playbook and execute it with ansible-playbook.
    """

    def _run(playbook_content: List[dict]):
        # Create playbook file
        pb_file = tmp_path / "playbook.yml"
        import yaml

        pb_file.write_text(yaml.dump(playbook_content))
        # Run ansible-playbook
        cmd = [
            "ansible-playbook",
            "-vvv",
            "-i",
            "localhost,",
            "-c",
            "local",
            "-M",
            str(PLUGIN_PATH),
            str(pb_file),
        ]
        result = subprocess.run(
            cmd, cwd=tmp_path, capture_output=True, text=True
        )
        return result

    return _run


def test_create_and_destroy_vm(run_playbook, request):
    name = f"test-vm-{uuid.uuid4().hex[:6]}"
    request.node.mark_vm_created(name)

    playbook = [
        {
            "hosts": "localhost",
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


def test_properties_and_tags_playbook(run_playbook, request):
    name = f"test-vm-{uuid.uuid4().hex[:6]}"
    request.node.mark_vm_created(name)

    playbook = [
        {
            "hosts": "localhost",
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
    assert "changed=" in result.stdout
    assert "tag1" in result.stdout and "tag2" in result.stdout


def test_inventory_playbook(run_playbook, tmp_path, qubes):
    # Generate inventory via playbook
    playbook = [
        {
            "hosts": "localhost",
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
