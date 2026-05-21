VERSION := $(shell cat version)
QUBE_COLLECTION_DIR := $(DESTDIR)/usr/share/ansible/collections/ansible_collections/qubesos

_install-common:
	mkdir -p $(QUBE_COLLECTION_DIR)/core/plugins/connection
	mkdir -p $(QUBE_COLLECTION_DIR)/core/plugins/modules
	mkdir -p $(QUBE_COLLECTION_DIR)/core/plugins/module_utils
	install -m 644 ansible_collections/qubesos/core/plugins/connection/qubes.py $(QUBE_COLLECTION_DIR)/core/plugins/connection/qubes.py
	install -m 644 ansible_collections/qubesos/core/plugins/module_utils/*.py $(QUBE_COLLECTION_DIR)/core/plugins/module_utils/
	install -m 644 ansible_collections/qubesos/core/plugins/modules/*.py $(QUBE_COLLECTION_DIR)/core/plugins/modules/

	# Legacy files
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/connection
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/modules
	ln -s ../../collections/ansible_collections/qubesos/core/plugins/connection/qubes.py \
		$(DESTDIR)/usr/share/ansible/plugins/connection/qubes.py
	install -m 644 plugins/modules/qubesos.py $(DESTDIR)/usr/share/ansible/plugins/modules/qubesos.py


_install-dom0:
	mkdir -p $(DESTDIR)/etc/qubes-rpc/
	mkdir -p $(DESTDIR)/usr/lib/qubes/qubes-rpc/
	install -m 755 qubes-rpc/qubes-ansible-manage-policies $(DESTDIR)/usr/lib/qubes/qubes-rpc/qubes-ansible-manage-policies
	ln -s ../../usr/lib/qubes/qubes-rpc/qubes-ansible-manage-policies $(DESTDIR)/etc/qubes-rpc/ansible.CreateManagementPolicies
	ln -s ../../usr/lib/qubes/qubes-rpc/qubes-ansible-manage-policies $(DESTDIR)/etc/qubes-rpc/ansible.RemoveManagementPolicies

_install-security:
	mkdir -p $(DESTDIR)/usr/lib/qubes/
	mkdir -p $(QUBE_COLLECTION_DIR)/security/plugins/callback
	mkdir -p $(QUBE_COLLECTION_DIR)/security/plugins/strategy
	install -m 644 ansible_collections/qubesos/security/plugins/callback/qubesos_strategy_guard.py $(QUBE_COLLECTION_DIR)/security/plugins/callback/qubesos_strategy_guard.py
	install -m 644 ansible_collections/qubesos/security/plugins/strategy/qubes_proxy.py $(QUBE_COLLECTION_DIR)/security/plugins/strategy/qubes_proxy.py
	install -m 755 update-ansible-default-strategy $(DESTDIR)/usr/lib/qubes/update-ansible-default-strategy

	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/callback
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/strategy
	ln -s ../../collections/ansible_collections/qubesos/security/plugins/callback/qubesos_strategy_guard.py \
		$(DESTDIR)/usr/share/ansible/plugins/callback/qubesos_strategy_guard.py
	ln -s ../../collections/ansible_collections/qubesos/security/plugins/strategy/qubes_proxy.py \
		$(DESTDIR)/usr/share/ansible/plugins/strategy/qubes_proxy.py

_install-vm:
	mkdir -p $(DESTDIR)/etc/qubes-rpc/
	install -m 755 qubes-rpc/qubes.AnsibleVM $(DESTDIR)/etc/qubes-rpc/qubes.AnsibleVM

_install-tests:
	mkdir -p $(DESTDIR)/usr/share/ansible/tests/qubes
	install -m 644 tests/qubes/*.py $(DESTDIR)/usr/share/ansible/tests/qubes/
	install -m 644 tests/*.cfg $(DESTDIR)/usr/share/ansible/tests/

install-vm: _install-common _install-vm
install-vm-sec: install-vm _install-security
install-vm-all: install-vm-sec _install-tests
install-dom0: _install-common _install-security _install-dom0 _install-tests
