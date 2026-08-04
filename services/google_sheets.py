import aiohttp, logging
from config import settings
async def send_to_sheet(action:str,data:dict)->bool:
    if not settings.sheets_webhook_url:
        logging.warning('Google Sheets webhook is disabled')
        return False
    payload={'action':action,'data':data,'secret':settings.sheets_webhook_secret}
    timeout=aiohttp.ClientTimeout(total=10)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(settings.sheets_webhook_url,json=payload) as response:
                    if 200<=response.status<300: return True
                    logging.error('Sheets webhook status=%s attempt=%s',response.status,attempt+1)
        except Exception:
            logging.exception('Sheets webhook failed attempt=%s',attempt+1)
    return False
