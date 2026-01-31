import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

discord_token = os.getenv("DISCORD_TOKEN")

if not discord_token:
    raise RuntimeError("DISCORD_TOKEN non définie dans le .env")

print("Lancement du bot...")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    print("Bot allumé !")
    try:
        synced = await bot.tree.sync()
        print(f"Commandes slash synchronisées : {len(synced)}")
    except Exception as e:
        print(e)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.content.lower() == "bonjour":
        # channel = message.channel
        # await channel.send("Comment tu vas ?")
        author = message.author
        await author.send("Comment tu vas ?")


@bot.tree.command(name="warnguy", description="Alerter une personne")
async def warnguy(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message("Alerte envoyé !")
    await member.send("Tu as reçu une alerte")


@bot.tree.command(name="banguy", description="Bannir une personne")
async def banguy(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message("Ban envoyé !")
    await member.send("Tu as été banni")


bot.run(discord_token)
