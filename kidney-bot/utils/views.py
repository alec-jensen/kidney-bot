import discord


class Confirm(discord.ui.View):
    def __init__(self, accept_response: str = 'Confirmed', deny_response: str = 'Cancelled',
                 ephemeral: bool = False):
        super().__init__()
        self.value = None
        self.accept_response = accept_response
        self.deny_response = deny_response
        self.ephemeral = ephemeral

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green, emoji='✅')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.accept_response, ephemeral=self.ephemeral)
        self.value = True
        
        for child in self.children:
            if child != button:
                child.disabled = True

        try:
            await interaction.message.edit(view=self)
        except discord.NotFound:
            pass

        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red, emoji='❌')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.deny_response, ephemeral=self.ephemeral)
        self.value = False

        for child in self.children:
            if child != button:
                child.disabled = True

        try:
            await interaction.message.edit(view=self)
        except discord.NotFound:
            pass

        self.stop()
