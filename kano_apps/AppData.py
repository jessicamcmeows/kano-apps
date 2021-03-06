# AppData.py
#
# Copyright (C) 2014, 2015 Kano Computing Ltd.
# License: http://www.gnu.org/licenses/gpl-2.0.txt GNU GPL v2
#
# Which apps to look for on the system

import os
import re
import json

from kano_settings.system.locale import get_locale, ensure_utf_locale
from kano_apps.utils import get_dpkg_dict
from kano_i18n.init import get_current_translation

# The system directory that contains *.app and *.desktop entries
_SYSTEM_APPLICATIONS_LOC = '/usr/share/applications/'
DEFAULT_LOCALE = 'en_US'
LOCALE_KEY = 'locale'
APP_LOCALE_DIR = os.path.join(_SYSTEM_APPLICATIONS_LOC, 'locale')


# Store the package list globally so it doesn't get parsed every time
# we query for applications - it takes some time to parse it.
_INSTALLED_PKGS = get_dpkg_dict()[0]


def refresh_package_list():
    """ Reload the cached list of installed packages. """

    global _INSTALLED_PKGS

    _INSTALLED_PKGS = get_dpkg_dict()[0]


def try_exec(app):
    """ Searches through system path and tries executing the app in question.

        :param app: Application name or full absolute path.
        :type app: str

        :returns: True if app exists and can be executed, False otherwise.
        :rtype: bool
    """

    path = None
    if len(app) <= 0:
        return False
    elif app[0] == '/':
        path = app
    else:
        for path in os.environ["PATH"].split(":"):
            possible_path = path + "/" + app
            if os.path.exists(possible_path):
                path = possible_path
                break

    return path is not None and \
        os.path.isfile(path) and \
        os.access(path, os.X_OK)


def is_app_installed(app):
    """ Query the installed packages.

        :param app: The application's dict.
        :type app: dict

        :returns: True if all the dependencies were installed, False otherwise.
    """

    for pkg in app["packages"] + app["dependencies"]:
        if pkg not in _INSTALLED_PKGS:
            return False
    return True


def get_locale_dir(locale_code):
    return os.path.join(APP_LOCALE_DIR, locale_code)

def flatten_locale(apps, locale):
    flat_apps = {}

    for app_name, app_data in apps.iteritems():
        app_locale = app_data.pop(LOCALE_KEY, {})
        if locale in app_locale:
            app_data.update(app_locale[locale])
        flat_apps[app_name] = app_data

    return flat_apps


def get_applications(parse_cmds=True, all_locales=False, current_locale=True):
    """ Get all the applications installed on the system.

        :param parse_cmds:
        :type parse_cmds: bool

        :returns: A dict with all apps.
        :rtype: dict
    """

    loc = os.path.expanduser(_SYSTEM_APPLICATIONS_LOC)
    blacklist = [
        "idle3.desktop", "idle.desktop", "idle-python2.7.desktop",
        "idle-python3.2.desktop", "xarchiver.desktop",
        "make-minecraft.desktop", "make-music.desktop", "make-pong.desktop",
        "make-snake.desktop", "kano-video.desktop", "lxsession-edit.desktop",
        "lxrandr.desktop", "lxinput.desktop", "obconf.desktop",
        "openbox.desktop", "libfm-pref-apps.desktop", "lxappearance.desktop",
        "htop.desktop", "pcmanfm-desktop-pref.desktop", "video-cli.desktop",
        "lxsession-default-apps.desktop", "pcmanfm.desktop", "help.desktop",
        "rxvt-unicode.desktop", "org.gnome.gedit.desktop",
        "chromium-browser.desktop", "openjdk-7-policytool.desktop"
    ]

    def _collect_apps(application_dir, skip_checks=False):
        if not os.path.exists(application_dir):
            return {}

        _applications = {}

        for f in os.listdir(os.path.join(application_dir, '')):
            fp = os.path.join(application_dir, f)

            if os.path.isdir(fp):
                continue

            if f[-4:] == ".app":
                data = load_from_app_file(fp, not skip_checks and parse_cmds)
                if data is not None:
                    if not skip_checks and not is_app_installed(data):
                        data["_install"] = True

                    _applications[f] = data
                    if "overrides" in data:
                        blacklist.extend(data["overrides"])

            elif f[-8:] == ".desktop" and f[0:5] != "auto_":
                data = _load_from_dentry(fp)
                if data is not None:
                    _applications[f] = data

        return _applications

    locales = [
        (DEFAULT_LOCALE, _SYSTEM_APPLICATIONS_LOC)
    ]

    locale_code = None

    if all_locales:
        locales += [
            (locale, get_locale_dir(locale))
            for locale in os.listdir(APP_LOCALE_DIR)
        ]
    elif current_locale:
        current_locale = ensure_utf_locale(get_locale())
        if current_locale and get_current_translation():
            locale_code = current_locale.split('.')[0]
            locales.append(
                (locale_code, get_locale_dir(locale_code))
            )

    apps = {}

    for locale, locale_dir in locales:
        locale_apps = _collect_apps(
            locale_dir, skip_checks=locale != DEFAULT_LOCALE
        )

        for app_name, app_data in locale_apps.iteritems():
            if app_name not in apps:
                apps[app_name] = {}

            if locale == DEFAULT_LOCALE:
                apps[app_name].update(app_data)
            else:
                if LOCALE_KEY not in apps[app_name]:
                    apps[app_name][LOCALE_KEY] = {}

                apps[app_name][LOCALE_KEY][locale] = app_data

    if locale_code:
        apps = flatten_locale(apps, locale_code)
        filtered_apps = [
            app for f, app in apps.iteritems()
            if os.path.basename(app['origin']) not in blacklist
        ]

        return sorted(filtered_apps, key=lambda a: a["title"])

    return apps



def load_from_app_file(app_path, parse_cmd=True):
    """ Read a *.app file and parse its contents into a dictionary.

        :param app_path: The location of the file.
        :type app_path: str
        :param parse_cmd: Process the exec command of the app.

        :returns: The app's dict.
        :rtype: dict
    """

    with open(app_path, "r") as f:
        app = json.load(f)

    app["origin"] = app_path
    app["type"] = "app"

    if parse_cmd:
        app["launch_command"] = parse_command(app["launch_command"])

    return app


def _load_from_dentry(de_path):
    """ Read a *.desktop file and parse its contents into a dictionary.

        :param de_path: The location of the desktop entry.
        :type de_path: str

        :returns: The app's dict.
        :rtype: dict
    """

    de = _parse_dentry(de_path)

    if ("NoDisplay" in de and de["NoDisplay"] == "true") or \
       "Icon" not in de or "Exec" not in de or "Name" not in de:
        return

    app = {
        "type": "dentry",
        "origin": de_path,

        "title": de["Name"],
        "tagline": "",
        "launch_command": parse_command(de["Exec"]),

        "icon": de["Icon"],

        "packages": [],
        "dependencies": [],

        "removable": False,
    }

    if "Comment[en_GB]" in de:
        app["tagline"] = de["Comment[en_GB]"]
    elif "Comment" in de:
        app["tagline"] = de["Comment"]

    return app


def _parse_dentry(dentry_path):
    """ Parse a desktop entry.

        :param dentry_path: The location of the desktop entry.
        :type dentry_path: str

        :returns: A dictionary with the key/value pairs.
        :rtype: dict
    """

    dentry_data = {}
    continuation = False
    cont_key = None
    with open(dentry_path, 'r') as dentry_file:
        for line in dentry_file.readlines():
            line = line.strip()
            if len(line) <= 0 or line == '[Desktop Entry]':
                continue

            if not continuation:
                split = line.split('=')

                key = split[0]
                value = '='.join(split[1:])
                dentry_data[key] = value
            else:
                dentry_data[cont_key] += "\n" + line

            if line[-1] == '\\':
                continuation = True
                cont_key = key
                dentry_data[key] = dentry_data[key][:-1]
            else:
                continuation = False
                cont_key = None

    return dentry_data


def parse_command(cmd_line):
    """ Process the exec command for an application.

        :param cmd_line: The application's exec command.
        :type cmd_line: str

        :returns: Processed command and a list of its arguments.
        :rtype: dict
    """

    cmd_line = re.sub(r'\%[fFuUpP]', '', cmd_line)

    split = cmd_line.split(' ')
    cmd = split[0]
    args = ' '.join(split[1:])

    token = ''
    tokens = []
    state = 'normal'
    for c in args:
        if state == 'normal':
            if c == '\'':
                state = 'single-quotes'
                if len(token) > 0:
                    tokens.append(token)
                token = ''
            elif c == '"':
                state = 'double-quotes'
                if len(token) > 0:
                    tokens.append(token)
                token = ''
            elif c == ' ':
                tokens.append(token)
                token = ''
            else:
                token += c
        elif state == 'single-quotes':
            if c == '\'':
                state = 'normal'
            else:
                token += c
        elif state == 'double-quotes':
            if c == '"':
                state = 'normal'
            else:
                token += c

    if len(token) > 0:
        tokens.append(token)

    return {'cmd': cmd, 'args': tokens}
