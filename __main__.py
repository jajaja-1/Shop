import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
from collections import Counter
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import datetime

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфігурація
TOKEN = "7985454883:AAHRjwlYjVAA_rYZRJp2rzrIrBPiSV6Zu34"
ADMIN_ID = 1955422946
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "telegram_shop_bot"

# Підключення до MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    products_collection = db["products"]
    carts_collection = db["carts"]
    orders_collection = db["orders"]

    products_collection.create_index("product_id")
    carts_collection.create_index("user_id")
    orders_collection.create_index("user_id")

    logger.info("Успішне підключення до MongoDB")
except PyMongoError as e:
    logger.error(f"Помилка підключення до MongoDB: {e}")
    raise

# Стани для ConversationHandler
CITY, POST_OFFICE = range(2)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Помилка в обробнику: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.callback_query:
        try:
            await update.callback_query.answer("Сталася помилка, спробуйте ще раз")
        except:
            pass

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE = None):
    try:
        keyboard = [
            [InlineKeyboardButton("🛍️ Каталог", callback_data="show_products")],
            [InlineKeyboardButton("🛒 Кошик", callback_data="show_cart")],
            [InlineKeyboardButton("ℹ️ Допомога", callback_data="show_help")],
            [InlineKeyboardButton("❌ Вийти", callback_data="close_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text("Оберіть дію:", reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                "Оберіть дію:",
                reply_markup=reply_markup
            )
            await update.callback_query.answer()
    except Exception as e:
        logger.error(f"Помилка в show_main_menu: {str(e)}")
        raise

async def close_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        await query.delete_message()
    except Exception as e:
        logger.error(f"Помилка в close_menu: {str(e)}")
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Ласкаво просимо до нашого магазину!")
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Помилка в start: {str(e)}")
        raise

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        categories = products_collection.distinct("category")

        if not categories:
            await query.edit_message_text("Категорії товарів не знайдені")
            return

        buttons = [
            [InlineKeyboardButton(f" {cat.capitalize()}", callback_data=f"category_{cat}")]
            for cat in sorted(categories)
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

        await query.edit_message_text(
            "Оберіть модель телефону:",
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Помилка в show_products: {str(e)}")
        await query.answer("Помилка завантаження категорій")
        raise

async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        category = query.data.split("_")[1]
        category_products = list(products_collection.find({"category": category}))

        if not category_products:
            await query.edit_message_text(f"Товари в категорії '{category}' не знайдені")
            return

        buttons = [
            [InlineKeyboardButton(
                f"{p['name']} - {p['price']}₴",
                callback_data=f"product_{p['product_id']}"
            )]
            for p in category_products
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="show_products")])

        await query.edit_message_text(
            f"Чохли на'{category}':",
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Помилка в show_category: {str(e)}")
        await query.answer("Помилка завантаження товарів")
        raise

async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        product_id = int(query.data.split("_")[1])
        product = products_collection.find_one({"product_id": product_id})

        if not product:
            await query.edit_message_text("Товар не знайдено")
            return

        buttons = [
            [InlineKeyboardButton("➕ У кошик", callback_data=f"add_{product_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_category_{product['category']}")]


        ]

        # Зберігаємо message_id для можливого видалення фото
        context.user_data['last_product_message_id'] = query.message.message_id

        if product.get('photo'):
            try:
                # Відправляємо нове повідомлення з фото
                sent_message = await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=product['photo'],
                    caption=(
                        f" <b>{product['name']}</b>\n\n"
                        f"{product['description']}\n\n"
                        f"💵 Ціна: <b>{product['price']}₴</b>"
                    ),
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode="HTML"
                )
                # Зберігаємо ID повідомлення з фото
                context.user_data['photo_message_id'] = sent_message.message_id
                # Видаляємо попереднє повідомлення (список товарів)
                await query.delete_message()
            except Exception as e:
                logger.error(f"Помилка відправки фото: {str(e)}")
                await query.edit_message_text(
                    f" <b>{product['name']}</b>\n\n"
                    f"{product['description']}\n\n"
                    f"💵 Ціна: <b>{product['price']}₴</b>",
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode="HTML"
                )
        else:
            await query.edit_message_text(
                f" <b>{product['name']}</b>\n\n"
                f"{product['description']}\n\n"
                f"💵 Ціна: <b>{product['price']}₴</b>",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Помилка в view_product: {str(e)}")
        await query.answer("Помилка завантаження товару")
        raise

async def back_to_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        category = query.data.split("_")[-1]

        # Видаляємо повідомлення з фото, якщо воно є
        if 'photo_message_id' in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=context.user_data['photo_message_id']
                )
            except Exception as e:
                logger.error(f"Помилка при видаленні повідомлення з фото: {str(e)}")

        # Отримуємо товари категорії
        category_products = list(products_collection.find({"category": category}))

        buttons = [
            [InlineKeyboardButton(
                f"{p['name']} - {p['price']}₴",
                callback_data=f"product_{p['product_id']}"
            )]
            for p in category_products
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="show_products")])

        # Відправляємо оновлене повідомлення зі списком товарів
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Товари в категорії '{category}':",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        # Видаляємо попереднє повідомлення (якщо є)
        try:
            await query.delete_message()
        except:
            pass

    except Exception as e:
        logger.error(f"Помилка в back_to_category: {str(e)}")
        await query.answer("Помилка при поверненні до категорії")
        raise

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        product_id = int(query.data.split("_")[1])
        product = products_collection.find_one({"product_id": product_id})

        if not product:
            await query.answer("Товар не знайдено")
            return

        user_id = query.from_user.id

        carts_collection.update_one(
            {"user_id": user_id},
            {"$push": {"items": product_id}},
            upsert=True
        )

        await query.answer(f"{product['name']} додано до кошика")
    except Exception as e:
        logger.error(f"Помилка в add_to_cart: {str(e)}")
        await query.answer("Помилка при додаванні до кошика")
        raise

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        cart = carts_collection.find_one({"user_id": user_id})
        cart_items = cart.get("items", []) if cart else []

        if not cart_items:
            buttons = [
                [InlineKeyboardButton("🛍️ До каталогу", callback_data="show_products")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(
                "🛒 Ваш кошик порожній",
                reply_markup=InlineKeyboardMarkup(buttons))
            return

        cart_counter = Counter(cart_items)
        items_text = []
        total = 0
        buttons = []

        for product_id, count in cart_counter.items():
            product = products_collection.find_one({"product_id": product_id})
            if product:
                item_total = product['price'] * count
                items_text.append(f"▪ {product['name']} ×{count} - {item_total}₴")
                total += item_total
                buttons.append([
                    InlineKeyboardButton(
                        f"❌ Видалити {product['name']}",
                        callback_data=f"remove_{product_id}"
                    )
                ])

        buttons.extend([
            [InlineKeyboardButton("✅ Оформити замовлення", callback_data="order")],
            [InlineKeyboardButton("🧹 Очистити кошик", callback_data="clear_cart")],
            [InlineKeyboardButton("🛍️ Продовжити покупки", callback_data="show_products")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])

        await query.edit_message_text(
            "🛒 <b>Ваш кошик:</b>\n\n" +
            "\n".join(items_text) +
            f"\n\n💵 <b>Всього: {total}₴</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в show_cart: {str(e)}")
        await query.answer("Помилка завантаження кошика")
        raise

async def remove_from_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        product_id = int(query.data.split("_")[1])
        user_id = query.from_user.id

        result = carts_collection.update_one(
            {"user_id": user_id},
            {"$pull": {"items": product_id}}
        )

        if result.modified_count > 0:
            await query.answer("Товар видалено з кошика")
            await show_cart(update, context)
        else:
            await query.answer("Товар не знайдено в кошику")
    except Exception as e:
        logger.error(f"Помилка в remove_from_cart: {str(e)}")
        await query.answer("Помилка при видаленні товару")
        raise

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user_id = query.from_user.id

        carts_collection.delete_one({"user_id": user_id})

        await query.answer("Кошик очищено")
        await show_cart(update, context)
    except Exception as e:
        logger.error(f"Помилка в clear_cart: {str(e)}")
        await query.answer("Помилка при очищенні кошика")
        raise

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        cart = carts_collection.find_one({"user_id": user_id})
        cart_items = cart.get("items", []) if cart else []

        if not cart_items:
            await query.answer("Кошик порожній")
            return

        context.user_data["cart_items"] = cart_items.copy()
        context.user_data["user_info"] = {
            "name": query.from_user.full_name,
            "username": query.from_user.username,
            "id": user_id
        }

        await query.edit_message_text(
            " <b>Оформлення замовлення</b>\n\n"
            "Будь ласка, вкажіть місто доставки:",
            parse_mode="HTML"
        )

        return CITY
    except Exception as e:
        logger.error(f"Помилка в start_order: {str(e)}")
        await query.answer("Помилка при оформленні замовлення")
        return ConversationHandler.END

async def process_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        city = update.message.text.strip()

        if not city:
            await update.message.reply_text("Будь ласка, вкажіть місто доставки:")
            return CITY

        context.user_data["delivery_city"] = city

        await update.message.reply_text(
            "Вкажіть номер відділення Нової пошти у вашому місті:"
        )

        return POST_OFFICE
    except Exception as e:
        logger.error(f"Помилка в process_city: {str(e)}")
        await update.message.reply_text("Сталася помилка, спробуйте ще раз")
        return CITY

async def process_post_office(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        post_office = update.message.text.strip()

        if not post_office.isdigit():
            await update.message.reply_text(
                "Будь ласка, введіть тільки номер поштового відділення (цифри). Спробуйте ще раз:")
            return POST_OFFICE

        data = context.user_data
        cart_items = data["cart_items"]
        cart_products = list(products_collection.find({"product_id": {"$in": cart_items}}))

        cart_counter = Counter(cart_items)
        order_details = []
        total = 0

        for product in cart_products:
            count = cart_counter[product["product_id"]]
            item_total = product['price'] * count
            order_details.append(f"{product['name']} ×{count} - {item_total}₴")
            total += item_total

        user_info_text = (
            f"👤 <b>Покупець:</b>\n"
            f"• Ім'я: {data['user_info']['name']}\n"
            f"• Юзернейм: @{data['user_info']['username'] if data['user_info']['username'] else 'немає'}\n"
            f"• ID: {data['user_info']['id']}\n\n"
            f"🚚 <b>Доставка:</b>\n"
            f"• Місто: {data['delivery_city']}\n"
            f"• Поштове відділення: {post_office}\n\n"
        )

        order_info = (
                f"🛒 <b>Замовлення:</b>\n" +
                "\n".join(order_details) +
                f"\n\n💵 <b>Всього: {total}₴</b>"
        )

        order_data = {
            "user_id": user_id,
            "user_info": data["user_info"],
            "delivery_info": {
                "city": data["delivery_city"],
                "post_office": post_office
            },
            "items": [{"product_id": pid, "quantity": q} for pid, q in cart_counter.items()],
            "total": total,
            "status": "new",
            "created_at": datetime.datetime.now()
        }
        orders_collection.insert_one(order_data)

        carts_collection.delete_one({"user_id": user_id})

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🆕 <b>НОВЕ ЗАМОВЛЕННЯ</b>\n\n{user_info_text}{order_info}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Помилка відправки сповіщення адміну: {str(e)}")

        await update.message.reply_text(
            "✅ <b>Замовлення оформлено!</b>\n\n" +
            user_info_text +
            order_info +
            "\n\nДякуємо за покупку! Ми скоро зв'яжемося з вами.",
            parse_mode="HTML"
        )

        context.user_data.clear()

        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Помилка в process_post_office: {str(e)}")
        await update.message.reply_text("Сталася помилка, спробуйте ще раз")
        return POST_OFFICE

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if "cart_items" in context.user_data:
            context.user_data.clear()

        await update.message.reply_text(
            "❌ Оформлення замовлення скасовано.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("У головне меню", callback_data="back_to_main")]])
        )
    except Exception as e:
        logger.error(f"Помилка в cancel_order: {str(e)}")

    return ConversationHandler.END

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        buttons = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]

        await query.edit_message_text(
            "ℹ️ <b>Допомога по боту</b>\n\n"
            "Якщо є питання,пишіть сюди➡️ тг-@mimimishak\n",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в show_help: {str(e)}")
        await query.answer("Помилка завантаження довідки")
        raise

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Помилка в back_to_main: {str(e)}")
        await query.answer("Помилка повернення в меню")
        raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Будь ласка, використовуйте кнопки меню")
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Помилка в handle_message: {str(e)}")
        raise

def main():
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_error_handler(error_handler)

        order_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_order, pattern="^order$")],
            states={
                CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_city)],
                POST_OFFICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_post_office)]
            },
            fallbacks=[
                CommandHandler('cancel', cancel_order),
                MessageHandler(filters.COMMAND, cancel_order)
            ]
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(order_conv_handler)

        handlers = [
            CallbackQueryHandler(show_products, pattern="^show_products$"),
            CallbackQueryHandler(show_category, pattern="^category_"),
            CallbackQueryHandler(view_product, pattern="^product_"),
            CallbackQueryHandler(back_to_category, pattern="^back_to_category_"),
            CallbackQueryHandler(add_to_cart, pattern="^add_"),
            CallbackQueryHandler(show_cart, pattern="^show_cart$"),
            CallbackQueryHandler(clear_cart, pattern="^clear_cart$"),
            CallbackQueryHandler(remove_from_cart, pattern="^remove_"),
            CallbackQueryHandler(show_help, pattern="^show_help$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
            CallbackQueryHandler(close_menu, pattern="^close_menu$")
        ]

        for handler in handlers:
            application.add_handler(handler)

        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Бот запускається...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Фатальна помилка при запуску бота: {str(e)}")

if __name__ == "__main__":
    main()