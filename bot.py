import asyncio
import json
import logging
import os
from datetime import datetime

import firebase_admin
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import BaseFilter, CommandStart, Command
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

# --- SOZLAMALAR ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
WEB_APP_URL = os.getenv("WEB_APP_URL")
# Agar kerak bo'lsa, Telegram API_ID va API_HASH ham o'qiladi
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Firebase'ga ulanish
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- BOTNI ISHGA TUSHIRISH ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)


# --- ADMIN FILTRI ---
class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == ADMIN_CHAT_ID


# --- BOT HANDLER'LARI ---

@dp.message(CommandStart())
async def command_start_handler(message: Message):
    """
    /start buyrug'i. Foydalanuvchini Firestore'ga saqlaydi.
    """
    user_ref = db.collection('users').document(str(message.from_user.id))
    user_ref.set({
        'id': str(message.from_user.id),
        'first_name': message.from_user.first_name,
        'last_name': message.from_user.last_name,
        'username': message.from_user.username,
        'last_activity': firestore.SERVER_TIMESTAMP,
        'chat_id': message.from_user.id
    }, merge=True)

    # Telefon raqamini so'rash
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(
        f"Assalomu alaykum, {message.from_user.full_name}! 👋\n\n"
        "🎉 Moda Markazi onlayn do'koniga xush kelibsiz!\n\n"
        "📞 Davom etish uchun telefon raqamingizni yuboring:",
        reply_markup=keyboard
    )


@dp.message(F.contact)
async def contact_handler(message: Message):
    """Telefon raqamni qabul qilish"""
    if message.contact and message.contact.user_id == message.from_user.id:
        # Telefon raqamni saqlash
        user_ref = db.collection('users').document(str(message.from_user.id))
        user_ref.update({
            'phone_number': message.contact.phone_number,
            'contact_shared': True
        })
        
        # Asosiy menu'ni ko'rsatish
        builder = InlineKeyboardBuilder()
        builder.button(text="🛍️ Do'konni ochish", web_app=WebAppInfo(url=WEB_APP_URL))
        builder.button(text="📦 Buyurtmalarim", callback_data="my_orders")
        builder.button(text="👤 Profilim", callback_data="profile")
        builder.button(text="ℹ️ Yordam", callback_data="help")
        
        await message.answer(
            "✅ Telefon raqamingiz qabul qilindi!\n\n"
            "🎉 Endi do'konimizdan foydalanishingiz mumkin.\n\n"
            "Quyidagi tugmalardan birini tanlang:",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer("❌ Faqat o'zingizning telefon raqamingizni yuborishingiz mumkin!")


@dp.message(F.web_app_data)
async def web_app_data_handler(message: Message):
    """
    Mini App'dan kelgan ma'lumotlarni qabul qiladi.
    """
    try:
        data = json.loads(message.web_app_data.data)
        
        # Agar yangi buyurtma bo'lsa, adminga xabar yuborish
        if data.get('type') == 'new_order':
            user_info = data.get('userInfo', {})
            items = data.get('items', [])
            total_price = data.get('totalPrice', 0)
            order_id = data.get('orderId', 'N/A')

            # O'zgaruvchilarni f-stringdan tashqarida e'lon qilish
            default_first_name = user_info.get('first_name', "Noma'lum")
            default_last_name = user_info.get('last_name', '')
            default_username = f"@{user_info.get('username', 'Mavjud emas')}"

            order_details = [
                "<b>✨ Yangi buyurtma!</b>\n",
                f"<b>🆔 Buyurtma ID:</b> <code>{order_id}</code>",
                f"<b>👤 Mijoz:</b> {default_first_name} {default_last_name}",
                f"<b>🆔 Foydalanuvchi ID:</b> <code>{user_info.get('id')}</code>",
                f"<b>✳️ Username:</b> {default_username}\n"
            ]
            
            order_details.append("<b>🛒 Mahsulotlar:</b>")
            for i, item in enumerate(items, 1):
                item_text = (
                    f"{i}. {item['name']} ({item['size']}) - "
                    f"{item['quantity']} dona x {item['price']:,} so'm = "
                    f"{(item['quantity'] * item['price']):,} so'm"
                )
                order_details.append(item_text)
            order_details.append(f"\n<b>💰 Jami summa:</b> {total_price:,} so'm")

            # Admin uchun keyboard
            admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Qabul qilindi", callback_data=f"order_accept_{order_id}"),
                    InlineKeyboardButton(text="❌ Bekor qilindi", callback_data=f"order_reject_{order_id}")
                ],
                [
                    InlineKeyboardButton(text="📞 Mijoz bilan bog'lanish", callback_data=f"contact_user_{user_info.get('id')}")
                ]
            ])

            await bot.send_message(
                chat_id=ADMIN_CHAT_ID, 
                text="\n".join(order_details),
                reply_markup=admin_keyboard
            )
            
            # Mijozga tasdiqlash xabari
            await message.answer(
                "✅ Buyurtmangiz muvaffaqiyatli qabul qilindi!\n\n"
                f"🆔 Buyurtma ID: <code>{order_id}</code>\n"
                f"💰 Jami summa: {total_price:,} so'm\n\n"
                "📞 Buyurtma holati haqida ma'lumot olish uchun @admin_username ga murojaat qiling."
            )
            
    except Exception as e:
        logging.error(f"Web App ma'lumotini o'qishda xatolik: {e}")
        await message.answer("❌ Buyurtma berishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")


# --- CALLBACK HANDLER'LARI ---

@dp.callback_query(F.data == "my_orders")
async def my_orders_handler(callback: types.CallbackQuery):
    try:
        user_id = str(callback.from_user.id)
        orders_ref = db.collection('orders').where('userId', '==', user_id).order_by('createdAt', direction=firestore.Query.DESCENDING)
        orders = list(orders_ref.stream())
        if not orders:
            await callback.message.answer("📦 Hozircha buyurtmalaringiz yo'q.")
            return
        # Ajratish
        yangi = []
        tugatilgan = []
        for order in orders:
            data = order.to_dict()
            if data.get('status') == 'Qabul qilindi':
                tugatilgan.append((order.id, data))
            else:
                yangi.append((order.id, data))
        response = "<b>📦 Mening buyurtmalarim:</b>\n\n"
        if yangi:
            response += "<b>🆕 Yangi buyurtmalar:</b>\n"
            for oid, o in yangi:
                response += f"🆔 <code>{oid}</code> | {o.get('totalPrice', 0):,} so'm | {o.get('status')}\n"
        if tugatilgan:
            response += "\n<b>✅ Tugatilgan/yetkazilgan:</b>\n"
            for oid, o in tugatilgan:
                response += f"🆔 <code>{oid}</code> | {o.get('totalPrice', 0):,} so'm | {o.get('status')}\n"
        await callback.message.answer(response)
    except Exception as e:
        logging.error(f"Buyurtmalarni yuklashda xatolik: {e}")
        await callback.message.answer("❌ Buyurtmalarni yuklashda xatolik yuz berdi.")


@dp.callback_query(F.data == "profile")
async def profile_handler(callback: types.CallbackQuery):
    """Foydalanuvchi profilini ko'rsatish"""
    try:
        user_id = str(callback.from_user.id)
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            
            profile_text = "<b>👤 Mening profilim</b>\n\n"
            profile_text += f"👤 <b>Ism:</b> {user_data.get('first_name', 'N/A')} {user_data.get('last_name', '')}\n"
            profile_text += f"🆔 <b>Foydalanuvchi ID:</b> <code>{user_id}</code>\n"
            
            if user_data.get('username'):
                profile_text += f"✳️ <b>Username:</b> @{user_data.get('username')}\n"
            
            if user_data.get('phone_number'):
                profile_text += f"📞 <b>Telefon:</b> {user_data.get('phone_number')}\n"
            
            # Buyurtmalar soni
            orders_ref = db.collection('orders').where('userId', '==', user_id)
            orders_count = len(list(orders_ref.stream()))
            profile_text += f"📦 <b>Buyurtmalar soni:</b> {orders_count} ta\n"
            
            await callback.message.answer(profile_text)
        else:
            await callback.message.answer("❌ Profil ma'lumotlari topilmadi!")
            
    except Exception as e:
        logging.error(f"Profil yuklashda xatolik: {e}")
        await callback.message.answer("❌ Profil yuklashda xatolik yuz berdi.")


@dp.callback_query(F.data == "help")
async def help_handler(callback: types.CallbackQuery):
    """Yordam ma'lumotlari"""
    help_text = (
        "<b>ℹ️ Yordam</b>\n\n"
        "🛍️ <b>Buyurtma berish:</b>\n"
        "1. 'Do'konni ochish' tugmasini bosing\n"
        "2. O'zingizga mos mahsulotni tanlang\n"
        "3. O'lchamni belgilang\n"
        "4. Savatga qo'shing va buyurtma bering\n\n"
        "📞 <b>Bog'lanish:</b>\n"
        "Savollaringiz bo'lsa @admin_username ga yozing\n\n"
        "💳 <b>To'lov:</b>\n"
        "Buyurtma tasdiqlangandan so'ng to'lov ma'lumotlari yuboriladi"
    )
    await callback.message.answer(help_text)


@dp.callback_query(F.data.startswith("order_"))
async def order_action_handler(callback: types.CallbackQuery):
    """Buyurtma holatini o'zgartirish"""
    is_admin_check = await IsAdmin().__call__(callback.message)
    if not is_admin_check:
        await callback.answer("❌ Bu funksiya faqat admin uchun!", show_alert=True)
        return
    
    data = callback.data
    if data.startswith("order_accept_"):
        order_id = data.replace("order_accept_", "")
        await update_order_status(order_id, "Qabul qilindi", callback)
    elif data.startswith("order_reject_"):
        order_id = data.replace("order_reject_", "")
        await update_order_status(order_id, "Bekor qilindi", callback)
    elif data.startswith("contact_user_"):
        user_id = data.replace("contact_user_", "")
        await contact_user(user_id, callback)


async def update_order_status(order_id: str, status: str, callback: types.CallbackQuery):
    """Buyurtma holatini yangilash"""
    try:
        order_ref = db.collection('orders').document(order_id)
        order_doc = order_ref.get()
        
        if not order_doc.exists:
            await callback.answer("❌ Buyurtma topilmadi!")
            return
        
        order_data = order_doc.to_dict()
        order_ref.update({'status': status})
        
        # Mijozga xabar yuborish
        user_id = order_data.get('userId')
        if user_id:
            status_emoji = "✅" if status == "Qabul qilindi" else "❌"
            await bot.send_message(
                chat_id=user_id,
                text=f"{status_emoji} Buyurtmangiz holati yangilandi!\n\n"
                     f"🆔 Buyurtma ID: <code>{order_id}</code>\n"
                     f"📊 Yangi holat: {status}"
            )
        
        await callback.answer(f"✅ Buyurtma holati '{status}' ga o'zgartirildi!")
        
    except Exception as e:
        logging.error(f"Buyurtma holatini yangilashda xatolik: {e}")
        await callback.answer("❌ Xatolik yuz berdi!")


async def contact_user(user_id: str, callback: types.CallbackQuery):
    """Mijoz bilan bog'lanish"""
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            contact_info = (
                f"👤 <b>Mijoz ma'lumotlari:</b>\n\n"
                f"📝 Ism: {user_data.get('first_name', "Noma'lum")} {user_data.get('last_name', '')}\n"
                f"🆔 Foydalanuvchi ID: <code>{user_id}</code>\n"
                f"✳️ Username: @{user_data.get('username', 'Mavjud emas')}\n"
                f"📞 Chat ID: <code>{user_data.get('chat_id', "Noma'lum")}</code>"
            )
            await callback.message.answer(contact_info)
        else:
            await callback.message.answer("❌ Mijoz ma'lumotlari topilmadi!")
            
    except Exception as e:
        logging.error(f"Mijoz ma'lumotlarini olishda xatolik: {e}")
        await callback.message.answer("❌ Xatolik yuz berdi!")


# --- ADMIN PANEL BO'LIMI ---

@dp.message(Command("admin"), IsAdmin())
async def admin_panel_handler(message: Message):
    """
    Admin paneli.
    """
    try:
        users_count = len(list(db.collection('users').stream()))
        orders_count = len(list(db.collection('orders').stream()))
        products_count = len(list(db.collection('products').stream()))
        
        # Oxirgi 24 soatdagi buyurtmalar
        from datetime import timedelta
        yesterday = datetime.now() - timedelta(days=1)
        recent_orders = list(db.collection('orders').where('createdAt', '>=', yesterday).stream())
        
        admin_text = (
            "<b>🔧 Admin Paneli</b>\n\n"
            f"📊 <b>Statistika:</b>\n"
            f"👥 Foydalanuvchilar: <b>{users_count}</b>\n"
            f"📦 Jami buyurtmalar: <b>{orders_count}</b>\n"
            f"🛍️ Mahsulotlar: <b>{products_count}</b>\n"
            f"📈 Oxirgi 24 soat: <b>{len(recent_orders)}</b> buyurtma\n\n"
            "<b>📋 Buyruqlar:</b>\n"
            "/stats - Batafsil statistika\n"
            "/orders - Oxirgi buyurtmalar\n"
            "/users - Foydalanuvchilar ro'yxati"
        )
        
        await message.answer(admin_text)
        
    except Exception as e:
        logging.error(f"Admin panelida xatolik: {e}")
        await message.answer("❌ Admin panelida xatolik yuz berdi!")


@dp.message(Command("stats"), IsAdmin())
async def stats_handler(message: Message):
    """Batafsil statistika"""
    try:
        users = list(db.collection('users').stream())
        orders = list(db.collection('orders').stream())
        
        total_revenue = sum(order.to_dict().get('totalPrice', 0) for order in orders)
        completed_orders = len([o for o in orders if o.to_dict().get('status') == 'Qabul qilindi'])
        
        stats_text = (
            "<b>📊 Batafsil Statistika</b>\n\n"
            f"💰 Jami daromad: <b>{total_revenue:,} so'm</b>\n"
            f"✅ Bajarilgan buyurtmalar: <b>{completed_orders}</b>\n"
            f"📦 Jami buyurtmalar: <b>{len(orders)}</b>\n"
            f"👥 Faol foydalanuvchilar: <b>{len(users)}</b>\n\n"
            f"📈 O'rtacha buyurtma: <b>{total_revenue // len(orders) if orders else 0:,} so'm</b>"
        )
        
        await message.answer(stats_text)
        
    except Exception as e:
        logging.error(f"Statistikani hisoblashda xatolik: {e}")
        await message.answer("❌ Statistika hisoblashda xatolik!")


@dp.message(Command("orders"), IsAdmin())
async def recent_orders_handler(message: Message):
    """Oxirgi buyurtmalar"""
    try:
        orders = list(db.collection('orders').order_by('createdAt', direction=firestore.Query.DESCENDING).limit(10).stream())
        
        if not orders:
            await message.answer("📦 Hozircha buyurtmalar yo'q.")
            return
        
        orders_text = "<b>📦 Oxirgi 10 ta buyurtma:</b>\n\n"
        for i, order in enumerate(orders, 1):
            order_data = order.to_dict()
            created_at = order_data.get('createdAt')
            date_str = created_at.strftime("%d.%m %H:%M") if created_at else "N/A"
            
            orders_text += (
                f"{i}. <code>{order.id}</code>\n"
                f"   👤 {order_data.get('userInfo', {}).get('first_name', 'N/A')}\n"
                f"   💰 {order_data.get('totalPrice', 0):,} so'm\n"
                f"   📅 {date_str}\n"
                f"   📊 {order_data.get('status', 'Jarayonda')}\n\n"
            )
        
        await message.answer(orders_text)
        
    except Exception as e:
        logging.error(f"Buyurtmalarni olishda xatolik: {e}")
        await message.answer("❌ Buyurtmalarni olishda xatolik!")


@dp.message(Command("buyurtmalar"), IsAdmin())
async def all_orders_handler(message: Message):
    """Barcha buyurtmalar"""
    try:
        orders = list(db.collection('orders').order_by('createdAt', direction=firestore.Query.DESCENDING).stream())
        
        if not orders:
            await message.answer("📦 Hozircha buyurtmalar yo'q.")
            return
        
        orders_per_page = 5
        total_orders = len(orders)
        total_pages = (total_orders + orders_per_page - 1) // orders_per_page
        
        page = 1
        start_idx = (page - 1) * orders_per_page
        end_idx = start_idx + orders_per_page
        page_orders = orders[start_idx:end_idx]
        
        orders_text = f"<b>📦 Barcha buyurtmalar ({total_orders} ta)</b>\n\n"
        
        for i, order in enumerate(page_orders, start_idx + 1):
            order_data = order.to_dict()
            
            # Ma'lumotlarni oldindan o'zgaruvchilarga olib, xatolikni oldini olish
            user_info = order_data.get('userInfo', {})
            first_name = user_info.get('first_name', "Noma'lum")
            last_name = user_info.get('last_name', '')
            username = f"@{user_info.get('username', 'Mavjud emas')}"
            
            created_at = order_data.get('createdAt')
            date_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "N/A"
            
            total_price = order_data.get('totalPrice', 0)
            status = order_data.get('status', 'Jarayonda')

            # Toza o'zgaruvchilarni f-qatorga qo'yish
            orders_text += (
                f"<b>{i}.</b> <code>{order.id}</code>\n"
                f"👤 {first_name} {last_name}\n"
                f"📞 {username}\n"
                f"💰 {total_price:,} so'm\n"
                f"📅 {date_str}\n"
                f"📊 {status}\n\n"
            )
        
        orders_text += f"📄 Sahifa {page}/{total_pages}"
        
        await message.answer(orders_text)
        
    except Exception as e:
        logging.error(f"Buyurtmalarni olishda xatolik: {e}")
        await message.answer("❌ Buyurtmalarni olishda xatolik!")


# --- ASOSIY FUNKSIYA ---
async def main():
    logging.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())