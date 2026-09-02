from __future__ import annotations

import asyncio


_INSTALLED = False


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    async def reminder_loop(bot):
        await asyncio.sleep(10)
        while True:
            try:
                async with module.api_client() as client:
                    response = await client.get("/api/v1/reminders-v2/due")
                    response.raise_for_status()
                    items = response.json()

                for item in items:
                    try:
                        await module.send_debt_reminder(bot, item, mark=False)
                        async with module.api_client() as client:
                            sent = await client.post("/api/v1/reminders-v2/sent", json={
                                "group_id": item["group_id"],
                                "debtor_user_id": item["debtor_user_id"],
                                "creditor_user_id": item["creditor_user_id"],
                                "amount": item["amount"],
                            })
                            sent.raise_for_status()
                    except Exception:
                        continue
            except Exception:
                pass

            await asyncio.sleep(3600)

    module.reminder_loop = reminder_loop
