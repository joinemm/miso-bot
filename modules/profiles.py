import traceback

import discord
import orjson

from modules import util


class ProfileEditor(discord.ui.View):
    def __init__(self, ctx, render_context):
        super().__init__()
        self.ctx = ctx
        self.disabled = False
        self.render_context = render_context

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.ctx.author:
            return True
        else:
            return False

    async def user_limits(self, user):
        if user.id == self.ctx.bot.owner_id:
            return 4, True

        tier = await self.ctx.bot.db.fetch_value(
            """
            SELECT donation_tier FROM donator
            WHERE user_id = %s
            AND currently_active
            """,
            user.id,
        )

        donator = bool(tier)
        tier = tier or 0

        return tier, donator

    async def run(self):
        self.border_max, self.background_privileges = await self.user_limits(self.ctx.author)

        data = await self.ctx.bot.db.fetch_row(
            """
            SELECT description, background_url, border, theme
            FROM user_profile WHERE user_id = %s
            """,
            self.ctx.author.id,
        )
        if data:
            self.current_bio, self.current_bg_image, self.current_border, self.current_theme = data
        else:
            self.current_bio = None
            self.current_bg_image = None
            self.current_border = 0
            self.current_theme = "dark"

        if self.current_border is None:
            self.current_border = 0

        if self.current_theme is None:
            self.current_theme = "dark"

        def locked(value):
            return "🔒" if self.border_max < value else "🔘"

        def is_current(value):
            return self.current_border == value

        self.border_select.options = [
            discord.SelectOption(
                value=0,
                label="Default border",
                emoji=locked(0),
                description="The default black border",
                default=is_current(0),
            ),
            discord.SelectOption(
                value=1,
                label="Silver border",
                emoji=locked(1),
                description="Unlocked by donating $3",
                default=is_current(1),
            ),
            discord.SelectOption(
                value=2,
                label="Golden border",
                emoji=locked(2),
                description="Unlocked by donating $6",
                default=is_current(2),
            ),
            discord.SelectOption(
                value=3,
                label="Diamond border",
                emoji=locked(3),
                description="Unlocked by donating $10",
                default=is_current(3),
            ),
            discord.SelectOption(
                value=4,
                label="Galaxy border",
                emoji=locked(4),
                description="Unlocked by donating $20",
                default=is_current(4),
            ),
        ]

        def is_current_theme(value):
            return self.current_theme == value

        self.theme_select.options = [
            discord.SelectOption(
                value="dark", label="Dark theme", emoji="⚫", default=is_current_theme("dark")
            ),
            discord.SelectOption(
                value="light", label="Light theme", emoji="⚪", default=is_current_theme("light")
            ),
        ]

        current_embed = self.create_current_embed()

        self.edit_bacground.disabled = not self.background_privileges

        await self.render_profile()
        self.message = await self.ctx.send(
            file=self.profile_image,
            embed=current_embed,
            view=self,
        )

    async def save_profile(self):
        pass

    def create_current_embed(self):
        current_embed = discord.Embed(color=int("2f3136", 16))
        current_embed.add_field(
            name="Current theme", value=self.current_theme.capitalize() or "none", inline=False
        )
        current_embed.add_field(name="Current bio", value=self.current_bio or "none", inline=False)
        current_embed.add_field(
            name="Current background image", value=self.current_bg_image or "none", inline=False
        )
        return current_embed

    async def render_profile(self):
        self.render_context["BACKGROUND_STYLE"] = (
            f'background-image: url("{self.current_bg_image}")'
            if self.current_bg_image
            else f"background-color: {self.ctx.author.color}"
        )
        self.render_context["BACKGROUND_CLASS"] = "bg-image" if self.current_bg_image else "bg"
        self.render_context["BIO"] = self.current_bio
        payload = {
            "templateName": "profile",
            "context": orjson.dumps(self.render_context).decode(),
            "width": 0,
            "height": 0,
            "imageFormat": "png",
        }
        buffer = await util.render_html(self.ctx.bot, payload, "template")
        self.profile_image = discord.File(fp=buffer, filename="profile-preview.png")

    @discord.ui.select(placeholder="Border", min_values=1, max_values=1)
    async def border_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = int(select.values[0])
        if value > self.border_max:
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                ":no_entry: You haven't unlocked that border", ephemeral=True
            )
        else:
            for option in select.options:
                option.default = False
            select.options[value].default = True
            self.current_border = value
            borders = ["", "silver", "golden", "diamond", "purple"]
            self.render_context["BORDER_CLASS"] = borders[value]
            await interaction.response.edit_message(view=self)

    @discord.ui.select(placeholder="Theme", min_values=1, max_values=1)
    async def theme_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = select.values[0]
        for option in select.options:
            if option.value == value:
                option.default = True
            else:
                option.default = False
        self.render_context["THEME"] = value
        self.current_theme = value
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="📝", label="Bio")
    async def edit_bio(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = BioEdit(self.current_bio)
        await interaction.response.send_modal(modal)
        if await modal.wait():
            return
        self.current_bio = modal.field.value
        await self.message.edit(embed=self.create_current_embed())

    @discord.ui.button(emoji="🖼️", label="Background image")
    async def edit_bacground(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = BackgroundEdit(self.current_bg_image)
        await interaction.response.send_modal(modal)
        if await modal.wait():
            return
        self.current_bg_image = modal.field.value
        await self.message.edit(embed=self.create_current_embed())

    @discord.ui.button(emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.render_profile()
        await interaction.response.edit_message(attachments=[self.profile_image], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await self.message.edit(view=self)

    @discord.ui.button(emoji="💾")
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_profile()
        await interaction.response.edit_message(content="Saved your profile edits!", view=None)


class BioEdit(discord.ui.Modal, title="Editing your bio"):
    def __init__(self, current_value):
        super().__init__()
        self.field = discord.ui.TextInput(
            label="Bio",
            style=discord.TextStyle.long,
            default=current_value,
            placeholder="none",
            required=False,
            max_length=255,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)

        # Make sure we know what the error actually is
        traceback.print_tb(error.__traceback__)


class BackgroundEdit(discord.ui.Modal, title="Editing your background image"):
    def __init__(self, current_value):
        super().__init__()
        self.field = discord.ui.TextInput(
            label="Image URL (direct link)",
            placeholder="none",
            default=current_value,
            required=False,
            max_length=255,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)

        # Make sure we know what the error actually is
        traceback.print_tb(error.__traceback__)
