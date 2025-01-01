from telebot.handler_backends import State, StatesGroup  # states

class UserState(StatesGroup):
    message = State()
    attachments = State()
    cancel_or_restart = State()