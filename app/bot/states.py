from aiogram.fsm.state import State, StatesGroup


class LeadApplication(StatesGroup):
    consent = State()
    phone = State()
    questionnaire = State()
    submitting = State()
