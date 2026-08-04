from aiogram.fsm.state import State, StatesGroup
class BuyTicket(StatesGroup):
    shopping=State(); waiting_for_quantity=State(); entering_names=State(); asking_promo_code=State(); choosing_payment_method=State(); waiting_for_receipt=State()
