from aiogram.fsm.state import State, StatesGroup
class ExpenseState(StatesGroup):
    waiting_for_event=State(); waiting_for_category=State(); waiting_for_amount=State(); waiting_for_payee=State(); waiting_for_note=State()
