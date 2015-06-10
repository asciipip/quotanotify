#!/usr/bin/env python

from model import *
from templates import *

import email.MIMEText
import optparse
import os
import platform
import smtplib
import textwrap

from pysqlite2 import dbapi2 as sqlite  # https://github.com/ghaering/pysqlite

# Don't send notifications more often than this.
NOTIFICATION_HYSTERESIS = timedelta(minutes=30)

parser = optparse.OptionParser()
parser.add_option(
    '-c', '--cache',
    default=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'cache'),
    help='Location of the quota cache file.')
parser.add_option(
    '-s', '--smtp-host', default='localhost',
    help='Host for sending SMTP mail.  Defaults to localhost.')
parser.add_option(
    '-f', '--from-address', default='root',
    help='Email address to use in From: header of sent emails.  Defaults to root.')
parser.add_option(
    '-r', '--reply-to',
    help='Use if you want the emails to have a Reply-To: header.')
parser.add_option(
    '-d', '--domain', default=platform.node(),
    help='Domain to append to usernames to get email addresses.  Defaults to this system\'s hostname.')
(options, args) = parser.parse_args()

cache = sqlite.connect(options.cache)
cur = cache.cursor()

def send_email(to, subject, body):
    to_addr = '%s@%s' % (to, options.domain)
    if '@' in options.from_address:
        from_addr = options.from_address
    else:
        from_addr = '%s@%s' % (options.from_address, options.domain)
    msg = email.MIMEText.MIMEText(body)
    msg['subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    if options.reply_to:
        msg['Reply-To'] = options.reply_to
    s = smtplib.SMTP(options.smtp_host)
    s.sendmail(from_addr, to_addr, msg.as_string())
    s.quit()

def pick_template(notification_state, current_state, grace_expires, quota_notify, hard_notify, ok_notify):
    states = (notification_state, current_state)
    if states == (QuotaState.under_quota, QuotaState.soft_limit):
        return TemplateOverQuota
    elif states == (QuotaState.under_quota, QuotaState.hard_limit):
        if grace_expires < datetime.now():
            # This branch is really unlikely, but just in case...
            return TemplateGraceExpired
        else:
            return TemplateHardLimit
    elif states == (QuotaState.soft_limit, QuotaState.under_quota):
        if (datetime.now() - quota_notify) > NOTIFICATION_HYSTERESIS:
            return TemplateUnderQuota
    elif states == (QuotaState.soft_limit, QuotaState.hard_limit):
        if grace_expires < datetime.now():
            return TemplateGraceExpired
        else:
            return TemplateHardLimit
    elif states == (QuotaState.hard_limit, QuotaState.under_quota):
        if (datetime.now() - hard_notify) > NOTIFICATION_HYSTERESIS:
            return TemplateUnderQuota
    elif states == (QuotaState.hard_limit, QuotaState.soft_limit):
        return None
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
