#!/usr/bin/env python

import optparse
import os.path
import platform
import sys

import yaml  # http://pyyaml.org

DEFAULTS = {
    'cache': 'cache',
    'smtp_host': 'localhost',
    'from_address': 'root',
    'reply_to': None,
    'domain': platform.node(),
    'notification_hysteresis': 30,
}

def find_config_file():
    for path in ['/etc/quotanotify/config.yaml', '/etc/quotanotify.yaml',
                 '/usr/local/etc/quotanotify/config.yaml',
                 '/usr/local/etc/quotanotify.yaml',
                 os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yaml')]:
        if os.path.isfile(path):
            return path
    return None

def canonify_path(path, base):
    if os.path.isabs(path):
        return path
    return os.path.realpath(os.path.join(base, path))

def load_config_file():
    parser = optparse.OptionParser()
    parser.add_option('-c', '--config', default=find_config_file(),
                      help='Location of the configuration file.')
    (options, args) = parser.parse_args()
    try:
        config_file = open(options.config)
        try:
            config_dir = os.path.dirname(options.config)
            config = yaml.load(config_file, Loader=yaml.CLoader)
            # Fill in defaults.
            for dkey, dvalue in DEFAULTS.iteritems():
                if dkey not in config:
                    config[dkey] = dvalue
            # Canonify path names.
            config['cache'] = canonify_path(config['cache'], config_dir)
            for template_name in config['templates']:
                config['templates'][template_name]['main_file'] = \
                    canonify_path(config['templates'][template_name]['main_file'],
                                  config_dir)
            return config
        finally:
            config_file.close()
    except IOError:
        print >>sys.stderr, 'Unable to open config file: %s' % options.config
        sys.exit(1)
