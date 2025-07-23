import os
import time

from plugins.modules.qubesos import core, VIRT_SUCCESS, VIRT_FAILED
from tests.qubes.conftest import qubes, vmname, Module


def test_lifecycle_full_create_start_shutdown_remove(qubes, vmname, request):

    request.node.mark_vm_created(vmname)

    # Create
    rc, _ = core(
        Module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    )
    assert rc == VIRT_SUCCESS
    assert vmname in qubes.domains

    # Start
    rc, _ = core(Module({"command": "start", "name": vmname}))
    assert rc == VIRT_SUCCESS
    vm = qubes.domains[vmname]
    assert vm.is_running()

    # Shutdown
    rc, _ = core(Module({"command": "shutdown", "name": vmname}))
    assert rc == VIRT_SUCCESS
    time.sleep(5)
    assert vm.is_halted()

    # Remove
    rc, _ = core(Module({"command": "remove", "name": vmname}))
    assert rc == VIRT_SUCCESS
    qubes.domains.refresh_cache(force=True)
    assert vmname not in qubes.domains


def test_lifecycle_create_and_absent(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create
    rc, _ = core(
        Module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    )
    assert rc == VIRT_SUCCESS
    assert vmname in qubes.domains

    # Absent
    rc, _ = core(Module({"state": "absent", "name": vmname}))
    assert rc == VIRT_SUCCESS
    qubes.domains.refresh_cache(force=True)
    assert vmname not in qubes.domains


def test_lifecycle_pause_and_resume(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    core(Module({"command": "create", "name": vmname, "vmtype": "AppVM"}))
    core(Module({"command": "start", "name": vmname}))
    time.sleep(1)

    rc, _ = core(Module({"command": "pause", "name": vmname}))
    assert rc == VIRT_SUCCESS
    assert qubes.domains[vmname].is_paused()

    rc, _ = core(Module({"command": "unpause", "name": vmname}))
    assert rc == VIRT_SUCCESS
    assert qubes.domains[vmname].is_running()

    # Clean up
    core(Module({"command": "destroy", "name": vmname}))
    core(Module({"state": "absent", "name": vmname}))


def test_lifecycle_status_reporting(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    core(Module({"command": "create", "name": vmname, "vmtype": "AppVM"}))
    rc, state = core(Module({"command": "status", "name": vmname}))
    assert rc == VIRT_SUCCESS
    assert state["status"] == "shutdown"

    core(Module({"command": "start", "name": vmname}))
    rc, state = core(Module({"command": "status", "name": vmname}))
    assert state["status"] == "running"

    core(Module({"command": "destroy", "name": vmname}))
    rc, state = core(Module({"command": "status", "name": vmname}))
    assert state["status"] == "shutdown"

    core(Module({"state": "absent", "name": vmname}))


def test_volumes_list_for_standalonevm(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create StandaloneVM
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "vmtype": "StandaloneVM",
                "template": "debian-12-xfce",
                "properties": {
                    "volumes": [
                        {"name": "root", "size": 32212254720},
                        {"name": "private", "size": 10737418240},
                    ]
                },
            }
        )
    )
    assert rc == VIRT_SUCCESS
    vm = qubes.domains[vmname]
    assert vm.klass == "StandaloneVM"
    assert vm.volumes["root"].size == 32212254720
    assert vm.volumes["private"].size == 10737418240

    # Resize root
    rc2, res2 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {
                    "volumes": [{"name": "root", "size": 42949672960}]
                },
            }
        )
    )
    assert rc2 == VIRT_SUCCESS
    assert "volume:root" in res2.get("Properties updated", [])
    assert vm.volumes["root"].size == 42949672960


def test_inventory_generation_and_grouping(tmp_path, qubes):
    # Use a temporary directory for inventory
    os.chdir(tmp_path)

    # Create a standalone VM (by default we don't have any)
    core(
        Module(
            {
                "command": "create",
                "name": "teststandalone",
                "vmtype": "StandaloneVM",
                "template": "debian-12-xfce",
            }
        )
    )

    # Collect expected VMs by class
    expected = {}
    for vm in qubes.domains.values():
        if vm.name == "dom0":
            continue
        expected.setdefault(vm.klass, []).append(vm.name)

    # Run createinventory
    rc, res = core(Module({"command": "createinventory"}))
    assert rc == VIRT_SUCCESS
    assert res["status"] == "successful"

    inv_file = tmp_path / "inventory"
    assert inv_file.exists()
    lines = inv_file.read_text().splitlines()

    # Helper to extract section values
    def section(name):
        start = lines.index(f"[{name}]") + 1
        # find next section header
        for i, line in enumerate(lines[start:], start=start):
            if line.startswith("["):
                end = i
                break
        else:
            end = len(lines)
        return [l for l in lines[start:end] if l.strip()]

    appvms = section("appvms")
    templatevms = section("templatevms")
    standalonevms = section("standalonevms")

    assert set(appvms) == set(expected.get("AppVM", []))
    assert set(templatevms) == set(expected.get("TemplateVM", []))
    assert set(standalonevms) == set(expected.get("StandaloneVM", []))


def test_properties_set_and_tag_vm(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {"autostart": True, "debug": True, "memory": 256}
    tags = ["tag1", "tag2"]
    params = {
        "state": "present",
        "name": vmname,
        "properties": props,
        "tags": tags,
    }
    rc, res = core(Module(params))
    assert rc == VIRT_SUCCESS
    changed_values = res["Properties updated"]
    assert "autostart" in changed_values
    assert qubes.domains[vmname].autostart is True
    for t in tags:
        assert t in qubes.domains[vmname].tags


def test_properties_invalid_key(qubes):
    # Unknown property should fail
    rc, res = core(
        Module(
            {"state": "present", "name": "dom0", "properties": {"titi": "toto"}}
        )
    )
    assert rc == VIRT_FAILED
    assert "Invalid property" in res


def test_properties_invalid_type(qubes, vmname, request):
    # Wrong type for memory
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"memory": "toto"},
            }
        )
    )
    assert rc == VIRT_FAILED
    assert "Invalid property value type" in res


def test_properties_missing_netvm(qubes, vmname, request):
    # netvm does not exist
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"netvm": "toto"},
            }
        )
    )
    assert rc == VIRT_FAILED
    assert "Missing netvm" in res


def test_properties_reset_to_default_netvm(qubes, vm, netvm, request):
    """
    Able to reset back to default netvm without needing to mention it by name
    """
    default_netvm = vm.netvm

    # Change to non-default netvm
    change_netvm_rc, change_netvm_res = core(
        Module(
            {
                "state": "present",
                "name": vm.name,
                "properties": {"netvm": netvm.name},
            }
        )
    )
    assert "netvm" in change_netvm_res["Properties updated"]
    assert change_netvm_rc == VIRT_SUCCESS

    # Ability to reset back to default netvm, whichever it is
    reset_netvm_rc, reset_netvm_res = core(
        Module(
            {
                "state": "present",
                "name": vm.name,
                "properties": {"netvm": "*default*"},
            }
        )
    )
    assert "netvm" in reset_netvm_res["Properties updated"]
    assert default_netvm != netvm
    assert reset_netvm_rc == VIRT_SUCCESS

    qubes.domains.refresh_cache(force=True)
    assert qubes.domains[vm.name].netvm == default_netvm


def test_properties_missing_default_dispvm(qubes):
    # default_dispvm does not exist
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": "dom0",
                "properties": {"default_dispvm": "toto"},
            }
        )
    )
    assert rc == VIRT_FAILED
    assert "Missing default_dispvm" in res


def test_properties_invalid_volume_name_for_appvm(qubes, vmname, request):
    # volume name not allowed for AppVM
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"volumes": [{"name": "root", "size": 10}]},
            }
        )
    )
    assert rc == VIRT_FAILED
    assert "Wrong volume name" in res


def test_properties_missing_volume_fields(qubes, vmname, request):
    # Missing name
    rc1, res1 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"volumes": [{"size": 10}]},
            }
        )
    )
    assert rc1 == VIRT_FAILED
    assert "Missing name for the volume" in res1

    # Missing size
    rc2, res2 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"volumes": [{"name": "private"}]},
            }
        )
    )
    assert rc2 == VIRT_FAILED
    assert "Missing size for the volume" in res2


def test_removetags_errors_if_no_tags_present(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create
    rc, _ = core(
        Module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    )
    assert rc == VIRT_SUCCESS
    assert vmname in qubes.domains

    # Remove tags
    rc, res = core(Module({"command": "removetags", "name": vmname}))
    assert rc == VIRT_FAILED
    assert "Missing tag" in res.get("Error", "")


def test_devices_pci_facts_match_actual(qubes):
    # Gather PCI facts from the module
    rc, res = core(Module({"gather_device_facts": True}))
    assert rc == VIRT_SUCCESS, "Fact‐gathering should succeed"

    facts = res["ansible_facts"]
    assert "pci_net" in facts
    assert "pci_usb" in facts
    assert "pci_audio" in facts

    # Compute the lists directly from qubes.domains["dom0"]
    net_actual = [
        f"pci:dom0:{dev.port_id}:{dev.device_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p02")
    ]
    usb_actual = [
        f"pci:dom0:{dev.port_id}:{dev.device_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p0c03")
    ]
    audio_actual = [
        f"pci:dom0:{dev.port_id}:{dev.device_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p0401")
        or repr(dev.interfaces[0]).startswith("p0403")
    ]

    # Compare sets
    assert set(facts["pci_net"]) == set(net_actual)
    assert set(facts["pci_usb"]) == set(usb_actual)
    assert set(facts["pci_audio"]) == set(audio_actual)


def test_devices_strict_single_pci_assignment(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Create VM in strict mode with only one PCI device
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [port],
            }
        )
    )
    assert rc == VIRT_SUCCESS

    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ports_assigned = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in assigned
    ]
    assert ports_assigned == [port]

    # Clean up
    core(Module({"state": "absent", "name": vmname}))


def test_devices_strict_multiple_with_block(
    qubes, vmname, request, latest_net_ports, block_device
):
    request.node.mark_vm_created(vmname)
    # Use both PCI net devices plus the block device
    devices = [latest_net_ports[-2], latest_net_ports[-1], block_device]

    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": devices,
            }
        )
    )
    assert rc == VIRT_SUCCESS

    qubes.domains.refresh_cache(force=True)
    pci_assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    blk_assigned = qubes.domains[vmname].devices["block"].get_assigned_devices()

    pci_ports = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in pci_assigned
    ]
    blk_ports = [
        f"block:dom0:{d.device.port_id}" if hasattr(d, "device") else d.port_id
        for d in blk_assigned
    ]
    assert set(pci_ports) == set(latest_net_ports[-2:]), "PCI ports mismatch"
    assert blk_ports == [block_device], "Block device not assigned correctly"

    core(Module({"state": "absent", "name": vmname}))


def test_devices_append_strategy_adds_without_removal(
    qubes, vmname, request, latest_net_ports, block_device
):
    request.node.mark_vm_created(vmname)
    first_port = latest_net_ports[-2]
    second_port = latest_net_ports[-1]

    # Initial create with first PCI port
    rc, _ = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [first_port],
            }
        )
    )
    assert rc == VIRT_SUCCESS

    # Re-run with append strategy: add second PCI and block, keep first
    rc, _ = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": {
                    "strategy": "append",
                    "items": [second_port, block_device],
                },
            }
        )
    )
    assert rc == VIRT_SUCCESS

    qubes.domains.refresh_cache(force=True)
    pci_ports = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ]
    blk_ports = [
        f"block:dom0:{d.device.port_id}" if hasattr(d, "device") else d.port_id
        for d in qubes.domains[vmname].devices["block"].get_assigned_devices()
    ]

    # All three must now be present
    assert set(pci_ports) == {first_port, second_port}
    assert blk_ports == [block_device]

    core(Module({"state": "absent", "name": vmname}))


def test_devices_per_device_mode_and_options(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Use dict format to specify a custom mode and options
    entry = {
        "device": port,
        "mode": "required",
        "options": {"no-strict-reset": True},
    }

    rc, _ = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [entry],
            }
        )
    )
    assert rc == VIRT_SUCCESS

    qubes.domains.refresh_cache(force=True)
    assigned = list(qubes.domains[vmname].devices["pci"].get_assigned_devices())
    assert len(assigned) == 1

    mode = assigned[0].mode.value
    opts = sorted(assigned[0].options or [])
    assert mode == "required"
    assert "no-strict-reset" in opts

    core(Module({"state": "absent", "name": vmname}))


def test_devices_strict_idempotent_sync(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Initial assignment of a single PCI port
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [port],
            }
        )
    )
    assert rc == VIRT_SUCCESS
    assert res.get("changed", False)

    # Re-run with the same device list (strict mode) — should be a no-op
    rc2, res2 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [port],
            }
        )
    )
    assert rc2 == VIRT_SUCCESS
    # No changes on the second sync
    assert not res2.get("changed", False)

    # Verify still exactly that one port is assigned
    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ports_assigned = [
        f"pci:dom0:{(d.virtual_device.port_id if hasattr(d, 'virtual_device') else d.port_id)}"
        for d in assigned
    ]
    assert ports_assigned == [port]


def test_devices_strict_unassign_all(qubes, vmname, request, latest_net_ports):
    request.node.mark_vm_created(vmname)
    ports = latest_net_ports[-2:]

    # Assign two PCI ports initially
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": ports,
            }
        )
    )
    assert rc == VIRT_SUCCESS
    assert res.get("changed", False)

    qubes.domains.refresh_cache(force=True)
    # Confirm both are there
    initial = {
        f"pci:dom0:{(d.virtual_device.port_id if hasattr(d, 'virtual_device') else d.port_id)}"
        for d in qubes.domains[vmname].devices["pci"].get_assigned_devices()
    }
    assert initial == set(ports)

    # Now sync to an empty list (strict default) to remove all devices
    rc2, res2 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [],  # strict empty
            }
        )
    )
    assert rc2 == VIRT_SUCCESS
    # Should report that it changed by removing devices
    assert res2.get("changed", False)

    # After removal, no PCI devices should remain assigned
    qubes.domains.refresh_cache(force=True)
    assert (
        list(qubes.domains[vmname].devices["pci"].get_assigned_devices()) == []
    )

    # And a second empty-sync is a no-op
    rc3, res3 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "devices": [],
            }
        )
    )
    assert rc3 == VIRT_SUCCESS
    assert res3.get("changed", False) is False


def test_services_aliased_to_features_only(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    services = ["clocksync", "minimal-netvm"]
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"services": services},
            }
        )
    )
    assert rc == VIRT_SUCCESS

    # The module should report 'features' was updated
    changed = res.get("Properties updated", [])
    assert "features" in changed

    # And the VM should now have service.<svc> = 1 for each
    qube = qubes.domains[vmname]
    for svc in services:
        key = f"service.{svc}"
        assert key in qube.features
        assert qube.features[key] == "1"


def test_services_and_explicit_features_combined(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Predefine an arbitrary feature
    features = {"foo": "bar"}
    services = ["audio", "net"]

    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {
                    "features": features,
                    "services": services,
                },
            }
        )
    )
    assert rc == VIRT_SUCCESS

    # The module should report 'features' was updated
    changed = res.get("Properties updated", [])
    assert "features" in changed

    # VM should have both the explicit feature and the aliased ones
    qube = qubes.domains[vmname]
    # features stays intact
    assert qube.features.get("foo") == "bar"
    # services get aliased
    for svc in services:
        key = f"service.{svc}"
        assert key in qube.features
        assert qube.features[key] == "1"


def test_lifecycle_shutdown_with_and_without_wait(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create VM
    rc, _ = core(
        Module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    )
    assert rc == VIRT_SUCCESS
    vm = qubes.domains[vmname]

    # Start VM
    rc, _ = core(Module({"command": "start", "name": vmname}))
    assert rc == VIRT_SUCCESS
    assert vm.is_running()

    # Shutdown without wait (default)
    rc, _ = core(Module({"state": "shutdown", "name": vmname}))
    assert rc == VIRT_SUCCESS
    # vm is not halted yet
    assert not vm.is_halted()
    # allow a bit of time for actual shutdown
    time.sleep(5)
    assert vm.is_halted()

    # Restart for the next check
    rc, _ = core(Module({"command": "start", "name": vmname}))
    assert rc == VIRT_SUCCESS
    assert vm.is_running()

    # Shutdown with wait=True
    rc, _ = core(Module({"state": "shutdown", "name": vmname, "wait": True}))
    assert rc == VIRT_SUCCESS
    # should already be halted, no extra sleep needed
    assert vm.is_halted()


def test_properties_set_kernelopts(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {"kernelopts": "swiotlb=4096 foo=bar"}
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": props,
            }
        )
    )
    assert rc == VIRT_SUCCESS
    assert "kernelopts" in res["Properties updated"]
    assert qubes.domains[vmname].kernelopts == "swiotlb=4096 foo=bar"


def test_properties_set_timeouts(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {"qrexec_timeout": 123, "shutdown_timeout": 456}
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": props,
            }
        )
    )
    assert rc == VIRT_SUCCESS
    updated = res["Properties updated"]
    assert "qrexec_timeout" in updated
    assert "shutdown_timeout" in updated
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.qrexec_timeout == 123
    assert vm.shutdown_timeout == 456


def test_properties_set_ip_ip6_and_mac(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {
        "ip": "10.1.2.3",
        "ip6": "fe80::1",
        "mac": "00:11:22:33:44:55",
    }
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": props,
            }
        )
    )
    assert rc == VIRT_SUCCESS
    updated = res["Properties updated"]
    for key in ("ip", "ip6", "mac"):
        assert key in updated
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.ip == "10.1.2.3"
    assert vm.ip6 == "fe80::1"
    assert vm.mac == "00:11:22:33:44:55"


def test_properties_set_management_dispvm_and_audiovm(
    qubes, vmname, managementdvm, audiovm, request
):
    request.node.mark_vm_created(vmname)
    props = {"management_dispvm": managementdvm.name, "audiovm": audiovm.name}
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": props,
            }
        )
    )
    assert rc == VIRT_SUCCESS
    updated = res["Properties updated"]
    assert "management_dispvm" in updated
    assert "audiovm" in updated
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.management_dispvm == managementdvm
    assert vm.audiovm == audiovm


def test_properties_set_default_user_and_guivm(qubes, vmname, guivm, request):
    request.node.mark_vm_created(vmname)
    props = {"default_user": "alice", "guivm": guivm.name}
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": props,
            }
        )
    )
    assert rc == VIRT_SUCCESS
    updated = res["Properties updated"]
    assert "default_user" in updated
    assert "guivm" in updated
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.default_user == "alice"
    assert vm.guivm == guivm.name


def test_properties_invalid_type_for_new_properties(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    # ip must be str, not int
    rc, res = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"ip": 12345},
            }
        )
    )
    assert rc == VIRT_FAILED
    assert "Invalid property value type" in res
    # qrexec_timeout must be int, not str
    rc2, res2 = core(
        Module(
            {
                "state": "present",
                "name": vmname,
                "properties": {"qrexec_timeout": "sixty"},
            }
        )
    )
    assert rc2 == VIRT_FAILED
    assert "Invalid property value type" in res2
