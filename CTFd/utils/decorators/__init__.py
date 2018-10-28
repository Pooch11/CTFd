from flask import request, redirect, url_for, session, abort, jsonify
from CTFd.utils import config, get_config, get_app_config
from CTFd.caching import cache
from CTFd.utils.dates import ctf_ended, ctf_paused, ctf_started, ctftime
from CTFd.utils import user as current_user
from CTFd.utils.user import get_current_user, get_current_team, is_admin, authed
from CTFd.utils.modes import TEAMS_MODE, USERS_MODE
import functools


def during_ctf_time_only(f):
    """
    Decorator to restrict an endpoint to only be seen during a CTF
    :param f:
    :return:
    """

    @functools.wraps(f)
    def during_ctf_time_only_wrapper(*args, **kwargs):
        if ctftime() or current_user.is_admin():
            return f(*args, **kwargs)
        else:
            if ctf_ended():
                if config.view_after_ctf():
                    return f(*args, **kwargs)
                else:
                    error = '{} has ended'.format(config.ctf_name())
                    abort(403, description=error)

            if ctf_started() is False:
                error = '{} has not started yet'.format(config.ctf_name())
                abort(403, description=error)

    return during_ctf_time_only_wrapper


def require_authentication_if_config(config_key):
    def _require_authentication_if_config(f):
        @functools.wraps(f)
        def __require_authentication_if_config(*args, **kwargs):
            value = get_config(config_key)
            if value and current_user.authed():
                return redirect(url_for('auth.login', next=request.path))
            else:
                return f(*args, **kwargs)
        return __require_authentication_if_config
    return _require_authentication_if_config


def require_verified_emails(f):
    """
    Decorator to restrict an endpoint to users with confirmed active email addresses
    :param f:
    :return:
    """

    @functools.wraps(f)
    def _require_verified_emails(*args, **kwargs):
        if get_config('verify_emails'):
            if current_user.authed():
                if current_user.is_admin() is False and current_user.is_verified() is False:  # User is not confirmed
                    return redirect(url_for('auth.confirm'))
        return f(*args, **kwargs)

    return _require_verified_emails


def viewable_without_authentication(status_code=None, message=None):
    """
    Decorator that allows users to view the specified endpoint if viewing challenges without authentication is enabled
    :param status_code:
    :param message:
    :return:
    """

    def viewable_without_authentication_decorator(f):
        @functools.wraps(f)
        def _viewable_without_authentication(*args, **kwargs):
            if config.user_can_view_challenges():
                return f(*args, **kwargs)
            else:
                if status_code:
                    if status_code == 403:
                        error = message or "An authorization error has occured"
                    abort(status_code, description=error)
                return redirect(url_for('auth.login', next=request.path))

        return _viewable_without_authentication

    return viewable_without_authentication_decorator


def authed_only(f):
    """
    Decorator that requires the user to be authenticated
    :param f:
    :return:
    """

    @functools.wraps(f)
    def authed_only_wrapper(*args, **kwargs):
        if session.get('id'):
            return f(*args, **kwargs)
        else:
            return redirect(url_for('auth.login', next=request.path))

    return authed_only_wrapper


def admins_only(f):
    """
    Decorator that requires the user to be authenticated and an admin
    :param f:
    :return:
    """

    @functools.wraps(f)
    def admins_only_wrapper(*args, **kwargs):
        if is_admin():
            return f(*args, **kwargs)
        else:
            return redirect(url_for('auth.login', next=request.path))

    return admins_only_wrapper


def require_team(f):
    @functools.wraps(f)
    def require_team_wrapper(*args, **kwargs):
        if get_config('user_mode') == TEAMS_MODE:
            team = get_current_team()
            if team is None:
                return redirect(url_for('teams.private', next=request.path))
        return f(*args, **kwargs)

    return require_team_wrapper


def ratelimit(method="POST", limit=50, interval=300, key_prefix="rl"):
    def ratelimit_decorator(f):
        @functools.wraps(f)
        def ratelimit_function(*args, **kwargs):
            ip_address = current_user.get_ip()
            key = "{}:{}:{}".format(key_prefix, ip_address, request.endpoint)
            current = cache.get(key)

            if request.method == method:
                if current and int(current) > limit - 1:  # -1 in order to align expected limit with the real value
                    resp = jsonify({
                        'code': 429,
                        "message": "Too many requests. Limit is %s requests in %s seconds" % (limit, interval)
                    })
                    resp.status_code = 429
                    return resp
                else:
                    if current is None:
                        cache.set(key, 1, timeout=interval)
                    else:
                        cache.set(key, int(current) + 1, timeout=interval)
            return f(*args, **kwargs)

        return ratelimit_function

    return ratelimit_decorator