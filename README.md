# quotanotify

This project is an attempt to make a system to notify people who have
gone over their quotas about that fact, but in a friendlier way than
the standard "run `warnquota` every night from cron".

This system will send an email to an account only once for each of the
following events:

 * The account goes over its soft limit for a quota.
 * The account hits its hard limit for a quota or its soft limit grace
   period expires.
 * The account goes back under all of its quotas.


## Installing

### Prerequisites

All of the scripts here are written in Python and should work at least
back as far as Python 2.4 (so they're useful on RHEL 5 systems).  You
will need the following Python modules installed:

 * enum34: Included with python 3.4; otherwise available from
   https://pypi.python.org/pypi/enum34
 * iso8601: https://bitbucket.org/micktwomey/pyiso8601
 * jinja2: http://jinja.pocoo.org
 * pysqlite: Included with Python 2.5 and later; otherwise available
   from https://github.com/ghaering/pysqlite
 * PyYAML: http://pyyaml.org

### Installation

Put the scripts anywhere you want, but they all need to be in the same
directory.  You should make an `/etc/quotanotify` (or
`/usr/local/etc/quotanotify`) directory and copy `config.example.yaml`
into that directory as `config.yaml`.  You should probably make a
`/etc/quotanotify/templates` (or `/usr/local/etc/quotanotify/etc/templates`)
directory and put your email templates there.  There are sample
templates in this project's `templates` directory and the template
structure is described later in this file.

Edit `config.yaml`.  The defaults are probably okay for most sites,
but you might want to modify the `domain` setting.  You'll also need
to choose a location for your cache file.  `/var/cache/quotanotify/cache`
would probably be ideal.

After `config.yaml` is set with the location of your cache file, run
`init_cache.py` to initialize the cache.

### Cron Jobs

`update_cache.py` needs to be run periodically to update the cache.
If you have few enough accounts (less than about 10,000 on an
otherwise decent system), you can run it every minute.  If that proves
to be too slow, you'll have to run it less often.  The program needs
to run as an account that has full access to your quota information,
which probably means root.  A suggested configuration is to put the
following content into a `/etc/cron.d/quotanotify` file:

    */1 * * * *  root  /path/to/update_cache.py

If you want to send notification emails, you'll need to run the
`send_email.py` program periodically, so you'll have to set up a cron
job for that, too.  Running it every five minutes should give you
reasonable results.  It only needs to be run with enough permissions
to read the cache file, so it doesn't need root privileges.  If you
created a quotanotify user account to own the cache file, you could
add the following line to your `/etc/cron.d/quotanotify` file:

    */5 * * * *  quotanotify  /path/to/send_emails.py


## The Configuration File

The configuration file, located in `/etc/quotanotify/config.yaml` or
`/usr/local/etc/quotanotify/config.yaml` (or passed to the quotanotify
programs via their `--config` command line parameter) is in
[YAML](http://yaml.org) format.  For the most part, that just means
that configuration options look like this in the file:

    option_name: value

The email templates use a bit more of YAML's structure; that's
described in the "Email Templates" section of this file.


## Email Templates

Templates for the emails sent are written in Jinja2; see
http://jinja.pocoo.org/docs/dev/templates/ for details about what you
can do with it.

There are four basic templates defined in the config file:

 * soft_limit: Used when an account has gone over its soft limit (but
   not hit its hard limit and still has time left in its grace
   period).
 * hard_limit: Used when an account has hit its hard limt.
 * grace_expired: Used when an account has exceeded the grace period
   for its soft limit.
 * under_quota: Used when an account has gone back under quota after
   previously having been notified of exceeding its quota.

The four templates are described using YAML's hierarchy in the
`config.yaml` file like this:

    templates:
      soft_limit:
        # Soft limit settings...
      hard_limit:
        # Hard limit settings...
      # Etc.

Each template has the following settings:

 * `main_file` - A file that gives the general template for the body
   of emails sent to people.  When the template is generated, it is
   given three parameters:
   * `account` - The `AccountInfo` object that contains information
     about the account being emailed.  See `model.py` for its
     properties.
   * `summary` - A string summarizing each of the areas where the
     account is over quota.
   * `details` - A list of strings, each of which gives details about
     an area where the account is over quota.
 * `subject` - The subject line to be used in the email sent to the
   account owner.
 * `block_summary_new`, `block_summary_old`, `inode_summary_new`, and
   `inode_summary_old` - Template strings that should give a summary
   of the problem.  The "`_old`" variants are used if the account
   owner has already been notified about that problem but another
   email is being sent because of a new problem in a different quota
   area.  (e.g. They've been over quota for block usage but they just
   went over quota for inode usage, too.)  These templates are passed
   two parameters:
   * `account` - An `AccountInfo` object that contains information
     about the account being emailed.
   * `quota` - A `QuotaInfo` object that contains information about
     the specific quota being addressed.  See its docstring in
     `model.py` for descriptions of its properties.
 * `block_detail`, `inode_detail` - Template strings that should give
   details about the problem.  It would be appropriate to describe,
   for instance, the exact amount of space the account is using and
   what its current limit is.  Like the summary templates, these are
   given two parameters: `account` and `quota`.

You can look at the `config.example.yaml` file in this project for
example templates.
