import asyncio

from bot import HorizonBot

if __name__ == "__main__":
    bot = HorizonBot()
    asyncio.run(bot.start())
