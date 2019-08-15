#!/usr/bin/python

# Copyright: (c) 2019, Lars Liedtke <liedtke@punkt.de>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: iocage

short_description: Use iocage to manage FreeBSD jails

version_added: "2.8" # TODO: check me

description:
    - >
        "In FreeBSD jails are chroot environments on steroids,
        incl. e.g high security and an own network stack.
        iocage (https://github.com/iocage/iocage) is a jail
        manager totally written in python using ZFS as storage
        backend. This module strives to automate jail management
        with iocage and ansible"

options:
    name:
        description:
            - Your jail's name
        required: true
    release:
        description:
            - The FreeBSD release to base your jail on
        required: false
    zpool:
        description:
            - Activate given ZPool if needed
        required: false
    started:
        description:
            - Define ff the jail should be running
        default:
            - true
        required: false
    boot:
        description:
            - Define if the jail should be started on host boot
        required: false

author:
    - Lars Liedtke (@Corvan)
'''

EXAMPLES = '''
# Pass in a message
- name: Test with a message
  my_test:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_test:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_test:
    name: fail me
'''

RETURN = '''
original_message:
    description: The original name param that was passed in
    type: str
    returned: always
message:
    description: The output message that the test module generates
    type: str
    returned: always
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.basic import to_text
from typing import Dict, List


class Jail:
    def __init__(self, name: str, release: str = None, template: str = None, started: bool = None,
                 boot: bool = None):
        if release is None and template is None:
            raise ValueError("You have to pass either release or template")
        self.name = name
        self.release = release
        self.template = template
        self.started = started
        self.boot = boot


class IOCage:

    IOCAGE = ["iocage"]
    LIST_COMMAND = list(IOCAGE)
    LIST_COMMAND.extend(list(["list", "-Hl"]))

    def __init__(self, module: AnsibleModule, result: Dict, zpool: str = None):
        super(IOCage, self).__init__()
        self.module = module
        self.result = result
        self.zpool = zpool

    def activate(self):
        if self.zpool is None:
            raise ValueError("No ZPool for activation given")
        self.module.run_command(["iocage", "activate", self.zpool], check_rc=True)

    def exists(self, jail: Jail) -> bool:
        stdout = self.module.run_command(IOCage.LIST_COMMAND, check_rc=True)[1]
        output = IOCage._parse_list_output(to_text(stdout))
        for line in output:
            if line.get('name') == jail.name:
                return True
        return False

    def create(self, jail: Jail):
        command = IOCage.IOCAGE
        command.extend(list(["create",
                             "-n", jail.name]))

        if jail.release:
            command.extend(["-r", jail.release])
        elif jail.template:
            command.extend(["-t", jail.template])

        if jail.boot:
            command.extend(["-o", "boot=on"])

        self.module.run_command(command, check_rc=True)

    def is_started(self, jail: Jail) -> bool:
        stdout = self.module.run_command(IOCage.LIST_COMMAND, check_rc=True)[1]
        output = IOCage._parse_list_output(to_text(stdout))
        for line in output:
            if line.get('name') == jail.name and line.get('state') == "up":
                return True
        return False

    def start(self, jail: Jail):
        command = list(IOCage.IOCAGE)
        command.extend(list(["start", jail.name]))
        self.module.run_command(command, check_rc=True)

    def stop(self, jail: Jail):
        command = list(IOCage.IOCAGE)
        command.extend(["stop", jail.name])
        self.module.run_command(command, check_rc=True)

    @staticmethod
    def _parse_list_output(stdout) -> List[Dict]:
        output = list()
        for line in stdout.splitlines():
            elements = line.split("\t")
            output.append(dict(jailid=elements[0],
                               name=elements[1],
                               boot=elements[2],
                               state=elements[3],
                               type=elements[4],
                               release=elements[5],
                               ipv4=elements[6],
                               ipv6=elements[7],
                               template=elements[8],
                               basejail=elements[9]))
        return output


def run_module(module: AnsibleModule, result: Dict):
    result['original_message'] = module.params['name']

    iocage = IOCage(module, result, module.params.get('zpool'))
    if iocage.zpool:
        iocage.activate()
        result['changed'] = True
        message = str("ZPool %s activated").format(iocage.zpool)
        result['message'] = str("%s, %s").format(result['message'], message)

    try:
        jail = Jail(name=module.params['name'],
                    release=module.params.get('release'),
                    started=module.params.get('started'),
                    boot=module.params.get('boot'))
    except ValueError as ve:
        module.exit_json(msg=str(ve))
    if not iocage.exists(jail):
        iocage.create(jail)
        result['changed'] = True
        message = "Jail %s created".format(jail.name)
        result['message'] = str("%s, %s").format(result['message'], message)
        result['changed'] = True

    if jail.started and not iocage.is_started(jail):
        iocage.start(jail)
        result['changed'] = True
        message = str("Jail %s started").format(jail.name)
        result['message'] = str("%s, %s").format(result['message'], message)

    if module.params['name'] == 'fail me':
        module.fail_json(msg='You requested this to fail', **result)

    return result


def main():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        name=dict(type='str', required=True),
        release=dict(type='str', required=False),
        zpool=dict(type='str', required=False),
        started=dict(type='bool', required=False, default=False),
        boot=dict(type='bool', required=False)
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        original_message='',
        message=''
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    result = run_module(module, result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


if __name__ == '__main__':
    main()
