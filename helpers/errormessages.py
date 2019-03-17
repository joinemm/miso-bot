PREFIX = ">"


def invalid_method(command, method):
    return f"**ERROR:** Invalid method `{method}`. Use `{PREFIX}{command} help` to get help"


def invalid_argument(command, method, argument):
    return f"**ERROR:** Invalid argument `{argument}` for {method}. Use `{PREFIX}{command} help` to get help"


def channel_not_found(channel):
    return f"**ERROR:** Channel `{channel}` not found"


def user_not_found(user):
    return f"**ERROR:** User `{user}` not found"


def missing_parameter(name):
    return f"**ERROR:** Missing parameter `{name}`"



