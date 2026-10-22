from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    language = State()
    consent = State()
    name = State()
    age = State()
    parent_phone = State()
    parent_consent = State()
    chat = State()  # свободный диалог с ИИ-консультантом
    test = State()
    writing = State()
    level = State()  # ручной выбор уровня, если тест недоступен
    days = State()
    time = State()
    choose_group = State()
    contact = State()
