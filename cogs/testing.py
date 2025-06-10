import discord
from discord.ext import commands

class testing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    testG = discord.SlashCommandGroup('test','Just testing stuff')

    @testG.command(name="test",Description="Fellow Bar")
    async def test(self, ctx):
        await ctx.respond("This works maybe?")

def setup(bot):
    bot.add_cog(testing(bot))
