#
# ovirt-host-deploy -- ovirt host deployer
# Copyright (C) 2012 Red Hat, Inc.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#


"""Install required vdsm packages."""


from distutils.version import LooseVersion
import os
import gettext
_ = lambda m: gettext.dgettext(message=m, domain='ovirt-host-deploy')


from otopi import util
from otopi import plugin


from ovirt_host_deploy import constants as odeploycons


@util.export
class Plugin(plugin.PluginBase):
    """vdsm packages plugin.

    Environment:
        VdsmEnv.VDSM_MINIMUM_VERSION -- Minimum version to validate.

    """
    def __init__(self, context):
        super(Plugin, self).__init__(context=context)

    @plugin.event(
        stage=plugin.Stages.STAGE_INIT,
    )
    def _init(self):
        self.environment.setdefault(
            odeploycons.VdsmEnv.VDSM_MINIMUM_VERSION,
            None
        )

    @plugin.event(
        stage=plugin.Stages.STAGE_VALIDATION,
    )
    def _validation(self):
        result = self.packager.queryPackages(patterns=['vdsm'])
        if not result:
            raise RuntimeError(
                _(
                    'Cannot locate vdsm package, '
                    'possible cause is incorrect channels'
                )
            )
        entry = result[0]
        self.logger.debug('Found vdsm %s', entry)

        minversion = self.environment[odeploycons.VdsmEnv.VDSM_MINIMUM_VERSION]
        currentversion = '%s-%s' % (
            entry['version'],
            entry['release'],
        )
        if minversion is not None:
            # this versio object does not handle the '-' as rpm...
            if [LooseVersion(v) for v in minversion.split('-')] > \
                    [LooseVersion(v) for v in currentversion.split('-')]:
                raise RuntimeError(
                    _(
                        'VDSM package is too old, '
                        'need {minimum} found {version}'
                    ).format(
                        minimum=minversion,
                        version=currentversion,
                    )
                )

    @plugin.event(
        stage=plugin.Stages.STAGE_PACKAGES,
    )
    def _packages(self):
        if self.services.exists('vdsmd'):
            self.services.state('vdsmd', False)
        self.packager.install(('qemu-kvm-tools',))
        self.packager.installUpdate(('vdsm', 'vdsm-cli'))

    @plugin.event(
        stage=plugin.Stages.STAGE_CLOSEUP,
    )
    def _closeup(self):

        with open(odeploycons.FileLocations.VDSM_FORCE_RECONFIGURE, 'w'):
            pass

        # libvirt-guests is a conflict
        if self.services.exists('libvirt-guests'):
            self.services.state('libvirt-guests', False)
            self.services.startup('libvirt-guests', False)

        self.services.startup('vdsmd', True)
        if not self.services.supportsDependency:
            if self.services.exists('libvirtd'):
                self.services.startup('libvirtd', True)
            if self.services.exists('messagebus'):
                self.services.startup('messagebus', True)

    # WORKAROUND-BEGIN
    # old vdsm does not support the reconfigure trigger.
    # we need to manually locate and reconfigure the init.d script.
    # can be removed while vdsm-4.9.6 (no fix) is gone.
    @plugin.event(
        stage=plugin.Stages.STAGE_CLOSEUP,
    )
    def _reconfigure(self):
        for script in ('/etc/init.d/vdsmd', '/lib/systemd/systemd-vdsmd'):
            if os.path.exists(script):
                rc, stdout, stderr = self.execute(
                    [script, 'reconfigure'],
                    raiseOnError=False
                )
                if rc != 0:
                    self.logger.warning('Cannot reconfigure vdsm')
                break
    # WORKAROUND-END

    @plugin.event(
        stage=plugin.Stages.STAGE_CLOSEUP,
        priority=plugin.Stages.PRIORITY_LOW,
        condition=lambda self: not self.environment[
            odeploycons.CoreEnv.FORCE_REBOOT
        ],
    )
    def _start(self):
        self.logger.info(_('Starting vdsm'))
        if not self.services.supportsDependency:
            if self.services.exists('messagebus'):
                self.services.state('messagebus', True)
            if self.services.exists('libvirtd'):
                self.services.state('libvirtd', True)
        self.services.state('vdsmd', True)


# vim: expandtab tabstop=4 shiftwidth=4
