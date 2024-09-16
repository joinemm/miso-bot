# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
from typing import Generic, TypeVar

import discord

T = TypeVar("T")
STYLE = discord.ButtonStyle.gray


class BaseButtonPaginator(Generic[T], discord.ui.View):
    """
    The Base Button Paginator class. Will handle all page switching without
    you having to do anything.

    Attributes
    ----------
    entries: list[Any]
        A list of entries to get spread across pages.
    per_page: :class:`int`
        The number of entries that get passed onto one page.
    pages: list[list[Any]]
        A list of pages which contain all entries for that page.
    clamp_pages: :class:`bool`
        Whether or not to clamp the pages to the min and max.
    """

    def __init__(
        self,
        *,
        entries: list[T],
        per_page: int,
        clamp_pages: bool = True,
    ) -> None:
        super().__init__(timeout=180)
        self.entries: list[T] = entries
        self.per_page: int = per_page
        self.clamp_pages: bool = clamp_pages
        self.message: discord.Message
        self._current_page = 0
        self.pages = [
            entries[i : i + per_page] for i in range(0, len(entries), per_page)
        ]
        self.page_number.label = f"Page {self._current_page + 1} of {self.max_page}"

    @property
    def max_page(self) -> int:
        """:class:`int`: The max page count for this paginator."""
        return len(self.pages)

    @property
    def min_page(self) -> int:
        """:class:`int`: The min page count for this paginator."""
        return 1

    @property
    def current_page(self) -> int:
        """:class:`int`: The current page the user is on."""
        return self._current_page + 1

    @property
    def total_pages(self) -> int:
        """:class:`int`: Returns the total amount of pages."""
        return len(self.pages)

    async def format_page(self, entries: list[T], /) -> dict:
        """|coro|

        Used to make the message that the user sees.

        Parameters
        ----------
        entries: List[Any]
            A list of entries for the current page.

        Returns
        -------
        :class:`dict`
            Kwargs to pass to message sender
        """
        raise NotImplementedError("Subclass did not overwrite format_page coro.")

    def _switch_page(self, count: int) -> list[T]:
        self._current_page += count

        if count < 0:
            if self.clamp_pages and self._current_page < 0:
                self._current_page = self.max_page - 1
        elif count > 0:
            if self.clamp_pages and self._current_page > self.max_page - 1:
                self._current_page = 0

        self.page_number.label = f"Page {self._current_page + 1} of {self.max_page}"
        return self.pages[self._current_page]

    @discord.ui.button(emoji="<:left:997949561911918643>", style=STYLE)
    async def on_arrow_backward(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        entries = self._switch_page(-1)
        message = await self.format_page(entries)
        return await interaction.response.edit_message(view=self, **message)

    @discord.ui.button(label="...", style=STYLE, disabled=True)
    async def page_number(
        self, _interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        pass

    @discord.ui.button(emoji="<:right:997949563665133570>", style=STYLE)
    async def on_arrow_forward(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        entries = self._switch_page(1)
        message = await self.format_page(entries)
        return await interaction.response.edit_message(view=self, **message)

    async def run(self, context: discord.abc.Messageable):
        message = await self.format_page(self.pages[0])
        if self.total_pages > 1:
            self.message = await context.send(view=self, **message)
        else:
            # no need to paginate at all
            await context.send(**message)
            self.stop()

    async def on_timeout(self):
        self.on_arrow_forward.disabled = True
        self.on_arrow_backward.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.NotFound:
            pass
        self.stop()


class RowPaginator(BaseButtonPaginator):
    def __init__(self, base_embed, entries: list[str], per_page=10, **kwargs):
        self.embed = base_embed
        super().__init__(entries=entries, per_page=per_page, **kwargs)

    async def format_page(self, entries):
        self.embed.description = "\n".join(entries)
        return {"embed": self.embed}


class Compliance(discord.ui.View):
    def __init__(self, author: discord.Member | discord.User):
        super().__init__()
        self.author = author
        self.agreed = None

    async def read_timer(self, n: int, message: discord.Message):
        await asyncio.sleep(n)
        self.confirm.disabled = False
        self.cancel.disabled = False
        await message.edit(view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.primary, label="I Understand", disabled=True
    )
    async def confirm(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if interaction.user == self.author:
            await interaction.response.defer()
            self.agreed = True
            self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary, label="Cancel", disabled=True
    )
    async def cancel(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if interaction.user == self.author:
            await interaction.response.defer()
            self.agreed = False
            self.stop()

    async def on_timeout(self):
        self.stop()


class TextPaginator(BaseButtonPaginator):
    def __init__(self, entries: list[dict], **kwargs):
        super().__init__(entries=entries, per_page=1, **kwargs)

    async def format_page(self, entries: list[dict]):
        return {"content": entries[0]}
