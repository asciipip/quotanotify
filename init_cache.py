#!/usr/bin/env python

from pysqlite2 import dbapi2 as sqlite

cache = sqlite.connect('cache')
cur = cache.cursor()

TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS entry (
    filesystem TEXT,
    account TEXT,
    blocks_used INTEGER,
    block_soft_limit INTEGER,
    block_hard_limit INTEGER,
    block_grace_period INTEGER,
    inodes_used INTEGER,
    inode_soft_limit INTEGER,
    inode_hard_limit INTEGER,
    inode_grace_period INTEGER,
    block_quota_notify TEXT,
    block_hard_notify TEXT,
    block_ok_notify TEXT,
    inode_quota_notify TEXT,
    inode_hard_notify TEXT,
    inode_ok_notify TEXT,
    PRIMARY KEY (filesystem, account)
)
"""
FILESYSTEM_INDEX_DEFINITION = 'CREATE INDEX IF NOT EXISTS entry_filesystem ON entry (filesystem)'
ACCOUNT_INDEX_DEFINITION    = 'CREATE INDEX IF NOT EXISTS entry_account ON entry (account)'

cur.execute(TABLE_DEFINITION)
cur.execute(FILESYSTEM_INDEX_DEFINITION)
cur.execute(ACCOUNT_INDEX_DEFINITION)
