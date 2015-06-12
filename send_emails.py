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
import syslog

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

def send_email_p(quotas):
    if len(quotas) == 0:
        return False

    # If any state has gotten worse, send an email.
    for q in quotas:
        if q.current_state > q.last_notify_state and \
                (q.current_state, q.last_notify_state) != (QuotaState.hard_limit, QuotaState.grace_expired):
            return True
    # No state is worse than it was.

    # Only send an email if all states are under quota...
    for q in quotas:
        if q.current_state != QuotaState.under_quota:
            return False
    # ...and at least one old state was over quota somehow.
    last_notification = max([q.last_notify_date for q in quotas])
    for q in quotas:
        if q.last_notify_state != QuotaState.under_quota:
            # Only send email if notification hysteresis has passed.
            return (datetime.now() - last_notification) > timedelta(minutes=config['notification_hysteresis'])

    # At this point, we've covered all of the circumstances under which we'd
    # want to send an email, so the default is not to send one.
    return False

def handle_state_change(ai):
    # Take all of the quota objects for the current account, throw out the ones
    # where there's no quota, and sort the rest by severity (worst first) and
    # then by anough other keys to guarantee a stable ordering.
    quotas_to_sort = [(q.current_state.index * -1, q.last_notify_state, q.last_notify_date, q.filesystem, q.quota_type, q) for q in ai.iter_quotas if q.current_state != QuotaState.no_quota]
    quotas = [t[-1] for t in sorted(quotas_to_sort)]

    # See if they're over quota anywhere.
    over_quotas = [q for q in quotas if q.current_state != QuotaState.under_quota]
    # If they're over quota at all, we only care about the areas where they're
    # over.
    if len(over_quotas) > 0:
        quotas = over_quotas

    if send_email_p(quotas):
        summary = ''
        details = []
        for q in quotas:
            if q.current_state == q.last_notify_state:
                template_key = '%s_summary_old' % q.quota_type.key
            else:
                template_key = '%s_summary_new' % q.quota_type.key
            template_str = config['templates'][q.current_state.key][template_key]
            if template_str:
                sum_text = jinja2.Template(template_str).render(account=ai, quota=q)
                if summary == '':
                    summary = sum_text
                else:
                    summary += '  Also, %s%s' % (sum_text[0].lower(), sum_text[1:])
            details.append(jinja2.Template(config['templates'][q.current_state.key]['%s_detail' % q.quota_type.key]).render(account=ai, quota=q))
        worst_state = quotas[0].current_state.key
        message = jj_env.get_template(config['templates'][worst_state]['main_file']).render(account=ai, summary=summary, details=details)
        if config['debug']:
            recipient = config['debug_mail_recipient']
        else:
            recipient = ai.username
        send_email(recipient, jinja2.Template(config['templates'][worst_state]['subject']).render(account=ai), message)
        log_message = 'Sent email to %s: %s' % (ai.username, ', '.join(['%s %s %s %s/%s' % (q.filesystem, q.quota_type.key, q.current_state.key, q.used, q.soft_limit) for q in quotas]))
        if config['debug']:
            print log_message
        else:
            syslog.syslog(syslog.LOG_INFO | syslog.LOG_USER, log_message)
        ai.set_notify(quotas)

for ai in AccountInfo.all(cur):
    handle_state_change(ai)
cache.commit()
