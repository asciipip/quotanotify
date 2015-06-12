#!/usr/bin/env python

# Copyright (c) 2015  Phil Gold <phil_g@pobox.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from config import *

from pysqlite2 import dbapi2 as sqlite

config = load_config_file()
cache = sqlite.connect(config['cache'])

TABLE_DEFINITION = """
CREATE TABLE IF NOT EXISTS entry (
    filesystem TEXT,
    uid INTEGER,
    quota_type INTEGER,
    used INTEGER,
    soft_limit INTEGER,
    hard_limit INTEGER,
    grace_expires TEXT,
    last_notify_date TEXT,
    last_notify_state INTEGER,
    last_update TEXT,
    PRIMARY KEY (filesystem, uid, quota_type)
)
"""
UID_INDEX_DEFINITION     = 'CREATE INDEX IF NOT EXISTS entry_uid ON entry (uid)'

cache.execute(TABLE_DEFINITION)
cache.execute(UID_INDEX_DEFINITION)
