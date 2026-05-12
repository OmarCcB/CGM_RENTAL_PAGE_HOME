"""
Azure AD authentication helpers for the CGM Rental admin panel.

Required environment variables:
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
  AZURE_TENANT_ID
  AZURE_REDIRECT_URI  (default: http://localhost:5000/admin/auth/callback)
"""
import os
import functools
from flask import session, redirect, url_for, flash

SCOPES = ["User.Read"]


def _azure_vars():
    return {
        "client_id":     os.getenv("AZURE_CLIENT_ID", ""),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET", ""),
        "tenant_id":     os.getenv("AZURE_TENANT_ID", ""),
        "redirect_uri":  os.getenv("AZURE_REDIRECT_URI", "http://localhost:5000/admin/auth/callback"),
    }


def _get_msal_app():
    v = _azure_vars()
    try:
        import msal
        return msal.ConfidentialClientApplication(
            v["client_id"],
            authority=f"https://login.microsoftonline.com/{v['tenant_id']}",
            client_credential=v["client_secret"],
        )
    except ImportError:
        return None


def azure_configured():
    """Returns True if all Azure AD env vars are set."""
    v = _azure_vars()
    return bool(v["client_id"] and v["client_secret"] and v["tenant_id"])


def get_auth_url():
    """Returns the Microsoft login URL, or None if not configured."""
    if not azure_configured():
        return None
    app = _get_msal_app()
    if app is None:
        return None
    return app.get_authorization_request_url(
        SCOPES,
        redirect_uri=_azure_vars()["redirect_uri"],
    )


def get_token_from_code(code):
    """Exchanges an authorization code for an access token dict, or None on failure."""
    if not azure_configured():
        return None
    app = _get_msal_app()
    if app is None:
        return None
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=_azure_vars()["redirect_uri"],
    )
    if "error" in result:
        return None
    return result


def get_user_info(token):
    """Returns a dict with name and email from the token, or None on failure."""
    if not token:
        return None
    try:
        import requests
        headers = {"Authorization": f"Bearer {token.get('access_token', '')}"}
        resp = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "name": data.get("displayName", "Administrador"),
                "email": data.get("mail") or data.get("userPrincipalName", ""),
            }
    except Exception:
        pass
    # Fallback: read from id_token_claims if available
    claims = token.get("id_token_claims", {})
    return {
        "name": claims.get("name", "Administrador"),
        "email": claims.get("preferred_username", ""),
    }


def admin_required(f):
    """Decorator that requires an active admin session."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_user"):
            flash("Debes iniciar sesión para acceder al panel.", "warning")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated_function
