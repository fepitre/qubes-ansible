#!/usr/bin/python3
# Copyright (c) 2017 Ansible Project
# Copyright (C) 2018 Kushal Das
# Copyright (C) 2025 Frédéric Pierret (fepitre) <frederic@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = """
---
module: qubesos
short_description: Manage Qubes OS virtual machines
description:
    - This module manages Qubes OS virtual machines using the qubesadmin API.
    - It supports VM creation, state management, and various operations such as starting, pausing, shutting down, and more.
    - For definitions of Qubes OS terminology (e.g. AppVM, TemplateVM, StandaloneVM, DispVM), please refer to the Qubes OS Glossary at https://www.qubes-os.org/doc/glossary/.
version_added: "2.8"
options:
  name:
    description:
      - Name of the Qubes OS virtual machine to manage.
      - This parameter is required for operations targeting a specific VM. It can also be specified as C(guest).
  state:
    description:
      - Desired state of the VM.
      - When set to C(present), ensures the VM is defined.
      - When set to C(running), ensures the VM is started.
      - When set to C(shutdown), ensures the VM is stopped.
      - When set to C(destroyed), forces the VM to shut down.
      - When set to C(restarted), shuts the VM down then starts it again.
      - When set to C(pause), pauses a running VM.
      - When set to C(absent), removes the VM definition.
    choices: [ present, running, shutdown, destroyed, restarted, pause, absent ]
  wait:
    description:
      - If C(true), block until the VM has fully halted before returning.
      - Only applies to C(shutdown) and C(restarted) states.
    type: bool
    default: false
  command:
    description:
      - Non-idempotent command to execute on the VM.
      - Available commands include:
        - C(create): Create a new VM.
        - C(destroy): Force shutdown of a VM.
        - C(pause): Pause a running VM.
        - C(shutdown): Gracefully shut down a VM.
        - C(status): Retrieve the current state of a VM.
        - C(start): Start a VM.
        - C(stop): Stop a VM.
        - C(unpause): Resume a paused VM.
        - C(removetags): Remove specified tags from a VM.
        - C(info): Retrieve information about all VMs.
        - C(list_vms): List VMs filtered by state.
        - C(get_states): Get the states of all VMs.
        - C(createinventory): Generate an inventory file for Qubes OS VMs.
  label:
    description:
      - Label (or color) assigned to the VM. For more details, see the Qubes OS Glossary.
    default: "red"
  vmtype:
    description:
      - The type of VM to manage.
      - Typical values include C(AppVM), C(StandaloneVM), and C(TemplateVM).
      - Refer to the Qubes OS Glossary for definitions of these terms.
    default: "AppVM"
  template:
    description:
      - Name of the template VM to use when creating or cloning a VM.
      - For AppVMs, this is the base TemplateVM from which the VM is derived.
    default: "default"
  properties:
    description:
      - A dictionary of VM properties to set.
      - Valid keys include:
          - autostart (bool)
          - debug (bool)
          - include_in_backups (bool)
          - kernel (str)
          - kernelopts (str)
          - label (str)
          - maxmem (int)
          - memory (int)
          - provides_network (bool)
          - netvm (str)
          - default_dispvm (str)
          - management_dispvm (str)
          - default_user (str)
          - guivm (str)
          - audiovm (str)
          - ip (str)
          - ip6 (str)
          - mac (str)
          - qrexec_timeout (int)
          - shutdown_timeout (int)
          - template (str)
          - template_for_dispvms (bool)
          - vcpus (int)
          - virt_mode (str)
          - features (dict)
          - services (list)
          - volumes (list of dict that must include both 'name' and 'size')
    default: {}
  tags:
    description:
      - A list of tags to apply to the VM.
      - Tags are used within Qubes OS for VM categorization.
    type: list
    default: []
  devices:
    description:
      - Device assignment configuration for the VM.
      - Supported usage patterns:
        1. A list (default _strict_ mode) device specs (strings or dicts). The VM's assigned devices will be exactly those listed, removing any others.
        2. A dictionary:
           - strategy (str): assignment strategy to use.  
             - C(strict) (default): enforce exact match of assigned devices to C(items).  
             - C(append): add only new devices in C(items), leaving existing assignments intact.
           - items (list): list of device specs (strings or dicts) to apply under the chosen strategy.
      - Device spec formats:
        - string: `<devclass>:<backend_domain>:<port_id>[:<dev_id>]` (e.g. C(pci:dom0:5), C(block:dom0:vdb))
        - dict:
          - device (str, required): the string spec as above.
          - mode (str, optional):
            - For PCI devices defaults to C(required).
            - For other classes defaults to C(auto-attach).
          - options (dict, optional): extra Qubes device flags to pass when attaching.
    type: raw
    default: []

requirements:
  - python >= 3.12
  - qubesadmin
  - jinja2
author:
  - Kushal Das
  - Frédéric Pierret
"""

import time
import traceback

try:
    import qubesadmin
    from qubesadmin.exc import (
        QubesVMNotStartedError,
        QubesTagNotFoundError,
        QubesVMError,
    )
    from qubesadmin.device_protocol import (
        VirtualDevice,
        DeviceAssignment,
        ProtocolError,
    )
except ImportError:
    qubesadmin = None
    QubesVMNotStartedError = None
    QubesTagNotFoundError = None
    QubesVMError = None


from jinja2 import Template
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

VIRT_FAILED = 1
VIRT_SUCCESS = 0
VIRT_UNAVAILABLE = 2

ALL_COMMANDS = []
VM_COMMANDS = [
    "create",
    "destroy",
    "pause",
    "shutdown",
    "remove",
    "status",
    "start",
    "stop",
    "unpause",
    "removetags",
]
HOST_COMMANDS = ["info", "list_vms", "get_states", "createinventory"]
ALL_COMMANDS.extend(VM_COMMANDS)
ALL_COMMANDS.extend(HOST_COMMANDS)

VIRT_STATE_NAME_MAP = {
    0: "running",
    1: "paused",
    4: "shutdown",
    5: "shutdown",
    6: "crashed",
}

PROPS = {
    "autostart": bool,
    "debug": bool,
    "include_in_backups": bool,
    "kernel": str,
    "kernelopts": str,
    "label": str,
    "maxmem": int,
    "memory": int,
    "provides_network": bool,
    "template": str,
    "template_for_dispvms": bool,
    "vcpus": int,
    "virt_mode": str,
    "default_dispvm": str,
    "management_dispvm": str,
    "default_user": str,
    "guivm": str,
    "audiovm": str,
    "netvm": str,
    "ip": str,
    "ip6": str,
    "mac": str,
    "qrexec_timeout": int,
    "shutdown_timeout": int,
    "features": dict,
    "services": list,
    "volumes": list,
}


def create_inventory(result):
    """
    Creates the inventory file dynamically for QubesOS
    """
    template_str = """[local]
localhost

[local:vars]
ansible_connection=local

{% if result.AppVM %}
[appvms]
{% for item in result.AppVM %}
{{ item -}}
{% endfor %}

[appvms:vars]
ansible_connection=qubes
{% endif %}

{% if result.TemplateVM %}
[templatevms]
{% for item in result.TemplateVM %}
{{ item -}}
{% endfor %}

[templatevms:vars]
ansible_connection=qubes
{% endif %}

{% if result.StandaloneVM %}
[standalonevms]
{% for item in result.StandaloneVM %}
{{ item -}}
{% endfor %}

[standalonevms:vars]
ansible_connection=qubes
{% endif %}
"""
    template = Template(template_str)
    res = template.render(result=result)
    with open("inventory", "w") as fobj:
        fobj.write(res)


class QubesVirt(object):

    def __init__(self, module):
        self.module = module
        self.app = qubesadmin.Qubes()

    def get_device_classes(self):
        """List all available device classes in dom0 (excluding 'testclass')."""
        return [c for c in self.app.list_deviceclass() if c != "testclass"]

    def find_devices_of_class(self, klass):
        """Yield the port IDs of all devices matching a given class in dom0."""
        for dev in self.app.domains["dom0"].devices["pci"]:
            if repr(dev.interfaces[0]).startswith("p" + klass):
                yield f"pci:dom0:{dev.port_id}:{dev.device_id}"

    def get_vm(self, vmname):
        """Retrieve a qube object by its name."""
        return self.app.domains[vmname]

    def __get_state(self, vmname):
        """Determine the current power state of a qube."""
        vm = self.app.domains[vmname]
        if vm.is_paused():
            return "paused"
        if vm.is_running():
            return "running"
        if vm.is_halted():
            return "shutdown"
        return None

    def get_states(self):
        """Get the names and states of all qubes."""
        state = []
        for vm in self.app.domains:
            state.append(f"{vm.name} {self.__get_state(vm.name)}")
        return state

    def list_vms(self, state):
        """List all non-dom0 qubes that match a specified state."""
        res = []
        for vm in self.app.domains:
            if vm.name != "dom0" and state == self.__get_state(vm.name):
                res.append(vm.name)
        return res

    def all_vms(self):
        """Group all non-dom0 qubes by their VM class."""
        res = {}
        for vm in self.app.domains:
            if vm.name == "dom0":
                continue
            res.setdefault(vm.klass, []).append(vm.name)
        return res

    def info(self):
        """Gather detailed info (state, network, label) for all non-dom0 qubes."""
        info = {}
        for vm in self.app.domains:
            if vm.name == "dom0":
                continue
            info[vm.name] = {
                "state": self.__get_state(vm.name),
                "provides_network": vm.provides_network,
                "label": vm.label.name,
            }
        return info

    def shutdown(self, vmname, wait=False):
        """
        Shutdown the specified qube via the given id or name,
        optionally waiting until it halts.
        """
        vm = self.get_vm(vmname)
        vm.shutdown()
        if wait:
            start = time.time()
            while time.time() - start < vm.shutdown_timeout:
                if vm.is_halted():
                    return 0
                time.sleep(1)
            raise RuntimeError(
                f"Timeout: VM {vmname} did not halt within {vm.shutdown_timeout}s"
            )
        return 0

    def restart(self, vmname, wait=False):
        """
        Restart the specified qube via the given id or name
        by shutting it down (with optional wait) and then starting it.
        """
        try:
            self.shutdown(vmname, wait=wait)
        except RuntimeError:
            raise
        vm = self.get_vm(vmname)
        vm.start()
        return 0

    def pause(self, vmname):
        """Pause the specified qube via the given id or name."""
        vm = self.get_vm(vmname)
        vm.pause()
        return 0

    def unpause(self, vmname):
        """Unpause the specified qube via the given id or name."""
        vm = self.get_vm(vmname)
        vm.unpause()
        return 0

    def create(
        self,
        vmname,
        vmtype="AppVM",
        label="red",
        template=None,
        netvm="*default*",
    ):
        """Create a new qube of the given type, label, template, and network."""
        template_vm = template or ""
        if netvm == "*default*":
            network_vm = self.app.default_netvm
        elif not netvm:
            network_vm = None
        else:
            network_vm = self.get_vm(netvm)
        if vmtype == "AppVM":
            vm = self.app.add_new_vm(
                vmtype, vmname, label, template=template_vm
            )
            vm.netvm = network_vm
        elif vmtype in ["StandaloneVM", "TemplateVM"] and template_vm:
            vm = self.app.clone_vm(template_vm, vmname, vmtype, ignore_devices=True)
            vm.label = label
        return 0

    def start(self, vmname):
        """Start the specified qube via the given id or name"""
        vm = self.get_vm(vmname)
        vm.start()
        return 0

    def destroy(self, vmname):
        """Immediately kill the specified qube via the given id or name (no graceful shutdown)."""
        vm = self.get_vm(vmname)
        vm.kill()
        return 0

    def properties(self, vmname, prefs):
        """Sets the given properties to the qube"""
        changed = False
        values_changed = []
        vm = self.get_vm(vmname)

        # VM-reference properties
        vm_ref_keys = [
            "audiovm",
            "default_dispvm",
            "default_user",
            "guivm",
            "management_dispvm",
            "netvm",
            "template",
        ]

        for key, val in prefs.items():
            if key in vm_ref_keys:
                # determine new value or default
                if val in (None, ""):
                    new_val = ""
                elif val == "*default*":
                    new_val = qubesadmin.DEFAULT
                else:
                    new_val = val
                # check and apply change
                if new_val is qubesadmin.DEFAULT:
                    if not vm.property_is_default(key):
                        setattr(vm, key, new_val)
                        changed = True
                        values_changed.append(key)
                else:
                    if getattr(vm, key) != new_val:
                        setattr(vm, key, new_val)
                        changed = True
                        values_changed.append(key)

            elif key == "features":
                for fkey, fval in val.items():
                    if fval is None:
                        if fkey in vm.features:
                            del vm.features[fkey]
                            changed = True
                    else:
                        if vm.features.get(fkey) != fval:
                            vm.features[fkey] = fval
                            changed = True
                if changed and "features" not in values_changed:
                    values_changed.append("features")

            elif key == "services":
                for svc in val:
                    feat = f"service.{svc}"
                    if vm.features.get(feat) != "1":
                        vm.features[feat] = "1"
                        changed = True
                if changed and "features" not in values_changed:
                    values_changed.append("features")

            elif key == "volumes":
                for vol in prefs.get("volumes", []):
                    try:
                        volume = vm.volumes[vol["name"]]
                        volume.resize(vol["size"])
                    except Exception:
                        return VIRT_FAILED, {"Failure in updating volume": vol["name"]}
                    changed = True
                    values_changed.append(f"volume:{vol["name"]}")

            else:
                current = getattr(vm, key)
                if current != val:
                    setattr(vm, key, val)
                    changed = True
                    values_changed.append(key)

        return changed, values_changed

    def remove(self, vmname):
        """Destroy and then delete a qube's configuration and disk."""
        try:
            self.destroy(vmname)
        except QubesVMNotStartedError:
            pass
        while True:
            if self.__get_state(vmname) == "shutdown":
                break
            time.sleep(1)
        del self.app.domains[vmname]
        return 0

    def status(self, vmname):
        """
        Return a state suitable for server consumption.  Aka, codes.py values, not XM output.
        """
        return self.__get_state(vmname)

    def tags(self, vmname, tags):
        """Add a list of tags to a qube, skipping any already present."""
        vm = self.get_vm(vmname)
        updated_tags = []
        for tag in tags:
            if tag in vm.tags:
                continue
            vm.tags.add(tag)
            updated_tags.append(tag)
        return updated_tags

    def parse_device(self, spec):
        """Parse a device specification string into its class and VirtualDevice."""
        parts = spec.split(":", 1)
        if len(parts) != 2:
            self.module.fail_json(msg=f"Invalid spec {spec}")
        devclass, rest = parts
        if devclass not in self.get_device_classes():
            self.module.fail_json(msg=f"Invalid devclass {devclass}")
        try:
            device = VirtualDevice.from_str(rest, devclass, self.app.domains)
            return devclass, device
        except Exception as e:
            self.module.fail_json(msg=f"Cannot parse device {spec}: {e}")
            return None

    def list_assigned_devices(self, vmname, devclass):
        """List currently assigned devices of a given class for a qube."""
        vm = self.get_vm(vmname)
        current = {}
        for ass in vm.devices[devclass].get_assigned_devices():
            # get the VirtualDevice
            d = getattr(ass, "virtual_device", None) or ass.device
            spec = f"{devclass}:{d.backend_domain}:{d.port_id}:{d.device_id}"
            mode = getattr(ass, "mode", None)
            opts = getattr(ass, "options", None) or {}
            current[spec] = (mode, opts)
        return current

    def assign(self, vmname, devclass, device_assignment):
        """Assign a device to the specified qube."""
        vm = self.get_vm(vmname)
        vm.devices[devclass].assign(device_assignment)
        return 0

    def unassign(self, vmname, devclass, device_assignment):
        """Remove an assigned device from the specified qube."""
        vm = self.get_vm(vmname)
        vm.devices[devclass].unassign(device_assignment)
        return 0

    def sync_devices(self, vmname, devclass, desired):
        """Synchronize a qube's device assignments to match the desired configuration."""
        # build desired map: spec -> (vd, per_mode, opts)
        desired_map = {
            f"{devclass}:{vd.backend_domain}:{vd.port_id}:{vd.device_id}": (
                vd,
                per_mode,
                opts or {},
            )
            for vd, per_mode, opts in (desired or [])
        }

        changed = False

        # current assignments: spec -> (mode, opts)
        current_map = self.list_assigned_devices(vmname, devclass)
        current_specs = set(current_map)
        desired_specs = set(desired_map)

        # 1) Unassign anything not in desired
        for spec in current_specs - desired_specs:
            cls, dev = self.parse_device(spec)
            self.unassign(
                vmname,
                cls,
                DeviceAssignment(dev, frontend_domain=self.get_vm(vmname)),
            )
            changed = True

        # 2) Reassign anything whose mode or options differ
        for spec in current_specs & desired_specs:
            existing_mode, existing_opts = current_map[spec]
            vd, per_mode, opts = desired_map[spec]
            # normalize desired_mode
            desired_mode = per_mode or (
                "required" if devclass == "pci" else "auto-attach"
            )
            if existing_mode.value != desired_mode or existing_opts != opts:
                # tear down the old and set up the new
                cls, dev = self.parse_device(spec)
                self.unassign(
                    vmname,
                    cls,
                    DeviceAssignment(dev, frontend_domain=self.get_vm(vmname)),
                )
                self.assign(
                    vmname,
                    devclass,
                    DeviceAssignment(vd, mode=desired_mode, options=opts),
                )
                changed = True

        # 3) Assign any new specs
        for spec in desired_specs - current_specs:
            vd, per_mode, opts = desired_map[spec]
            assign_mode = per_mode or (
                "required" if devclass == "pci" else "auto-attach"
            )
            self.assign(
                vmname,
                devclass,
                DeviceAssignment(vd, mode=assign_mode, options=opts),
            )
            changed = True

        return changed


def core(module):
    state = module.params.get("state", None)
    guest = module.params.get("name", None)
    command = module.params.get("command", None)
    vmtype = module.params.get("vmtype", "AppVM")
    label = module.params.get("label", "red")
    template = module.params.get("template", None)
    properties = module.params.get("properties", {})
    tags = module.params.get("tags", [])
    devices = module.params.get("devices", [])
    netvm = None
    res = {}
    device_specs = []

    v = QubesVirt(module)

    # Normalize devices into (set_mode, device_specs)
    if isinstance(devices, dict):
        set_mode = devices.get("strategy", "strict")
        device_specs = devices.get("items") or []
    elif isinstance(devices, list):
        # flat list -> always strict
        set_mode = "strict"
        device_specs = devices
    else:
        module.fail_json(msg=f"Invalid devices parameter: {devices!r}")

    # Now expand each spec into (class, VirtualDevice, per_mode, options)
    normalized_devices = []
    for entry in device_specs:
        if isinstance(entry, str):
            # simple string spec -> no per-device mode or options
            cls, vd = v.parse_device(entry)
            normalized_devices.append((cls, vd, None, []))
        elif isinstance(entry, dict):
            # dict spec must have a "device" key
            device_str = entry.get("device")
            if not device_str:
                module.fail_json(
                    msg=f"Device entry missing 'device': {entry!r}"
                )
            cls, vd = v.parse_device(device_str)
            # optional per-device mode (e.g. "required" or "auto-attach")
            per_mode = entry.get("mode")
            # optional options list
            opts = entry.get("options", {})
            normalized_devices.append((cls, vd, per_mode, opts))
        else:
            module.fail_json(msg=f"Invalid device entry: {entry!r}")

    def apply_devices(vmname):
        devices_changed = False
        for device_class in v.get_device_classes():
            # gather only the entries for this class
            wants = [
                (vd, per_mode, opts)
                for (cls, vd, per_mode, opts) in normalized_devices
                if cls == device_class
            ]
            if set_mode == "strict":
                devices_changed |= v.sync_devices(vmname, device_class, wants)
            elif set_mode == "append":
                current_map = v.list_assigned_devices(vmname, device_class)
                for vd, per_mode, opts in wants:
                    spec = f"{device_class}:{vd.backend_domain}:{vd.port_id}:{vd.device_id}"
                    if spec in current_map:
                        # already present -> leave it (no mode/options change in append mode)
                        continue
                    # new device -> assign with its mode/options
                    assign_mode = per_mode or (
                        "required" if device_class == "pci" else "auto-attach"
                    )
                    v.assign(
                        vmname,
                        device_class,
                        DeviceAssignment(vd, mode=assign_mode, options=opts),
                    )
                    devices_changed = True
            else:
                module.fail_json(msg=f"Invalid devices strategy: {set_mode}")
        return devices_changed

    # gather device facts
    if module.params.get("gather_device_facts", False):
        facts = {
            "pci_net": sorted(v.find_devices_of_class("02")),
            "pci_usb": sorted(v.find_devices_of_class("0c03")),
            "pci_audio": sorted(
                list(v.find_devices_of_class("0401"))
                + list(v.find_devices_of_class("0403"))
            ),
        }
        return VIRT_SUCCESS, {"changed": False, "ansible_facts": facts}

    if state == "present" and guest and vmtype:
        try:
            v.get_vm(guest)
        except KeyError:
            v.create(guest, vmtype, label, template)

    # properties will only work with state=present
    if properties:
        for key, val in properties.items():
            if key not in PROPS:
                return VIRT_FAILED, {"Invalid property": key}
            if type(val) != PROPS[key]:
                return VIRT_FAILED, {"Invalid property value type": key}

            # Make sure that the netvm exists
            if key == "netvm" and val not in ["*default*", "", "none", "None"]:
                try:
                    vm = v.get_vm(val)
                except KeyError:
                    return VIRT_FAILED, {"Missing netvm": val}
                # Also the vm should provide network
                if not vm.provides_network:
                    return VIRT_FAILED, {"Missing netvm capability": val}
                netvm = vm

            # Make sure volume has both name and value
            if key == "volumes":
                if not isinstance(val, list):
                    return VIRT_FAILED, {"Invalid volumes provided": val}
                for vol in val:
                    try:
                        if "name" not in vol:
                            return VIRT_FAILED, {"Missing name for the volume": vol}
                        if "size" not in vol:
                            return VIRT_FAILED, {"Missing size for the volume": vol}
                        if not vol["name"] in ["root", "private"]:
                            return VIRT_FAILED, {"Wrong volume name": vol["name"]}
                    except KeyError:
                        return VIRT_FAILED, {"Invalid volume provided": vol}

            # Make sure that the default_dispvm exists
            if key == "default_dispvm":
                try:
                    vm = v.get_vm(val)
                except KeyError:
                    return VIRT_FAILED, {"Missing default_dispvm": val}
                # Also the vm should provide network
                if not vm.template_for_dispvms:
                    return VIRT_FAILED, {"Missing dispvm capability": val}

        if state == "present" and guest and vmtype:
            prop_changed, prop_vals = v.properties(guest, properties)
            # Apply the tags
            tags_changed = []
            if tags:
                tags_changed = v.tags(guest, tags)
            dev_changed = apply_devices(guest)
            res = {"changed": prop_changed or dev_changed}
            if tags_changed:
                res["Tags updated"] = tags_changed
            if prop_changed:
                res["Properties updated"] = prop_vals
            if dev_changed:
                res["Devices updated"] = True
            return VIRT_SUCCESS, res

    # This is without any properties
    if state == "present" and guest:
        try:
            v.get_vm(guest)
            dev_changed = apply_devices(guest)
            res = {"changed": dev_changed}
        except KeyError:
            v.create(guest, vmtype, label, template)
            # Apply the tags
            tags_changed = []
            if tags:
                tags_changed = v.tags(guest, tags)
            apply_devices(guest)
            res = {"changed": True, "created": guest, "devices": devices}
            if tags_changed:
                res["tags"] = tags_changed
        return VIRT_SUCCESS, res

    # list_vms, get_states, createinventory commands
    if state and command == "list_vms":
        res = v.list_vms(state=state)
        if not isinstance(res, dict):
            res = {command: res}
        return VIRT_SUCCESS, res

    if command == "get_states":
        states = v.get_states()
        res = {"states": states}
        return VIRT_SUCCESS, res

    if command == "createinventory":
        result = v.all_vms()
        create_inventory(result)
        return VIRT_SUCCESS, {"status": "successful"}

    # single-command VM operations
    if command:
        if command in VM_COMMANDS:
            if not guest:
                module.fail_json(msg=f"{command} requires 1 argument: guest")
            if command == "create":
                try:
                    v.get_vm(guest)
                except KeyError:
                    v.create(guest, vmtype, label, template, netvm)
                    res = {"changed": True, "created": guest}
                return VIRT_SUCCESS, res
            elif command == "removetags":
                vm = v.get_vm(guest)
                changed = False
                if not tags:
                    return VIRT_FAILED, {"Error": "Missing tag(s) to remove."}
                for tag in tags:
                    try:
                        vm.tags.remove(tag)
                        changed = True
                    except QubesTagNotFoundError:
                        pass
                return VIRT_SUCCESS, {
                    "Message": "Removed the tag(s).",
                    "changed": changed,
                }
            res = getattr(v, command)(guest)
            if not isinstance(res, dict):
                res = {command: res}
            return VIRT_SUCCESS, res
        elif hasattr(v, command):
            res = getattr(v, command)()
            if not isinstance(res, dict):
                res = {command: res}
            return VIRT_SUCCESS, res

        else:
            module.fail_json(msg=f"Command {command} not recognized")

    if state:
        if not guest:
            module.fail_json(msg="State change requires a guest specified")
        current = v.status(guest)
        if state == "running":
            if current == "paused":
                res["changed"] = True
                res["msg"] = v.unpause(guest)
            elif current != "running":
                res["changed"] = True
                res["msg"] = v.start(guest)
        elif state == "shutdown":
            if current != "shutdown":
                res["changed"] = True
                try:
                    v.shutdown(guest, wait=module.params.get("wait", False))
                except RuntimeError as e:
                    module.fail_json(msg=str(e))
        elif state == "restarted":
            res["changed"] = True
            try:
                v.restart(guest, wait=module.params.get("wait", False))
                res["msg"] = "restarted"
            except RuntimeError as e:
                module.fail_json(msg=str(e))
        elif state == "destroyed":
            if current != "shutdown":
                res["changed"] = True
                res["msg"] = v.destroy(guest)
        elif state == "pause":
            if current == "running":
                res["changed"] = True
                res["msg"] = v.pause(guest)
        elif state == "absent":
            if current == "shutdown":
                res["changed"] = True
                res["msg"] = v.remove(guest)
        else:
            module.fail_json(msg="Unexpected state")

        return VIRT_SUCCESS, res

    module.fail_json(msg="Expected state or command parameter to be specified")

    return None


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type="str", aliases=["guest"]),
            state=dict(
                type="str",
                choices=[
                    "destroyed",
                    "pause",
                    "running",
                    "shutdown",
                    "restarted",
                    "absent",
                    "present",
                ],
            ),
            wait=dict(type="bool", default=False),
            command=dict(type="str", choices=ALL_COMMANDS),
            label=dict(type="str", default="red"),
            vmtype=dict(type="str", default="AppVM"),
            template=dict(type="str", default=None),
            properties=dict(type="dict", default={}),
            tags=dict(type="list", default=[]),
            devices=dict(type="raw", default=[]),
            gather_device_facts=dict(type="bool", default=False),
        ),
    )

    if not qubesadmin:
        module.fail_json(
            msg="The `qubesos` module is not importable. Check the requirements."
        )

    result = None
    rc = VIRT_SUCCESS
    try:
        rc, result = core(module)
    except Exception as e:
        module.fail_json(msg=to_native(e), exception=traceback.format_exc())

    if rc != 0:  # something went wrong emit the msg
        module.fail_json(rc=rc, msg=result)
    else:
        module.exit_json(**result)


if __name__ == "__main__":
    main()
