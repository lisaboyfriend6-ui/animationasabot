import json

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    ContextTypes,
    PicklePersistence,
    filters,
)
from . import bot_token, proxy_uri, admin_ids, logger, inline_cmd


async def start(update: Update, context: ContextTypes):
    user = update.effective_user
    if not user.id in admin_ids:
        await update.effective_chat.send_message(
            "⚠️ You are not allowed to use this bot."
        )
        return
    await update.effective_chat.send_message(
        f"Hi, {user.first_name}, I am working now."
    )
    context.user_data["set_media_idx"] = None


def get_quickreply():
    with open("./quick_reply.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        return data


async def on_inline_query(update: Update, context: ContextTypes):
    query = update.inline_query.query
    user = update.inline_query.from_user
    if not user.id in admin_ids:
        query.answer([])
    if not query:
        return

    # 查找缓存。图床目前不好找，还是自己配置下比较好。
    quick_replies = get_quickreply()
    for quick_reply in quick_replies:
        if quick_reply.get("type", "text") == "photo" and not quick_reply.get(
            "media_id", ""
        ):
            await update.inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id=uuid.uuid4().hex,
                        title="图片未配置。机器人对话 /set ",
                        input_message_content=InputTextMessageContent(
                            "图片未配置。机器人对话 /set", parse_mode="HTML"
                        ),
                    )
                ]
            )
            return

    result = []
    for idx, quick_reply in enumerate(quick_replies):
        params = {
            "id": uuid.uuid4().hex,
            "title": quick_reply["title"],
        }
        buttons = quick_reply.get("buttons", [])
        btn_matrx = []
        for btn_row in buttons:
            row = []
            for btn in btn_row:
                row.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
            btn_matrx.append(row)
        keyboard = InlineKeyboardMarkup(btn_matrx)
        params["reply_markup"] = keyboard
        params["input_message_content"] = InputTextMessageContent(
            f"<b>{quick_reply['title']}</b>\n\n{quick_reply['msg']}",
            parse_mode="HTML",
        )
        if quick_reply.get("type", "text") == "text":
            result.append(InlineQueryResultArticle(**params))
        elif quick_reply.get("type", "text") == "photo":
            params["photo_file_id"] = quick_reply.get("media_id", "")
            params["caption"] = quick_reply.get("msg", "")
            params["parse_mode"] = "HTML"
            params["description"] = quick_reply.get("title", "")
            params["show_caption_above_media"] = True
            result.append(InlineQueryResultCachedPhoto(**params))

    await update.inline_query.answer(result)


async def set_media(update: Update, context: ContextTypes):
    quick_replies = get_quickreply()

    buttons = []
    for idx, quick_reply in enumerate(quick_replies):
        name = ""
        if quick_reply.get("type", "text") == "photo":
            if quick_reply.get("media_id", ""):
                name = "✔️已配置"
            else:
                name = "❌未配置"
            name += f" 【{quick_reply['title']}】"
            buttons.append(InlineKeyboardButton(name, callback_data=f"set_media:{idx}"))
    if not buttons:
        await update.effective_chat.send_message("没有可配置的图片回复。")
        return
    keyboard = InlineKeyboardMarkup([buttons])
    await update.effective_chat.send_message(
        "请选择要配置的图片回复，点击按钮后，发送图片即可设置", reply_markup=keyboard
    )


async def on_callback_query(update: Update, context: ContextTypes):
    query = update.callback_query
    quick_replies = get_quickreply()
    await query.answer()
    if query.data.startswith("set_media:"):
        idx = int(query.data.split(":")[1])
        context.user_data["set_media_idx"] = idx
        await query.message.reply_text("请发送图片。")


async def on_photo(update: Update, context: ContextTypes):
    if not update.message.photo:
        await update.message.reply_text("请发送图片。")
        return
    idx = context.user_data.get("set_media_idx", None)
    if idx is None:
        await update.message.reply_text("请先选择要配置的图片回复。(输入 /set ) ")
        return
    quick_replies = get_quickreply()
    quick_replies[idx]["media_id"] = update.message.photo[-1].file_id
    with open("./quick_reply.json", "w", encoding="utf-8") as f:
        json.dump(quick_replies, f, ensure_ascii=False, indent=4)
    await update.message.reply_text(
        "图片配置成功, quick_reply.json 已经重新记录了图片内容 。\n\n发送 /set 重新配置。"
    )
    context.user_data["set_media_idx"] = None


async def error_handler(update: Update, context: ContextTypes):
    logger.error(f"Update: {update} caused error: {context.error}")
    # await update.effective_chat.send_message(f"An error occurred: {context.error}")


if __name__ == "__main__":
    pickle_persistence = PicklePersistence(filepath=f"./cache.pickle")
    application = (
        ApplicationBuilder()
        .token(bot_token)
        .persistence(persistence=pickle_persistence)
    )
    if proxy_uri:
        application = application.proxy(proxy_uri).get_updates_proxy(proxy_uri).build()
    else:
        application = application.build()

    application.add_handler(
        CommandHandler(
            "start",
            start,
            filters.ChatType.PRIVATE & filters.User(user_id=admin_ids),
        )
    )
    application.add_handler(
        CommandHandler(
            "set", set_media, filters.ChatType.PRIVATE & filters.User(user_id=admin_ids)
        )
    )
    application.add_handler(
        CallbackQueryHandler(on_callback_query, pattern=f"^set_media:")
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.User(user_id=admin_ids), on_photo
        ),
    )
    application.add_handler(
        InlineQueryHandler(on_inline_query, pattern=f"^{inline_cmd}")
    )
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)
