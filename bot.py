import os
import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI
from shodan import Shodan
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Config
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ALLOWED_USER_IDS = set(map(int, os.getenv("ALLOWED_USER_IDS", "").split(","))) if os.getenv("ALLOWED_USER_IDS") else set()

# AI Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")

# Shodan Config
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY")

# Initialize Clients
ai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
shodan_client = Shodan(SHODAN_API_KEY) if SHODAN_API_KEY else None

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync slash commands
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = MyBot()

# Access Control Check for Slash Commands
def is_allowed():
    def predicate(interaction: discord.Interaction) -> bool:
        return not ALLOWED_USER_IDS or interaction.user.id in ALLOWED_USER_IDS
    return app_commands.check(predicate)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.tree.command(name="find", description="Ask AI to find something on Shodan")
@is_allowed()
async def find(interaction: discord.Interaction, query: str):
    """Asks AI to generate a Shodan query, runs it, and returns results."""
    if not shodan_client:
        return await interaction.response.send_message("❌ Shodan API key is not configured.", ephemeral=True)

    await interaction.response.defer()

    try:
        # 1. Ask AI to generate the Shodan query
        prompt = (
            f"Translate the following request into a Shodan search query. "
            f"Respond ONLY with the search string, no explanation or quotes.\n"
            f"Request: {query}"
        )
        ai_response = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "system", "content": "You are a Shodan query expert."},
                      {"role": "user", "content": prompt}]
        )
        shodan_query = ai_response.choices[0].message.content.strip().strip('"').strip("'")
        
        # 2. Execute Shodan search
        results = shodan_client.search(shodan_query, limit=5)
        
        # 3. Build Embed
        embed = discord.Embed(
            title=f"Shodan Results for: {shodan_query}",
            description=f"Generated from: *{query}*",
            color=discord.Color.blue()
        )
        
        if results['total'] > 0:
            for result in results['matches']:
                ip = result.get('ip_str', 'Unknown IP')
                port = result.get('port', 'Unknown Port')
                org = result.get('org', 'Unknown Org')
                location = f"{result.get('location', {{}}).get('city', 'N/A')}, {result.get('location', {{}}).get('country_name', 'N/A')}"
                
                embed.add_field(
                    name=f"IP: {ip}:{port}",
                    value=f"**Org:** {org}\n**Loc:** {location}",
                    inline=False
                )
            embed.set_footer(text=f"Total results: {results['total']} | Showing top 5")
        else:
            embed.description = f"No results found for query: `{shodan_query}`"

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("⛔ You are not authorized to use this command.", ephemeral=True)
    else:
        print(f"Slash Command Error: {error}")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN is not set.")
    else:
        bot.run(DISCORD_TOKEN)
