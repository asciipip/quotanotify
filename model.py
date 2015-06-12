#!/usr/bin/env python

# Copyright (c) 2015  Phil Gold <phil_g@pobox.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


import pwd
import subprocess

from datetime import datetime, timedelta

import iso8601  # https://bitbucket.org/micktwomey/pyiso8601
from enum import Enum  # https://pypi.python.org/pypi/enum34

QuotaType = Enum('block', 'inode')
QuotaState = Enum('no_quota', 'under_quota', 'soft_limit', 'hard_limit', 'grace_expired')

def parse_datetime(field):
    """Parses an ISO-8601-formatted datetime.  Returns None for None."""
    if field:
        return iso8601.parse_date(field).replace(tzinfo=None)
    else:
        return None

def list_quota_filesystems():
    filesystems = set()
    mtab = open('/etc/mtab')
    try:
        for line in mtab:
            dev, mountpoint, fstype, options, dump, fsck = line.split()
            if 'usrquota' in options.split(','):
                filesystems.add(mountpoint)
    finally:
        mtab.close()
    return filesystems


class QuotaInfo:
    """Information about a specific type of quota (block or inode) for a
    specific account on a specific filesystem.

    Attributes:
        uid         The UID of the account to which this quota applies.
        filesystem  The filesystem to which this quota applies.
        quota_type  A member of the QuotaType enum indicating whether this is a
                    block quota or inode quota.
        used        The number of resources (blocks or inodes) currently in use.
        soft_limit  The soft limit for this resource.
        hard_limit  The hard limit for this resource.
        grace_expires  A datetime indicating when the grace period for exceeding
                       the soft limit will expire.  If the soft limit is not
                       exceeded, the value of this attribute will be None.
        last_notify_date  A datetime indicating the date and time when the
                          account owner was last contacted about their quota
                          usage.
        last_notify_state  A member of the QuotaState enum indicating the state
                           of the account's quota at the time given by
                           last_notify_date.
        current_state  A member of the QuotaState enum indicating the current
                       state of this quota.
        bytes_used  For block quotas, the number of bytes currently in use.
        byte_soft_limit  For block quotas, the soft limit in bytes.
        byte_hard_limit  For block quotas, the hard limit in bytes.
    """

    def __init__(self, uid, filesystem, quota_type, db_cursor):
        self.uid = uid
        self.filesystem = filesystem
        self.quota_type = quota_type
        self.db_cursor = db_cursor
        self.refresh()

    def __repr__(self):
        return '<QuotaInfo(%s, %s, %s): %s %s/%s/%s>' % (self.uid, self.filesystem, self.quota_type.key, self.current_state.key, self.used, self.soft_limit, self.hard_limit)

    def refresh(self):
        self.db_cursor.execute('SELECT * FROM entry WHERE uid = ? AND filesystem = ? AND quota_type = ?',
                               (self.uid, self.filesystem, self.quota_type.index))
        # RHEL 5's pysqlite is too old to have indexing by field name, so we
        # have to fake it.
        indices = {}
        for i in xrange(0, len(self.db_cursor.description)):
            indices[self.db_cursor.description[i][0]] = i
        
        row = self.db_cursor.fetchone()
        if row:
            self.used = row[indices['used']]
            self.soft_limit = row[indices['soft_limit']]
            self.hard_limit = row[indices['hard_limit']]
            self.grace_expires = parse_datetime(row[indices['grace_expires']])
            self.last_notify_date = parse_datetime(row[indices['last_notify_date']])
            last_notify_state = row[indices['last_notify_state']]
            if last_notify_state:
                self.last_notify_state = QuotaState[last_notify_state]
            else:
                # Pretend everything's okay.
                self.last_notify_state = QuotaState.under_quota
        else:
            self.used = None
            self.soft_limit = None
            self.hard_limit = None
            self.grace_expires = None
            self.last_notify_date = None
            self.last_notify_state = None
        
    def set_from_quotatool(self, used, soft_limit, hard_limit, grace):
        """Update this object's quota information from the strings parsed from
        quotatool's output."""
        self.used = int(used)
        self.soft_limit = int(soft_limit)
        self.hard_limit = int(hard_limit)
        if int(grace) == 0:
            self.grace_expires = None
        else:
            self.grace_expires = \
                datetime.now().replace(microsecond=0) + timedelta(seconds=int(grace))

    @property
    def current_state(self):
        if self.soft_limit == 0:
            return QuotaState.no_quota
        if self.used < self.soft_limit:
            return QuotaState.under_quota
        if self.used < self.hard_limit and datetime.now() < self.grace_expires:
            return QuotaState.soft_limit
        if self.used >= self.hard_limit:
            return QuotaState.hard_limit
        return QuotaState.grace_expired

    @property
    def bytes_used(self):
        return self.used * 1024

    @property
    def byte_soft_limit(self):
        return self.soft_limit * 1024

    @property
    def byte_hard_limit(self):
        return self.hard_limit * 1024

    def update(self):
        self.db_cursor.execute(
            """UPDATE entry
                 SET used = ?,
                     soft_limit = ?,
                     hard_limit = ?,
                     grace_expires = ?,
                     last_notify_date = ?,
                     last_notify_state = ?,
                     last_update = ?
                 WHERE uid = ?
                   AND filesystem = ?
                   AND quota_type = ?""",
            (self.used, self.soft_limit, self.hard_limit,
             self.grace_expires and self.grace_expires.isoformat(),
             self.last_notify_date and self.last_notify_date.isoformat(),
             self.last_notify_state and self.last_notify_state.index,
             datetime.now().isoformat(),
             self.uid, self.filesystem, self.quota_type.index))
        if self.db_cursor.rowcount == 0:
            self.db_cursor.execute(
                """INSERT INTO entry
                     (used, soft_limit, hard_limit, grace_expires,
                      last_notify_date, last_notify_state, last_update,
                      uid, filesystem, quota_type)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.used, self.soft_limit, self.hard_limit,
                 self.grace_expires and self.grace_expires.isoformat(),
                 self.last_notify_date and self.last_notify_date.isoformat(),
                 self.last_notify_state and self.last_notify_state.index,
                 datetime.now().isoformat(),
                 self.uid, self.filesystem, self.quota_type.index))

    def set_notify(self):
        """Update this object with a new notification date."""
        self.last_notify_state = self.current_state
        self.last_notify_date = datetime.now()
        

class AccountInfo:
    """Quota information about a particular account.

    Attributes:
        uid     The UID of the account.
        quotas  A nested dictionary of QuotaInfo objects.  The first set of keys
                are the filesystems for which quota information exists.  The
                second set of keys are the values of the QuotaType enum.  Thus,
                to access the block quotas for the /home filesystem, you would
                use `obj.quotas['/home'][QuotaType.block]`.
    """

    @staticmethod
    def all(db_cursor):
        """Generator that yields all entries in the cache."""
        db_cursor.execute('SELECT DISTINCT uid FROM entry')
        results = db_cursor.fetchall()
        for row in results:
            yield AccountInfo(row[0], db_cursor)

    def __init__(self, uid, db_cursor):
        self.uid = uid
        self.db_cursor = db_cursor

        self.refresh_from_db()

    @property
    def username(self):
        try:
            return pwd.getpwuid(self.uid).pw_name
        except KeyError:
            return '#%d' % self.uid

    @property
    def iter_quotas(self):
        """Generator to iterate through all quota objects in a flat manner."""
        for filesystem in sorted(self.quotas.keys()):
            for area in QuotaType:
                yield self.quotas[filesystem][area]

    def refresh_from_db(self):
        self.quotas = {}
        self.db_cursor.execute(
            'SELECT DISTINCT filesystem FROM entry WHERE uid = ?', (self.uid,))
        rows = self.db_cursor.fetchall()
        for row in rows:
            self.quotas[row[0]] = {}
            self.quotas[row[0]][QuotaType.block] = QuotaInfo(self.uid, row[0], QuotaType.block, self.db_cursor)
            self.quotas[row[0]][QuotaType.inode] = QuotaInfo(self.uid, row[0], QuotaType.inode, self.db_cursor)

    def refresh_from_system(self):
        self.quotas = {}
        for filesystem in list_quota_filesystems():
            self.quotas[filesystem] = {}

            bqi = QuotaInfo(self.uid, filesystem, QuotaType.block, self.db_cursor)
            iqi = QuotaInfo(self.uid, filesystem, QuotaType.inode, self.db_cursor)

            qt = subprocess.Popen(['quotatool', '-u', str(self.uid),
                                   '-d', filesystem],
                                  stdout=subprocess.PIPE)
            stdout, stderr = qt.communicate()
            qt_uid, qt_fs, \
                blocks_used, block_quota, block_limit, block_grace, \
                inodes_used, inode_quota, inode_limit, inode_grace = \
                stdout.split()
            
            bqi.set_from_quotatool(blocks_used, block_quota, block_limit, block_grace)
            iqi.set_from_quotatool(inodes_used, inode_quota, inode_limit, inode_grace)

            self.quotas[filesystem][QuotaType.block] = bqi
            self.quotas[filesystem][QuotaType.inode] = iqi

    def update(self):
        """Update the cache file with the current object's information."""
        for quota in self.iter_quotas:
            quota.update()

    def set_notify(self, quotas_notified):
        """Update all supplied quotas with a new notification date."""
        self.refresh_from_db()
        for q in quotas_notified:
            self.quotas[q.filesystem][q.quota_type].set_notify()
        self.update()
