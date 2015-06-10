#!/usr/bin/env python

import pwd
import subprocess

from datetime import datetime, timedelta

import iso8601  # https://bitbucket.org/micktwomey/pyiso8601
from enum import Enum  # https://pypi.python.org/pypi/enum34

def parse_datetime(field):
    """Parses an ISO-8601-formatted datetime.  Returns None for None."""
    if field:
        return iso8601.parse_date(field).replace(tzinfo=None)
    else:
        return None

QuotaState = Enum('under_quota', 'soft_limit', 'hard_limit', 'grace_expired')

def current_state(used, quota, limit, grace_expires):
    if quota == 0:
        return QuotaState.under_quota
    if used < quota:
        return QuotaState.under_quota
    if used < limit and datetime.now() < grace_expires:
        return QuotaState.soft_limit
    if used >= limit:
        return QuotaState.hard_limit
    return QuotaState.grace_expired

def notification_state(ok_notify, quota_notify, hard_notify):
    # Go with whichever notification was sent last.
    pairs = [(ok_notify, QuotaState.under_quota),
             (quota_notify, QuotaState.soft_limit),
             (hard_notify, QuotaState.grace_expired)]
    sorted_pairs = sorted([p for p in pairs if p[0]])
    if len(sorted_pairs) > 0:
        return sorted_pairs[-1][1]
    else:
        # No notifications ever sent, assume everything's okay.
        return QuotaState.under_quota

class AccountInfo:
    def __init__(self, filesystem, uid, db_cursor):
        self.filesystem = filesystem
        self.uid = uid
        self.db_cursor = db_cursor
        try:
            self.username = pwd.getpwuid(self.uid).pw_name
        except KeyError:
            self.username = '#%d' % self.uid

        self.db_cursor.execute('SELECT * FROM entry WHERE filesystem = ? AND uid = ?',
                               (self.filesystem, self.uid))
        # RHEL 5's pysqlite is too old to have indexing by field name, so we
        # have to fake it.
        indices = {}
        for i in xrange(0, len(self.db_cursor.description)):
            indices[self.db_cursor.description[i][0]] = i

        row = self.db_cursor.fetchone()
        if row:
            self.blocks_used = row[indices['blocks_used']]
            self.block_quota = row[indices['block_soft_limit']]
            self.block_limit = row[indices['block_hard_limit']]
            self.block_grace_expires = parse_datetime(row[indices['block_grace_expires']])
            self.inodes_used = row[indices['inodes_used']]
            self.inode_quota = row[indices['inode_soft_limit']]
            self.inode_limit = row[indices['inode_hard_limit']]
            self.inode_grace_expires = parse_datetime(row[indices['inode_grace_expires']])
            self.last_update = parse_datetime(row[indices['last_update']])
            self.block_quota_notify = parse_datetime(row[indices['block_quota_notify']])
            self.block_hard_notify = parse_datetime(row[indices['block_hard_notify']])
            self.block_ok_notify = parse_datetime(row[indices['block_ok_notify']])
            self.inode_quota_notify = parse_datetime(row[indices['inode_quota_notify']])
            self.inode_hard_notify = parse_datetime(row[indices['inode_hard_notify']])
            self.inode_ok_notify = parse_datetime(row[indices['inode_ok_notify']])
        else:
            self.blocks_used = None
            self.block_quota = None
            self.block_limit = None
            self.block_grace_expires = None
            self.inodes_used = None
            self.inode_quota = None
            self.inode_limit = None
            self.inode_grace_expires = None
            self.last_update = None
            self.block_quota_notify = None
            self.block_hard_notify = None
            self.block_ok_notify = None
            self.inode_quota_notify = None
            self.inode_hard_notify = None
            self.inode_ok_notify = None
            
    @staticmethod
    def from_quotatool(filesystem, uid, db_cursor):
        ai = AccountInfo(filesystem, uid, db_cursor)

        qt = subprocess.Popen(['quotatool', '-u', str(uid), '-d', filesystem],
                              stdout=subprocess.PIPE)
        stdout, stderr = qt.communicate()
        qt_uid, qt_fs, \
            blocks_used, block_quota, block_limit, block_grace, \
            inodes_used, inode_quota, inode_limit, inode_grace = \
            stdout.split()

        ai.blocks_used = int(blocks_used)
        ai.block_quota = int(block_quota)
        ai.block_limit = int(block_limit)
        ai.inodes_used = int(inodes_used)
        ai.inode_quota = int(inode_quota)
        ai.inode_limit = int(inode_limit)

        if int(block_grace) == 0:
            ai.block_grace_expires = None
        else:
            ai.block_grace_expires = \
                datetime.now().replace(microsecond=0) + timedelta(seconds=int(block_grace))
        if int(inode_grace) == 0:
            ai.inode_grace_expires = None
        else:
            ai.inode_grace_expires = \
                datetime.now().replace(microsecond=0) + timedelta(seconds=int(inode_grace))

        return ai

    @staticmethod
    def all(db_cursor):
        """Generator that yields all entries in the cache."""
        tmp_cur = db_cursor.connection.cursor()
        tmp_cur.execute('SELECT filesystem, uid FROM entry')
        for row in tmp_cur:
            yield AccountInfo(row[0], row[1], db_cursor)

    def update(self):
        self.db_cursor.execute(
            """UPDATE entry
                 SET blocks_used = ?,
                     block_soft_limit = ?,
                     block_hard_limit = ?,
                     inodes_used = ?,
                     inode_soft_limit = ?,
                     inode_hard_limit = ?,
                     block_grace_expires = ?,
                     inode_grace_expires = ?,
                     block_quota_notify = ?,
                     block_hard_notify = ?,
                     block_ok_notify = ?,
                     inode_quota_notify = ?,
                     inode_hard_notify = ?,
                     inode_ok_notify = ?,
                     last_update = ?,
                     username = ?
                 WHERE filesystem = ?
                   AND uid = ?""",
            (self.blocks_used, self.block_quota, self.block_limit,
             self.inodes_used, self.inode_quota, self.inode_limit,
             self.block_grace_expires and self.block_grace_expires.isoformat(),
             self.inode_grace_expires and self.inode_grace_expires.isoformat(),
             self.block_quota_notify and self.block_quota_notify.isoformat(),
             self.block_hard_notify and self.block_hard_notify.isoformat(),
             self.block_ok_notify and self.block_ok_notify.isoformat(),
             self.inode_quota_notify and self.inode_quota_notify.isoformat(),
             self.inode_hard_notify and self.inode_hard_notify.isoformat(),
             self.inode_ok_notify and self.inode_ok_notify.isoformat(),
             datetime.now().isoformat(),
             self.username, self.filesystem, self.uid))
        if self.db_cursor.rowcount == 0:
            self.db_cursor.execute(
                """INSERT INTO entry
                     (blocks_used, block_soft_limit, block_hard_limit,
                      inodes_used, inode_soft_limit, inode_hard_limit,
                      block_grace_expires, inode_grace_expires,
                      block_quota_notify, block_hard_notify, block_ok_notify,
                      inode_quota_notify, inode_hard_notify, inode_ok_notify,
                      last_update, username, filesystem, uid)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.blocks_used, self.block_quota, self.block_limit,
                 self.inodes_used, self.inode_quota, self.inode_limit,
                 self.block_grace_expires and self.block_grace_expires.isoformat(),
                 self.inode_grace_expires and self.inode_grace_expires.isoformat(),
                 self.block_quota_notify and self.block_quota_notify.isoformat(),
                 self.block_hard_notify and self.block_hard_notify.isoformat(),
                 self.block_ok_notify and self.block_ok_notify.isoformat(),
                 self.inode_quota_notify and self.inode_quota_notify.isoformat(),
                 self.inode_hard_notify and self.inode_hard_notify.isoformat(),
                 self.inode_ok_notify and self.inode_ok_notify.isoformat(),
                 datetime.now().isoformat(),
                 self.username, self.filesystem, self.uid))

    @property
    def current_block_state(self):
        return current_state(self.blocks_used, self.block_quota,
                             self.block_limit, self.block_grace_expires)

    @property
    def current_inode_state(self):
        return current_state(self.inodes_used, self.inode_quota,
                             self.inode_limit, self.inode_grace_expires)

    @property
    def notification_block_state(self):
        return notification_state(self.block_ok_notify,
                                  self.block_quota_notify,
                                  self.block_hard_notify)

    @property
    def notification_inode_state(self):
        return notification_state(self.inode_ok_notify,
                                  self.inode_quota_notify,
                                  self.inode_hard_notify)

    @property
    def bytes_used(self):
        return self.blocks_used * 1024

    @property
    def bytes_quota(self):
        return self.block_quota * 1024

    @property
    def bytes_limit(self):
        return self.block_limit * 1024
