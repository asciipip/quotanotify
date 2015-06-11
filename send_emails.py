#!/usr/bin/env python

# Copyright (c) 2015  Phil Gold <phil_g@pobox.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from config import *
from model import *

import email.MIMEText
import smtplib
import textwrap

import jinja2  # http://jinja.pocoo.org

from pysqlite2 import dbapi2 as sqlite  # https://github.com/ghaering/pysqlite

config = load_config_file()
cache = sqlite.connect(config['cache'])
cur = cache.cursor()

jj_env = jinja2.Environment(loader=jinja2.FileSystemLoader('/'))

def send_email(to, subject, body):
    to_addr = '%s@%s' % (to, config['domain'])
    if '@' in config['from_address']:
        from_addr = config['from_address']
    else:
        from_addr = '%s@%s' % (config['from_address'], config['domain'])
    msg = email.MIMEText.MIMEText(body)
    msg['subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    if config['reply_to']:
        msg['Reply-To'] = config['reply_to']
    s = smtplib.SMTP(config['smtp_host'])
    s.sendmail(from_addr, to_addr, msg.as_string())
    s.quit()

def send_email_p(changes, last_notification):
    # If any state has gotten worse, send an email.
    for new_state, old_state, area in changes:
        if new_state > old_state and (old_state, new_state) != (QuotaState.hard_limit, QuotaState.grace_expired):
            return True
    # No state is worse than it was.
    # Only send an email if all states are under quota...
    for new_state, old_state, area in changes:
        if new_state != QuotaState.under_quota:
            return False
    # ...and at least one old state was over quota somehow.
    for new_state, old_state, area in changes:
        if old_state != QuotaState.under_quota:
            # Only send email if notification hysteresis has passed.
            return (datetime.now() - last_notification) > timedelta(minutes=config['notification_hysteresis'])
    # At this point, we've covered all of the circumstances under which we'd
    # want to send an email, so the default is not to send one.
    return False

def handle_state_change(ai):
    changes = [(ai.current_block_state, ai.notification_block_state, 'block'),
               (ai.current_inode_state, ai.notification_inode_state, 'inode')]
    # See if the person is currently under quota.
    under_quota = True
    for new_state, old_state, area in changes:
        if new_state != QuotaState.under_quota:
            under_quota = False
    # If they're not under quota, we only care about the areas where they're
    # over.
    if not under_quota:
        changes = [c for c in changes if c[0] != QuotaState.under_quota]
    changes.sort()
    changes.reverse()
    if send_email_p(changes, ai.last_notification):
        summary = ''
        details = []
        for new_state, old_state, area in changes:
            if old_state == new_state:
                template_key = '%s_summary_old' % area
            else:
                template_key = '%s_summary_new' % area
            template_str = config['templates'][new_state.key][template_key]
            if template_str:
                sum_text = jinja2.Template(config['templates'][new_state.key][template_key]).render(ai=ai)
                if summary == '':
                    summary = sum_text
                else:
                    summary += '  Also, %s%s' % (sum_text[0].lower(), sum_text[1:])
            details.append(jinja2.Template(config['templates'][new_state.key]['%s_detail' % area]).render(ai=ai))
        worst_state = changes[0][0]
        message = jj_env.get_template(config['templates'][worst_state.key]['main_file']).render(ai=ai, summary=summary, details=details)
        send_email('phil', jinja2.Template(config['templates'][worst_state.key]['subject']).render(ai=ai), message)

for ai in AccountInfo.all(cur):
    handle_state_change(ai)
