#!/usr/bin/python

# Copyright: (c) 2019, Lars Liedtke <liedtke@punkt.de>
# GNU General Public License v3.0+
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: iocage

short_description: Use iocage to manage FreeBSD jails

version_added: "2.x" # TODO: check me

description: >
    In FreeBSD jails are chroot environments on steroids,
    incl. e.g high security and an own network stack 
    U(https://www.freebsd.org/doc/en_US.ISO8859-1/books/handbook/jails.html).
    iocage U(https://github.com/iocage/iocage) is a jail
    manager totally written in python using ZFS as storage
    backend. This module strives to automate jail management
    with iocage and ansible. Find more on iocage at
    U(https://iocage.readthedocs.io/en/latest/index.html) and
    in iocage(8) of the FreeBSD Manual

options:
    zpool:
        description: Activate given ZPool if needed
        type: str
        required: false
    uuid:
        description: >
            Set this if you don't want iocage to set a random one.
            If you don't set a uuid but set I(name) the name will 
            be used as uuid 
        type: str
        required: false
    name:
        description: Your jail's name
        type: str
        required: false
    state:
        description: Define in which state your jail should be in
        type: str
        choices:
            present: >
                The jail is present but not running.
                It will be created, if it is not present yet.
                It will be stopped, if it is present and running.
            started: >
                The jail is present and running.
                It will be created if it is not present yet.
                It will be started if it is not running.
            absent: >
                The jail will be destroyed, if it is present.
         default: started
        required: false
    release:
        description: >
            The FreeBSD release to base your jail on, 
            see U(https://www.freebsd.org/relnotes.html)
        required: false
        type: str
    template:
        description: > 
            If you created a template jail, you can pass its name here
            to base this jail on the template,
            see U(https://iocage.readthedocs.io/en/latest/jailtypes.html#template)
        type: str
    empty:
        description: >
            Create an empty jail,
            see U(https://iocage.readthedocs.io/en/latest/jailtypes.html#empty)
        type: bool
    properties:
        description: > 
            iocage offers a lot of properties to further define jail 
            configurations, see iocage(8) in the FreeBSD Manual. The suboptions 
            are mirroring the values properties can be set to using the set 
            command or passing them with create, see also 
            U(https://iocage.readthedocs.io/en/latest/basic-use.html#create-a-jail)
        type: dict
        required: false
author:
    - Lars Liedtke (@Corvan)
'''

EXAMPLES = '''
- name: ensure jail is created
  iocage:
    name: test
    release: 12.0-RELEASE
    
- name: > 
      ensure jail is created with a certain 
      zfs pool activated
  iocage:
    zpool: zroot
    name: test
    release: 12.0-RELEASE

- name: Ensure jail is started
  iocage:
    name: test
    release: 12.0-RELEASE
    state: started


- name: Ensure jail is stopped
  iocage:
    name: test
    release: 12.0-RELEASE
    state: present

- name: Ensure jail is destroyed
  iocage:
    name: test
    state: absent
    
- name: ensure jail properties are set
  iocage:
    name: test
    state: present
    release: 12.0-RELEASE
    properties:
      boot: "on"
      vnet: "on"
      ip4_addr: "192.168.1.2/24"
      defaultrouter: "192.168.1.1"
      '''

RETURN = '''
changed: 
    description: indicator if ansible has changed a jail
    type: bool
    returned: always    
failed: 
    description: indicator if everything went ok
    type: bool
    returned: always
message: 
    description: what steps have been changed
    type: str
    returned: always but empty string if nothing has been done
name:
    description: the jail's name
    type: str
    returned: if the jail has got a name
properties: 
    description: >
        all the jail's properties, see iocage(8) for
        explanations about their meanings 
    type: dict
    returned: if the jail exists after a successful run
release: 
    description: the FreeBSD release the jail is based upon
    type: str
    returned: if the jail exists after a successful run
state:
    description: the jail's state, see I(state)
    type: str
    returned: if the jail exists after a successful run
uuid:
    description: the jail's uuid
    type: str
    returned: if the jail exists after a successful run
zpool:
    description: the zpool activated for iocage
    type: str
    returned: if the jail exists after a successful run'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.basic import to_text
from typing import Dict
from typing import List


class Jail:

    def __init__(self, name: str, uuid: str = None, release: str = None, template: str = None,
                 empty: bool = False, state: str = False,
                 properties: Dict = None):
        self.name = name
        self.uuid = uuid
        self.release = release
        self.template = template
        self.empty = empty
        self.state = state
        self.properties = properties


class IOCage:
    IOCAGE = ["iocage"]

    def __init__(self, module: AnsibleModule, result: Dict, zpool: str = None):
        self.module = module
        self.result = result
        self.zpool = zpool

    def is_activated(self, zpool: str) -> bool:
        """
        Check if the given zpool has been activated for use with iocage
        """
        stdout = self.get_activated_zpool()
        if stdout == zpool:
            return True
        return False

    def get_activated_zpool(self) -> str:
        """
        Return the zpool, which has been activated to use with iocage
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["get", "-p"]))
        stdout = self.module.run_command(command, check_rc=True)[1]
        return stdout.strip()

    def activate(self, zpool: str):
        """
        Activate the given zpool
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["activate", zpool]))
        self.module.run_command(command, check_rc=True)

    def exists(self, jail: Jail) -> bool:
        """
        Check if the given jail exists
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["list", "-Hl"]))
        stdout = self.module.run_command(command, check_rc=True)[1]
        try:
            output = IOCage._parse_list_output(to_text(stdout))
        except StopIteration:
            return False
        for line in output:
            if line.get('name') == jail.name if jail.name else jail.uuid:
                return True
        return False

    def create(self, jail: Jail):
        """
        Create a jail after the given definition
        """
        command = list(IOCage.IOCAGE)
        command.append("create")

        if jail.name:
            command.extend(list(["-n", jail.name]))
        if jail.uuid:
            command.extend(list(["-u", jail.uuid]))
        if jail.release:
            command.extend(list(["-r", jail.release]))
        elif jail.template:
            command.extend(list(["-t", jail.template]))
        elif jail.empty:
            command.append("-e")

        if jail.properties:
            for k, v in jail.properties.items():
                if k and v:
                    command.append("%s=%s" % (k, v))

        self.module.run_command(command, check_rc=True)

    def destroy(self, jail: Jail):
        """
        Destroy the given jail
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["destroy", "-f",
                             jail.name if jail.name else jail.uuid]))
        self.module.run_command(command, check_rc=True)

    def is_started(self, jail: Jail) -> bool:
        """
        Check if the given jail is running
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["list", "-Hl"]))
        stdout = self.module.run_command(command, check_rc=True)[1]
        output = IOCage._parse_list_output(to_text(stdout))
        for line in output:
            if line.get('name') == jail.name \
                    and line.get('state') == "up":
                return True
        return False

    def start(self, jail: Jail):
        """
        Start the given jail
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["start",
                             jail.name if jail.name else jail.uuid]))
        self.module.run_command(command, check_rc=True)

    def stop(self, jail: Jail):
        """
        Stop the given jail
        """
        command = list(IOCage.IOCAGE)
        command.extend(list(["stop", "-f",
                             jail.name if jail.name else jail.uuid]))
        self.module.run_command(command, check_rc=True)

    def has_changed_properties(self, jail: Jail) -> bool:
        """
        Check if the given jail has got properties, which are different from the ones in the
        given jail definition
        """
        if jail.properties is None:
            return False
        for k, v in jail.properties.items():
            if k and v:
                command = list(IOCage.IOCAGE)
                command.extend(list(["get", k,
                                     jail.name if jail.name else jail.uuid]))
                stdout = self.module.run_command(command, check_rc=True)[1]
                if stdout.strip() != v:
                    return True
        return False

    def get_properties(self, jail: Jail, properties_to_get: List[str] = None) -> Dict:
        """
        Get the jail's properties
        :param properties_to_get: a list of the names of the properties.
               If it is None or ["all"], all properties of the jail are
               retuned
        """
        command = list(IOCage.IOCAGE)
        properties_got = dict()
        if (properties_to_get is None or len(properties_to_get) == 0) \
                or len(properties_to_get) == 1 and properties_to_get[0] == "all":
            command.extend(list(["get", "all",
                                 jail.name if jail.name else jail.uuid]))
            stdout = self.module.run_command(command, check_rc=True)[1]
            for line in stdout.splitlines():
                IOCage._add_line_to_properties(properties_got, line.strip())
        else:
            for p in properties_to_get:
                pcommand = list(command)
                pcommand.extend(list(["get", p]))
                stdout = self.module.run_command(command, check_rc=True)[1]
                IOCage._add_line_to_properties(properties_got, stdout.strip())
        return properties_got

    def set_properties(self, jail: Jail):
        """
        Set the jail's properties to the values given in the definition
        """
        for k, v in jail.properties.items():
            if k and v:
                get_command = list(IOCage.IOCAGE)
                get_command.extend(list(["get", k, jail.name]))
                stdout = self.module.run_command(get_command, check_rc=True)[1]
                if stdout.strip() != v:
                    set_command = list(IOCage.IOCAGE)
                    set_command.extend(list(["set", "%s=%s" % (k, v),
                                             jail.name if jail.name else jail.uuid]))
                    self.module.run_command(set_command, check_rc=True)

    @staticmethod
    def _parse_list_output(stdout: str) -> List[Dict]:
        """
        Parse the output of the command 'iocage list'
        :param stdout: the command's standard out
        :return: a list of dicts, which have got the single items per jail
        """
        output = list()
        for line in stdout.splitlines():
            items = line.split("\t")
            if len(items) == 0:
                raise StopIteration
            output.append(dict(jailid=items[0],
                               name=items[1],
                               boot=items[2],
                               state=items[3],
                               type=items[4],
                               release=items[5],
                               ipv4=items[6],
                               ipv6=items[7],
                               template=items[8],
                               basejail=items[9]))
        return output

    @staticmethod
    def _add_line_to_properties(properties: Dict, line: str):
        """
        Add a line of the output of 'iocage get' as an item to the properties dict
        :param properties:
        :param line:
        """
        items = line.split(":")
        properties[items[0]] = items[1]


def run_module(module: AnsibleModule, result: Dict):
    iocage = IOCage(module, result, module.params.get('zpool'))
    if iocage.zpool and not iocage.is_activated(iocage.zpool):
        iocage.activate(iocage.zpool)
        result['changed'] = True
        message = str("ZPool %s activated" % iocage.zpool)
        result['message'] = str("%s, %s" % (result['message'], message)) \
            if result['message'] else message

    try:
        jail = Jail(name=module.params['name'],
                    uuid=module.params['uuid'],
                    release=module.params.get('release'),
                    template=module.params.get('template'),
                    empty=module.params.get('empty'),
                    state=module.params.get('state'),
                    properties=module.params.get('properties'))
    except ValueError as ve:
        module.fail_json(msg=str(ve))

    if (jail.state == "present" or jail.state == "started") and not iocage.exists(jail):
        iocage.create(jail)
        result['changed'] = True
        message = "Jail '%s' created" % jail.name
        result['message'] = str("%s, %s" % (result['message'], message)) \
            if result['message'] else message

    if jail.state == "started" and not iocage.is_started(jail):
        if iocage.has_changed_properties(jail):
            iocage.set_properties(jail)
        iocage.start(jail)
        result['changed'] = True
        message = str("Jail '%s' started" % jail.name)
        result['message'] = str("%s, %s" % (result['message'], message)) \
            if result['message'] else message

    if jail.state == "started" and iocage.is_started(jail) and iocage.has_changed_properties(jail):
        iocage.stop(jail)
        iocage.set_properties(jail)
        iocage.start(jail)
        result['changed'] = True
        message = str("Jail '%s' started" % jail.name)
        result['message'] = str("%s, %s" % (result['message'], message)) \
            if result['message'] else message

    if jail.state == "present" and iocage.is_started(jail):
        iocage.stop(jail)
        if iocage.has_changed_properties(jail):
            iocage.set_properties(jail)
        result['changed'] = True
        message = str("Jail '%s' stopped" % jail.name)
        result['message'] = str("%s, %s" % (result['message'], message)) \
            if result['message'] else message

    if jail.state == "absent" and iocage.exists(jail):
        if iocage.is_started(jail):
            iocage.stop(jail)
            result['changed'] = True
            message = str("Jail '%s' stopped" % jail.name)
            result['message'] = str("%s, %s" % (result['message'], message)) \
                if result['message'] else message
        iocage.destroy(jail)
        result['changed'] = True
        message = str("Jail '%s' destroyed" % jail.name)
        result['message'] = str("%s, %s" % (result['message'], message)) \
            if result['message'] else message

    if iocage.exists(jail):
        result.update(dict({"name": jail.name,
                            "uuid": jail.uuid,
                            "zpool": iocage.get_activated_zpool(),
                            "release": jail.release,
                            "state": jail.state,
                            "properties": iocage.get_properties(jail)}))

    return result


def main():
    module_arguments = dict(
        zpool=dict(type='str', required=False),
        name=dict(type='str', required=False),
        uuid=dict(type='str', required=False),
        state=dict(type='str', required=False, default="started",
                   choices=list(["present", "absent", "started"])),
        release=dict(type='str'),
        template=dict(type='str'),
        empty=dict(type='bool', default=False),
    )
    if module_arguments.get('name') and not module_arguments.get('uuid'):
        module_arguments['uuid'] = module_arguments['name']

    # Some of the properties could have been dealt with by using
    # bool; but they were set to the same types and values iocage
    # expects to mimic its interface as is.
    # The order of the properties is the same as in iocage(8)
    # Only choices are set, where applicable because defaults will be set by
    # iocage. That makes it easier as well to check if options are set by user.
    iocage_properties = dict(bpf=dict(type='str', choices=list(["on", "off"])),
                             depends=dict(type='str'),
                             dhcp=dict(type='str', choices=list(["on", "off"])),
                             pkglist=dict(type='str'),
                             vnet=dict(type='str', choices=list(["on", "off"])),
                             ip4_addr=dict(type='str'),
                             ip4_saddrsel=dict(type='int', choices=list([0, 1])),
                             ip4=dict(type=str, choices=list(["new", "disable", "inherit"])),
                             defaultrouter=dict(type='str'),
                             defaultrouter6=dict(type='str'),
                             resolver=dict(type=str),
                             ip6_addr=dict(type='str'),
                             ip6_saddrsel=dict(type='int', choices=list([0, 1])),
                             interfaces=dict(type='str'),
                             host_domainname=dict(type='str'),
                             host_hostname=dict(type='str'),
                             exec_fib=dict(type='int', choices=list([0, 1])),
                             devfs_ruleset=dict(type='int'),
                             mount_devfs=dict(type='int', choices=list([0, 1])),
                             exec_start=dict(type='str'),
                             exec_stop=dict(type='str'),
                             exec_prestart=dict(type='str'),
                             exec_prestop=dict(type='str'),
                             exec_poststop=dict(type='str'),
                             exec_poststart=dict(type='str'),
                             exec_clean=dict(type='int', choices=list([0, 1])),
                             exec_timeout=dict(type='int'),
                             stop_timeout=dict(type='int'),
                             exec_jail_user=dict(type='str'),
                             exec_system_jail_user=dict(type='int', choices=list([0, 1])),
                             exec_system_user=dict(type='str'),
                             mount_fdescfs=dict(type='int', choices=list([0, 1])),
                             mount_procfs=dict(type='int', choices=list([0, 1])),
                             enforce_statfs=dict(type='int', choices=list([0, 1, 2])),
                             children_max=dict(type='int'),
                             login_flags=dict(type='str'),
                             jail_zfs=dict(type='str', choices=list(["on", "off"])),
                             jail_zfs_dataset=dict(type='str'),
                             securelevel=dict(type=int, choices=list([-1, 0, 1, 2, 3])),
                             allow_set_hostname=dict(type='int', choices=list([0, 1])),
                             allow_sysvipc=dict(type='int', choices=list([0, 1])),
                             sysvmsg=dict(type=str, choices=list(["new", "disable", "inherit"])),
                             sysvsem=dict(type=str, choices=list(["new", "disable", "inherit"])),
                             sysvshm=dict(type=str, choices=list(["new", "disable", "inherit"])),
                             allow_raw_sockets=dict(type='int', choices=list([0, 1])),
                             allow_chflags=dict(type='int', choices=list([0, 1])),
                             allow_mount=dict(type='int', choices=list([0, 1])),
                             allow_mount_devfs=dict(type='int', choices=list([0, 1])),
                             allow_mount_fusefs=dict(type='int', choices=list([0, 1])),
                             allow_mount_nullfs=dict(type='int', choices=list([0, 1])),
                             allow_mount_procfs=dict(type='int', choices=list([0, 1])),
                             allow_mount_tmpfs=dict(type='int', choices=list([0, 1])),
                             allow_mount_zfs=dict(type='int', choices=list([0, 1])),
                             allow_quotas=dict(type='int', choices=list([0, 1])),
                             allow_socket_af=dict(type='int', choices=list([0, 1])),
                             allow_tun=dict(type='int', choices=list([0, 1])),
                             allow_mlock=dict(type='int', choices=list([0, 1])),
                             allow_vmm=dict(type='int', choices=list([0, 1])),
                             host_hostuuid=dict(type='str'),
                             name=dict(type='str'),
                             template=dict(type='str', choices=list(["yes", "no"])),
                             boot=dict(type='str', choices=list(["on", "off"])),
                             notes=dict(type='str'),
                             owner=dict(type='str'),
                             priority=dict(type='int'),
                             last_started=dict(type='str'),
                             type=dict(type='str', choices=list(["basejail", "empty", "normal"])),
                             release=dict(type='str'),
                             compression=dict(type='str',
                                              choices=list(["on", "off", "lzjb", "gzip",
                                                            "gzip-N", "zle", "lz4"])),
                             origin=dict(type='str'),
                             quota=dict(type='str'),
                             dedup=dict(type='str', choices=list(["on", "off", "verify",
                                                                  "sha256", "sha256,verify"])),
                             reservation=dict(type='str'),
                             cpuset=dict(type="str"),
                             vnet_interfaces=dict(type='str'),
                             vnet_default_interface=dict(type='str'),
                             hostid_strict_check=dict(type='str', choices=list(["on", "off"])))

    module_arguments['properties'] = dict(type='dict', options=iocage_properties)

    required_one_of = list([
        list(['release', 'template', 'empty'])
    ])
    mutually_exclusive = list([
        list(['release', 'template', 'empty'])
    ])

    result = dict(
        changed=False,
        message=''
    )

    module = AnsibleModule(
        supports_check_mode=True,
        argument_spec=module_arguments,
        required_one_of=required_one_of,
        mutually_exclusive=mutually_exclusive
    )

    # If the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications.
    if module.check_mode:
        module.exit_json(**result)

    result = run_module(module, result)

    module.exit_json(**result)


if __name__ == '__main__':
    main()
