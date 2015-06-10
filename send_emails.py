#!/usr/bin/env python

from config import *
from model import *
from templates import *

import email.MIMEText
import smtplib
import textwrap

from pysqlite2 import dbapi2 as sqlite  # https://github.com/ghaering/pysqlite

config = load_config_file()
cache = sqlite.connect(config['cache'])
cur = cache.cursor()

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

def pick_template(notification_state, current_state, grace_expires, quota_notify, hard_notify, ok_notify):
    if current_state > notification_state:
        # Things have gotten worse; we should send an email.
        if (notification_state, current_state) == (QuotaState.hard_limit, QuotaState.grace_expired):
            # But we don't send emails if they've already hit their hard limit.
            return None
        if current_state == QuotaState.soft_limit:
            return TemplateOverQuota
        if current_state == QuotaState.hard_limit:
            return TemplateHardLimit
        if current_state == QuotaState.grace_expired:
            return TemplateGraceExpired
    if current_state == QuotaState.under_quota and \
            notification_state != QuotaState.under_quota and \
            (datetime.now() - quota_notify) > config['notification_hysteresis']:
        return TemplateUnderQuota
    return None

def handle_state_change(ai):
    if ai.current_block_state == ai.notification_block_state and \
            ai.current_inode_state == ai.notification_inode_state:
        return
    block_template = pick_template(ai.notification_block_state,
                                   ai.current_block_state,
                                   ai.block_grace_expires,
                                   ai.block_quota_notify,
                                   ai.block_hard_notify,
                                   ai.block_ok_notify)
    inode_template = pick_template(ai.notification_inode_state,
                                   ai.current_inode_state,
                                   ai.inode_grace_expires,
                                   ai.inode_quota_notify,
                                   ai.inode_hard_notify,
                                   ai.inode_ok_notify)
    if ai.current_inode_state > ai.current_block_state and inode_template:
        general_template = inode_template
    else:
        general_template = block_template
    if general_template.header != '':
        msg = general_template.header + '\n\n'
    else:
        msg = ''
    if block_template:
        msg += '\n'.join(textwrap.wrap(block_template.block_text.render(ai=ai)))
        msg += '\n\n'
    if inode_template:
        msg += '\n'.join(textwrap.wrap(inode_template.inode_text.render(ai=ai)))
        msg += '\n\n'
    msg += general_template.footer
    send_email('phil', general_template.subject.render(ai=ai), msg)

for ai in AccountInfo.all(cur):
    handle_state_change(ai)
