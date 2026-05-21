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

find $repo_dir -name 'qubes-ansible-*.noarch.rpm' \
    -not -name  'qubes-ansible-admin*.noarch.rpm' \
    -not -name  'qubes-ansible-tests*.noarch.rpm' \
    -exec qvm-copy-to-vm "$default_mgmt_dispvm_template" "{}" \;

qvm-run --pass-io "$default_mgmt_dispvm_template" "sudo dnf install -y /home/user/QubesIncoming/dom0/*.rpm"
qvm-shutdown --wait "$default_mgmt_dispvm_template"
