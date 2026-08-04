import base64, hashlib, hmac, json, time
from config import settings

def create_ticket_token(ticket_id:int,tracking_code:str,event_id:int)->str:
    payload={'v':1,'tid':ticket_id,'code':tracking_code,'eid':event_id,'iat':int(time.time())}
    raw=json.dumps(payload,separators=(',',':'),sort_keys=True).encode(); body=base64.urlsafe_b64encode(raw).decode().rstrip('=')
    sig=hmac.new(settings.qr_signing_secret.encode(),body.encode(),hashlib.sha256).hexdigest()
    return f'TK1.{body}.{sig}'

def verify_ticket_token(token:str)->dict:
    try:
        prefix,body,sig=token.split('.',2)
        if prefix!='TK1': raise ValueError
        expected=hmac.new(settings.qr_signing_secret.encode(),body.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): raise ValueError
        raw=base64.urlsafe_b64decode(body+'='*(-len(body)%4)); return json.loads(raw)
    except Exception as exc: raise ValueError('QR نامعتبر یا دست‌کاری‌شده است.') from exc
