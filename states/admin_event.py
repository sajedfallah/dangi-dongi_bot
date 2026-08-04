from aiogram.fsm.state import State, StatesGroup
class EventCreate(StatesGroup):
    waiting_for_title=State(); waiting_for_description=State(); waiting_for_date=State(); waiting_for_location=State(); waiting_for_capacity=State()
class EventEdit(StatesGroup):
    waiting_for_new_capacity=State(); waiting_for_checker_id=State(); edit_event_id=State()
class TicketTypeCreate(StatesGroup):
    event_id=State(); waiting_for_name=State(); waiting_for_price=State()
class PromoCreate(StatesGroup):
    event_id=State(); waiting_for_code=State(); waiting_for_discount=State(); waiting_for_uses=State()
class VIPCreate(StatesGroup):
    event_id=State(); waiting_for_name=State(); waiting_for_role=State()
class CompTicketCreate(StatesGroup):
    event_id=State(); waiting_for_tt_id=State(); waiting_for_name=State()
class AdminSearchInvoice(StatesGroup): waiting_for_invoice_id=State()
