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

class PaginationView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current_page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self.update_view(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.update_view(interaction)

    async def update_view(self, interaction: discord.Interaction):
        # Update button states
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page == len(self.embeds) - 1)
        
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

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
        
        # Truncate query if it's too long
        if len(shodan_query) > 1000:
            shodan_query = shodan_query[:997] + "..."
        
        # 2. Execute Shodan search
        results = shodan_client.search(shodan_query, limit=15) # Increased limit for pagination
        
        if results['total'] > 0:
            embeds = []
            current_embed = None
            
            # Truncate original query for display
            display_query = query[:500] + "..." if len(query) > 500 else query
            
            for i, result in enumerate(results['matches']):
                # Start a new embed every 5 results or if it's the first
                if i % 5 == 0:
                    current_embed = discord.Embed(
                        title=f"Shodan Results",
                        description=f"**Query:** `{shodan_query}`\n**Original:** *{display_query}*",
                        color=discord.Color.blue()
                    )
                    embeds.append(current_embed)
                
                ip = result.get('ip_str', 'Unknown IP')
                port = result.get('port', 'Unknown Port')
                org = result.get('org', 'Unknown Org') or "Unknown Organization"
                location_data = result.get('location', {})
                city = location_data.get('city', 'N/A')
                country = location_data.get('country_name', 'N/A')
                
                # Truncate long org names to prevent overflow
                if len(org) > 100:
                    org = org[:97] + "..."
                
                current_embed.add_field(
                    name=f"🌐 {ip}:{port}",
                    value=f"**Org:** `{org}`\n**Loc:** {city}, {country}\n**Link:** [View on Shodan](https://www.shodan.io/host/{ip})",
                    inline=False
                )
            
            # Set footers with page info
            total_pages = len(embeds)
            for i, embed in enumerate(embeds):
                embed.set_footer(text=f"Page {i+1}/{total_pages} | Total results: {results['total']}")

            if total_pages > 1:
                view = PaginationView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
            else:
                await interaction.followup.send(embed=embeds[0])
        else:
            display_query = query[:500] + "..." if len(query) > 500 else query
            embed = discord.Embed(
                title="Shodan Results",
                description=f"No results found for query: `{shodan_query}`\n**Original:** *{display_query}*",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    except Exception as e:
        error_str = str(e)
        if len(error_str) > 1000:
            error_str = error_str[:997] + "..."
            
        error_msg = f"❌ Error: {error_str}"
        if 'shodan_query' in locals() and shodan_query:
            q_clean = shodan_query[:500] + "..." if len(shodan_query) > 500 else shodan_query
            error_msg += f"\n**Query tried:** `{q_clean}`"
        
        # Final safety check for Discord's 2000 char limit
        if len(error_msg) > 2000:
            error_msg = error_msg[:1997] + "..."
            
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
