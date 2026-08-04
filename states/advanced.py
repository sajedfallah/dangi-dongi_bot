from aiogram.fsm.state import State, StatesGroup
class AdvancedStates(StatesGroup):
    waiting_for_support_text=State(); waiting_for_admin_reply=State(); reply_ticket_id=State(); waiting_for_refund_card=State(); waiting_for_broadcast_msg=State(); waiting_for_edit_tracking=State()
