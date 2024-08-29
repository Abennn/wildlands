import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Needed to manage member roles

bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("DISCORD_TOKEN")

# The IDs of the "unverified", "member", and "developer" roles
UNVERIFIED_ROLE_ID = 1277431882379694131  # Replace with your unverified role ID
MEMBER_ROLE_ID = 1277431881511604287  # Replace with your member role ID
DEVELOPER_ROLE_ID = 1277431849265664061  # Replace with your developer role ID
CHANNEL_ID = 1277433677181354025  # Replace with your verification channel ID
WELCOME_CHANNEL_ID = 1277433827106754583  # Replace with your welcome channel ID
MAINTENANCE_CHANNEL_ID = 1277433308904558696  # Replace with your maintenance channel ID

MESSAGE_ID_FILE = "message_id.json"
MAINTENANCE_DATA_FILE = "maintenance_data.json"

# Ensure the maintenance data file exists for persistence
if not os.path.exists(MAINTENANCE_DATA_FILE):
    with open(MAINTENANCE_DATA_FILE, "w") as f:
        json.dump({}, f)

class VerifyButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout, making the button persistent

    @ui.button(label="Verify", style=discord.ButtonStyle.primary, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        unverified_role = interaction.guild.get_role(UNVERIFIED_ROLE_ID)
        member_role = interaction.guild.get_role(MEMBER_ROLE_ID)
        
        if unverified_role in interaction.user.roles:
            await interaction.user.remove_roles(unverified_role)
            await interaction.user.add_roles(member_role)
            await interaction.response.send_message("You have been verified and assigned the member role!", ephemeral=True)
        else:
            await interaction.response.send_message("You are already verified!", ephemeral=True)

async def send_or_retrieve_verification_message(channel):
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            data = json.load(f)
            message_id = data.get("message_id")
            if message_id:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(view=VerifyButton())  # Reattach the button view
                    return message
                except discord.NotFound:
                    pass

    # If the message ID doesn't exist or the message was not found, send a new message
    embed = discord.Embed(title="Verify Your Account", description="Click the button below to verify your account.", color=0x6a0dad)  # Purple color
    view = VerifyButton()
    message = await channel.send(embed=embed, view=view)

    # Save the message ID for persistence
    with open(MESSAGE_ID_FILE, "w") as f:
        json.dump({"message_id": message.id}, f)
    
    return message


# Load cogs from the cogs directory
async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="🖥️ Wildlands"))
    channel = bot.get_channel(CHANNEL_ID)
    await load_cogs()
    await send_or_retrieve_verification_message(channel)
    # Sync the application commands (slash commands)
    await bot.tree.sync()

@bot.command()
@commands.has_permissions(administrator=True)
async def grant_all_members(ctx):
    member_role = ctx.guild.get_role(MEMBER_ROLE_ID)
    if member_role is None:
        await ctx.send("The member role does not exist.")
        return

    members_without_role = [member for member in ctx.guild.members if member_role not in member.roles]
    
    if not members_without_role:
        await ctx.send("All members already have the member role.")
        return
    
    for member in members_without_role:
        await member.add_roles(member_role)
    
    await ctx.send(f"Granted the member role to {len(members_without_role)} members.")

@bot.command()
async def send_verification(ctx):
    message = await send_or_retrieve_verification_message(ctx.channel)
    await ctx.send(f"Verification message is set up with ID: {message.id}")

# Assign the "unverified" role to new members and send a welcome message
@bot.event
async def on_member_join(member):
    unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role:
        await member.add_roles(unverified_role)
        print(f'Assigned unverified role to {member.name}')
    
    welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    verification_channel = member.guild.get_channel(CHANNEL_ID)
    
    if welcome_channel and verification_channel:
        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=f"Hello {member.mention}, welcome to the server! Please verify your account in {verification_channel.mention}.",
            color=0x6a0dad  # Purple color
        )
        await welcome_channel.send(embed=embed)
        
# To make sure the button remains persistent even after a restart
@bot.event
async def on_resume():
    channel = bot.get_channel(CHANNEL_ID)
    await send_or_retrieve_verification_message(channel)

# Maintenance commands group
async def is_developer(interaction: discord.Interaction):
    role = interaction.guild.get_role(DEVELOPER_ROLE_ID)
    return role in interaction.user.roles

maintenance_group = app_commands.Group(name="maintenance", description="Maintenance commands")

@maintenance_group.command(name="start", description="Start maintenance mode for the Minecraft server.")
@app_commands.describe(
    minecraft_server_ip="The Minecraft server IP",
    reason="Reason for maintenance",
    duration="Optional: duration (in minutes)",
    outage="Set to True if this is an outage instead of planned maintenance"
)
@app_commands.check(is_developer)
async def maintenance_start(interaction: discord.Interaction, minecraft_server_ip: str, reason: str, duration: int = None, outage: bool = False):
    channel = interaction.guild.get_channel(MAINTENANCE_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("Maintenance channel not found!", ephemeral=True)
        return
    
    # Calculate the end time if duration is provided
    end_time = None
    if duration:
        end_time = datetime.utcnow() + timedelta(minutes=duration)
        timestamp = f"<t:{int(end_time.timestamp())}:R>"
    else:
        timestamp = "N/A"

    # Set the title and color based on whether it's an outage or maintenance
    if outage:
        title = "⚠️ Outage Alert"
        description = f"The Minecraft server `{minecraft_server_ip}` is currently experiencing an outage."
        color = 0xFF4500  # Red-Orange color for outage
    else:
        title = "🚧 Maintenance Mode Activated"
        description = f"The Minecraft server `{minecraft_server_ip}` is currently under maintenance."
        color = 0xFFA500  # Orange color for maintenance

    # Create the embed
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Estimated Duration", value=timestamp, inline=False)
    embed.set_footer(text=f"{interaction.user.display_name} ○ Developer", icon_url=interaction.user.display_avatar.url)

    # Send the embed
    message = await channel.send(embed=embed)

    # Save the maintenance message ID and channel ID for later reference
    with open(MAINTENANCE_DATA_FILE, "w") as f:
        json.dump({"message_id": message.id, "channel_id": channel.id}, f)

    await interaction.response.send_message("Maintenance or outage alert started.", ephemeral=True)


@maintenance_group.command(name="end", description="End the maintenance mode and announce server is back online.")
@app_commands.check(is_developer)
async def maintenance_end(interaction: discord.Interaction):
    # Load the saved maintenance message data
    with open(MAINTENANCE_DATA_FILE, "r") as f:
        data = json.load(f)
    
    if "message_id" not in data or "channel_id" not in data:
        await interaction.response.send_message("No ongoing maintenance found.", ephemeral=True)
        return

    try:
        channel = interaction.guild.get_channel(data["channel_id"])
        message = await channel.fetch_message(data["message_id"])

        # Create the embed for the maintenance end announcement
        embed = discord.Embed(
            title="✅ Maintenance Completed",
            description="The Minecraft server is now back online.",
            color=0xADD8E6  # Pastel blue color
        )
        embed.set_footer(text=f"{interaction.user.display_name} ○ Developer", icon_url=interaction.user.display_avatar.url)

        # Reply to the original maintenance message with the end message
        await message.reply(embed=embed)
        
        # Clear the saved data
        with open(MAINTENANCE_DATA_FILE, "w") as f:
            json.dump({}, f)

        await interaction.response.send_message("Maintenance mode ended.", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("Could not find the original maintenance message.", ephemeral=True)


# Command to post server updates
@bot.tree.command(name="update", description="Post server updates.")
@app_commands.describe(
    server_ip="The Minecraft server IP",
    updates="List of updates separated by commas"
)
@app_commands.check(is_developer)
async def update_command(interaction: discord.Interaction, server_ip: str, updates: str):
    channel = interaction.guild.get_channel(1277433083561246751)
    if not channel:
        await interaction.response.send_message("Updates channel not found!", ephemeral=True)
        return
    
    # Split the updates by commas and format each update
    update_lines = updates.split(',')
    formatted_updates = "\n\n".join([f"• {update.strip()}" for update in update_lines])

    # Create the embed
    embed = discord.Embed(
        title="🔄 Server Updates",
        description=f"Here are the latest updates for the Minecraft server `{server_ip}`:",
        color=0x6a0dad  # Purple color
    )
    embed.add_field(name="What's New:", value=formatted_updates, inline=False)
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1278119601145778256/1278119639536111656/logo_3.png")  # Replace with a relevant image URL
    embed.set_footer(text=f"{interaction.user.display_name} ○ Developer", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()  # Adds the current timestamp to the embed

    # Send the embed
    await channel.send(embed=embed)
    await interaction.response.send_message("Update posted successfully.", ephemeral=True)

# Add the maintenance command group to the bot
bot.tree.add_command(maintenance_group)

bot.run(TOKEN)  # Replace with your bot token
