from discord.ui import Button, View


class LinkButton(View):
    def __init__(self, label, url):
        super().__init__()
        button = Button(label=label, url=url)
        self.add_item(button)
