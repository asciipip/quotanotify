#!/usr/bin/env python

from pysqlite2 import dbapi2 as sqlite

config = load_config_file()
cache = sqlite.connect(config['cache'])

TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS entry (
    filesystem TEXT,
    uid INTEGER,
    username TEXT,
    blocks_used INTEGER,
    block_soft_limit INTEGER,
    block_hard_limit INTEGER,
    block_grace_expires TEXT,
    inodes_used INTEGER,
    inode_soft_limit INTEGER,
    inode_hard_limit INTEGER,
    inode_grace_expires TEXT,
    block_quota_notify TEXT,
    block_hard_notify TEXT,
    block_ok_notify TEXT,
    last_update TEXT,
    inode_quota_notify TEXT,
    inode_hard_notify TEXT,
    inode_ok_notify TEXT,
    PRIMARY KEY (filesystem, uid)
)
"""
FILESYSTEM_INDEX_DEFINITION = 'CREATE INDEX IF NOT EXISTS entry_filesystem ON entry (filesystem)'
UID_INDEX_DEFINITION     = 'CREATE INDEX IF NOT EXISTS entry_uid ON entry (uid)'
USERNAME_INDEX_DEFINITION   = 'CREATE INDEX IF NOT EXISTS entry_username ON entry (username)'

cache.execute(TABLE_DEFINITION)
cache.execute(FILESYSTEM_INDEX_DEFINITION)
cache.execute(UID_INDEX_DEFINITION)
cache.execute(USERNAME_INDEX_DEFINITION)
