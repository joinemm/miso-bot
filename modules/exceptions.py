from discord.ext import commands


class Info(commands.CommandError):
    def __init__(self, message, **kwargs):
        super().__init__(message)
        self.kwargs = kwargs


class Warning(commands.CommandError):
    def __init__(self, message, **kwargs):
        super().__init__(message)
        self.kwargs = kwargs


class Error(commands.CommandError):
    def __init__(self, message, **kwargs):
        super().__init__(message)
        self.kwargs = kwargs


class LastFMError(commands.CommandError):
    def __init__(self, error_code, message):
        super().__init__()
        self.error_code = error_code
        self.message = message

    def __str__(self):
        return f"LastFM error {self.error_code}"

    def display(self):
        return f"LastFM error {self.error_code} : {self.message}"


class RendererError(commands.CommandError):
    pass


class ServerTooBig(commands.CheckFailure):
    def __init__(self, member_count):
        super().__init__()
        self.member_count = member_count


class Blacklist(commands.CommandError):
    pass


class BlacklistedUser(Blacklist):
    def __init__(self):
        super().__init__()
        self.message = "You have been blacklisted from using Miso Bot"


class BlacklistedMember(Blacklist):
    def __init__(self):
        super().__init__()
        self.message = "You have been blacklisted from using commands by the server moderators"


class BlacklistedGuild(Blacklist):
    def __init__(self):
        super().__init__()
        self.message = "This server is blacklisted from using Miso Bot"


class BlacklistedCommand(Blacklist):
    def __init__(self):
        super().__init__()
        self.message = "This command has been disabled by the server moderators"


class BlacklistedChannel(Blacklist):
    def __init__(self):
        super().__init__()
        self.message = "Command usage in this channel has been disabled by the server moderators"
