# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Utilities and helper functions."""

import base64
import contextlib
import datetime
import errno
import functools
import hashlib
import inspect
import os
import paramiko
import pyclbr
import random
import re
import shlex
import shutil
import signal
import socket
import struct
import sys
import tempfile
import time
import types
import warnings
import uuid
import json
import anyjson
import threading
import commands

from string import Template
from xml.dom import minidom
from xml.parsers import expat
from xml import sax
from xml.sax import expatreader
from xml.sax import saxutils

from eventlet import event
from eventlet.green import subprocess
from eventlet import greenthread
from eventlet import pools

from vsm import exception
from vsm import flags
from vsm.openstack.common import excutils
from vsm.openstack.common import importutils
from vsm.openstack.common import log as logging
from vsm.openstack.common import timeutils
from vsm.openstack.common.gettextutils import _
from vsm import ipcalc

LOG = logging.getLogger(__name__)
ISO_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
PERFECT_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
FLAGS = flags.FLAGS

def find_config(config_path):
    """Find a configuration file using the given hint.

    :param config_path: Full or relative path to the config.
    :returns: Full path of the config, if it exists.
    :raises: `vsm.exception.ConfigNotFound`

    """
    possible_locations = [
        config_path,
        os.path.join(FLAGS.state_path, "etc", "vsm", config_path),
        os.path.join(FLAGS.state_path, "etc", config_path),
        os.path.join(FLAGS.state_path, config_path),
        "/etc/vsm/%s" % config_path,
    ]

    for path in possible_locations:
        if os.path.exists(path):
            return os.path.abspath(path)

    raise exception.ConfigNotFound(path=os.path.abspath(config_path))

def fetchfile(url, target):
    LOG.debug(_('Fetching %s') % url)
    execute('curl', '--fail', url, '-o', target)

def _subprocess_setup():
    # Python installs a SIGPIPE handler by default. This is usually not what
    # non-Python subprocesses expect.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

def execute_simpleCmd(cmd):
    return commands.getstatusoutput(cmd)

def lcoal_execute(*cmd, **kwargs):
    """Helper method to execute command with optional retry.

    :param cmd:                Passed to subprocess.Popen.
    :param process_input:      Send to opened process.
    :param check_exit_code:    Single bool, int, or list of allowed exit
                               codes.  Defaults to [0].  Raise
                               exception.ProcessExecutionError unless
                               program exits with one of these code.
    :param delay_on_retry:     True | False. Defaults to True. If set to
                               True, wait a short amount of time
                               before retrying.
    :param attempts:           How many times to retry cmd.
    :param run_as_root:        True | False. Defaults to False. If set to True,
                               the command is prefixed by the command specified
                               in the root_helper FLAG.

    :raises exception.Error: on receiving unknown arguments
    :raises exception.ProcessExecutionError:

    :returns: a tuple, (stdout, stderr) from the spawned process, or None if
             the command fails.
    """

    process_input = kwargs.pop('process_input', None)
    check_exit_code = kwargs.pop('check_exit_code', [0])
    ignore_exit_code = kwargs.pop('ignore_exit_code', False)

    if isinstance(check_exit_code, int):
        check_exit_code = [check_exit_code]

    delay_on_retry = kwargs.pop('delay_on_retry', True)
    attempts = kwargs.pop('attempts', 1)
    run_as_root = kwargs.pop('run_as_root', False)
    shell = kwargs.pop('shell', False)

    if len(kwargs):
        raise exception.Error(_('Got unknown keyword args '
                                'to utils.remote_ssh_execute: %r') % kwargs)

    if run_as_root:

        if FLAGS.root_helper != 'sudo':
            LOG.deprecated(_('The root_helper option (which lets you specify '
                             'a root wrapper different from vsm-rootwrap, '
                             'and defaults to using sudo) is now deprecated. '
                             'You should use the rootwrap_config option '
                             'instead.'))

        cmd = shlex.split(FLAGS.root_helper) + list(cmd)

    cmd = map(str, cmd) # pylint: disable=W0141

    while attempts > 0:
        attempts -= 1
        try:
            cmd_str = ' '.join(cmd)
            if cmd_str.find('ceph') != -1:
                LOG.debug(_('Running cmd %s'), ' '.join(cmd))
            if cmd_str.find('erasure-code-profile') != -1:
                cmd = shlex.split(cmd_str)

            _PIPE = subprocess.PIPE  # pylint: disable=E1101
            obj = subprocess.Popen(cmd,
                                   stdin=_PIPE,
                                   stdout=_PIPE,
                                   stderr=_PIPE,
                                   close_fds=True,
                                   preexec_fn=_subprocess_setup,
                                   shell=shell)
            result = None
            if process_input is not None:
                result = obj.communicate(process_input)
            else:
                result = obj.communicate()
            obj.stdin.close()  # pylint: disable=E1101
            _returncode = obj.returncode  # pylint: disable=E1101
            if _returncode:
                LOG.debug(_('Result was %s') % _returncode)
                if not ignore_exit_code and _returncode not in check_exit_code:
                    (stdout, stderr) = result
                    # only raise exception for ceph related commands
                    if cmd_str.lower().find('ceph') != -1 and \
                       cmd_str.lower().find('pgrep') == -1 and \
                       cmd_str.find('--connect-timeout') == -1:
                        LOG.info('---------CMD-------------')
                        LOG.info('Running cmd = %s' % cmd_str)
                        LOG.info('stdout = %s' % stdout)
                        LOG.info('stderr = %s' % stderr)
                        LOG.info('---------CMD-------------')
                        raise exception.ProcessExecutionError(
                            exit_code=_returncode,
                            stdout=stdout,
                            stderr=stderr,
                            cmd=' '.join(cmd))
            return result
        except exception.ProcessExecutionError as e:
            LOG.info(_('%r failed. Retrying.'), e.message)
            if not attempts:
                raise
            else:
                LOG.debug(_('%r failed. Retrying.'), cmd)
                if delay_on_retry:
                    greenthread.sleep(random.randint(20, 200) / 100.0)
        finally:
            # NOTE(termie): this appears to be necessary to let the subprocess
            #               call clean something up in between calls, without
            #               it two execute calls in a row hangs the second one
            greenthread.sleep(0)


def execute(*cmd, **kwargs):
    """Helper method to execute command with optional retry.

    If you add a run_as_root=True command, don't forget to add the
    corresponding filter to etc/vsm/rootwrap.d !

    :param cmd:                Passed to subprocess.Popen.
    :param process_input:      Send to opened process.
    :param check_exit_code:    Single bool, int, or list of allowed exit
                               codes.  Defaults to [0].  Raise
                               exception.ProcessExecutionError unless
                               program exits with one of these code.
    :param delay_on_retry:     True | False. Defaults to True. If set to
                               True, wait a short amount of time
                               before retrying.
    :param attempts:           How many times to retry cmd.
    :param run_as_root:        True | False. Defaults to False. If set to True,
                               the command is prefixed by the command specified
                               in the root_helper FLAG.

    :raises exception.Error: on receiving unknown arguments
    :raises exception.ProcessExecutionError:

    :returns: a tuple, (stdout, stderr) from the spawned process, or None if
             the command fails.
    """

    process_input = kwargs.pop('process_input', None)
    check_exit_code = kwargs.pop('check_exit_code', [0])
    ignore_exit_code = kwargs.pop('ignore_exit_code', False)

    if isinstance(check_exit_code, int):
        check_exit_code = [check_exit_code]

    delay_on_retry = kwargs.pop('delay_on_retry', True)
    attempts = kwargs.pop('attempts', 1)
    run_as_root = kwargs.pop('run_as_root', False)
    shell = kwargs.pop('shell', False)

    if len(kwargs):
        raise exception.Error(_('Got unknown keyword args '
                                'to utils.execute: %r') % kwargs)

    if run_as_root:

        if FLAGS.rootwrap_config is None or FLAGS.root_helper != 'sudo':
            LOG.deprecated(_('The root_helper option (which lets you specify '
                             'a root wrapper different from vsm-rootwrap, '
                             'and defaults to using sudo) is now deprecated. '
                             'You should use the rootwrap_config option '
                             'instead.'))

        if (FLAGS.rootwrap_config is not None):
            cmd = ['sudo', 'vsm-rootwrap',
                   FLAGS.rootwrap_config] + list(cmd)
        else:
            cmd = shlex.split(FLAGS.root_helper) + list(cmd)
    cmd = map(str, cmd) # pylint: disable=W0141

    while attempts > 0:
        attempts -= 1
        try:
            cmd_str = ' '.join(cmd)
            if cmd_str.find('ceph') != -1:
                LOG.debug(_('Running cmd %s'), ' '.join(cmd))
            if cmd_str.find('erasure-code-profile') != -1:
                cmd = shlex.split(cmd_str)

            _PIPE = subprocess.PIPE  # pylint: disable=E1101
            obj = subprocess.Popen(cmd,
                                   stdin=_PIPE,
                                   stdout=_PIPE,
                                   stderr=_PIPE,
                                   close_fds=True,
                                   preexec_fn=_subprocess_setup,
                                   shell=shell)
            result = None
            if process_input is not None:
                result = obj.communicate(process_input)
            else:
                result = obj.communicate()
            obj.stdin.close()  # pylint: disable=E1101
            _returncode = obj.returncode  # pylint: disable=E1101
            if _returncode:
                LOG.debug(_('Result was %s') % _returncode)
                if not ignore_exit_code and _returncode not in check_exit_code:
                    (stdout, stderr) = result
                    # only raise exception for ceph related commands
                    if cmd_str.lower().find('ceph') != -1 and \
                       cmd_str.lower().find('pgrep') == -1 and \
                       cmd_str.find('--connect-timeout') == -1:
                        LOG.info('---------CMD-------------')
                        LOG.info('Running cmd = %s' % cmd_str)
                        LOG.info('stdout = %s' % stdout)
                        LOG.info('stderr = %s' % stderr)
                        LOG.info('---------CMD-------------')
                        raise exception.ProcessExecutionError(
                            exit_code=_returncode,
                            stdout=stdout,
                            stderr=stderr,
                            cmd=' '.join(cmd))
            return result
        except exception.ProcessExecutionError as e:
            LOG.info(_('%r failed. Retrying.'), e.message)
            if not attempts:
                raise
            else:
                LOG.debug(_('%r failed. Retrying.'), cmd)
                if delay_on_retry:
                    greenthread.sleep(random.randint(20, 200) / 100.0)
        finally:
            # NOTE(termie): this appears to be necessary to let the subprocess
            #               call clean something up in between calls, without
            #               it two execute calls in a row hangs the second one
            greenthread.sleep(0)

def trycmd(*args, **kwargs):
    """
    A wrapper around execute() to more easily handle warnings and errors.

    Returns an (out, err) tuple of strings containing the output of
    the command's stdout and stderr.  If 'err' is not empty then the
    command can be considered to have failed.

    :discard_warnings   True | False. Defaults to False. If set to True,
                        then for succeeding commands, stderr is cleared

    """
    discard_warnings = kwargs.pop('discard_warnings', False)

    try:
        out, err = execute(*args, **kwargs)
        failed = False
    except exception.ProcessExecutionError, exn:
        out, err = '', str(exn)
        LOG.debug(err)
        failed = True

    if not failed and discard_warnings and err:
        # Handle commands that output to stderr but otherwise succeed
        LOG.debug(err)
        err = ''

    return out, err

def ssh_execute(ssh, cmd, process_input=None,
                addl_env=None, check_exit_code=True):
    LOG.debug(_('Running cmd (SSH): %s'), cmd)
    if addl_env:
        raise exception.Error(_('Environment not supported over SSH'))

    if process_input:
        # This is (probably) fixable if we need it...
        raise exception.Error(_('process_input not supported over SSH'))

    stdin_stream, stdout_stream, stderr_stream = ssh.exec_command(cmd, get_pty=True)
    channel = stdout_stream.channel

    #stdin.write('process_input would go here')
    #stdin.flush()

    # NOTE(justinsb): This seems suspicious...
    # ...other SSH clients have buffering issues with this approach
    stdout = stdout_stream.read()
    stderr = stderr_stream.read()
    stdin_stream.close()
    stdout_stream.close()
    stderr_stream.close()

    exit_status = channel.recv_exit_status()

    # exit_status == -1 if no exit code was returned
    if exit_status != -1:
        LOG.debug(_('Result was %s') % exit_status)
        if check_exit_code and exit_status != 0:
            raise exception.ProcessExecutionError(exit_code=exit_status,
                                                  stdout=stdout,
                                                  stderr=stderr,
                                                  cmd=cmd)
    channel.close()
    return (stdout, stderr)

class SSHPool(pools.Pool):
    """A simple eventlet pool to hold ssh connections."""

    def __init__(self, ip, port, conn_timeout, login, password=None,
                 privatekey=None, *args, **kwargs):
        self.ip = ip
        self.port = port
        self.login = login
        self.password = password
        self.conn_timeout = conn_timeout if conn_timeout else None
        self.privatekey = privatekey
        super(SSHPool, self).__init__(*args, **kwargs)

    def create(self):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if self.password:
                ssh.connect(self.ip,
                            port=self.port,
                            username=self.login,
                            password=self.password,
                            timeout=self.conn_timeout)
            elif self.privatekey:
                LOG.info(' file path=%s' % self.privatekey)
                pkfile = os.path.expanduser(self.privatekey)
                privatekey = paramiko.RSAKey.from_private_key_file(pkfile)
                ssh.connect(self.ip,
                            port=self.port,
                            username=self.login,
                            pkey=privatekey,
                            timeout=self.conn_timeout)
            else:
                msg = _("Specify a password or private_key")
                raise exception.VsmException(msg)

            # Paramiko by default sets the socket timeout to 0.1 seconds,
            # ignoring what we set thru the sshclient. This doesn't help for
            # keeping long lived connections. Hence we have to bypass it, by
            # overriding it after the transport is initialized. We are setting
            # the sockettimeout to None and setting a keepalive packet so that,
            # the server will keep the connection open. All that does is send
            # a keepalive packet every ssh_conn_timeout seconds.
            if self.conn_timeout:
                transport = ssh.get_transport()
                transport.sock.settimeout(None)
                transport.set_keepalive(self.conn_timeout)
            return ssh
        except Exception as e:
            msg = _("Error connecting via ssh: %s") % e
            LOG.error(msg)
            raise paramiko.SSHException(msg)

    def get(self):
        """
        Return an item from the pool, when one is available.  This may
        cause the calling greenthread to block. Check if a connection is active
        before returning it. For dead connections create and return a new
        connection.
        """
        if self.free_items:
            conn = self.free_items.popleft()
            if conn:
                if conn.get_transport().is_active():
                    return conn
                else:
                    conn.close()
            return self.create()
        if self.current_size < self.max_size:
            created = self.create()
            self.current_size += 1
            return created
        return self.channel.get()

class SSHClient():
    """
    ssh client methods for ssh key pair authentication
    """

    def __init__(self, ip, user, key_file, timeout=10):
        self.host = ip
        self.login = user
        self.pfile = key_file
        self.timeout = timeout

    def _get_conn(self):
        ssh = SSHPool(ip=self.host,
                      port=22,
                      login=self.login,
                      conn_timeout=self.timeout,
                      privatekey=self.pfile)
        if ssh:
            try:
                return ssh.get()
            except paramiko.SSHException:
                return None

    @staticmethod
    def make_remote_dirs(sftp, remote):
        """
        emulates mkdir_p if required.
        sftp - is a valid sftp object
        remote - remote path to create.
        """
        dirs_ = []
        dir_, basename = os.path.split(remote)
        while len(dir_) > 1:
            dirs_.append(dir_)
            dir_, name_ = os.path.split(dir_)

        if len(dir_) == 1 and not dir_.startswith("/"):
            # For a remote path like y/x.txt
            dirs_.append(dir_)

        while len(dirs_):
            dir_ = dirs_.pop()
            try:
                sftp.stat(dir_)
            except IOError:
                LOG.debug("making ... dir",  dir_)
                sftp.mkdir(dir_)

    def check_ssh(self, retries=1):
        """
        Check ssh connection to hosts.
        """
        for x in range(retries):
            if self._get_conn():
                return True
        return False

    def ssh_copy(self, local_path, remote_path):
        if not local_path or not remote_path:
            return False

        if not os.path.exists(local_path):
            LOG.debug('Path %s does exists on host %s.' % (local_path, socket.gethostname()))
            return False

        client = self._get_conn()
        if client:
            sftp = client.open_sftp()
            SSHClient.make_remote_dirs(sftp, remote_path)
            sftp.put(local_path, remote_path)
            sftp.close()
            return True

        return False

    def ssh_copyDir(self, local_path, remote_path):
        if not local_path or not remote_path:
            return False

        if not os.path.exists(local_path):
            LOG.debug('Path %s does exists on host %s.' % (local_path, socket.gethostname()))
            return False

        client = self._get_conn()
        if client:
            sftp = client.open_sftp()
            SSHClient.make_remote_dirs(sftp, remote_path)
            files = os.listdir(local_path)
            #files = sftp.listdir(remote_path)
            for f in files :
                local_file_path = os.path.join(local_path,f)
                if os.path.isfile(local_file_path) :
                    LOG.info('Start put file=%s' % local_file_path)
                    sftp.put(local_file_path,os.path.join(remote_path,f))
            sftp.close()
            return True

        return False

def get_sshConn(serverIp, user, key_file):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkfile = os.path.expanduser(key_file)
    privatekey = paramiko.RSAKey.from_private_key_file(pkfile)
    ssh.connect(serverIp, 22, username=user, password=None, pkey=privatekey)
    return ssh

def sftp_copy(serverIp, user, key_file, local_path, remote_path):
    scp = paramiko.Transport(serverIp, 22)
    pkfile = os.path.expanduser(key_file)
    privatekey = paramiko.RSAKey.from_private_key_file(pkfile)
    scp.connect(username=user,password=None, pkey=privatekey)
    sftp=paramiko.SFTPClient.from_transport(scp)
    if os.path.isfile(local_path) :
        LOG.info('Start put file=%s' % local_path)
        sftp.put(local_path, remote_path)
    else :
        files = os.listdir(local_path)
        #files = sftp.listdir(remote_path)
        for f in files :
            local_file_path = os.path.join(local_path,f)
            if os.path.isfile(local_file_path) :
                LOG.info('Start put file=%s' % local_file_path)
                sftp.put(local_file_path,os.path.join(remote_path,f))
    sftp.close()

def vsmdir():
    import vsm
    return os.path.abspath(vsm.__file__).split('vsm/__init__.py')[0]

def debug(arg):
    LOG.debug(_('debug in callback: %s'), arg)
    return arg

def generate_uid(topic, size=8):
    characters = '01234567890abcdefghijklmnopqrstuvwxyz'
    choices = [random.choice(characters) for x in xrange(size)]
    return '%s-%s' % (topic, ''.join(choices))

# Default symbols to use for passwords. Avoids visually confusing characters.
# ~6 bits per symbol
DEFAULT_PASSWORD_SYMBOLS = ('23456789',  # Removed: 0,1
                            'ABCDEFGHJKLMNPQRSTUVWXYZ',   # Removed: I, O
                            'abcdefghijkmnopqrstuvwxyz')  # Removed: l

# ~5 bits per symbol
EASIER_PASSWORD_SYMBOLS = ('23456789',  # Removed: 0, 1
                           'ABCDEFGHJKLMNPQRSTUVWXYZ')  # Removed: I, O

def last_completed_audit_period(unit=None):
    """This method gives you the most recently *completed* audit period.

    arguments:
            units: string, one of 'hour', 'day', 'month', 'year'
                    Periods normally begin at the beginning (UTC) of the
                    period unit (So a 'day' period begins at midnight UTC,
                    a 'month' unit on the 1st, a 'year' on Jan, 1)
                    unit string may be appended with an optional offset
                    like so:  'day@18'  This will begin the period at 18:00
                    UTC.  'month@15' starts a monthly period on the 15th,
                    and year@3 begins a yearly one on March 1st.

    returns:  2 tuple of datetimes (begin, end)
              The begin timestamp of this audit period is the same as the
              end of the previous."""
    if not unit:
        unit = FLAGS.storage_usage_audit_period

    offset = 0
    if '@' in unit:
        unit, offset = unit.split("@", 1)
        offset = int(offset)

    rightnow = timeutils.utcnow()
    if unit not in ('month', 'day', 'year', 'hour'):
        raise ValueError('Time period must be hour, day, month or year')
    if unit == 'month':
        if offset == 0:
            offset = 1
        end = datetime.datetime(day=offset,
                                month=rightnow.month,
                                year=rightnow.year)
        if end >= rightnow:
            year = rightnow.year
            if 1 >= rightnow.month:
                year -= 1
                month = 12 + (rightnow.month - 1)
            else:
                month = rightnow.month - 1
            end = datetime.datetime(day=offset,
                                    month=month,
                                    year=year)
        year = end.year
        if 1 >= end.month:
            year -= 1
            month = 12 + (end.month - 1)
        else:
            month = end.month - 1
        begin = datetime.datetime(day=offset, month=month, year=year)

    elif unit == 'year':
        if offset == 0:
            offset = 1
        end = datetime.datetime(day=1, month=offset, year=rightnow.year)
        if end >= rightnow:
            end = datetime.datetime(day=1,
                                    month=offset,
                                    year=rightnow.year - 1)
            begin = datetime.datetime(day=1,
                                      month=offset,
                                      year=rightnow.year - 2)
        else:
            begin = datetime.datetime(day=1,
                                      month=offset,
                                      year=rightnow.year - 1)

    elif unit == 'day':
        end = datetime.datetime(hour=offset,
                                day=rightnow.day,
                                month=rightnow.month,
                                year=rightnow.year)
        if end >= rightnow:
            end = end - datetime.timedelta(days=1)
        begin = end - datetime.timedelta(days=1)

    elif unit == 'hour':
        end = rightnow.replace(minute=offset, second=0, microsecond=0)
        if end >= rightnow:
            end = end - datetime.timedelta(hours=1)
        begin = end - datetime.timedelta(hours=1)

    return (begin, end)

def generate_password(length=20, symbolgroups=DEFAULT_PASSWORD_SYMBOLS):
    """Generate a random password from the supplied symbol groups.

    At least one symbol from each group will be included. Unpredictable
    results if length is less than the number of symbol groups.

    Believed to be reasonably secure (with a reasonable password length!)

    """
    r = random.SystemRandom()

    # NOTE(jerdfelt): Some password policies require at least one character
    # from each group of symbols, so start off with one random character
    # from each symbol group
    password = [r.choice(s) for s in symbolgroups]
    # If length < len(symbolgroups), the leading characters will only
    # be from the first length groups. Try our best to not be predictable
    # by shuffling and then truncating.
    r.shuffle(password)
    password = password[:length]
    length -= len(password)

    # then fill with random characters from all symbol groups
    symbols = ''.join(symbolgroups)
    password.extend([r.choice(symbols) for _i in xrange(length)])

    # finally shuffle to ensure first x characters aren't from a
    # predictable group
    r.shuffle(password)

    return ''.join(password)

def generate_username(length=20, symbolgroups=DEFAULT_PASSWORD_SYMBOLS):
    # Use the same implementation as the password generation.
    return generate_password(length, symbolgroups)

def last_octet(address):
    return int(address.split('.')[-1])

def get_my_linklocal(interface):
    try:
        if_str = execute('ip', '-f', 'inet6', '-o', 'addr', 'show', interface)
        condition = '\s+inet6\s+([0-9a-f:]+)/\d+\s+scope\s+link'
        links = [re.search(condition, x) for x in if_str[0].split('\n')]
        address = [w.group(1) for w in links if w is not None]
        if address[0] is not None:
            return address[0]
        else:
            raise exception.Error(_('Link Local address is not found.:%s')
                                  % if_str)
    except Exception as ex:
        raise exception.Error(_("Couldn't get Link Local IP of %(interface)s"
                                " :%(ex)s") % locals())

def parse_mailmap(mailmap='.mailmap'):
    mapping = {}
    if os.path.exists(mailmap):
        fp = open(mailmap, 'r')
        for l in fp:
            l = l.strip()
            if not l.startswith('#') and ' ' in l:
                canonical_email, alias = l.split(' ')
                mapping[alias.lower()] = canonical_email.lower()
    return mapping

def str_dict_replace(s, mapping):
    for s1, s2 in mapping.iteritems():
        s = s.replace(s1, s2)
    return s

class LazyPluggable(object):
    """A pluggable backend loaded lazily based on some value."""

    def __init__(self, pivot, **backends):
        self.__backends = backends
        self.__pivot = pivot
        self.__backend = None

    def __get_backend(self):
        if not self.__backend:
            backend_name = FLAGS[self.__pivot]
            if backend_name not in self.__backends:
                raise exception.Error(_('Invalid backend: %s') % backend_name)

            backend = self.__backends[backend_name]
            if isinstance(backend, tuple):
                name = backend[0]
                fromlist = backend[1]
            else:
                name = backend
                fromlist = backend

            self.__backend = __import__(name, None, None, fromlist)
            LOG.debug(_('backend %s'), self.__backend)
        return self.__backend

    def __getattr__(self, key):
        backend = self.__get_backend()
        return getattr(backend, key)

class LoopingCallDone(Exception):
    """Exception to break out and stop a LoopingCall.

    The poll-function passed to LoopingCall can raise this exception to
    break out of the loop normally. This is somewhat analogous to
    StopIteration.

    An optional return-value can be included as the argument to the exception;
    this return-value will be returned by LoopingCall.wait()

    """

    def __init__(self, retvalue=True):
        """:param retvalue: Value that LoopingCall.wait() should return."""
        self.retvalue = retvalue

class LoopingCall(object):
    def __init__(self, f=None, *args, **kw):
        self.args = args
        self.kw = kw
        self.f = f
        self._running = False

    def start(self, interval, initial_delay=None):
        self._running = True
        done = event.Event()

        def _inner():
            if initial_delay:
                greenthread.sleep(initial_delay)

            try:
                while self._running:
                    self.f(*self.args, **self.kw)
                    if not self._running:
                        break
                    greenthread.sleep(interval)
            except LoopingCallDone, e:
                self.stop()
                done.send(e.retvalue)
            except Exception:
                LOG.exception(_('in looping call'))
                done.send_exception(*sys.exc_info())
                return
            else:
                done.send(True)

        self.done = done

        greenthread.spawn(_inner)
        return self.done

    def stop(self):
        self._running = False

    def wait(self):
        return self.done.wait()

class ProtectedExpatParser(expatreader.ExpatParser):
    """An expat parser which disables DTD's and entities by default."""

    def __init__(self, forbid_dtd=True, forbid_entities=True,
                 *args, **kwargs):
        # Python 2.x old style class
        expatreader.ExpatParser.__init__(self, *args, **kwargs)
        self.forbid_dtd = forbid_dtd
        self.forbid_entities = forbid_entities

    def start_doctype_decl(self, name, sysid, pubid, has_internal_subset):
        raise ValueError("Inline DTD forbidden")

    def entity_decl(self, entityName, is_parameter_entity, value, base,
                    systemId, publicId, notationName):
        raise ValueError("<!ENTITY> forbidden")

    def unparsed_entity_decl(self, name, base, sysid, pubid, notation_name):
        # expat 1.2
        raise ValueError("<!ENTITY> forbidden")

    def reset(self):
        expatreader.ExpatParser.reset(self)
        if self.forbid_dtd:
            self._parser.StartDoctypeDeclHandler = self.start_doctype_decl
        if self.forbid_entities:
            self._parser.EntityDeclHandler = self.entity_decl
            self._parser.UnparsedEntityDeclHandler = self.unparsed_entity_decl

def safe_minidom_parse_string(xml_string):
    """Parse an XML string using minidom safely.

    """
    try:
        return minidom.parseString(xml_string, parser=ProtectedExpatParser())
    except sax.SAXParseException as se:
        raise expat.ExpatError()

def xhtml_escape(value):
    """Escapes a string so it is valid within XML or XHTML.

    """
    return saxutils.escape(value, {'"': '&quot;', "'": '&apos;'})

def utf8(value):
    """Try to turn a string into utf-8 if possible.

    Code is directly from the utf8 function in
    http://github.com/facebook/tornado/blob/master/tornado/escape.py

    """
    if isinstance(value, unicode):
        return value.encode('utf-8')
    assert isinstance(value, str)
    return value

def delete_if_exists(pathname):
    """delete a file, but ignore file not found error"""

    try:
        os.unlink(pathname)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return
        else:
            raise

def get_from_path(items, path):
    """Returns a list of items matching the specified path.

    Takes an XPath-like expression e.g. prop1/prop2/prop3, and for each item
    in items, looks up items[prop1][prop2][prop3].  Like XPath, if any of the
    intermediate results are lists it will treat each list item individually.
    A 'None' in items or any child expressions will be ignored, this function
    will not throw because of None (anywhere) in items.  The returned list
    will contain no None values.

    """
    if path is None:
        raise exception.Error('Invalid mini_xpath')

    (first_token, sep, remainder) = path.partition('/')

    if first_token == '':
        raise exception.Error('Invalid mini_xpath')

    results = []

    if items is None:
        return results

    if not isinstance(items, list):
        # Wrap single objects in a list
        items = [items]

    for item in items:
        if item is None:
            continue
        get_method = getattr(item, 'get', None)
        if get_method is None:
            continue
        child = get_method(first_token)
        if child is None:
            continue
        if isinstance(child, list):
            # Flatten intermediate lists
            for x in child:
                results.append(x)
        else:
            results.append(child)

    if not sep:
        # No more tokens
        return results
    else:
        return get_from_path(results, remainder)

def flatten_dict(dict_, flattened=None):
    """Recursively flatten a nested dictionary."""
    flattened = flattened or {}
    for key, value in dict_.iteritems():
        if hasattr(value, 'iteritems'):
            flatten_dict(value, flattened)
        else:
            flattened[key] = value
    return flattened

def partition_dict(dict_, keys):
    """Return two dicts, one with `keys` the other with everything else."""
    intersection = {}
    difference = {}
    for key, value in dict_.iteritems():
        if key in keys:
            intersection[key] = value
        else:
            difference[key] = value
    return intersection, difference

def map_dict_keys(dict_, key_map):
    """Return a dict in which the dictionaries keys are mapped to new keys."""
    mapped = {}
    for key, value in dict_.iteritems():
        mapped_key = key_map[key] if key in key_map else key
        mapped[mapped_key] = value
    return mapped

def subset_dict(dict_, keys):
    """Return a dict that only contains a subset of keys."""
    subset = partition_dict(dict_, keys)[0]
    return subset

def check_isinstance(obj, cls):
    """Checks that obj is of type cls, and lets PyLint infer types."""
    if isinstance(obj, cls):
        return obj
    raise Exception(_('Expected object of type: %s') % (str(cls)))
    # TODO(justinsb): Can we make this better??
    return cls()  # Ugly PyLint hack

def bool_from_str(val):
    """Convert a string representation of a bool into a bool value"""

    if not val:
        return False
    try:
        return True if int(val) else False
    except ValueError:
        return val.lower() == 'true'

def int_from_str(text, default=None):
    """
    Try to turn a string into a int value
    """
    if not text:
        return default
    try:
        if isinstance(text, int):
            return text
        elif isinstance(text, str) and text.isdigit():
            return int(text, base=10)
        else:
            # long type or convertible type to int
            return int(text)
    except (ValueError, TypeError):
        LOG.debug("Got value or type error when convert %s from str" % text)
    return default

def is_valid_boolstr(val):
    """Check if the provided string is a valid bool string or not. """
    val = str(val).lower()
    return (val == 'true' or val == 'false' or
            val == 'yes' or val == 'no' or
            val == 'y' or val == 'n' or
            val == '1' or val == '0')

def is_valid_ipv4(address):
    """valid the address strictly as per format xxx.xxx.xxx.xxx.
    where xxx is a value between 0 and 255.
    """
    parts = address.split(".")
    if len(parts) != 4:
        return False
    for item in parts:
        try:
            if not 0 <= int(item) <= 255:
                return False
        except ValueError:
            return False
    return True

def monkey_patch():
    """  If the Flags.monkey_patch set as True,
    this function patches a decorator
    for all functions in specified modules.
    You can set decorators for each modules
    using FLAGS.monkey_patch_modules.
    The format is "Module path:Decorator function".
    Example: 'vsm.api.ec2.cloud:' \
     vsm.openstack.common.notifier.api.notify_decorator'

    Parameters of the decorator is as follows.
    (See vsm.openstack.common.notifier.api.notify_decorator)

    name - name of the function
    function - object of the function
    """
    # If FLAGS.monkey_patch is not True, this function do nothing.
    if not FLAGS.monkey_patch:
        return
    # Get list of modules and decorators
    for module_and_decorator in FLAGS.monkey_patch_modules:
        module, decorator_name = module_and_decorator.split(':')
        # import decorator function
        decorator = importutils.import_class(decorator_name)
        __import__(module)
        # Retrieve module information using pyclbr
        module_data = pyclbr.readmodule_ex(module)
        for key in module_data.keys():
            # set the decorator for the class methods
            if isinstance(module_data[key], pyclbr.Class):
                clz = importutils.import_class("%s.%s" % (module, key))
                for method, func in inspect.getmembers(clz, inspect.ismethod):
                    setattr(
                        clz, method,
                        decorator("%s.%s.%s" % (module, key, method), func))
            # set the decorator for the function
            if isinstance(module_data[key], pyclbr.Function):
                func = importutils.import_class("%s.%s" % (module, key))
                setattr(sys.modules[module], key,
                        decorator("%s.%s" % (module, key), func))

def convert_to_list_dict(lst, label):
    """Convert a value or list into a list of dicts"""
    if not lst:
        return None
    if not isinstance(lst, list):
        lst = [lst]
    return [{label: x} for x in lst]

def timefunc(func):
    """Decorator that logs how long a particular function took to execute"""
    @functools.wraps(func)
    def inner(*args, **kwargs):
        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            total_time = time.time() - start_time
            LOG.debug(_("timefunc: '%(name)s' took %(total_time).2f secs") %
                      dict(name=func.__name__, total_time=total_time))
    return inner

def generate_glance_url():
    """Generate the URL to glance."""
    # TODO(jk0): This will eventually need to take SSL into consideration
    # when supported in glance.
    return "http://%s:%d" % (FLAGS.glance_host, FLAGS.glance_port)

@contextlib.contextmanager
def logging_error(message):
    """Catches exception, write message to the log, re-raise.
    This is a common refinement of save_and_reraise that writes a specific
    message to the log.
    """
    try:
        yield
    except Exception as error:
        with excutils.save_and_reraise_exception():
            LOG.exception(message)

@contextlib.contextmanager
def remove_path_on_error(path):
    """Protect code that wants to operate on PATH atomically.
    Any exception will cause PATH to be removed.
    """
    try:
        yield
    except Exception:
        with excutils.save_and_reraise_exception():
            delete_if_exists(path)

def make_dev_path(dev, partition=None, base='/dev'):
    """Return a path to a particular device.

    >>> make_dev_path('xvdc')
    /dev/xvdc

    >>> make_dev_path('xvdc', 1)
    /dev/xvdc1
    """
    path = os.path.join(base, dev)
    if partition:
        path += str(partition)
    return path

def total_seconds(td):
    """Local total_seconds implementation for compatibility with python 2.6"""
    if hasattr(td, 'total_seconds'):
        return td.total_seconds()
    else:
        return ((td.days * 86400 + td.seconds) * 10 ** 6 +
                td.microseconds) / 10.0 ** 6

def sanitize_hostname(hostname):
    """Return a hostname which conforms to RFC-952 and RFC-1123 specs."""
    if isinstance(hostname, unicode):
        hostname = hostname.encode('latin-1', 'ignore')

    hostname = re.sub('[ _]', '-', hostname)
    hostname = re.sub('[^\w.-]+', '', hostname)
    hostname = hostname.lower()
    hostname = hostname.strip('.-')

    return hostname

def read_cached_file(filename, cache_info, reload_func=None):
    """Read from a file if it has been modified.

    :param cache_info: dictionary to hold opaque cache.
    :param reload_func: optional function to be called with data when
                        file is reloaded due to a modification.

    :returns: data from file

    """
    mtime = os.path.getmtime(filename)
    if not cache_info or mtime != cache_info.get('mtime'):
        with open(filename) as fap:
            cache_info['data'] = fap.read()
        cache_info['mtime'] = mtime
        if reload_func:
            reload_func(cache_info['data'])
    return cache_info['data']

def file_open(*args, **kwargs):
    """Open file

    see built-in file() documentation for more details

    Note: The reason this is kept in a separate module is to easily
          be able to provide a stub module that doesn't alter system
          state at all (for unit tests)
    """
    return file(*args, **kwargs)

def hash_file(file_like_object):
    """Generate a hash for the contents of a file."""
    checksum = hashlib.sha1()
    any(map(checksum.update, iter(lambda: file_like_object.read(32768), '')))
    return checksum.hexdigest()

@contextlib.contextmanager
def temporary_mutation(obj, **kwargs):
    """Temporarily set the attr on a particular object to a given value then
    revert when finished.

    One use of this is to temporarily set the read_deleted flag on a context
    object:

        with temporary_mutation(context, read_deleted="yes"):
            do_something_that_needed_deleted_objects()
    """
    NOT_PRESENT = object()

    old_values = {}
    for attr, new_value in kwargs.items():
        old_values[attr] = getattr(obj, attr, NOT_PRESENT)
        setattr(obj, attr, new_value)

    try:
        yield
    finally:
        for attr, old_value in old_values.items():
            if old_value is NOT_PRESENT:
                del obj[attr]
            else:
                setattr(obj, attr, old_value)

def service_is_up(service):
    """Check whether a service is up based on last heartbeat."""
    last_heartbeat = service['updated_at'] or service['created_at']
    # Timestamps in DB are UTC.
    elapsed = total_seconds(timeutils.utcnow() - last_heartbeat)
    return abs(elapsed) <= FLAGS.service_down_time

def generate_mac_address():
    """Generate an Ethernet MAC address."""
    # NOTE(vish): We would prefer to use 0xfe here to ensure that linux
    #             bridge mac addresses don't change, but it appears to
    #             conflict with libvirt, so we use the next highest octet
    #             that has the unicast and locally administered bits set
    #             properly: 0xfa.
    #             Discussion: https://bugs.launchpad.net/vsm/+bug/921838
    mac = [0xfa, 0x16, 0x3e,
           random.randint(0x00, 0x7f),
           random.randint(0x00, 0xff),
           random.randint(0x00, 0xff)]
    return ':'.join(map(lambda x: "%02x" % x, mac))

def read_file_as_root(file_path):
    """Secure helper to read file as root."""
    try:
        out, _err = execute('cat', file_path, run_as_root=True)
        return out
    except exception.ProcessExecutionError:
        raise exception.FileNotFound(file_path=file_path)

def write_file_as_root(file_path, content, open_type="a+"):
    """Secure helper to read file as root."""
    try:
        out, _err = execute('vsm-assist',
                            'write_file',
                            file_path,
                            content,
                            open_type,
                            run_as_root=True)
        return out
    except exception.ProcessExecutionError:
        raise exception.FileNotFound(file_path=file_path)

def file_is_exist_as_root(file_path):
    """Secure helper to read file as root."""
    try:
        out, _err = execute('vsm-assist',
                            'checkfile',
                            file_path,
                            run_as_root=True)
        if out.find('1') != -1:
            return True
        else:
            return None
    except exception.ProcessExecutionError:
        raise exception.FileNotFound(file_path=file_path)

@contextlib.contextmanager
def temporary_chown(path, owner_uid=None):
    """Temporarily chown a path.

    :params owner_uid: UID of temporary owner (defaults to current user)
    """
    if owner_uid is None:
        owner_uid = os.getuid()

    orig_uid = os.stat(path).st_uid

    if orig_uid != owner_uid:
        execute('chown', owner_uid, path, run_as_root=True)
    try:
        yield
    finally:
        if orig_uid != owner_uid:
            execute('chown', orig_uid, path, run_as_root=True)

@contextlib.contextmanager
def tempdir(**kwargs):
    tmpdir = tempfile.mkdtemp(**kwargs)
    try:
        yield tmpdir
    finally:
        try:
            shutil.rmtree(tmpdir)
        except OSError, e:
            LOG.debug(_('Could not remove tmpdir: %s'), str(e))

def strcmp_const_time(s1, s2):
    """Constant-time string comparison.

    :params s1: the first string
    :params s2: the second string

    :return: True if the strings are equal.

    This function takes two strings and compares them.  It is intended to be
    used when doing a comparison for authentication purposes to help guard
    against timing attacks.
    """
    if len(s1) != len(s2):
        return False
    result = 0
    for (a, b) in zip(s1, s2):
        result |= ord(a) ^ ord(b)
    return result == 0

def walk_class_hierarchy(clazz, encountered=None):
    """Walk class hierarchy, yielding most derived classes first"""
    if not encountered:
        encountered = []
    for subclass in clazz.__subclasses__():
        if subclass not in encountered:
            encountered.append(subclass)
            # drill down to leaves first
            for subsubclass in walk_class_hierarchy(subclass, encountered):
                yield subsubclass
            yield subclass

class UndoManager(object):
    """Provides a mechanism to facilitate rolling back a series of actions
    when an exception is raised.
    """
    def __init__(self):
        self.undo_stack = []

    def undo_with(self, undo_func):
        self.undo_stack.append(undo_func)

    def _rollback(self):
        for undo_func in reversed(self.undo_stack):
            undo_func()

    def rollback_and_reraise(self, msg=None, **kwargs):
        """Rollback a series of actions then re-raise the exception.

        .. note:: (sirp) This should only be called within an
                  exception handler.
        """
        with excutils.save_and_reraise_exception():
            if msg:
                LOG.exception(msg, **kwargs)

            self._rollback()

def ensure_tree(path):
    """Create a directory (and any ancestor directories required)

    :param path: Directory to create
    """
    try:
        #os.makedirs(path)
        execute('mkdir', '-p', path, run_as_root=True)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            if not os.path.isdir(path):
                raise
        else:
            raise

def rm_subtree(path, is_remove_dir=False):
    """ Remove all the contents under the the path including files and folders
    "param path: the directory
    """
    try:
        execute('chown', '-R', 'vsm:vsm', path, run_as_root=True)
        if os.path.isfile(path):
            os.unlink(path)
        else:
            for root, dirs, files in os.walk(path):
                for f in files:
                    os.unlink(os.path.join(root, f))
                if is_remove_dir:
                    for d in dirs:
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    except OSError:
        raise

def gen_ssh_key(username="vsm", hostname=None):
    """ Generate ssh key."""
    try:
        out, _err = execute('vsm-assist', 'checkfile', FLAGS.id_rsa_pub,
                                    run_as_root=True)
        LOG.info("DEBUG sshfile result%su" % out)
        if out[0] == "0":
            if hostname is None:
                hostname, err = execute('hostname', run_as_root=True)
            str = username+"@"+hostname
            LOG.info("DEBUG user:host %s" % str)
            execute('ssh-keygen', '-f', FLAGS.key_name, '-N', "",
                        '-C', str, run_as_root=True)
    except:
        raise

def to_bytes(text, default=0):
    """Try to turn a string into a number of bytes. Looks at the last
    characters of the text to determine what conversion is needed to
    turn the input text into a byte number.

    Supports: B/b, K/k, M/m, G/g, T/t (or the same with b/B on the end)

    """
    BYTE_MULTIPLIERS = {
        '': 1,
        't': 1024 ** 4,
        'g': 1024 ** 3,
        'm': 1024 ** 2,
        'k': 1024,
    }

    # Take off everything not number 'like' (which should leave
    # only the byte 'identifier' left)
    mult_key_org = text.lstrip('-1234567890')
    mult_key = mult_key_org.lower()
    mult_key_len = len(mult_key)
    if mult_key.endswith("b"):
        mult_key = mult_key[0:-1]
    try:
        multiplier = BYTE_MULTIPLIERS[mult_key]
        if mult_key_len:
            # Empty cases shouldn't cause text[0:-0]
            text = text[0:-mult_key_len]
        return int(text) * multiplier
    except KeyError:
        msg = _('Unknown byte multiplier: %s') % mult_key_org
        raise TypeError(msg)
    except ValueError:
        return default

def read_cached_file(filename, cache_info, reload_func=None):
    """Read from a file if it has been modified.

    :param cache_info: dictionary to hold opaque cache.
    :param reload_func: optional function to be called with data when
                        file is reloaded due to a modification.

    :returns: data from file

    """
    mtime = os.path.getmtime(filename)
    if not cache_info or mtime != cache_info.get('mtime'):
        with open(filename) as fap:
            cache_info['data'] = fap.read()
        cache_info['mtime'] = mtime
        if reload_func:
            reload_func(cache_info['data'])
    return cache_info['data']

def dumps(value):
    try:
        return json.dumps(value)
    except TypeError:
        pass
    return json.dumps(value)
    # ???? return json.dumps(to_primitive(value))

def loads(s):
    return json.loads(s)

def check_string_content(value, name):
    """Check the content of specified string"""    
    template = "^[a-zA-Z][0-9a-zA-Z_]*$"
    if not re.findall(template, value):
        msg = _("%(name)s has illegal characters") % locals()
        raise exception.InvalidInput(message=msg)

def check_string_length(value, name, min_length=0, max_length=None):
    """Check the length of specified string
    :param value: the value of the string
    :param name: the name of the string
    :param min_length: the min_length of the string
    :param max_length: the max_length of the string
    """
    if not isinstance(value, basestring):
        msg = _("%s is not a string or unicode") % name
        raise exception.InvalidInput(message=msg)

    if len(value) < min_length:
        msg = _("%(name)s has less than %(min_length)s "
                    "characters.") % locals()
        raise exception.InvalidInput(message=msg)

    if max_length and len(value) > max_length:
        msg = _("%(name)s has more than %(max_length)s "
                    "characters.") % locals()
        raise exception.InvalidInput(message=msg)

def gen_ceph_conf(values):
    """Use values dict to generate ceph.conf file."""
    def _check_values(conf_values):
        try:
            conf_values.get('monitor_ip_list')
            conf_values.get('monitor_host_list')
            conf_values.get('fsid')
            conf_values.get('public_network')
            conf_values.get('cluster_network')
            return True
        except:
            return False

    if not _check_values(values):
        return None

    with open(FLAGS.ceph_conf_template, 'r') as f:
        s = f.read()
        t = Template(s)
        return t.substitute(values)
    return None

def is_in_lan(ip, ip_mask):
    """Decide three networks:
            public addresss,
            secondary public address,
            cluster address
    """
    if ip in ipcalc.Network(ip_mask):
        return True
    else:
        return False

def gen_mon_keyring():
    """Just generate mon keyring."""
    key = os.urandom(16)
    header = struct.pack(
        '<hiih',
        1,                 # le16 type: CEPH_CRYPTO_AES
        int(time.time()),  # le32 created: seconds
        0,                 # le32 created: nanoseconds,
        len(key),          # le16: len(key)
    )
    key_string = base64.b64encode(header + key)
    keyring = '[mon.]\nkey = %s\ncaps mon = allow *' % key_string
    return keyring

def status_tracker(status_func):
    """status_tracker is used to update status in DB.

    status_func: refers to the function:
        db.init_node_update(context, init_node_id, values)

    In order to use this function.

    Prechecking: The DB updated must have status item.

    Step 1: Set parameters in context.
            values = {'id': id,
                      'values': values}
            context.status_values = values

    Step 1: Manager.py 's function should set as:
            @status_tracker(db.init_node_update)
            def do_something(context, ....)

    """
    def _deco(func):
        def __deco(*args, **kwargs):
            parameters = None
            try:
                ctxt = args[1]
                parameters = ctxt.values.get('status_values', None)

                if parameters:
                    LOG.info('Get parameters from context!')
                    LOG.info('Parameters in context = %s' % parameters)
                    parameters['values']['status'] = func.__name__
                    status_func(context=ctxt, **parameters)
                else:
                    LOG.info('Can not get parameters from context!')
            except:
                LOG.warning('Can not get parameters from context!')
                pass

            try:
                func(*args, **kwargs)
            except:
                if parameters:
                    parameters['values']['status'] = func.__name__ + 'Error'
                    status_func(context=ctxt, **parameters)
                raise exception.StatusTrackingError()
        return __deco
    return _deco

def clean_dirs(dir_path):
    try:
        files = execute('ls', dir_path, run_as_root=True)[0]
        files = files.split()
        for f in files:
            try:
                execute('rm', '-rf', dir_path + "/" + f,
                                    run_as_root=True)
            except:
                LOG.info('Error when delete file = %s' % f)
    except:
        LOG.info('LOOK UP dir failed %s' % dir_path)

def remove_lock_files():
    prog_name = os.path.basename(inspect.stack()[-1][1])
    try:
        execute('mkdir', '-p', FLAGS.state_path, run_as_root=True)
        out = execute('pgrep', prog_name, run_as_root=True)[0]
    except:
        pass

    if len(out) > 1:
        return

    try:
        files = execute('ls', FLAGS.state_path, run_as_root=True)[0]
        for file  in files.split():
            if file.find(prog_name) != -1:
                execute('rm', '-rf',
                    os.path.join(FLAGS.state_path, file),
                    run_as_root=True)
    except:
        pass

class FileLock(object):
    def __init__(self, file_name):
        prog_name = os.path.basename(inspect.stack()[-1][1])
        file_name = prog_name + file_name
        self.dir_path = os.path.join(FLAGS.state_path, file_name)
        try_times = 0
        while os.path.exists(self.dir_path):
            LOG.info('Wait for %s' % self.dir_path)
            time.sleep(20)
            try_times = try_times + 1
            if try_times > 10:
                break
        execute('touch', self.dir_path, run_as_root=True)

    def __del__(self):
        execute('rm', '-rf', self.dir_path, run_as_root=True)

uuid_dict = {}
def single_lock(func):
    def _deco(*args, **kwargs):
        uuid_str = uuid_dict.get(func.__name__, None)
        if not uuid_str:
            uuid_str = str(uuid.uuid1())
            uuid_dict[func.__name__] = uuid_str

        file_name = func.__name__ + uuid_str
        lock = FileLock(file_name)
        ret = func(*args, **kwargs)
        return ret
    return _deco

class PassLock(object):
    def __init__(self, file_name):
        prog_name = os.path.basename(inspect.stack()[-1][1])
        file_name = prog_name + file_name
        self.dir_path = os.path.join(FLAGS.state_path, file_name)
        self._run = True
        if os.path.exists(self.dir_path):
            self._run = False
        else:
            execute('touch', self.dir_path, run_as_root=True)

    def run(self):
        return self._run

    def __del__(self):
        if not self._run:
            return
        execute('rm', '-rf', self.dir_path, run_as_root=True)

def pass_lock(uuid_str):
    def _deco(func):
        def __deco(*args, **kwargs):
            file_name = func.__name__ + uuid_str
            lock = PassLock(file_name)
            if lock.run():
                ret = func(*args, **kwargs)
                return ret
        return __deco
    return _deco

class MultiThread(threading.Thread):

    def __init__(self, func, *args, **kwargs):
        threading.Thread.__init__(self)
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self): #pylint: disable=W0221
        try:
            ret = self._func(*self._args, **self._kwargs)
            LOG.debug('Thread run func = %s, ret = %s' % \
                (self._func, ret))
        except:
            raise

def start_threads(thread_list):
    def wait_single_thread(thd):
        while thd.is_alive():
            time.sleep(1)
    if isinstance(thread_list, list):
        for thd in thread_list:
            try:
                thd.start()
            except:
                raise
        for thd in thread_list:
            wait_single_thread(thd)
    else:
        try:
            thd.start()
        except:
            raise
        wait_single_thread(thd)

def get_fs_options(fs_type):
    if fs_type == 'ext4':
        return ['-F', 'user_xattr,rw,noatime']
    if fs_type == 'btrfs':
        return ['-f', 'noatime,nodiratime']
    if fs_type == 'xfs':
        return ['-f', 'rw,noatime,inode64,logbsize=256k,delaylog']

def append_to_file(file_path, msg):
    try:
        with open(file_path, 'a') as fd:
            fd.write(msg)
        return True
    except IOError as e:
        LOG.error(e)
        return False

    
