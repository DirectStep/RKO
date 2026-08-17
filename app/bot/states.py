from aiogram.fsm.state import State, StatesGroup


class LeadApplication(StatesGroup):
    consent = State()
    phone = State()
    questionnaire = State()
    submitting = State()


class PartnerCreation(StatesGroup):
    name = State()
    commission = State()


class ChannelCreation(StatesGroup):
    partner = State()
    name = State()
