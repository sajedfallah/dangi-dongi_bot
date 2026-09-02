import asyncio
import os

os.environ["DANGI_BOT_PROCESS"] = "1"

import app.bot.final_main as final_main  # noqa: E402
from app.bot.ux_runtime import install as install_ux  # noqa: E402
from app.bot.advanced_expense_runtime import install as install_advanced_expense  # noqa: E402
from app.bot.join_notification_runtime import install as install_join_notifications  # noqa: E402
from app.bot.reminder_cadence_runtime import install as install_reminder_cadence  # noqa: E402
from app.bot.v11_runtime import install as install_v11  # noqa: E402

install_ux(final_main)
install_advanced_expense(final_main)
install_join_notifications(final_main)
install_reminder_cadence(final_main)
install_v11(final_main)


if __name__ == "__main__":
    asyncio.run(final_main.run_bot())
