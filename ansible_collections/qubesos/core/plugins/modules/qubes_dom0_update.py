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

from __future__ import absolute_import, division, print_function


__metaclass__ = type

DOCUMENTATION = r"""
---
module: qubes_dom0_update

short_description: Manage dom0 packages in Qubes OS

description:
  - Installs, removes, or upgrades packages in Qubes OS dom0 using C(qubes-dom0-update).
  - Can also manage audio daemon.

version_added: "1.0.0"

author:
  - Guillaume Chinal <guiiix@invisiblethingslab.com>

options:
  name:
    description:
      - List of package names to manage
      - Use C(*) alone with O(state=latest) to upgrade all installed packages.
      - Globs are not supported for update only.
    type: list
    elements: str
    aliases:
      - pkg
    default: []

  state:
    description:
      - Desired state of the packages.
      - Use V(present) or V(installed) to install missing packages.
      - Use V(latest) to install and upgrade packages to their latest available version.
      - Use V(absent) or V(removed) to remove packages.
    type: str
    default: present
    choices:
      - absent
      - installed
      - present
      - removed
      - latest

  force_xen_upgrade:
    description:
      - Pass C(--force-xen-upgrade) to C(qubes-dom0-update).
      - Force major Xen upgrade even if some qubes are running.
    type: bool
    default: false

  skip_boot_check:
    description:
      - Pass C(--skip-boot-check) to C(qubes-dom0-update).
      - Does not check if /boot & /boot/efi should be mounted.
    type: bool
    default: false

  switch_audio_server:
    description:
      - Switch the dom0 audio daemon to the specified backend.
      - Mutually exclusive with O(name).
    type: str
    choices:
      - pipewire
      - pulseaudio

notes:
  - This module must be run as root.
"""

EXAMPLES = r"""
- name: Install a package
  qubesos.core.qubes_dom0_update:
    name: nano
    state: present

- name: Install multiple packages
  qubesos.core.qubes_dom0_update:
    name:
      - nano
      - htop
    state: present

- name: Remove a package
  qubesos.core.qubes_dom0_update:
    name: nano
    state: absent

- name: Upgrade specific packages
  qubesos.core.qubes_dom0_update:
    name:
      - qubes-core-dom0
      - qubes-gui-daemon
    state: latest

- name: Upgrade all dom0 packages
  qubesos.core.qubes_dom0_update:
    name: "*"
    state: latest

- name: Upgrade all dom0 packages, forcing Xen upgrade
  qubesos.core.qubes_dom0_update:
    name: "*"
    state: latest
    force_xen_upgrade: true

- name: Switch audio server to PipeWire
  qubesos.core.qubes_dom0_update:
    switch_audio_server: pipewire
"""

import libdnf5
import libdnf5.transaction
import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.locale import get_best_parsable_locale


ARGUMENT_SPEC = dict(
    force_xen_upgrade=dict(type="bool", default=False),
    name=dict(type="list", elements="str", aliases=["pkg"], default=[]),
    skip_boot_check=dict(type="bool", default=False),
    state=dict(
        type="str",
        default="present",
        choices=["absent", "installed", "present", "removed", "latest"],
    ),
    switch_audio_server=dict(
        type="str",
        choices=[
            "pipewire",
            "pulseaudio",
        ],
    ),
)


class QubesDom0UpdateModule:
    def __init__(self, module):
        self.module = module

        self.force_xen_upgrade = module.params["force_xen_upgrade"]
        self.names = [p.strip() for p in self.module.params["name"]]
        self.skip_boot_check = module.params["skip_boot_check"]
        self.state = self.module.params["state"]
        self.switch_audio_server = self.module.params["switch_audio_server"]

        locale = get_best_parsable_locale(self.module)
        os.environ["LC_ALL"] = os.environ["LC_MESSAGES"] = locale
        os.environ["LANGUAGE"] = os.environ["LANG"] = locale

        self.dnf_base = None
        self.dnf_conf = None

    def _call_qubes_dom0_update(self, options=None, args=None):
        opts = self._get_dnf_opts()
        if options:
            opts += options
        if args:
            opts += args
        return self.module.run_command(["/usr/bin/qubes-dom0-update", *opts])

    def _get_dnf_opts(self):
        args = ["-y"]
        if self.force_xen_upgrade:
            args.append("--force-xen-upgrade")
        if self.skip_boot_check:
            args.append("--skip-boot-check")
        return args

    def _init_dnf(self):
        self.dnf_base = libdnf5.base.Base()
        self.conf = self.dnf_base.get_config()
        try:
            self.dnf_base.load_config()
        except RuntimeError as e:
            self.module.fail_json(
                msg=str(e),
                conf_file=self.dnf_conf.config_file_path,
                failures=[],
                rc=1,
            )
        self.dnf_base.setup()
        log_router = self.dnf_base.get_logger()
        global_logger = libdnf5.logger.GlobalLogger()
        global_logger.set(log_router.get(), libdnf5.logger.Logger.Level_DEBUG)
        # FIXME hardcoding the filename does not seem right, should libdnf5 expose the default file name?
        logger = libdnf5.logger.create_file_logger(self.dnf_base, "dnf5.log")
        log_router.add_logger(logger)
        sack = self.dnf_base.get_repo_sack()
        sack.create_repos_from_system_configuration()

        # Disable all repo as we'll work with local RPM database only
        repo_query = libdnf5.repo.RepoQuery(self.dnf_base)
        repo_query.filter_id("*", libdnf5.common.QueryCmp_IGLOB)
        for repo in repo_query:
            repo.disable()
        sack.load_repos()

    def _process_install(self):
        """Install packages if not present

        This will check in local RPM database if wanted packages are
        installed If not, qubes-dom0-update is called and RPM database is read
        to return the installed version.

        We need to check in local RPM database because qubes-dom0-update will
        always update our package even when using --action=install
        """
        results = []
        packages_to_install = set()
        for pkg_name in self.names:
            if self.get_package_info(pkg_name) is None:
                packages_to_install.add(pkg_name)

        if packages_to_install:
            rc, stdout, stderr = self._call_qubes_dom0_update(
                ["--action=install"],
                packages_to_install,
            )

            if rc != 0:
                self.module.exit_json(
                    msg="Failed to installed the specified package",
                    failures=stderr,
                    rc=1,
                )

            self._init_dnf()

            for pkg in packages_to_install:
                pkg_info = self.get_package_info(pkg)
                if pkg_info:
                    results.append(f"Installed: {pkg_info.get_nevra()}")
                else:
                    results.append(f"Installed: {pkg}")

        if results:
            self.module.exit_json(
                results=results,
                changed=True,
            )

        else:
            self.module.exit_json(msg="Nothing to do")

    def _process_remove(self):
        """Rely on local dnf to remove packages"""
        results = []
        goal = libdnf5.base.Goal(self.dnf_base)
        settings = libdnf5.base.GoalJobSettings()
        settings.set_group_with_name(True)

        for pkg_name in self.names:
            try:
                goal.add_remove(pkg_name, settings)
            except RuntimeError as e:
                self.module.fail_json(msg=str(e), failures=[], rc=1)

        try:
            transaction = goal.resolve()
        except RuntimeError as e:
            self.module.fail_json(msg=str(e), failures=[], rc=1)

        if transaction.get_problems():
            failures = [
                log_event.to_string()
                for log_event in transaction.get_resolve_logs()
            ]

            if (
                transaction.get_problems()
                & libdnf5.base.GoalProblem_SOLVER_ERROR
                != 0
            ):
                msg = "Depsolve Error occurred"
            else:
                msg = "Failed to install some of the specified packages"

            self.module.fail_json(
                msg=msg,
                failures=failures,
                rc=1,
            )

        for pkg in transaction.get_transaction_packages():
            results.append(f"Removed: {pkg.get_package().get_nevra()}")

        transaction.set_description(
            "ansible qubesos.core.qubes_dom0_update module"
        )
        result = transaction.run()
        if result != libdnf5.base.Transaction.TransactionRunResult_SUCCESS:
            self.module.fail_json(
                msg="Transaction failure",
                failures=[
                    "{}: {}".format(
                        transaction.transaction_result_to_string(result),
                        log,
                    )
                    for log in transaction.get_transaction_problems()
                ],
                rc=1,
            )

        if not results:
            self.module.exit_json(msg="Nothing to do")

        self.module.exit_json(changed=True, results=results)

    def _process_update(self):
        """Call qubes-dom0-update and read last transaction"""
        if self.names == ["*"]:
            rc, stdout, stderr = self._call_qubes_dom0_update(
                ["--action=update", "--clean"]
            )
        elif "*" in self.names:
            self.module.fail_json(msg="'*' cannot be used with other packages")
        else:
            rc, stdout, stderr = self._call_qubes_dom0_update(
                ["--clean"], self.names
            )

        # If system is up to date, an error may occur because nothing has
        # been downloaded. Check stderr to confirm
        # Fixed in recent versions of qubes-core-dom0-linux
        # https://github.com/QubesOS/qubes-core-admin-linux/pull/210
        if "Nothing to do." in (stdout + stderr):
            self.module.exit_json(msg="Nothing to do")

        if rc != 0:
            self.module.fail_json(
                msg="Failed to update the specified packages",
                rc=1,
                failures=stderr,
            )

        # Return last transaction details
        history = libdnf5.transaction.TransactionHistory(self.dnf_base)
        last_tx = history.list_all_transactions()[-1]
        changes = []
        for pkg in last_tx.get_packages():
            pkg_action = libdnf5.transaction.transaction_item_action_to_string(
                pkg.get_action()
            )
            pkg_nevra = pkg.to_string()
            changes.append(f"{pkg_action}: {pkg_nevra}")
        self.module.exit_json(
            changed=True,
            results=changes,
        )

    def _switch_audio_server(self):
        required_packages = {
            "pipewire": ["pipewire", "pipewire-pulseaudio"],
            "pulseaudio": ["pulseaudio"],
        }
        self._init_dnf()

        if all(
            self.get_package_info(pkg) is not None
            for pkg in required_packages[self.switch_audio_server]
        ):
            self.module.exit_json(msg="Nothing to do")

        rc, stdout, stderr = self._call_qubes_dom0_update(
            [f"--switch-audio-server-to={self.switch_audio_server}"]
        )

        if rc != 0:
            self.module.exit_json(
                msg=f"Failed to switch audio daemon to {self.switch_audio_server}",
                failures=stderr,
                rc=1,
            )

        self.module.exit_json(
            changed=True,
            msg=f"Audio daemon switched to {self.switch_audio_server}",
        )

    def get_package_info(self, pkg_name):
        """Extracted from is_installed() function of dnf5 module"""
        # settings = libdnf5.base.ResolveSpecSettings()
        installed_query = libdnf5.rpm.PackageQuery(self.dnf_base)
        installed_query.filter_installed()
        installed_query.filter_name(pkg_name)

        pkgs = list(installed_query)

        if len(pkgs) == 0:
            return None

        return pkgs[0]

    def run(self):
        if os.geteuid() != 0:
            self.module.fail_json(
                msg="This command has to be run under the root user.",
                failures=[],
                rc=1,
            )

        if self.names:
            if self.state in {"present", "installed"}:
                pkg_with_glob = [pkg for pkg in self.names if "*" in pkg]
                if pkg_with_glob:
                    self.module.fail_json(
                        msg="Globs are not supported with state present and installed",
                        failures=pkg_with_glob,
                        rc=1,
                    )
            self._init_dnf()

            if self.names:
                if self.state in {"installed", "present"}:
                    self._process_install()
                elif self.state in {"removed", "absent"}:
                    self._process_remove()
                elif self.state == "latest":
                    self._process_update()

        if self.switch_audio_server:
            self._switch_audio_server()


def main():
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        required_one_of=[["name", "switch_audio_server"]],
        mutually_exclusive=[["name", "switch_audio_server"]],
    )

    QubesDom0UpdateModule(module).run()


if __name__ == "__main__":
    main()
