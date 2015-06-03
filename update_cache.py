#!/usr/bin/env python

import datetime
import pwd
import subprocess
import sys

from datetime import datetime, timedelta

from pysqlite2 import dbapi2 as sqlite  # https://github.com/ghaering/pysqlite


cache = sqlite.connect('cache')
cur = cache.cursor()

# Get mounted filesystems with user quotas.
filesystems = set()
mtab = open('/etc/mtab')
try:
    for line in mtab:
        dev, mountpoint, fstype, options, dump, fsck = line.split()
        if 'usrquota' in options.split(','):
            filesystems.add(mountpoint)
finally:
    mtab.close()

# Update quotas for every account on the system.
for pwd_entry in pwd.getpwall():
    for fs in filesystems:
        qt = subprocess.Popen(['quotatool', '-u', str(pwd_entry.pw_uid), '-d', fs], stdout=subprocess.PIPE)
        stdout, stderr = qt.communicate()
        uid, qt_fs, \
            blocks_used, block_quota, block_limit, block_grace, \
            inodes_used, inode_quota, inode_limit, inode_grace = \
            stdout.split()
        block_grace = int(block_grace)
        inode_grace = int(inode_grace)

        if block_grace == 0:
            block_grace_expires = None
        else:
            block_grace_expires = \
                (datetime.now().replace(microsecond=0) + timedelta(seconds=block_grace)).isoformat()
        if inode_grace == 0:
            inode_grace_expires = None
        else:
            inode_grace_expires = \
                (datetime.now().replace(microsecond=0) + timedelta(seconds=inode_grace)).isoformat()
        cur.execute("""UPDATE entry
                         SET blocks_used = ?,
                             block_soft_limit = ?,
                             block_hard_limit = ?,
                             inodes_used = ?,
                             inode_soft_limit = ?,
                             inode_hard_limit = ?,
                             block_grace_expires = ?,
                             inode_grace_expires = ?,
                             last_update = ?,
                             username = ?
                         WHERE filesystem = ?
                           AND uid = ?""",
                    (blocks_used, block_quota, block_limit,
                     inodes_used, inode_quota, inode_limit,
                     block_grace_expires, inode_grace_expires,
                     datetime.now().isoformat(),
                     pwd_entry.pw_name, fs, pwd_entry.pw_uid))
        if cur.rowcount == 0:
            cur.execute("""INSERT INTO entry
                             (blocks_used, block_soft_limit, block_hard_limit,
                              inodes_used, inode_soft_limit, inode_hard_limit,
                              block_grace_expires, inode_grace_expires,
                              last_update, username, filesystem, uid)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (blocks_used, block_quota, block_limit,
                     inodes_used, inode_quota, inode_limit,
                     block_grace_expires, inode_grace_expires,
                     datetime.now().isoformat(),
                     pwd_entry.pw_name, fs, pwd_entry.pw_uid))

cache.commit()
