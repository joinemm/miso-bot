PREFIX = ">"


def invalid_method(command, method):
    return f"Invalid subcommand `{method}`. Use `{PREFIX}{command} help` to get help"


def invalid_argument(command, method, argument):
    return f"Invalid argument `{argument}` for {method}. Use `{PREFIX}{command} help` to get help"


def channel_not_found(channel):
    return f"Channel {channel} not found"


def user_not_found(user):
    return f"User {user} not found."


def role_not_found(role):
    return f"Role {role} not found."


def missing_parameter(name):
    return f"Required argument `{name}` is missing."



