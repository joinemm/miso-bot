import io
from contextlib import closing

import aioboto3
import discord
from discord.ext import commands

from libraries import emoji_literals
from modules import exceptions
from modules.misobot import MisoBot


class GenderSelect(discord.ui.Select):
    def __init__(self, voices):
        self.voices = voices
        options = [discord.SelectOption(label="Male"), discord.SelectOption(label="Female")]
        super().__init__(placeholder="Choose voice gender", options=options)

    async def callback(self, interaction: discord.Interaction):
        for child in filter(lambda c: isinstance(c, VoiceSelect), self.view.children):
            self.view.remove_item(child)

        self.view.voice_select = VoiceSelect(
            filter(lambda v: v["Gender"] == self.values[0], self.voices)
        )
        self.view.add_item(self.view.voice_select)
        await interaction.response.edit_message(view=self.view)


class VoiceSelect(discord.ui.Select):
    def __init__(self, voices):
        options = [
            discord.SelectOption(
                label=voice["Id"],
                description=voice["LanguageName"],
                emoji=emoji_literals.NAME_TO_UNICODE.get(
                    f":flag_{voice['LanguageCode'].split('-')[1].lower()}:"
                ),
            )
            for voice in voices
        ]

        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(
            placeholder="Choose TTS voice",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Use the interaction object to send a response message containing
        # the user's favourite colour or choice. The self object refers to the
        # Select object, and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        # await interaction.response.edit_message()
        pass


class DropdownView(discord.ui.View):
    def __init__(self, voices):
        super().__init__()
        self.add_item(GenderSelect(voices))


class TTS(commands.Cog):
    """Text to speech"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.aws_session = aioboto3.Session(
            aws_access_key_id=self.bot.keychain.AWS_ACCESS_KEY,
            aws_secret_access_key=self.bot.keychain.AWS_ACCESS_SECRET,
        )

    @commands.command()
    async def tts(self, ctx: commands.Context):
        # Create the view containing our dropdown
        async with self.aws_session.client("polly", "us-east-1") as polly:
            voices = await polly.describe_voices(Engine="neural")

        view = DropdownView(voices["Voices"])
        await ctx.send("**Text to speech generator**", view=view)
        # Wait for the View to stop listening for input...
        await view.wait()
        if view.value is None:
            print("Timed out...")
        elif view.value:
            print("Confirmed...")
        else:
            print("Cancelled...")

    async def generate_audio_file(self, text):
        async with self.aws_session.client("polly", "us-east-1") as polly:
            response = await polly.synthesize_speech(
                Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural"
            )
            if response["AudioStream"]:
                with closing(response["AudioStream"]) as stream:
                    data = await stream.read()
                    file = discord.File(fp=io.BytesIO(data), filename="speech.mp3")
                    return file
            else:
                raise exceptions.CommandError("Could not get AudioStream from AWS")


async def setup(bot):
    await bot.add_cog(TTS(bot))
