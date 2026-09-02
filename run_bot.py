import asyncio
import os

os.environ["DANGI_BOT_PROCESS"] = "1"

import app.bot.final_main as final_main  # noqa: E402
from app.bot.ux_runtime import install as install_ux  # noqa: E402

install_ux(final_main)


if __name__ == "__main__":
    asyncio.run(final_main.run_bot())
