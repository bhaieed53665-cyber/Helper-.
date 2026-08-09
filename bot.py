# -*- coding: utf-8 -*-
"""
بوت تذاكر (Tickets) بالديسكورد - Melaad Support
مبني بـ discord.py

قبل التشغيل لازم تعبي القيم بقسم الإعدادات (CONFIG) تحت.
"""

import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

# =========================================================
# ============ إعدادات (CONFIG) - من Environment Variables ============
# =========================================================

def _clean_id(raw: str):
    """ينضف قيمة آيدي جاية من Environment Variable"""
    if not raw:
        return None
    cleaned = raw.strip().strip("<>").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        raise RuntimeError(
            f"القيمة '{raw}' مش رقم آيدي صحيح. لازم تكون أرقام بس بدون أقواس < > أو مسافات."
        )


BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = _clean_id(os.getenv("GUILD_ID"))
TICKET_CATEGORY_ID = _clean_id(os.getenv("TICKET_CATEGORY_ID"))
STAFF_ROLE_ID = _clean_id(os.getenv("STAFF_ROLE_ID")) or 1535668575585566871
SPECIAL_ADMIN_ID = _clean_id(os.getenv("SPECIAL_ADMIN_ID")) or 920981254554406952
PANEL_IMAGE_URL = os.getenv("PANEL_IMAGE_URL", "")

TICKET_ICON_EMOJI = os.getenv("TICKET_ICON_EMOJI", "🎫")
CLAIM_EMOJI = os.getenv("CLAIM_EMOJI", "🔒")
DELETE_EMOJI = os.getenv("DELETE_EMOJI", "🗑️")

if not BOT_TOKEN:
    raise RuntimeError("لازم تعبي متغير BOT_TOKEN بلوحة تحكم Railway (Variables).")

# =========================================================
# ===================== نهاية الإعدادات ====================
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def is_staff(member: discord.Member) -> bool:
    if member.id == SPECIAL_ADMIN_ID:
        return True
    if member.guild_permissions.administrator:
        return True
    role = discord.utils.get(member.roles, id=STAFF_ROLE_ID)
    return role is not None


def parse_topic(topic: str):
    data = {}
    if not topic:
        return data
    for part in topic.split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            data[k.strip()] = v.strip()
    return data


TYPE_LABELS = {
    "inquiry": "استفسار",
    "complaint": "شكوى",
    "help": "مساعدة",
    "special": "رتب خاصة",
}


# =========================================================
# ==================== أزرار / فيوهات الحذف والاستلام =========
# =========================================================

class TicketActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=CLAIM_EMOJI, custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        data = parse_topic(channel.topic)
        ticket_type = data.get("type")

        if ticket_type == "special":
            if interaction.user.id != SPECIAL_ADMIN_ID:
                await interaction.response.send_message("هذه التذكرة خاصة، لا يمكنك استلامها.", ephemeral=True)
                return
        else:
            if not is_staff(interaction.user):
                await interaction.response.send_message("لا تملك صلاحية استلام التذاكر.", ephemeral=True)
                return

        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"تم استلام هذه التذكرة من قبل {interaction.user.mention}.")

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=DELETE_EMOJI, custom_id="ticket_delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        data = parse_topic(channel.topic)
        ticket_type = data.get("type")

        if ticket_type == "special":
            if interaction.user.id != SPECIAL_ADMIN_ID:
                await interaction.response.send_message("هذه التذكرة خاصة، لا يمكنك حذفها.", ephemeral=True)
                return
        else:
            if not is_staff(interaction.user):
                await interaction.response.send_message("لا تملك صلاحية حذف التذاكر.", ephemeral=True)
                return

        await interaction.response.send_message("جارٍ حذف التذكرة خلال خمس ثوانٍ...", ephemeral=True)
        await asyncio.sleep(5)
        await channel.delete()


# =========================================================
# ================= قائمة اختيار نوع التذكرة =================
# =========================================================

class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="استفسار", value="inquiry"),
            discord.SelectOption(label="شكوى", value="complaint"),
            discord.SelectOption(label="مساعدة", value="help"),
            discord.SelectOption(label="رتب خاصة", value="special"),
        ]
        super().__init__(placeholder="اختر طلبك", options=options, min_values=1, max_values=1,
                         custom_id="ticket_type_select")

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        guild = interaction.guild
        user = interaction.user

        category = None
        if TICKET_CATEGORY_ID:
            category = guild.get_channel(TICKET_CATEGORY_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        if value == "special":
            special_member = guild.get_member(SPECIAL_ADMIN_ID)
            if special_member:
                overwrites[special_member] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
        else:
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        channel_name = f"{value}-{user.name}"[:95]
        topic = f"type:{value}|user:{user.id}"

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=topic,
        )

        staff_role = guild.get_role(STAFF_ROLE_ID)
        mention_line = f"{staff_role.mention if staff_role else 'Staff Team'} | {user.mention}"

        welcome_embed = discord.Embed(
            description="أهلاً وسهلاً، يرجى كتابة موضوع طلبك، وسيتم الرد عليك من قبل المسؤولين.",
            color=discord.Color.dark_theme(),
        )
        if PANEL_IMAGE_URL:
            welcome_embed.set_image(url=PANEL_IMAGE_URL)

        ticket_message = await ticket_channel.send(
            content=mention_line, embed=welcome_embed, view=TicketActionsView()
        )
        try:
            await ticket_message.pin()
        except discord.HTTPException:
            pass

        await interaction.response.edit_message(content=f"تم فتح تذكرتك هنا: {ticket_channel.mention}", view=None)


class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


# =========================================================
# ===================== لوحة فتح التذكرة =====================
# =========================================================

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=TICKET_ICON_EMOJI, custom_id="open_ticket_panel")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(content="يرجى تحديد طلبك", view=TicketTypeView(), ephemeral=True)


# =========================================================
# ========================= الأوامر =========================
# =========================================================

@bot.tree.command(name="panel", description="إرسال لوحة فتح التذاكر")
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction):
    content = PANEL_IMAGE_URL if PANEL_IMAGE_URL else ""

    await interaction.channel.send(content=content, view=TicketPanelView())
    await interaction.response.send_message("تم إرسال اللوحة.", ephemeral=True)


@panel.error
async def panel_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("هذا الأمر مخصص للمشرفين فقط.", ephemeral=True)
    else:
        raise error


@bot.tree.command(name="memberadd", description="إضافة شخص للتذكرة الحالية")
@app_commands.describe(member="الشخص يلي بدك تضيفه على التذكرة")
async def memberadd(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    data = parse_topic(channel.topic)

    if "type" not in data:
        await interaction.response.send_message("هذا الأمر يعمل فقط داخل قناة تذكرة.", ephemeral=True)
        return

    if not is_staff(interaction.user):
        await interaction.response.send_message("لا تملك صلاحية إضافة أشخاص إلى التذاكر.", ephemeral=True)
        return

    await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"تم إضافة {member.mention} إلى التذكرة.")


@memberadd.error
async def memberadd_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("لا تملك صلاحية استخدام هذا الأمر.", ephemeral=True)
    else:
        raise error


# =========================================================
# ========================= الإقلاع =========================
# =========================================================

@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketTypeView())
    bot.add_view(TicketActionsView())

    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
    else:
        await bot.tree.sync()

    print(f"تم تسجيل الدخول كـ {bot.user}")


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
