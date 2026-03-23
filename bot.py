import os
import discord
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI
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
AI_MODEL = os.getenv("AI_MODEL", "cheap")

# Shodan Config
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY")

# Initialize Clients
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
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
    print(f"Scope Bot logged in as {bot.user} (ID: {bot.user.id})")
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
        system_prompt = (
            "You are a Shodan query expert. Your task is to translate user requests into precise Shodan search queries.\n\n"
            "Rules:\n"
            "1. Respond ONLY with the search string.\n"
            "2. DO NOT include quotes, explanations, or any other text.\n"
            "3. DO NOT use markdown code blocks.\n"
            "4. If the request is ambiguous, generate the most likely query.\n\n"
            "Examples:\n"
            "Request: Apache servers in New York\n"
            "Response: product:Apache city:\"New York\"\n\n"
            "Request: Webcams in Japan\n"
            "Response: \"webcam\" country:JP"
        )
        
        ai_response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": f"Request: {query}"}]
        )
        
        # Robustly handle different response types (Object, String, or Stream)
        shodan_query = ""
        if isinstance(ai_response, str):
            shodan_query = ai_response
        elif hasattr(ai_response, "choices"):
            shodan_query = ai_response.choices[0].message.content
        else:
            # Handle potential streaming response (Async Iterator)
            content_parts = []
            async for chunk in ai_response:
                if hasattr(chunk, "choices") and chunk.choices[0].delta.content:
                    content_parts.append(chunk.choices[0].delta.content)
            shodan_query = "".join(content_parts)

        # Final cleaning
        shodan_query = shodan_query.strip().strip('"').strip("'").strip("`")
        if "shodan" in shodan_query.lower() and ":" not in shodan_query: # Edge case for weird model responses
             shodan_query = shodan_query.replace("shodan", "").strip()
        
        # 2. Execute Shodan search
        results = shodan_client.search(shodan_query, limit=5)
        
        # 3. Build Embed
        embed = discord.Embed(
            title=f"Shodan Results",
            description=f"**Query:** `{shodan_query}`\n**Original:** *{query}*",
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
        error_msg = f"❌ Error: {str(e)}"
        if 'shodan_query' in locals() and shodan_query:
            error_msg += f"\n**Query tried:** `{shodan_query}`"
        await interaction.followup.send(error_msg)

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
