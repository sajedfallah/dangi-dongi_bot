import asyncio
import os

os.environ["DANGI_BOT_PROCESS"] = "1"

from app.bot.main import run_bot  # noqa: E402


if __name__ == "__main__":
    asyncio.run(run_bot())
