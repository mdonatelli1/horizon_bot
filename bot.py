import discord
from discord.ext import commands

from config import Config
from database.database import Database


class HorizonBot:
    def __init__(self):
        print("🚀 Initialisation du bot HRZN...")

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        self.bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

        # Attacher la base de données au bot
        self.bot.db = Database()
        self.db = self.bot.db

        self.setup_events()

    def setup_events(self):
        @self.bot.event
        async def on_ready():
            print(f"✅ Bot connecté en tant que {self.bot.user}")
            print(f"📊 Connecté à {len(self.bot.guilds)} serveur(s)")

            # Charger les cogs AVANT de synchroniser
            await self.load_cogs()

            try:
                synced = await self.bot.tree.sync()
                print(f"⚡ {len(synced)} commandes slash synchronisées")
            except Exception as e:
                print(f"❌ Erreur de synchronisation: {e}")

    async def load_cogs(self):
        """Charge uniquement le module Activity"""
        try:
            await self.bot.load_extension("cogs.activity")
            print("📦 Module chargé: cogs.activity")
        except Exception as e:
            print(f"❌ Erreur chargement cogs.activity: {e}")

    async def start(self):
        try:
            await self.bot.start(Config.DISCORD_TOKEN)
        except KeyboardInterrupt:
            print("\n⏸️  Arrêt du bot...")
            await self.bot.close()
