# Copyright (c) 2017 Ansible Project
# Copyright (C) 2018 Kushal Das
# Copyright (C) 2025 Frédéric Pierret (fepitre) <frederic@invisiblethingslab.com>
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

# Based on the buildah connection plugin

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = """
    connection: qubes
    short_description: Interact with an existing qube.
    description:
        - Run commands or put/fetch files to an existing qube using Qubes OS tools.
    author: Qubes OS Team <qubes-devel@googlegroups.com>
    version_added: "2.8"
    options:
      remote_addr:
        description:
            - vm name
        default: inventory_hostname
        vars:
            - name: inventory_hostname
            - name: ansible_host
      remote_user:
        description:
            - The user to execute as inside the qube.
        choices:
            - user
            - root
        default: user
        vars:
            - name: ansible_user
"""

import shutil
import subprocess

from ansible.module_utils.common.text.converters import to_bytes
from ansible.plugins.connection import ConnectionBase, ensure_connect

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display

    display = Display()


class Connection(ConnectionBase):
    """
    This connection plugin for Qubes OS uses the qvm-run executable
    to interact with QubesVMs.
    """

    transport = "qubes"
    has_pipelining = True

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        super(Connection, self).__init__(
            play_context, new_stdin, *args, **kwargs
        )
        self._remote_vmname = self._play_context.remote_addr
        self._connected = False
        # Use the provided remote_user if set; otherwise default to "user".
        self.user = (
            self._play_context.remote_user
            if self._play_context.remote_user
            else "user"
        )

    def _qubes(self, cmd: str, in_data: bytes = None):
        """
        Execute a command in the qube via qvm-run.

        :param cmd: Command string to execute on the remote system.
        :param in_data: Additional data to pass to the remote command's stdin.
        :param shell: Service type (e.g. qubes.VMShell or qubes.VMRootShell).
        :return: Tuple of (returncode, stdout, stderr).
        """
        display.vvvv(f"CMD: {cmd}")
        if not cmd.endswith("\n"):
            cmd += "\n"

        if shutil.which("qrexec-client-vm"):
            local_cmd = [
                "qrexec-client-vm",
                self._remote_vmname,
            ]
        else:
            local_cmd = [
                "qvm-run",
                "--no-gui",
                "--pass-io",
                "--service",
                self._remote_vmname,
            ]
        # The Ansible module framework catches invalid remote_user values
        if self.user == "root":
            local_cmd.append("qubes.VMRootShell")
        else:
            local_cmd.append("qubes.VMShell")
        local_cmd_bytes = [
            to_bytes(arg, errors="surrogate_or_strict") for arg in local_cmd
        ]
        display.vvvv(f"Local cmd: {local_cmd_bytes}")
        display.vvv(f"RUN {local_cmd_bytes}", host=self._remote_vmname)

        # Combine the command and any additional input data
        combined_input = to_bytes(cmd, errors="surrogate_or_strict")
        if in_data:
            combined_input += in_data

        try:
            result = subprocess.run(
                local_cmd_bytes,
                input=combined_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except Exception as e:
            display.error(f"Error executing command via qvm-run: {e}")
            raise

        return result.returncode, result.stdout, result.stderr

    def _connect(self):
        """
        Establish the connection (no persistent connection is maintained).
        """
        super(Connection, self)._connect()
        self._connected = True

    @ensure_connect
    def exec_command(self, cmd, in_data=None, sudoable=False):
        """
        Run the specified command in the QubesVM.

        :param cmd: Command to run.
        :param in_data: Data to send to stdin.
        :param sudoable: Not used in this plugin.
        :return: Tuple (returncode, stdout, stderr).
        """
        display.vvvv(f"CMD IS: {cmd}")
        rc, stdout, stderr = self._qubes(cmd, in_data)
        display.vvvvv(
            f"STDOUT {stdout!r} STDERR {stderr!r}", host=self._remote_vmname
        )
        return rc, stdout, stderr

    def put_file(self, in_path, out_path):
        """
        Copy a local file from 'in_path' to the remote VM at 'out_path'.
        """
        display.vvv(f"PUT {in_path} TO {out_path}", host=self._remote_vmname)
        with open(in_path, "rb") as fobj:
            source_data = fobj.read()

        retcode, _, _ = self._qubes(f'cat > "{out_path}"\n', source_data)
        if retcode != 0:
            raise RuntimeError(f"Failed to put_file to {out_path}")

    def fetch_file(self, in_path, out_path):
        """
        Retrieve a file from the remote VM located at 'in_path' and save it to 'out_path'.
        """
        display.vvv(f"FETCH {in_path} TO {out_path}", host=self._remote_vmname)
        if shutil.which("qrexec-client-vm"):
            cmd_args = [
                "qrexec-client-vm",
                self._remote_vmname,
                "qubes.VMShell",
            ]
        else:
            cmd_args = [
                "qvm-run",
                "--pass-io",
                "--no-gui",
                "--service",
                self._remote_vmname,
                "qubes.VMShell",
            ]
        with open(out_path, "wb") as fobj:
            result = subprocess.run(
                cmd_args, stdout=fobj, input=f"cat {in_path}".encode()
            )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to fetch file to {out_path}")

    def close(self):
        """
        Close the connection.
        """
        super(Connection, self).close()
        self._connected = False
