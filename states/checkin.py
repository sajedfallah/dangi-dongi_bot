from aiogram.fsm.state import State, StatesGroup
class CheckinState(StatesGroup): waiting_for_tracking_code=State()
