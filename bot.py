# -*- coding: utf-8 -*-
"""
بوت تذاكر عبر ديسكورد - دعم ميلاد
مبني باستخدام discord.py مع نظام سجلات ورابط لمعاينة المحادثة
"""

import os
import io
import asyncio
import datetime
import discord
from discord import app_commands
from discord.ext import commands

# =========================================================
# ============ الاعدادات (config) - من متغيرات البيئة ============
# =========================================================

def _clean_id(raw: str):
    if not raw:
        return None
    cleaned = raw.strip().strip("<>").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        raise RuntimeError(
            f"القيمة '{raw}' ليست رقم معرف صحيح. يجب ان تتكون من ارقام فقط بدون اقواس < > او مسافات."
        )


BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = _clean_id(os.getenv("GUILD_ID"))
TICKET_CATEGORY_ID = _clean_id(os.getenv("TICKET_CATEGORY_ID"))
STAFF_ROLE_ID = _clean_id(os.getenv("STAFF_ROLE_ID")) or 1535668575585566871
SPECIAL_ADMIN_ID = _clean_id(os.getenv("SPECIAL_ADMIN_ID")) or 920981254554406952
LOG_CHANNEL_ID = _clean_id(os.getenv("LOG_CHANNEL_ID")) or 1281894208550076477
PANEL_IMAGE_URL = os.getenv("PANEL_IMAGE_URL", "")

# الرموز التعبيرية المخصصة للازرار
TICKET_ICON_EMOJI = os.getenv("TICKET_ICON_EMOJI", "<:linkssssss:1536040564112367738>")
CLAIM_EMOJI = os.getenv("CLAIM_EMOJI", "<:claim:1536007978090500096>")
DELETE_EMOJI = os.getenv("DELETE_EMOJI", "<:delete:1536007930325770340>")

# عداد التذاكر التلقائي
ticket_counter = 1

if not BOT_TOKEN:
    raise RuntimeError("يجب تعبئة متغير BOT_TOKEN من لوحة تحكم Railway (Variables).")

# =========================================================
# ===================== نهاية الاعدادات ====================
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

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


async def generate_html_transcript(channel: discord.TextChannel) -> discord.File:
    """تنشئ ملف HTML يحتوي على جميع الرسائل والصور داخل التذكرة"""
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>سجل تذكرة - {channel.name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #36393f; color: #dcddde; padding: 20px; }}
            .header {{ border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 20px; }}
            .message {{ background-color: #2f3136; padding: 10px; margin-bottom: 10px; border-radius: 5px; }}
            .author {{ font-weight: bold; color: #5865f2; }}
            .time {{ font-size: 0.8em; color: #72767d; margin-right: 10px; }}
            .content {{ margin-top: 5px; white-space: pre-wrap; }}
            .attachment {{ margin-top: 5px; color: #00aff4; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>سجل المحادثة للتذكرة: {channel.name}</h2>
            <p>تاريخ الارشفة: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
    """

    for msg in messages:
        time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        content = discord.utils.escape_mentions(msg.content) if msg.content else ""
        attachments_html = ""
        for att in msg.attachments:
            attachments_html += f'<div class="attachment"><a href="{att.url}" target="_blank">مرفق: {att.filename}</a></div>'

        html_content += f"""
        <div class="message">
            <span class="author">{msg.author.display_name} ({msg.author})</span>
            <span class="time">{time_str}</span>
            <div class="content">{content}</div>
            {attachments_html}
        </div>
        """

    html_content += "</body></html>"

    file_bytes = io.BytesIO(html_content.encode("utf-8"))
    return discord.File(file_bytes, filename=f"transcript-{channel.name}.html")


async def auto_delete_ticket_task(channel: discord.TextChannel, owner_id: int):
    """
    تنتظر هذه الدالة مدة ساعتين ثم تتحقق مما اذا كان صاحب التذكرة نفسه
    قد ارسل اي رسالة داخل القناة، بغض النظر عن ردود فريق الدعم.
    في حال عدم وجود اي رد من صاحب التذكرة يتم حذف القناة دون اي اشعار.
    """
    await asyncio.sleep(7200)  # الانتظار ساعتين (7200 ثانية)

    try:
        current_channel = bot.get_channel(channel.id)
        if not current_channel:
            return

        owner_replied = False
        async for msg in current_channel.history(limit=None, oldest_first=True):
            if msg.author.id == owner_id:
                owner_replied = True
                break

        # اذا لم يرسل صاحب التذكرة اي رسالة خلال الساعتين يتم الحذف بصمت وبدون سجل
        if not owner_replied:
            await current_channel.delete()
    except discord.NotFound:
        pass
    except Exception:
        pass


# =========================================================
# ==================== نافذة تاكيد الحذف ===================
# =========================================================

class ConfirmDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="تاكيد الحذف", style=discord.ButtonStyle.danger, custom_id="confirm_delete_btn")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        data = parse_topic(channel.topic)
        ticket_type = data.get("type")

        if ticket_type == "special":
            if interaction.user.id != SPECIAL_ADMIN_ID:
                await interaction.response.send_message("لا يمكنك حذف هذه التذكرة", ephemeral=True)
                return
        else:
            if not is_staff(interaction.user):
                await interaction.response.send_message("لا تملك صلاحية حذف التذكرة", ephemeral=True)
                return

        button.disabled = True
        await interaction.response.edit_message(content="جاري حفظ السجل وحذف التذكرة خلال خمس ثواني", view=None)

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            transcript_file = await generate_html_transcript(channel)
            owner_id = data.get("user")
            owner_mention = f"<@{owner_id}>" if owner_id else "غير معروف"

            embed = discord.Embed(
                title="تم اغلاق التذكرة وحفظ السجل",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="اسم التذكرة", value=channel.name, inline=True)
            embed.add_field(name="صاحب التذكرة", value=owner_mention, inline=True)
            embed.add_field(name="بواسطة", value=interaction.user.mention, inline=True)

            # يتم ارسال السجل مع ملف المحادثة نفسه والابقاء عليه في القناة
            await log_channel.send(embed=embed, file=transcript_file)

        await asyncio.sleep(5)
        await channel.delete()


# =========================================================
# ==================== ازرار / نوافذ الحذف والاستلام =========
# =========================================================

class TicketActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=DELETE_EMOJI, custom_id="ticket_delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        data = parse_topic(channel.topic)
        ticket_type = data.get("type")

        if ticket_type == "special":
            if interaction.user.id != SPECIAL_ADMIN_ID:
                await interaction.response.send_message("لا يمكنك حذف هذه التذكرة", ephemeral=True)
                return
        else:
            if not is_staff(interaction.user):
                await interaction.response.send_message("لا تملك صلاحية حذف التذكرة", ephemeral=True)
                return

        await interaction.response.send_message(
            content="هل انت متاكد من انك تريد حذف هذه التذكرة؟",
            view=ConfirmDeleteView(),
            ephemeral=True
        )

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=CLAIM_EMOJI, custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild
        data = parse_topic(channel.topic)
        ticket_type = data.get("type")

        if ticket_type == "special":
            if interaction.user.id != SPECIAL_ADMIN_ID:
                await interaction.response.send_message("لا يمكنك استلام هذه التذكرة", ephemeral=True)
                return
        else:
            if not is_staff(interaction.user):
                await interaction.response.send_message("لا تملك صلاحية استلام التذكرة", ephemeral=True)
                return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:
            await channel.set_permissions(staff_role, view_channel=False)

        await channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True)

        button.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.send_message(f"تم استلام هذه التذكرة من قبل {interaction.user.mention}")

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="تم استلام التذكرة وقفلها",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="القناة", value=channel.mention, inline=True)
            embed.add_field(name="المستلم", value=interaction.user.mention, inline=True)
            await log_channel.send(embed=embed)


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
        global ticket_counter
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

        channel_name = f"🎫・{ticket_counter}"
        ticket_counter += 1

        topic = f"type:{value}|user:{user.id}"

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=topic,
        )

        staff_role = guild.get_role(STAFF_ROLE_ID)
        mention_line = f"{staff_role.mention if staff_role else 'فريق الدعم'} | {user.mention}"

        welcome_embed = discord.Embed(
            description="اهلا وسهلا يرجى كتابة موضوع طلبك وسيتم الرد عليك من قبل المسؤولين",
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

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="تم فتح تذكرة جديدة",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="صاحب التذكرة", value=user.mention, inline=True)
            embed.add_field(name="النوع", value=value, inline=True)
            embed.add_field(name="القناة", value=ticket_channel.mention, inline=True)
            await log_channel.send(embed=embed)

        await interaction.response.edit_message(content=f"تم فتح تذكرتك هنا {ticket_channel.mention}", view=None)

        # البدء بمراقبة الحذف التلقائي بعد ساعتين من عدم رد صاحب التذكرة
        asyncio.create_task(auto_delete_ticket_task(ticket_channel, user.id))


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
        await interaction.response.send_message(view=TicketTypeView(), ephemeral=True)


# =========================================================
# ========================= الاوامر =========================
# =========================================================

@bot.tree.command(name="panel", description="ارسال لوحة فتح التذاكر")
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction):
    content = PANEL_IMAGE_URL if PANEL_IMAGE_URL else ""

    await interaction.channel.send(content=content, view=TicketPanelView())
    await interaction.response.send_message("تم ارسال اللوحة", ephemeral=True)


@panel.error
async def panel_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("هذا الامر مخصص للمشرفين فقط", ephemeral=True)
    else:
        raise error


@bot.tree.command(name="memberadd", description="اضافة شخص للتذكرة الحالية")
@app_commands.describe(member="الشخص الذي تريد اضافته الى التذكرة")
async def memberadd(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    data = parse_topic(channel.topic)

    if "type" not in data:
        await interaction.response.send_message("هذا الامر يعمل فقط داخل قناة تذكرة", ephemeral=True)
        return

    if not is_staff(interaction.user):
        await interaction.response.send_message("لا تملك صلاحية اضافة اشخاص الى التذاكر", ephemeral=True)
        return

    await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"تم اضافة {member.mention} الى التذكرة")


@memberadd.error
async def memberadd_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("لا تملك صلاحية استخدام هذا الامر", ephemeral=True)
    else:
        raise error


# =========================================================
# ========================= الاقلاع =========================
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
