import random
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_CHANNEL_ID = os.environ.get("ADMIN_CHANNEL_ID", "")
MIN_WITHDRAW = 50
REFERRAL_BONUS = 5

db = Database()
WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_NUMBER = range(3)


async def send_captcha(update, context):
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    correct = a + b
    wrong = list({correct+2, correct-2, correct+3, correct-3} - {correct})[:3]
    options = (wrong + [correct])[:4]
    random.shuffle(options)
    context.user_data["cap"] = correct
    kb = [
        [InlineKeyboardButton(str(o), callback_data=f"cap_{o}") for o in options[:2]],
        [InlineKeyboardButton(str(o), callback_data=f"cap_{o}") for o in options[2:]]
    ]
    txt = f"👋 স্বাগতম! *Gram Earn Bot*\n\nশুরু করার আগে প্রমাণ করুন আপনি রোবট নন —\n\n❓ *{a} + {b} = ?*"
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def captcha_check(update, context):
    query = update.callback_query
    await query.answer()
    chosen = int(query.data.split("_")[1])
    if chosen == context.user_data.get("cap"):
        user = query.from_user
        referrer_id = context.user_data.get("referrer_id")
        is_new = db.register_user(user.id, user.first_name, user.username, referrer_id)
        if is_new and referrer_id:
            db.add_balance(referrer_id, REFERRAL_BONUS)
            try:
                await context.bot.send_message(referrer_id, f"🎉 রেফারেল বোনাস! +{REFERRAL_BONUS} টাকা")
            except Exception:
                pass
        await show_main_menu(update, context)
    else:
        await query.answer("❌ ভুল উত্তর! আবার চেষ্টা করুন।", show_alert=True)
        await send_captcha(update, context)


async def start(update, context):
    args = context.args
    if args and args[0].isdigit():
        context.user_data["referrer_id"] = int(args[0])
    await send_captcha(update, context)


async def show_main_menu(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    balance = user["balance"] if user else 0
    text = (
        f"👋 স্বাগতম! *Gram Earn Bot*\n\n"
        f"💰 আপনার ব্যালেন্স: *{balance:.2f} টাকা*\n\n"
        f"টাস্ক করুন, টাকা আয় করুন!"
    )
    keyboard = [
        [InlineKeyboardButton("📋 টাস্ক লিস্ট", callback_data="tasks"),
         InlineKeyboardButton("💼 আমার ব্যালেন্স", callback_data="balance")],
        [InlineKeyboardButton("💸 উইথড্র", callback_data="withdraw"),
         InlineKeyboardButton("👥 রেফার করুন", callback_data="referral")],
        [InlineKeyboardButton("📊 লিডারবোর্ড", callback_data="leaderboard")],
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_tasks(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    tasks = db.get_all_tasks()
    completed = db.get_completed_tasks(user_id)
    if not tasks:
        await query.edit_message_text("😔 এখন কোনো টাস্ক নেই।",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]]))
        return
    keyboard = []
    for task in tasks:
        status = "✅" if task["id"] in completed else "🔲"
        btn = f"{status} {task['title']} (+{task['reward']} টাকা)"
        cb = "already_done" if task["id"] in completed else f"do_task_{task['id']}"
        keyboard.append([InlineKeyboardButton(btn, callback_data=cb)])
    keyboard.append([InlineKeyboardButton("🏠 মেনু", callback_data="menu")])
    await query.edit_message_text("📋 *সকল টাস্ক*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def do_task(update, context):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    if db.is_task_completed(user_id, task_id):
        await query.answer("⚠️ আগেই করা হয়েছে!", show_alert=True)
        return
    task = db.get_task(task_id)
    if not task:
        return
    text = (
        f"📌 *{task['title']}*\n\n"
        f"📝 {task['description']}\n\n"
        f"💰 পুরস্কার: *{task['reward']} টাকা*\n\n"
        f"লিংকে গিয়ে কাজটি করুন।"
    )
    keyboard = [
        [InlineKeyboardButton("🔗 লিংকে যান", url=task["link"])],
        [InlineKeyboardButton("✅ করা হয়েছে", callback_data=f"verify_task_{task_id}")],
        [InlineKeyboardButton("🔙 ফিরে যান", callback_data="tasks")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def verify_task(update, context):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    if db.is_task_completed(user_id, task_id):
        await query.answer("⚠️ আগেই করা হয়েছে!", show_alert=True)
        return
    task = db.get_task(task_id)
    task_type = task.get("task_type", "telegram")
    if task_type == "facebook":
        context.user_data["pending_task_id"] = task_id
        await query.edit_message_text(
            "📸 *স্ক্রিনশট পাঠান*\n\nফেসবুক টাস্কটি সম্পন্ন করার পর স্ক্রিনশট পাঠান।\n\nঅ্যাডমিন যাচাই করার পর টাকা পাবেন।",
            parse_mode="Markdown"
        )
    else:
        try:
            member = await context.bot.get_chat_member(task["link"].replace("https://t.me/", "@"), user_id)
            if member.status in ["left", "kicked"]:
                await query.answer("❌ চ্যানেলে জয়েন করুন!", show_alert=True)
                return
        except Exception:
            pass
        db.complete_task(user_id, task_id, task["reward"])
        await query.edit_message_text(
            f"🎉 *টাস্ক সম্পন্ন!*\n\n+{task['reward']} টাকা যোগ হয়েছে!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 আরো টাস্ক", callback_data="tasks")],
                [InlineKeyboardButton("🏠 মেনু", callback_data="menu")],
            ])
        )


async def handle_screenshot(update, context):
    user_id = update.effective_user.id
    task_id = context.user_data.get("pending_task_id")
    if not task_id or not update.message.photo:
        return
    task = db.get_task(task_id)
    file_id = update.message.photo[-1].file_id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ অনুমোদন", callback_data=f"approve_fb_{user_id}_{task_id}"),
         InlineKeyboardButton("❌ বাতিল", callback_data=f"reject_fb_{user_id}_{task_id}")]
    ])
    try:
        channel = ADMIN_CHANNEL_ID or ADMIN_ID
        await context.bot.send_photo(
            channel, file_id,
            caption=f"📸 *FB প্রমাণ*\n👤 {update.effective_user.first_name} (ID: {user_id})\n📌 {task['title']}\n💰 {task['reward']} টাকা",
            parse_mode="Markdown", reply_markup=keyboard
        )
    except Exception:
        pass
    context.user_data.pop("pending_task_id", None)
    await update.message.reply_text(
        "✅ স্ক্রিনশট পাঠানো হয়েছে! অ্যাডমিন যাচাই করবেন।",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]])
    )


async def approve_fb(update, context):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ অ্যাডমিন নন!", show_alert=True)
        return
    parts = query.data.split("_")
    action = parts[0]
    user_id = int(parts[2])
    task_id = int(parts[3])
    task = db.get_task(task_id)
    if action == "approve":
        db.complete_task(user_id, task_id, task["reward"])
        await query.edit_message_caption("✅ অনুমোদিত!")
        await context.bot.send_message(user_id, f"✅ Facebook টাস্ক অনুমোদিত! +{task['reward']} টাকা!")
    else:
        await query.edit_message_caption("❌ বাতিল!")
        await context.bot.send_message(user_id, "❌ Facebook টাস্কের স্ক্রিনশট গৃহীত হয়নি।")


async def show_balance(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = db.get_user(user_id)
    completed_count = len(db.get_completed_tasks(user_id))
    referral_count = db.get_referral_count(user_id)
    text = (
        f"💼 *আমার অ্যাকাউন্ট*\n\n"
        f"👤 নাম: {user['name']}\n"
        f"💰 ব্যালেন্স: *{user['balance']:.2f} টাকা*\n"
        f"✅ সম্পন্ন টাস্ক: {completed_count}টি\n"
        f"👥 রেফারেল: {referral_count}জন\n"
        f"📅 যোগ দিয়েছেন: {user['joined_date']}"
    )
    await query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]]))


async def withdraw_start(update, context):
    query = update.callback_query
    await query.answer()
    user = db.get_user(query.from_user.id)
    if user["balance"] < MIN_WITHDRAW:
        await query.edit_message_text(
            f"❌ কমপক্ষে *{MIN_WITHDRAW} টাকা* দরকার।\nআপনার ব্যালেন্স: {user['balance']:.2f} টাকা",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]]))
        return ConversationHandler.END
    await query.edit_message_text(f"💸 কত টাকা উইথড্র করবেন?\n(সর্বনিম্ন {MIN_WITHDRAW} টাকা)\n\nসংখ্যা লিখুন:")
    return WITHDRAW_AMOUNT


async def withdraw_amount(update, context):
    text = update.message.text
    if not text.isdigit():
        await update.message.reply_text("❌ শুধু সংখ্যা লিখুন!")
        return WITHDRAW_AMOUNT
    amount = int(text)
    user = db.get_user(update.effective_user.id)
    if amount < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ সর্বনিম্ন {MIN_WITHDRAW} টাকা!")
        return WITHDRAW_AMOUNT
    if amount > user["balance"]:
        await update.message.reply_text(f"❌ ব্যালেন্স মাত্র {user['balance']:.2f} টাকা!")
        return WITHDRAW_AMOUNT
    context.user_data["withdraw_amount"] = amount
    keyboard = [[InlineKeyboardButton("📱 বিকাশ", callback_data="bkash"),
                 InlineKeyboardButton("💚 নগদ", callback_data="nagad")]]
    await update.message.reply_text("পেমেন্ট মেথড বেছে নিন:", reply_markup=InlineKeyboardMarkup(keyboard))
    return WITHDRAW_METHOD


async def withdraw_method(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["withdraw_method"] = "বিকাশ" if query.data == "bkash" else "নগদ"
    await query.edit_message_text(f"আপনার *{context.user_data['withdraw_method']}* নম্বর লিখুন:", parse_mode="Markdown")
    return WITHDRAW_NUMBER


async def withdraw_number(update, context):
    number = update.message.text.strip()
    user_id = update.effective_user.id
    amount = context.user_data["withdraw_amount"]
    method = context.user_data["withdraw_method"]
    db.create_withdrawal(user_id, amount, method, number)
    db.deduct_balance(user_id, amount)
    try:
        channel = ADMIN_CHANNEL_ID or ADMIN_ID
        await context.bot.send_message(
            channel,
            f"🔔 *নতুন উইথড্র!*\n\n👤 ID: {user_id}\n💰 {amount} টাকা\n📱 {method}: {number}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ অনুমোদন", callback_data=f"approve_{user_id}_{amount}"),
                 InlineKeyboardButton("❌ বাতিল", callback_data=f"reject_{user_id}_{amount}")]
            ])
        )
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ রিকোয়েস্ট পাঠানো হয়েছে!\n💰 {amount} টাকা\n📱 {method}: {number}\n\n২৪ ঘণ্টার মধ্যে পাবেন।",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]]))
    return ConversationHandler.END


async def cancel(update, context):
    await update.message.reply_text("❌ বাতিল।")
    return ConversationHandler.END


async def show_referral(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"
    count = db.get_referral_count(user_id)
    await query.edit_message_text(
        f"👥 *রেফারেল প্রোগ্রাম*\n\nপ্রতি রেফারেলে: *{REFERRAL_BONUS} টাকা*\nআপনার রেফারেল: *{count}জন*\n\nআপনার লিংক:\n`{link}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]]))


async def show_leaderboard(update, context):
    query = update.callback_query
    await query.answer()
    leaders = db.get_leaderboard()
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    text = "🏆 *টপ আর্নার্স*\n\n"
    for i, u in enumerate(leaders[:5]):
        text += f"{medals[i]} {u['name']} — {u['balance']:.2f} টাকা\n"
    await query.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মেনু", callback_data="menu")]]))


async def admin_add_task(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("ব্যবহার:\n`/addtask টাইটেল বিবরণ লিংক পরিমাণ [telegram/facebook]`", parse_mode="Markdown")
        return
    title = args[0].replace("_", " ")
    desc = args[1].replace("_", " ")
    link = args[2]
    reward = float(args[3])
    task_type = args[4] if len(args) > 4 else "telegram"
    db.add_task(title, desc, link, reward, task_type)
    await update.message.reply_text(f"✅ টাস্ক যোগ: {title} (+{reward} টাকা) [{task_type}]")


async def admin_stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 *স্ট্যাটিসটিক্স*\n\n👥 ইউজার: {stats['total_users']}\n✅ টাস্ক: {stats['total_completions']}\n💸 পেন্ডিং: {stats['pending_withdrawals']}টি\n💰 পরিশোধ: {stats['total_paid']:.2f} টাকা",
        parse_mode="Markdown")


async def admin_approve(update, context):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ অ্যাডমিন নন!", show_alert=True)
        return
    parts = query.data.split("_")
    action = parts[0]
    user_id = int(parts[1])
    amount = float(parts[2])
    if action == "approve":
        db.update_withdrawal_status(user_id, amount, "approved")
        await query.edit_message_text(f"✅ {user_id} এর {amount} টাকা অনুমোদিত।")
        await context.bot.send_message(user_id, f"✅ {amount} টাকার উইথড্র অনুমোদিত!")
    else:
        db.add_balance(user_id, amount)
        db.update_withdrawal_status(user_id, amount, "rejected")
        await query.edit_message_text(f"❌ {user_id} এর {amount} টাকা বাতিল।")
        await context.bot.send_message(user_id, f"❌ {amount} টাকার উইথড্র বাতিল। টাকা ফেরত দেওয়া হয়েছে।")


async def admin_broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার: /broadcast মেসেজ")
        return
    msg = " ".join(context.args)
    users = db.get_all_users()
    count = 0
    for user in users:
        try:
            await context.bot.send_message(user["user_id"], msg)
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ {count}জনকে মেসেজ পাঠানো হয়েছে।")


async def admin_ban(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return
    user_id = int(context.args[0])
    db.ban_user(user_id)
    await update.message.reply_text(f"✅ {user_id} ব্যান করা হয়েছে।")


async def admin_unban(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return
    user_id = int(context.args[0])
    db.unban_user(user_id)
    await update.message.reply_text(f"✅ {user_id} আনব্যান করা হয়েছে।")


async def already_done(update, context):
    await update.callback_query.answer("✅ এই টাস্কটি আগেই সম্পন্ন!", show_alert=True)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method, pattern="^(bkash|nagad)$")],
            WITHDRAW_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_number)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtask", admin_add_task))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("ban", admin_ban))
    app.add_handler(CommandHandler("unban", admin_unban))
    app.add_handler(withdraw_conv)
    app.add_handler(CallbackQueryHandler(captcha_check, pattern="^cap_"))
    app.add_handler(CallbackQueryHandler(show_main_menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(show_tasks, pattern="^tasks$"))
    app.add_handler(CallbackQueryHandler(do_task, pattern="^do_task_"))
    app.add_handler(CallbackQueryHandler(verify_task, pattern="^verify_task_"))
    app.add_handler(CallbackQueryHandler(already_done, pattern="^already_done$"))
    app.add_handler(CallbackQueryHandler(show_balance, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(show_referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern="^(approve|reject)_\\d+_"))
    app.add_handler(CallbackQueryHandler(approve_fb, pattern="^(approve|reject)_fb_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    print("✅ বট চালু হয়েছে...")
    app.run_polling()


if __name__ == "__main__":
    main()
