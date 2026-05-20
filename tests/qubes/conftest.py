import subprocess
import sys
import uuid

import pytest
import qubesadmin
from qubesadmin.utils import vm_dependencies

sys.path.append("/usr/share/ansible/collections")

from tests.qubes.ansible_test_utils import (
    AnsibleFailJson,
    run_module_qubesos_core_qube_main as run_module,
)
from pathlib import Path
from typing import List


DEBIAN_TEMPLATE = "debian-12-minimal"
PLUGIN_PATH = Path(__file__).parent / "plugins" / "modules"


@pytest.fixture(scope="function")
def qubes():
    """Return a Qubes app instance"""
    try:
        return qubesadmin.Qubes()
    except Exception as e:
        pytest.skip(f"Qubes API not available: {e}")


@pytest.fixture(scope="function")
def vmname():
    """Generate a random VM name for testing"""
    return f"test-vm-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def vm(qubes, request):
    """Generate a VM with default configurations"""
    vmname = f"test-vm-{uuid.uuid4().hex[:8]}"
    run_module({"state": "present", "name": vmname})
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def minimalvm(qubes, request):
    vmname = f"test-minimalvm-{uuid.uuid4().hex[:8]}"
    run_module(
        {"state": "present", "name": vmname, "template": DEBIAN_TEMPLATE}
    )
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def netvm(qubes, request):
    vmname = f"test-netvm-{uuid.uuid4().hex[:8]}"
    run_module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"provides_network": True},
        }
    )
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def audiovm(qubes, request):
    vmname = f"test-audiovm-{uuid.uuid4().hex[:8]}"
    run_module({"state": "present", "name": vmname})
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def guivm(qubes, request):
    vmname = f"test-guivm-{uuid.uuid4().hex[:8]}"
    run_module({"state": "present", "name": vmname})
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def managementdvm(qubes, request):
    vmname = f"test-mdvm-{uuid.uuid4().hex[:8]}"
    run_module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"template_for_dispvms": True},
        }
    )
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(autouse=True)
def cleanup_vm(qubes, request):
    """Ensure any test VM is removed after test, breaking dependencies first."""
    created = []

    def mark(name):
        created.append(name)

    # allow tests to call request.node.mark_vm_created(vmname)
    request.node.mark_vm_created = mark

    yield

    # teardown: for each VM we created, first clear any references, then remove it
    for name in created:
        # break inter-VM references
        try:
            deps = vm_dependencies(qubes, name)
        except Exception:
            deps = []

        for holder, prop_name in deps:
            # skip global qubes properties
            if holder is None:
                continue

            # get current value
            current = getattr(holder, prop_name, None)

            # if it's a list, remove our VM name from it
            if isinstance(current, list):
                if name in current:
                    current.remove(name)
                    setattr(holder, prop_name, current)

            # otherwise, just null it out
            else:
                setattr(holder, prop_name, None)

        # now remove the VM itself
        try:
            run_module({"state": "absent", "name": name})
        except AnsibleFailJson:
            pass


@pytest.fixture
def latest_net_ports(qubes):
    # Collect all net‐class PCI port_ids from dom0
    # See fepitre/qubes-g2g-continuous-integration
    ports = [
        f"pci:dom0:{dev.port_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p02")
    ]
    assert len(ports) >= 2, "Need at least two PCI net devices for these tests"
    return ports


@pytest.fixture
def block_device():
    # Assume the block device under test is always present
    # See fepitre/qubes-g2g-continuous-integration
    return "block:dom0:vdb"


@pytest.fixture
def run_playbook(tmp_path, ansible_config):
    """
    Helper to write a playbook and execute it with ansible-playbook.
    """

    ansible_config_path = Path(__file__).parent.parent / f"{ansible_config}.cfg"
    assert ansible_config_path.is_file()

    def _run(playbook_content: List[dict], vms: List[str] = []):
        # Create playbook file
        pb_file = tmp_path / "playbook.yml"
        import yaml

        pb_file.write_text(yaml.dump(playbook_content))
        # Run ansible-playbook
        cmd = [
            "ansible-playbook",
            "-i",
            f"localhost,dom0,{','.join(vms)}",
            "-c",
            "local",
            "-M",
            str(PLUGIN_PATH),
            str(pb_file),
        ]
        result = subprocess.run(
            cmd,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"ANSIBLE_CONFIG": str(ansible_config_path)},
        )
        return result

    return _run
