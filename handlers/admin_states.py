from aiogram.fsm.state import State, StatesGroup


class AddTheme(StatesGroup):
    platform = State()
    category = State()
    name = State()
    url = State()
    description = State()
    confirm = State()


class EditTheme(StatesGroup):
    value = State()
    confirm = State()


class Broadcast(StatesGroup):
    audience = State()
    message = State()
    confirm = State()


class AddLanguage(StatesGroup):
    name = State()
    url = State()
    confirm = State()


class EditLanguage(StatesGroup):
    value = State()
    confirm = State()
