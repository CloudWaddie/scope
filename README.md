# Scope: Discord AI & Shodan Bot

**Scope** is a Discord bot built with `discord.py` featuring OpenAI-compatible chat and Shodan host lookups. Designed for containerized deployment (e.g., Docker, Coolify).

## Features

- **OpenAI Compatible Chat**: Use any OpenAI-style API (OpenAI, LocalAI, Ollama, etc.).
- **Shodan Lookup**: Query IP addresses directly from Discord.
- **Access Control**: Only authorized User IDs can trigger commands.
- **Docker Ready**: Easy deployment with a slim Docker image.

## Setup & Deployment

### 1. Configure Environment Variables

The bot requires several environment variables to function. You can set these in your `.env` file or directly in your hosting provider (like Coolify):

- `DISCORD_TOKEN`: Your bot's token from the [Discord Developer Portal](https://discord.com/developers/applications).
- `ALLOWED_USER_IDS`: A comma-separated list of Discord User IDs allowed to use the bot (e.g., `123456789,987654321`).
- `OPENAI_API_KEY`: Your API key for the OpenAI-compatible endpoint.
- `OPENAI_BASE_URL`: The base URL for the API (default: `https://api.openai.com/v1`).
- `AI_MODEL`: The model name to use (default: `gpt-3.5-turbo`).
- `SHODAN_API_KEY`: Your API key from [Shodan](https://developer.shodan.io/).

### 2. Deployment with Coolify

1.  **Repository**: Connect your git repository to Coolify.
2.  **Discord Portal**: Enable **Message Content Intent** in the Bot tab of your application in the [Discord Developer Portal](https://discord.com/developers/applications).
3.  **Build Pack**: Select **Docker**.
3.  **Environment Variables**: Add the variables listed above in the Coolify dashboard.
4.  **Deploy**: Click deploy.

## Usage

The bot uses **Slash Commands** (`/`). After inviting the bot, type `/` to see available commands:

- `/chat <message>`: Send a prompt to the configured AI model.
- `/find <natural_language_query>`: Uses AI to translate your search request into a Shodan query, executes it, and returns results in a formatted embed.

## Shodan AI Query Generation

When you use `/find`, the bot:
1.  Takes your request (e.g., "Find open FTP servers in London").
2.  Uses the configured AI model to generate a valid Shodan search string (e.g., `port:21 city:"London"`).
3.  Executes that search against the Shodan API.
4.  Displays the top 5 matches in a Discord Embed.

## Security

Only users whose IDs are listed in `ALLOWED_USER_IDS` can use the bot's commands. Unauthorized users will receive a rejection message.
