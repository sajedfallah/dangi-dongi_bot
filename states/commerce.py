from aiogram.fsm.state import State, StatesGroup
class WalletStates(StatesGroup):
    waiting_for_withdrawal_account=State(); waiting_for_withdrawal_receipt=State()
class WaitlistStates(StatesGroup): waiting_for_quantity=State()
