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
import os
import pytest
import subprocess
import rpm


@pytest.fixture(autouse=True)
def skip_if_not_dom0():
    if not os.path.exists("/usr/bin/qubes-dom0-update"):
        pytest.skip("Can be tested on dom0 only")


@pytest.fixture
def nano_installed():
    if is_package_installed("nano"):
        return

    result = subprocess.run(
        ["/usr/bin/qubes-dom0-update", "-y", "nano"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.fixture
def nano_uninstalled():
    result = subprocess.run(
        ["dnf", "remove", "-y", "nano"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.fixture
def notif_daemon_downgraded():
    result = subprocess.run(
        [
            "/usr/bin/qubes-dom0-update",
            "--action=downgrade",
            "-y",
            "qubes-notification-daemon",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def get_installed_packages(package_name) -> rpm.mi:
    ts = rpm.TransactionSet()
    return ts.dbMatch("name", package_name)


def is_package_installed(package_name):
    return len(get_installed_packages(package_name)) > 0


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy"],
)
def test_playbook_pkg_nano_installed(run_playbook, nano_uninstalled):
    assert not is_package_installed("nano")

    playbook = [
        {
            "hosts": "dom0",
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Install nano",
                    "qubesos.core.qubes_dom0_update": {
                        "name": "nano",
                        "state": "present",
                    },
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    task_results = returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"][
        "results"
    ][0]

    mi = get_installed_packages("nano")
    assert len(mi) == 1
    pkg = list(mi)[0]
    assert task_results == f"Installed: {pkg.nevra}"


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy"],
)
def test_playbook_pkg_nano_installed_using_package(
    run_playbook, nano_uninstalled
):
    assert not is_package_installed("nano")

    playbook = [
        {
            "hosts": "dom0",
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Install nano",
                    "package": {
                        "name": "nano",
                        "state": "present",
                        "use": "qubesos.core.qubes_dom0_update",
                    },
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    task_results = returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"][
        "results"
    ][0]

    mi = get_installed_packages("nano")
    assert len(mi) == 1
    pkg = list(mi)[0]
    assert task_results == f"Installed: {pkg.nevra}"


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy"],
)
def test_playbook_pkg_nano_removed(run_playbook, nano_installed):
    mi = get_installed_packages("nano")
    assert len(mi) == 1
    pkg = list(mi)[0]

    playbook = [
        {
            "hosts": "dom0",
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Install nano",
                    "qubesos.core.qubes_dom0_update": {
                        "name": "nano",
                        "state": "absent",
                    },
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    task_results = returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"][
        "results"
    ][0]

    assert task_results == f"Removed: {pkg.nevra}"


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy"],
)
def test_installed_package_should_be_upgraded_only_when_state_latest(
    run_playbook, notif_daemon_downgraded
):
    mi = get_installed_packages("qubes-notification-daemon")
    assert len(mi) == 1
    pkg_before = list(mi)[0]

    playbook = [
        {
            "hosts": "dom0",
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Install qubes-notification-daemon",
                    "qubesos.core.qubes_dom0_update": {
                        "name": "qubes-notification-daemon",
                        "state": "present",
                    },
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert not returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]
    mi = get_installed_packages("qubes-notification-daemon")
    assert len(mi) == 1
    pkg_after = list(mi)[0]
    assert (
        rpm.labelCompare(
            (pkg_before.epoch, pkg_before.version, pkg_before.release),
            (pkg_after.epoch, pkg_after.version, pkg_after.release),
        )
        == 0
    )

    playbook[0]["tasks"][0]["qubesos.core.qubes_dom0_update"][
        "state"
    ] = "latest"
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]
    mi = get_installed_packages("qubes-notification-daemon")
    assert len(mi) == 1
    pkg_after = list(mi)[0]
    assert (
        rpm.labelCompare(
            (pkg_before.epoch, pkg_before.version, pkg_before.release),
            (pkg_after.epoch, pkg_after.version, pkg_after.release),
        )
        == -1
    )


@pytest.mark.parametrize(
    "ansible_config",
    ["ansible_linear_strategy"],
)
def test_idempotence(run_playbook, nano_uninstalled, notif_daemon_downgraded):
    assert not is_package_installed("nano")

    playbook = [
        {
            "hosts": "dom0",
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Install nano",
                    "qubesos.core.qubes_dom0_update": {
                        "name": "nano",
                        "state": "present",
                    },
                },
            ],
        }
    ]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]

    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert not returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]

    playbook[0]["tasks"][0]["qubesos.core.qubes_dom0_update"][
        "state"
    ] = "absent"

    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]

    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert not returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]

    playbook[0]["tasks"][0]["qubesos.core.qubes_dom0_update"][
        "state"
    ] = "latest"
    playbook[0]["tasks"][0]["qubesos.core.qubes_dom0_update"]["name"] = "*"

    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]

    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    returned_data = json.loads(result.stdout)
    assert not returned_data["plays"][0]["tasks"][0]["hosts"]["dom0"]["changed"]
