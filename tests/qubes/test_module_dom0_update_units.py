#!/usr/bin/python3
# Copyright (C) 2026 Guillaume Chinal (guiiix) <guiiix@invisiblethingslab.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import sys
import pytest


from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes
from unittest.mock import MagicMock, patch


_libdnf5 = MagicMock()
sys.modules["libdnf5"] = _libdnf5
sys.modules["libdnf5.base"] = _libdnf5
sys.modules["libdnf5.rpm"] = _libdnf5
sys.modules["libdnf5.repo"] = _libdnf5
sys.modules["libdnf5.common"] = _libdnf5
sys.modules["libdnf5.logger"] = _libdnf5
sys.modules["libdnf5.transaction"] = _libdnf5

from ansible_collections.qubesos.core.plugins.modules.qubes_dom0_update import (
    QubesDom0UpdateModule,
    main,
    ARGUMENT_SPEC,
)

# ---------------------------------------------------------------------------
# Ansible test helpers
# ---------------------------------------------------------------------------


def set_module_args(args) -> None:
    """prepare arguments so that they will be picked up during module creation
    (https://docs.ansible.com/projects/ansible/latest/dev_guide/testing_units_modules.html)
    """
    basic._ANSIBLE_ARGS = to_bytes(json.dumps({"ANSIBLE_MODULE_ARGS": args}))


class AnsibleExitJson(Exception):
    """Exception class to be raised by module.exit_json and caught by the test case"""


class AnsibleFailJson(Exception):
    """Exception class to be raised by module.fail_json and caught by the test case"""


def exit_json(*args, **kwargs):
    """function to patch over exit_json; package return data into an exception"""
    kwargs.setdefault("changed", False)
    raise AnsibleExitJson(kwargs)


def fail_json(*args, **kwargs):
    kwargs["failed"] = True
    raise AnsibleFailJson(kwargs)


def fake_pkg(nevra: str) -> MagicMock:
    pkg = MagicMock()
    pkg.get_nevra.return_value = nevra
    return pkg


def init_module(params=None) -> QubesDom0UpdateModule:
    if params is None:
        params = {}
    set_module_args(params)

    return QubesDom0UpdateModule(
        basic.AnsibleModule(argument_spec=ARGUMENT_SPEC)
    )


@pytest.fixture(autouse=True)
def setup():
    _libdnf5.reset_mock()
    with patch.multiple(
        basic.AnsibleModule, exit_json=exit_json, fail_json=fail_json
    ), patch("os.geteuid", return_value=0), patch(
        "ansible_collections.qubesos.core.plugins.modules.qubes_dom0_update.get_best_parsable_locale",
        return_value="C",
    ), patch.dict(
        "os.environ", {}, clear=False
    ):
        yield


# ---------------------------------------------------------------------------
# Call qubes_dom0_update
# ---------------------------------------------------------------------------


def test_call_qubes_dom0_update_default_options():
    m = init_module()
    with patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ) as mock_run:
        m._call_qubes_dom0_update()
    assert mock_run.call_args[0][0] == ["/usr/bin/qubes-dom0-update", "-y"]


def test_call_qubes_dom0_opts_force_xen_upgrade():
    m = init_module({"force_xen_upgrade": True})
    with patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ) as mock_run:
        m._call_qubes_dom0_update()
    assert mock_run.call_args[0][0] == [
        "/usr/bin/qubes-dom0-update",
        "-y",
        "--force-xen-upgrade",
    ]


def test_call_qubes_dom0_opts_skip_boot_check():
    m = init_module({"skip_boot_check": True})
    with patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ) as mock_run:
        m._call_qubes_dom0_update()
    assert mock_run.call_args[0][0] == [
        "/usr/bin/qubes-dom0-update",
        "-y",
        "--skip-boot-check",
    ]


def test_call_qubes_dom0_update_with_options_and_args():
    m = init_module({"force_xen_upgrade": True})
    with patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ) as mock_run:
        m._call_qubes_dom0_update(options=["--action=install"], args=["pkg1"])
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/usr/bin/qubes-dom0-update"
    assert "-y" in cmd
    assert "--force-xen-upgrade" in cmd
    assert "--action=install" in cmd
    assert "pkg1" in cmd


# ---------------------------------------------------------------------------
# Module inputs checks
# ---------------------------------------------------------------------------


def test_run_fails_when_not_root():
    with patch("os.geteuid", return_value=1000) as _:
        module = init_module()
        with pytest.raises(AnsibleFailJson) as exc:
            module.run()
        assert (
            exc.value.args[0]["msg"]
            == "This command has to be run under the root user."
        )


def test_run_rejects_glob_with_state_present():
    set_module_args({"name": ["pkg*"], "state": "present"})
    with pytest.raises(AnsibleFailJson) as exc:
        main()
    assert "Globs are not supported" in exc.value.args[0]["msg"]
    assert "pkg*" in exc.value.args[0]["failures"]


def test_run_rejects_glob_with_state_installed():
    set_module_args({"name": ["*-devel"], "state": "installed"})
    with pytest.raises(AnsibleFailJson) as exc:
        main()
    assert "*-devel" in exc.value.args[0]["failures"]


def test_run_rejects_glob_with_other_packages():
    set_module_args({"name": ["*", "pkg"], "state": "latest"})
    with pytest.raises(AnsibleFailJson) as exc:
        main()
    assert exc.value.args[0]["msg"] == "'*' cannot be used with other packages"


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def test_process_install_nothing_to_do():
    set_module_args({"name": ["pkg1"], "state": "present"})
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule,
        "get_package_info",
        return_value=fake_pkg("pkg1-1.0-1.x86_64"),
    ), patch.object(basic.AnsibleModule, "run_command") as mock_run:
        mock_run.return_value = (0, "", "")
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["msg"] == "Nothing to do"
    mock_run.assert_not_called()


def test_process_install_installs_missing_package():
    set_module_args({"name": ["pkg1"], "state": "present"})
    pkg = fake_pkg("pkg1-1.0-1.x86_64")
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule, "get_package_info", side_effect=[None, pkg]
    ), patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["changed"] is True
    assert "Installed: pkg1-1.0-1.x86_64" in exc.value.args[0]["results"]


def test_process_install_multiple_missing_packages():
    set_module_args({"name": ["pkg1", "pkg2"], "state": "present"})
    pkg1 = fake_pkg("pkg1-1.0-1.x86_64")
    pkg2 = fake_pkg("pkg2-2.0-1.x86_64")

    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule,
        "get_package_info",
        side_effect=[None, None, pkg1, pkg2],
    ), patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ) as mock_run:
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    results = exc.value.args[0]["results"]
    assert any("pkg1" in r for r in results)
    assert any("pkg2" in r for r in results)
    mock_run.assert_called_once()
    assert [
        "/usr/bin/qubes-dom0-update",
        "-y",
        "--action=install",
    ] == mock_run.call_args_list[0].args[0][0:3]
    assert ["pkg1", "pkg2"] == sorted(mock_run.call_args_list[0].args[0][3:])


def test_process_install_exits_on_command_failure():
    set_module_args({"name": ["pkg1"], "state": "present"})
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule, "get_package_info", return_value=None
    ), patch.object(
        basic.AnsibleModule,
        "run_command",
        return_value=(1, "", "download failed"),
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["rc"] == 1


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

_QUBES_DOM0_UPDATE_NOTHING_TO_DO_STDOUT = """
Nothing to do.
"""

_QUBES_DOM0_UPDATE_NOTHING_TO_DO_STDERR = """
Using sys-firewall as UpdateVM for Dom0
Downloading updates. This may take a while...
Updating and loading repositories:
 Qubes Host Repository (updates)        100% |   4.0 KiB/s |   2.7 KiB |  00m01s
 Fedora 41 - x86_64 - Updates           100% |   6.6 KiB/s |   3.4 KiB |  00m01s
 Fedora 41 - x86_64                     100% |  51.2 KiB/s |   3.6 KiB |  00m00s
Repositories loaded.
Updating and loading repositories:
 Qubes OS Repository for Dom0           100% |   0.0   B/s |   1.5 KiB |  00m00s
Repositories loaded.
"""

_QUBES_DOM0_UPDATE_ERROR_STDERR = """
Using sys-firewall as UpdateVM for Dom0
Downloading updates. This may take a while...
Updating and loading repositories:
 Fedora 41 - x86_64 - Updates ???% |   0.0   B  0.0   B
 Fedora 41 - x86_64 - Updates ???% |   0.0   BKiB_[1A
 Qubes Host Repository (updates) 100% |   2.7 KiB_[1A
 Fedora 41 - x86_64 - Updates 100% |   3.4 KiB
 Fedora 41 - x86_64 100% |  23.9 MiB

Broadcast message from root@sys-firewall (Wed 2026-04-29 10:01:55 CEST):

The system will power off now!


Session terminated, killing shell...
"""


def test_process_update_nothing_to_do():
    set_module_args({"name": ["pkg1"], "state": "latest"})
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        basic.AnsibleModule,
        "run_command",
        return_value=(
            0,
            _QUBES_DOM0_UPDATE_NOTHING_TO_DO_STDOUT,
            _QUBES_DOM0_UPDATE_NOTHING_TO_DO_STDERR,
        ),
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["msg"] == "Nothing to do"


def test_process_update_fails_on_qubes_error():
    set_module_args({"name": ["pkg1"], "state": "latest"})
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        basic.AnsibleModule,
        "run_command",
        return_value=(1, "", _QUBES_DOM0_UPDATE_ERROR_STDERR),
    ):
        with pytest.raises(AnsibleFailJson) as exc:
            main()
    assert "Failed to update" in exc.value.args[0]["msg"]


def _setup_update_transaction_history(packages_info):
    """Set up libdnf5.transaction mocks for the update path.

    packages_info: list of (action_string, nevra_string) tuples.
    """
    pkg_mocks = []
    action_map = {}
    for action_str, nevra_str in packages_info:
        pkg_mock = MagicMock()
        pkg_mock.to_string.return_value = nevra_str
        action_mock = MagicMock()
        pkg_mock.get_action.return_value = action_mock
        action_map[action_mock] = action_str
        pkg_mocks.append(pkg_mock)

    last_tx_mock = MagicMock()
    last_tx_mock.get_packages.return_value = pkg_mocks

    history_mock = MagicMock()
    history_mock.list_all_transactions.return_value = [last_tx_mock]

    _libdnf5.transaction.TransactionHistory.return_value = history_mock
    _libdnf5.transaction.transaction_item_action_to_string.side_effect = (
        lambda a: action_map[a]
    )


def test_process_update_returns_transaction_history():
    set_module_args({"name": ["pkg1"], "state": "latest"})
    _setup_update_transaction_history(
        [
            ("Upgrade", "pkg1-2.0-1.x86_64"),
            ("Replaced", "pkg1-1.0-1.x86_64"),
        ]
    )
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "updated", "")
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()

    assert exc.value.args[0]["changed"] is True
    assert exc.value.args[0]["results"] == [
        "Upgrade: pkg1-2.0-1.x86_64",
        "Replaced: pkg1-1.0-1.x86_64",
    ]


def test_process_update_returns_multiple_package_changes():
    set_module_args({"name": ["pkg1", "pkg2", "pkg3"], "state": "latest"})
    _setup_update_transaction_history(
        [
            ("Upgrade", "pkg1-2.0-1.x86_64"),
            ("Upgrade", "pkg2-3.0-1.x86_64"),
            ("Install", "pkg3-1.0-1.x86_64"),
        ]
    )
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "updated", "")
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()

    results = exc.value.args[0]["results"]
    assert "Upgrade: pkg1-2.0-1.x86_64" in results
    assert "Upgrade: pkg2-3.0-1.x86_64" in results
    assert "Install: pkg3-1.0-1.x86_64" in results


def test_process_update_returns_empty_changes_when_no_packages():
    set_module_args({"name": ["pkg1"], "state": "latest"})
    _setup_update_transaction_history([])
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "updated", "")
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()

    assert exc.value.args[0]["changed"] is True
    assert exc.value.args[0]["results"] == []


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def _setup_remove_transaction(transaction_packages, run_succeeds=True):
    success_val = object()
    _libdnf5.base.Transaction.TransactionRunResult_SUCCESS = success_val

    transaction_mock = MagicMock()
    transaction_mock.get_problems.return_value = 0
    transaction_mock.get_transaction_packages.return_value = (
        transaction_packages
    )
    transaction_mock.run.return_value = (
        success_val if run_succeeds else MagicMock()
    )

    goal_mock = MagicMock()
    goal_mock.resolve.return_value = transaction_mock
    _libdnf5.base.Goal.return_value = goal_mock
    _libdnf5.base.GoalJobSettings.return_value = MagicMock()
    return transaction_mock


def test_process_remove_nothing_to_do():
    set_module_args({"name": ["pkg1"], "state": "absent"})
    _setup_remove_transaction([])
    with patch.object(QubesDom0UpdateModule, "_init_dnf"):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["msg"] == "Nothing to do"


def test_process_remove_success():
    set_module_args({"name": ["pkg1"], "state": "absent"})
    pkg_mock = MagicMock()
    pkg_mock.get_package.return_value = fake_pkg("pkg1-1.0-1.x86_64")
    _setup_remove_transaction([pkg_mock])
    with patch.object(QubesDom0UpdateModule, "_init_dnf"):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["changed"] is True
    assert "Removed: pkg1-1.0-1.x86_64" in exc.value.args[0]["results"]


def test_process_remove_fails_on_transaction_run_error():
    set_module_args({"name": ["pkg1"], "state": "absent"})
    pkg_mock = MagicMock()
    pkg_mock.get_package.return_value = fake_pkg("pkg1-1.0-1.x86_64")
    _setup_remove_transaction([pkg_mock], run_succeeds=False)
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), pytest.raises(
        AnsibleFailJson
    ) as exc:
        main()
    assert "Transaction failure" in exc.value.args[0]["msg"]


def test_process_remove_fails_on_goal_resolve_error():
    set_module_args({"name": ["pkg1"], "state": "absent"})
    goal_mock = MagicMock()
    goal_mock.resolve.side_effect = RuntimeError("depsolve error")
    _libdnf5.base.Goal.return_value = goal_mock
    _libdnf5.base.GoalJobSettings.return_value = MagicMock()
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), pytest.raises(
        AnsibleFailJson
    ) as exc:
        main()
    assert exc.value.args[0]["msg"] == "depsolve error"


def test_process_remove_fails_on_add_remove_error():
    set_module_args({"name": ["pkg1"], "state": "absent"})
    goal_mock = MagicMock()
    goal_mock.add_remove.side_effect = RuntimeError("cannot remove pkg1")
    _libdnf5.base.Goal.return_value = goal_mock
    _libdnf5.base.GoalJobSettings.return_value = MagicMock()
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), pytest.raises(
        AnsibleFailJson
    ) as exc:
        main()
    assert exc.value.args[0]["msg"] == "cannot remove pkg1"


# ---------------------------------------------------------------------------
# _switch_audio_server -- tested via main()
# ---------------------------------------------------------------------------


def test_switch_audio_server_pipewire_nothing_to_do():
    set_module_args({"switch_audio_server": "pipewire"})
    pkg = fake_pkg("pipewire-1.0-1.x86_64")
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule, "get_package_info", return_value=pkg
    ), patch.object(basic.AnsibleModule, "run_command") as mock_run:
        mock_run.return_value = (0, "", "")
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["msg"] == "Nothing to do"
    mock_run.assert_not_called()


def test_switch_audio_server_pulseaudio_nothing_to_do():
    set_module_args({"switch_audio_server": "pulseaudio"})
    pkg = fake_pkg("pulseaudio-1.0-1.x86_64")
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule, "get_package_info", return_value=pkg
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["msg"] == "Nothing to do"


def test_switch_audio_server_success():
    set_module_args({"switch_audio_server": "pulseaudio"})
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule, "get_package_info", return_value=None
    ), patch.object(
        basic.AnsibleModule, "run_command", return_value=(0, "", "")
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["changed"] is True
    assert exc.value.args[0]["msg"] == "Audio daemon switched to pulseaudio"


def test_switch_audio_server_command_fails():
    set_module_args({"switch_audio_server": "pipewire"})
    with patch.object(QubesDom0UpdateModule, "_init_dnf"), patch.object(
        QubesDom0UpdateModule, "get_package_info", return_value=None
    ), patch.object(
        basic.AnsibleModule,
        "run_command",
        return_value=(1, "", "switch failed"),
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            main()
    assert exc.value.args[0]["rc"] == 1
    assert (
        exc.value.args[0]["msg"] == "Failed to switch audio daemon to pipewire"
    )
