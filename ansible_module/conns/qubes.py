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

# Based on the buildah connection plugin

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = """
    connection: qubes
    short_description: Interact with an existing QubesOS AppVM

    description:
        - Run commands or put/fetch files to an existing Qubes AppVM using qubes tools.

    author: Kushal Das (@kushaldas)

    version_added: "2.8"

    options:
      remote_addr:
        description:
            - vm name
        default: inventory_hostname
        vars:
            - name: ansible_host
      remote_user:
        description:
            - The user to execute as inside the vm.
        default: user
        vars:
            - name: ansible_user
#        keyword:
#            - name: hosts
"""

import shlex
import shutil

import os
import base64
import subprocess

import ansible.constants as C
from ansible.module_utils._text import to_bytes, to_native
from ansible.plugins.connection import ConnectionBase, ensure_connect


try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


# this _has to be_ named Connection
class Connection(ConnectionBase):
    """This is a connection plugin for qubes: it uses qubes-run-vm binary to interact with the containers."""

    # String used to identify this Connection class from other classes
    transport = 'qubes'
    has_pipelining = True

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        super(Connection, self).__init__(play_context, new_stdin, *args, **kwargs)

        self._remote_vmname = self._play_context.remote_addr
        self._connected = False
        # Default username in Qubes
        self.user = "user"
        if self._play_context.remote_user:
            self.user = self._play_context.remote_user

    def _qubes(self, cmd=None, in_data=None, shell="qubes.VMShell"):
        """run qvm-run executable

        :param cmd: cmd string for remote system
        :param in_data: data passed to qvm-run-vm's stdin
        :return: return code, stdout, stderr
        """
        display.vvvv("CMD: ", cmd)
        if not cmd.endswith("\n"):
            cmd = cmd + "\n"
        local_cmd = []

        # For dom0
        local_cmd.extend(["qvm-run", "--pass-io", "--service"])
        if self.user != "user":
            # Means we have a remote_user value
            local_cmd.extend(["-u", self.user])

        local_cmd.append(self._remote_vmname)

        local_cmd.append(shell)

        local_cmd = [to_bytes(i, errors='surrogate_or_strict') for i in local_cmd]

        display.vvvv("Local cmd: ", local_cmd)

        display.vvv("RUN %s" % (local_cmd,), host=self._remote_vmname)
        p = subprocess.Popen(local_cmd, shell=False, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Here we are writing the actual command to the remote bash
        p.stdin.write(to_bytes(cmd, errors='surrogate_or_strict'))
        stdout, stderr = p.communicate(input=in_data)
        return p.returncode, stdout, stderr

    def _connect(self):
        """No persistent connection is being maintained."""
        super(Connection, self)._connect()
        self._connected = True

    @ensure_connect
    def exec_command(self, cmd, in_data=None, sudoable=False):
        """Run specified command in a running QubesVM """
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)

        display.vvvv("CMD IS: %s" % cmd)

        rc, stdout, stderr = self._qubes(cmd)

        display.vvvvv("STDOUT %r STDERR %r" % (stderr, stderr))
        return rc, stdout, stderr

    def put_file(self, in_path, out_path):
        """ Place a local file located in 'in_path' inside VM at 'out_path' """
        super(Connection, self).put_file(in_path, out_path)
        display.vvv("PUT %s TO %s" % (in_path, out_path), host=self._remote_vmname)

        with open(in_path, "rb") as fobj:
            source_data = fobj.read()

        retcode, dummy, dummy = self._qubes('cat > "{0}"\n'.format(out_path), source_data, "qubes.VMRootShell")
        # if qubes.VMRootShell service not supported, fallback to qubes.VMShell and
        # hope it will have appropriate permissions
        if retcode == 127:
            retcode, dummy, dummy = self._qubes('cat > "{0}"\n'.format(out_path), source_data)

        if retcode != 0:
            raise RuntimeError('Failed to put_file to {0}'.format(out_path))

    def fetch_file(self, in_path, out_path):
        """Obtain file specified via 'in_path' from the container and place it at 'out_path' """
        super(Connection, self).fetch_file(in_path, out_path)
        display.vvv("FETCH %s TO %s" % (in_path, out_path), host=self._remote_vmname)

        # We are running in dom0
        cmd_args_list = ["qvm-run", "--pass-io", self._remote_vmname, "cat {0}".format(in_path)]
        with open(out_path, "wb") as fobj:
            p = subprocess.Popen(cmd_args_list, shell=False, stdout=fobj)
            p.communicate()
            if p.returncode != 0:
                raise RuntimeError('Failed to fetch file to {0}'.format(out_path))

    def close(self):
        """ Closing the connection """
        super(Connection, self).close()
        self._connected = False
