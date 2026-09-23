"""Supabase Auth identity verification; authorization remains in the DB."""
import hashlib
import hmac
import json
import urllib.error
import urllib.request
import uuid


class AuthenticationError(Exception):
    pass


class AuthenticationUnavailable(Exception):
    pass


def token_hash(token, pepper):
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def verify_admin_identity(token, settings):
    if not token or len(token) > 8192:
        raise AuthenticationError()
    if not settings.publishable_key:
        raise AuthenticationUnavailable()
    request = urllib.request.Request(settings.supabase_url + '/auth/v1/user',
        headers={'apikey': settings.publishable_key, 'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read(65537))
        user_id = str(uuid.UUID(data['id']))
        if data.get('is_anonymous') or not data.get('email_confirmed_at'):
            raise AuthenticationError()
        return user_id
    except urllib.error.HTTPError as error:
        if error.code in (400, 401, 403):
            raise AuthenticationError() from None
        raise AuthenticationUnavailable() from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise AuthenticationUnavailable() from None
    except (KeyError, ValueError, TypeError):
        raise AuthenticationError() from None
