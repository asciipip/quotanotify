#!/usr/bin/env python

import pwd

from pysqlite2 import dbapi2 as sqlite  # https://github.com/ghaering/pysqlite

from model import *

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
        ai = AccountInfo.from_quotatool(fs, pwd_entry.pw_uid, cur)
        ai.update()

cache.commit()
