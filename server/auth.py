"""Cookie hashing and real Supabase Auth verification."""
import hashlib,hmac,json,urllib.error,urllib.request,uuid
class AuthenticationError(RuntimeError): pass
class AuthenticationUnavailable(RuntimeError): pass
def token_hash(token,pepper): return hmac.new(pepper.encode(),token.encode(),hashlib.sha256).hexdigest()
def deterministic_participant_token(bootstrap_token,pepper): return hmac.new(pepper.encode(),("participant:"+bootstrap_token).encode(),hashlib.sha256).hexdigest()
def verify_admin_identity(token,settings):
    if not token or len(token)>8192: raise AuthenticationError()
    req=urllib.request.Request(settings.supabase_url+"/auth/v1/user",headers={"apikey":settings.publishable_key,"Authorization":"Bearer "+token})
    try:
        with urllib.request.urlopen(req,timeout=5) as res: data=json.loads(res.read(65537))
        uid=str(uuid.UUID(data["id"]))
        if data.get("is_anonymous") or not data.get("email_confirmed_at"): raise AuthenticationError()
        return uid
    except urllib.error.HTTPError as error:
        if error.code in (400,401,403): raise AuthenticationError() from None
        raise AuthenticationUnavailable() from None
    except (urllib.error.URLError,TimeoutError,OSError,json.JSONDecodeError): raise AuthenticationUnavailable() from None
    except (KeyError,TypeError,ValueError): raise AuthenticationError() from None
