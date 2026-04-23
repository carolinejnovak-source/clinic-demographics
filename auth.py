"""
Shared auth module — username/password session login.
Import and use the `login_required` decorator on any route.
"""
from functools import wraps
from flask import session, redirect, url_for, request

APP_USERNAME = "CarolineJNovak"
APP_PASSWORD = "crap"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def check_credentials(username, password):
    return username == APP_USERNAME and password == APP_PASSWORD
