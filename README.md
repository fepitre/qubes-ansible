# Ansible plugins for QubesOS

This project provides Ansible plugins to interact and manage your 
[Qubes OS](https://qubes-os.org) system.

Those plugins are under active development, so the syntax and keywords may 
change in future releases. Contributions and feedback are welcome!

## Online documentation

The documentation is generated automatically and [is available in the Gitlab
pages of this project](https://qubesos.gitlab.io/qubes-ansible).

## Collections and plugins

This project provides **QubesOS** Ansible plugins under 2 collections:
  * `qubesos.core`: Everything related to **QubesOS** management (management 
modules, the connection plugin...).
  * `qubesos.security`: Ansible plugins related to **dom0** and **ManagementVM**
protection while executing management modules.


### Modules

  * `qubesos.core.qube`: Use this module for all tasks related to qubes management (create, destroy, start, set volumes, features, labels...)
  * `qubesos.core.command`: Non-idempotent commands, used for legacy compatibility, inventory generation...
  * `host_devices_facts`: Use this module to gather facts about available devices on the host. You likely want
to use this module to get a list of devices to assign to a VM with the `qubes.core.qube` module.

### ``qubesos.core.qubes`` connection plugin

Given the QubesOS architecture, using SSH to connect to your qubes for management is not relevant.
Instead, the Ansible connection plugin `qubesos.core.qube` allows to execute all Ansible stuff on
your target hosts using the [QubesOS qrexec framework](https://www.qubes-os.org/doc/qrexec/).

As you would do with the command `qvm_run`, Ansible will execute modules codes through the RPCs `qubes.VMShell` and 
`qubes.VMRootShell`.

### ``qubesos.secrurity.qubes_proxy`` strategy plugin

This strategy plugin must be used when Ansible is running on dom0 or ManagementVM to prevent any
security issue. The plugin acts as a router which will proxify play execution for a 
given qube into its management disposable VM.

Technically, the plugin builds an extract of the running playbook, extract host variables and roles
and run `ansible-playbook` on the management disposable.


Using this plugin ensures dom0 isolation from untrusted Ansible data (see https://github.com/QubesOS/qubes-issues/issues/10030).

__NOTE__ - this strategy is set as the default on dom0. Switching to another strategy 
will raise an error and interrupt Ansible execution.

## Installation

### Dom0

Install the following package: ``qubes-ansible``.

### Management DVM

The package ``qubes-ansible-vm`` (``qubes-ansible`` for Debian and Archlinux) must be installed 
in the templates used by your management DVM (``default-mgmt-dvm`` by default).

## Usage

``qubes.core.qubes`` and ``qubesos.security.qubes_proxy`` plugins work out of the box when installed using 
RPM. The strategy plugin will read the value of the ``hosts`` field 
in your playbooks and:
  - run the play locally when ``localhost`` is present in the list (dom0 management / ``qubesos`` module usage)
  - proxify play execution through the target disposable management VM that will automatically use the ``qubes`` connection plugin to run the tasks on the target

Using a custom `ansible.cfg` file may override Ansible strategy to `linear` would be detected 
by the `qubesos_strategy_guard` callback and would cause Ansible to stop. If using such file, 
add the following setting to ensure `qubes_proxy` strategy is used:
```
[defaults]
strategy=qubes_proxy
```

You can also put this line in your Play declaration:
```
strategy: qubesos.security.qubes_proxy
```

If extra files need to be present on the disposable VM to execute the playbook, you will need
to place those files in a role and call the role in your play using the `roles` keyword:
```
- hosts: work
  connection: qubes
  strategy: qubes_proxy
  roles:
  - my_role_which_will_copy_files_to_work
```

The repository structure should look the following:

```
ansible
|    playbook.yml
|    inventory
└─── roles
     └─── my_role_which_will_copy_files_to_work
          └── tasks
              └── main.yml
          └── files
              └── file_to_copy_to_work.txt    
```

__Note__: you can use symlink here if multiple roles need the same file. The qubes proxy will dereference
the symlink before building the archive. 

See the [examples](EXAMPLES.md) for sample playbooks and role tasks demonstrating common usage scenarios.

## Limitations

The proxy plugin may modify the behavior of your playbooks. Please notice the following indications and 
limitations:
* **Access to facts and variables from other hosts is not possible**: the proxy strategy builds a single
  host vars file containing a merged view of the target's host variables (i.e., variables issued from command line, group vars, host vars, inventory...).
  Therefore, attempting to access a variable not directly associated with that host will not work as it will
  not be present in the merged view.
* **Extra files may not be copied to the disposable VM**: the proxy plugin does not parse playbooks tasks so
  it has no idea which file needs to be copied to the disposable. However, play roles are copied to the dispvm.
* **Tasks executions are not synchronous but Play execution are**: behavious should be almost the same as the [free strategy](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/free_strategy.html).
* **Disposables output is not parsed**:
  * Play recap will reflect the number of plays ran for each host instead of the number of tasks
  * Only plain text output is supported

## Management VM (advanced)

You can use a dedicated qube to run your Ansible playbooks. Install the
package `qubes-ansible-admin`: it will deploy the `qubesos.core` collection and
all the `qubesos.security` plugins.

Then, you will need to write policies that fit your needs. 

First, you can add the following lines to `/etc/qubes/policy.d/include/admin-local-rwx`:
```
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
```

And append the following lines to `/etc/qubes/policy.d/include/admin-global-ro`:
```
mgmtvm @adminvm               allow target=dom0
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
```

This lets your ManagementVM manage the qubes it creates.

You may also want to allow your ManagementVM to read properties of sys vms and 
several templates. For example, when setting a netvm to a qube, the module checks 
if the target qube exits and provides network, which requires the mgmtvm to be 
able to read the target qube properties:

`/etc/qubes/policy.d/include/admin-global-ro`:
```
mgmtvm sys-net                allow target=dom0
mgmtvm sys-firewall           allow target=dom0
mgmtvm sys-usb                allow target=dom0
mgmtvm debian-13-xfce         allow target=dom0
mgmtvm fedora-42-xfce         allow target=dom0
```

`/etc/qubes/policy.d/include/admin-local-ro`:
```
mgmtvm sys-net                allow target=dom0
mgmtvm sys-firewall           allow target=dom0
mgmtvm sys-usb                allow target=dom0
mgmtvm debian-13-xfce         allow target=dom0
mgmtvm fedora-42-xfce         allow target=dom0
```

Then, create a policy file at `/etc/qubes/policy.d/30-mgmtvm.policy` and adjust 
its content to fit your security requirements:
```
# =================
# Qubes management
# =================

# The ManagementVM must be able to create new qubes and manage them
admin.vm.Create.AppVM            * mgmtvm dom0                   allow
admin.vm.Create.StandaloneVM     * mgmtvm dom0                   allow
admin.vm.Create.TemplateVM       * mgmtvm dom0                   allow


# You may want to allow to clone some template to create StandaloneVMs or new TemplateVMs
admin.vm.volume.CloneFrom        * mgmtvm debian-13-xfce         allow target=dom0
admin.vm.volume.CloneFrom        * mgmtvm fedora-42-xfce         allow target=dom0

# And to remove created ones
admin.vm.Remove                  * mgmtvm @tag:created-by-mgmtvm allow target=dom0

# Get available devices (qubesos.core.host_devices_facs)
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
```

## Legacy module `qubesos`

In previous versions of qubes-ansible, a single `qubesos` module were provided 
which has been split into the following 3 modules to improve reliability and
maintenance:
  * `qubesos.core.qube`
  * `qubesos.core.command`
  * `qubesos.core.host_devices_facts`

To prevent breaking changes, this module is still present in newer versions of 
**qubes-ansible** but is considered deprecated and may be removed in a future
release.

The module takes the same options and will try to translate to calls to the new 
modules with the appropriate options.

**Note**: to prevent unexpected behaviors in your playbooks, the option `wait`
has no more effect. The module will always wait for the actions (qube start, stop...)
to finish before starting a new task.

## Legacy plugins

Plugins from previous **qubes-ansible** versions were deployed in
`/usr/share/ansible/plugins`. Now these plugins are packaged in an Ansible collection 
in `/usr/share/ansible/collections/ansible_collections/qubesos`.

If you look into `/usr/share/ansible/plugins`, you will still find symlinks to 
the new plugins (those in the collections directory) making you able to write
your playbooks with any of those syntaxes:

```
- hosts: appvms
  connection: qubesos.core.qubes
  strategy: qubesos.security.qubes_proxy
  ...
  
 - hosts: appvms
   connection: qubes
   strategy: qubes_proxy
   ...
```

## License

This project is licensed under the GPLv3+ license. Please see the [LICENSE](LICENSE) file for the full license text.
