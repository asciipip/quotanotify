#!/usr/bin/env python

import re
import subprocess

from pysqlite2 import dbapi2 as sqlite

cache = sqlite.connect('cache')
cur = cache.cursor()

repquota = subprocess.Popen(['repquota', '-va'], stdout=subprocess.PIPE)
repquota_out, ignored = repquota.communicate()

for line in repquota_out.splitlines():
    dev_match = re.search('^\\*\\*\\* Report for user quotas on device (.*)$',
                          line)
    if dev_match:
        device = dev_match.group(1)
        in_header = True
        continue
    if re.search('^-+$', line):
        in_header = False
        continue
    if in_header:
        continue
    # In the below regex, grace periods could be five-character descriptions,
    # e.g. "5days" or "25:32", or they could be blank (composed of spaces).
    # That's the main reason we have to use a regex to parse this rather than
    # just using line.split()
    detail_match = re.search(r"""^([^ ]+)\ +    # username
                                 ([-+]{2})\ +   # quota summary
                                 ([0-9]+)\ +    # blocks used
                                 ([0-9]+)\ +    # block soft limit
                                 ([0-9]+)\ {2}  # block hard limit
                                 (.....)\ +     # block grace period
                                 ([0-9]+)\ +    # inodes used
                                 ([0-9]+)\ +    # inode soft limit
                                 ([0-9]+)\ {2}  # inode hard limit
                                 (.....)$       # inode grace period
                                 """, line, re.X)
    if detail_match:
        username = detail_match.group(1)
        blocks_used      = int(detail_match.group(3))
        block_soft_limit = int(detail_match.group(4))
        block_hard_limit = int(detail_match.group(5))
        inodes_used      = int(detail_match.group(7))
        inode_soft_limit = int(detail_match.group(8))
        inode_hard_limit = int(detail_match.group(9))
        if detail_match.group(6).strip() != '':
            print '"%s"' % detail_match.group(6)
        cur.execute("""UPDATE entry
                         SET blocks_used = ?,
                             block_soft_limit = ?,
                             block_hard_limit = ?,
                             inodes_used = ?,
                             inode_soft_limit = ?,
                             inode_hard_limit = ?
                         WHERE filesystem = ?
                           AND account = ?""",
                    (blocks_used, block_soft_limit, block_hard_limit,
                     inodes_used, inode_soft_limit, inode_hard_limit,
                     device, username))
        if cur.rowcount == 0:
            cur.execute("""INSERT INTO entry
                             (blocks_used, block_soft_limit, block_hard_limit,
                              inodes_used, inode_soft_limit, inode_hard_limit,
                              filesystem, account)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (blocks_used, block_soft_limit, block_hard_limit,
                     inodes_used, inode_soft_limit, inode_hard_limit,
                     device, username))

cache.commit()
