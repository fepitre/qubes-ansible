#!/bin/bash

set -e

function err_ex() {
    echo "$1" >&2
    exit 1
}

default_mgmt_dispvm="$(qubes-prefs management_dispvm)"
default_mgmt_dispvm_template="$(qvm-prefs "$default_mgmt_dispvm" template)"
[[ "$default_mgmt_dispvm_template" == fedora-* ]] || err_ex "unsupported template $default_mgmt_dispvm_template"
fedora_ver="$(echo "$default_mgmt_dispvm_template" | cut -d- -f2)"

repo_dir="artifacts/repository/vm-fc${fedora_ver}"
[[ -d "$repo_dir" ]] || err_ex "'$repo_dir' not found"

qvm-create --class AppVM --property maxmem=800 --label black --template "$default_mgmt_dispvm_template" mgmtvm

find $repo_dir -name 'qubes-ansible-*.noarch.rpm' \
    -not -name  'qubes-ansible-vm*.noarch.rpm' \
    -exec qvm-copy-to-vm mgmtvm "{}" \;


fedora_ver="$(echo "$default_mgmt_dispvm_template" | cut -d- -f2)"

repo_dir="artifacts/repository/vm-fc${fedora_ver}"
[[ -d "$repo_dir" ]] || err_ex "'$repo_dir' not found"

qvm-run -p -u root --no-gui mgmtvm "dnf update -y"
qvm-run -p -u root --no-gui  mgmtvm "dnf install -y python3-coverage /home/user/QubesIncoming/dom0/*.rpm"

cat << EOF >> /etc/qubes/policy.d/include/admin-local-rwx
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
EOF

cat << EOF >> /etc/qubes/policy.d/include/admin-global-ro
mgmtvm @adminvm               allow target=dom0
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
mgmtvm sys-net                allow target=dom0
mgmtvm sys-firewall           allow target=dom0
mgmtvm sys-usb                allow target=dom0
mgmtvm fedora-42-xfce         allow target=dom0
mgmtvm debian-13-xfce         allow target=dom0
EOF

cat << EOF >> /etc/qubes/policy.d/include/admin-local-ro
mgmtvm sys-net                allow target=dom0
mgmtvm sys-firewall           allow target=dom0
mgmtvm sys-usb                allow target=dom0
mgmtvm fedora-42-xfce         allow target=dom0
mgmtvm debian-13-xfce         allow target=dom0
EOF

cat << EOF > /etc/qubes/policy.d/30-mgmtvm.policy
# =================
# Qubes management
# =================

# The ManagementVM must be able to create new qubes and manage them
admin.vm.Create.AppVM            * mgmtvm dom0                   allow
admin.vm.Create.StandaloneVM     * mgmtvm dom0                   allow
admin.vm.Create.TemplateVM       * mgmtvm dom0                   allow

# You may want to allow the ManagementVM to clone some templates to create StandaloneVMs or new TemplateVMs
admin.vm.volume.CloneFrom        * mgmtvm debian-13-xfce         allow target=dom0
admin.vm.volume.CloneFrom        * mgmtvm fedora-42-xfce         allow target=dom0

# And to remove created ones
admin.vm.Remove                  * mgmtvm @tag:created-by-mgmtvm allow target=dom0

# Get available devices
admin.vm.device.pci.Available    * mgmtvm dom0 allow
admin.vm.device.block.Available  * mgmtvm dom0 allow


# You may want to assign devices to your qubes
admin.vm.device.pci.Assign       * mgmtvm @tag:created-by-mgmtvm allow target=dom0

# =============
# Proxy Plugin
# =============

# The proxy creates a dispvm from the management dvm of the managed qubes
# Copy these lines for each value of the management_dispvm preference used by your qubes.
admin.vm.Create.DispVM           +default-mgmt-dvm mgmtvm dom0 allow
admin.vm.property.Get            +label            mgmtvm default-mgmt-dvm allow target=dom0

# Allow mgmtvm to call RPC managing dynamic policy creation allowing to run the
# connection plugin
ansible.CreateManagementPolicies * mgmtvm @tag:created-by-mgmtvm allow target=dom0
ansible.RemoveManagementPolicies * mgmtvm @tag:created-by-mgmtvm allow target=dom0

# The proxy needs to copy and execute playbooks on DispVMs
qubes.AnsibleVM                  * mgmtvm @tag:created-by-mgmtvm allow
qubes.Filecopy                   * mgmtvm @tag:created-by-mgmtvm allow

# For tests that are using linear strategy instead of qubes proxy
qubes.VMShell                    * mgmtvm @tag:created-by-mgmtvm allow
qubes.VMRootShell                * mgmtvm @tag:created-by-mgmtvm allow

# Some tests need to access dom0 properties
admin.vm.property.Get            * mgmtvm dom0                   allow
EOF
