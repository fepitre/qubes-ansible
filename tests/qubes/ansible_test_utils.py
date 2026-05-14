import json
from unittest.mock import patch

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes

from plugins.modules.qubesos import (
    main as qubesos_legacy_main,
)

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_qube import (
    main as qubesos_core_qube_main,
)

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_host_devices_facts import (
    main as qubesos_core_host_devices_facts_main,
)

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_command import (
    main as qubesos_core_command_main,
)

from ansible_collections.qubesos.core.plugins.modules.qube_facts import (
    main as qubesos_core_qube_facts_main,
)


class AnsibleExitJson(Exception):
    pass


class AnsibleFailJson(Exception):
    pass


def exit_json(*args, **kwargs):
    if "changed" not in kwargs:
        kwargs["changed"] = False
    raise AnsibleExitJson(kwargs)


def fail_json(*args, **kwargs):
    kwargs["failed"] = True
    raise AnsibleFailJson(kwargs)


def set_module_args(args):
    basic._ANSIBLE_ARGS = to_bytes(json.dumps({"ANSIBLE_MODULE_ARGS": args}))


def run_patched_module(args, module):
    """Run the specified module. Returns result dict on success, raises AnsibleFailJson on failure."""
    set_module_args(args)
    with patch.multiple(
        basic.AnsibleModule, exit_json=exit_json, fail_json=fail_json
    ):
        try:
            module()
        except AnsibleExitJson as e:
            return e.args[0]
    raise AssertionError("Module did not call exit_json or fail_json")


def run_module_qubesos_core_qube_main(args):
    return run_patched_module(args, qubesos_core_qube_main)


def run_module_qubesos_core_host_devices_facts(args):
    return run_patched_module(args, qubesos_core_host_devices_facts_main)


def run_module_qubesos_core_command(args):
    return run_patched_module(args, qubesos_core_command_main)


def run_module_qubesos_core_qube_facts(args):
    return run_patched_module(args, qubesos_core_qube_facts_main)


def run_module_qubesos_legacy(args):
    """Run the qube module. Returns result dict on success, raises AnsibleFailJson on failure."""
    set_module_args(args)
    with patch.multiple(
        basic.AnsibleModule, exit_json=exit_json, fail_json=fail_json
    ):
        try:
            qubesos_legacy_main()
        except AnsibleExitJson as e:
            return 0, e.args[0]
        except AnsibleFailJson as e:
            return e.args[0]["rc"], e.args[0]["msg"]
    raise AssertionError("Module did not call exit_json or fail_json")
