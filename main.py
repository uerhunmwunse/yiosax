import os
import re
import random
import asyncio
import logging
import sqlite3
from re import search
from dotenv import load_dotenv
from typing import Optional, Dict, List
from fuzzywuzzy import process, fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Message
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import requests
from rainforest_api import RainforestAPI
from user_manager import UserManager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())

class PriceTrackerBot:
    def __init__(self):
        os.makedirs("/data", exist_ok=True)
        load_dotenv()
        self.rainforest_api_key = os.getenv("RAINFOREST_API_KEY")
        self.token = os.getenv("TELEGRAM_TOKEN")

        if not self.token or not self.rainforest_api_key:
            raise ValueError("Missing required environment variables")

        self.db_conn = sqlite3.connect("/data/price_tracker.db")
        self.user_manager = UserManager(self.db_conn)
        self.rainforest = RainforestAPI(self.rainforest_api_key)
        self.application = Application.builder().token(self.token).build()

        self._register_handlers()
        self._setup_logging()

    def _setup_logging(self):
        self.logger = logging.getLogger(__name__)
        file_handler = logging.FileHandler("price_tracker.log")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _register_handlers(self):
        handlers = [
            CommandHandler("start", self._handle_start),
            CommandHandler("track", self._start_advanced_tracking),
            CommandHandler("stop", self._handle_stop),
            CommandHandler("list", self._handle_list),
            CommandHandler("help", self._handle_help),
            CallbackQueryHandler(self._handle_confirmation),
            CommandHandler("cancel", self._handle_cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message),
            MessageHandler(filters.COMMAND, self._handle_unknown_command)
        ]

        for handler in handlers:
            self.application.add_handler(handler)
        self.application.add_error_handler(self._handle_error)

    async def _handle_unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❓ Sorry, I didn't recognize that command.\n"
            "Type /help to see what I can do."
        )

    def _parse_price(self, price_str):
        if price_str:
            try:
                return float(price_str.replace("$", "").replace(",", "").strip())
            except Exception:
                return None
        return None

    def escape_markdown(self, text: str) -> str:
        escape_chars = r'\_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

    async def _show_track_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🔍 How to track products:\n\n"
            "1. Basic tracking:\n"
            "   /track \"Product Name\" TargetPrice\n"
            "   Example: /track \"PlayStation 5\" 499.99\n\n"
            "2. Advanced tracking:\n"
            "   /track advanced\n"
            "   Guided search with filters\n\n"
            "3. Cancel: Type /cancel anytime"
        )
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(3)
        await update.message.reply_text(help_text)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_first_name = update.effective_user.first_name
        await asyncio.sleep(1.5)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await update.message.reply_text(
            f"👋 Hey {user_first_name}, I’m *Yiosax* — your personal deal hunter! \n"
            f"I’ll keep an eye out and alert you when your tracked product drops to your target price.\n"
            f"Let’s find you the best deal 💸🔍",
            parse_mode="Markdown"
        )
        await asyncio.sleep(1.5)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await update.message.reply_text(
            "👉 To get started, type /track to begin tracking a product.\n"
            "Need assistance? Type /help to see what I can do!"
        )

    async def _start_advanced_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1)
        await self._ask_for_category(update, context)

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stage = context.user_data.get('tracking_stage')
        if stage == 'awaiting_category':
            context.user_data['category'] = update.message.text
            user_input = update.message.text.strip()
            if user_input == "Phones":
                await asyncio.sleep(1.5)
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await update.message.reply_text(
                    "📱 Got it! Now please enter the exact name or series of the phone you'd like to track.\n"
                    "For example: iPhone 14, Galaxy S23, Pixel 8 Pro"
                )
                context.user_data['tracking_stage'] = 'awaiting_mobile_name'
            elif user_input == "Headphones":
                await self._handle_unimplemented_category(user_input, update, context)
            elif user_input == "Laptops":
                await self._ask_for_laptop_manufacturer(update, context)
            elif user_input == "TVs":
                await self._handle_unimplemented_category(user_input, update, context)
            elif user_input == "Cameras":
                await self._handle_unimplemented_category(user_input, update, context)
            elif user_input == "Gaming":
                await asyncio.sleep(1.5)
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await update.message.reply_text(
                    "Awesome! 🎮 Now tell me which gaming console you're looking to track.\n\n"
                    "For example: PlayStation 5, Xbox Series X, Nintendo Switch OLED"
                )
                context.user_data['tracking_stage'] = 'awaiting_console_name'
            # elif user_input == "Cancel Operation":
            #     self._handle_cancel(update, context)
            else:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(2)
                await update.message.reply_text(
                    "❌ That category isn’t recognized.\n"
                    "Please choose from the list of available categories below or type `/cancel` to exit.",
                    reply_markup=ReplyKeyboardMarkup(
                        [["Phones", "Headphones", "Laptops"],
                         ["TVs", "Cameras", "Gaming"]],
                        resize_keyboard=True,
                        one_time_keyboard=True
                    )
                )
        elif stage == "awaiting_mobile_name":
            context.user_data['product_name'] = update.message.text
            await self._ask_for_mobile_manufacturer(update, context)
        elif stage == 'awaiting_mobile_manufacturer':
            context.user_data["mobile_manufacturer_name"] = update.message.text
            await self._ask_for_mobile_model(update, context)
        elif stage == 'awaiting_mobile_model':
            context.user_data['model_name'] = update.message.text
            await self._ask_for_mobile_storage(update, context)
        elif stage == 'awaiting_mobile_storage':
            context.user_data["mobile_storage"] = update.message.text
            await self._ask_for_mobile_price(update, context)
        elif stage == 'awaiting_laptop_manufacturer':
            context.user_data["laptop_manufacturer_name"] = update.message.text
            await self._ask_for_laptop_model(update, context)
        elif stage == 'awaiting_laptop_model':
            context.user_data['product_name'] = update.message.text
            await self._ask_for_ram(update, context)
        elif stage == 'awaiting_laptop_ram':
            context.user_data["laptop_ram"] = update.message.text
            await self._ask_for_laptop_storage(update, context)
        elif stage == 'awaiting_laptop_storage':
            context.user_data["laptop_storage"] = update.message.text
            await self._ask_for_processor(update, context)
        elif stage == "awaiting_laptop_processor":
            context.user_data["laptop_processor"] = update.message.text
            await self._ask_for_laptop_price(update, context)
        elif stage == 'awaiting_console_name':
            context.user_data['product_name'] = update.message.text
            await self._ask_for_console_manufacturer(update, context)
        elif stage == 'awaiting_console_manufacturer':
            context.user_data['gaming_manufacturer_name'] = update.message.text
            await self._ask_for_console_price(update, context)
        elif stage == 'awaiting_console_price':
            try:
                target_price = float(update.message.text)
                context.user_data['console_target_price'] = target_price
                await self._confirm_console_product_search(update, context, context.user_data['category'],
                                                          context.user_data['product_name'],
                                                          context.user_data["gaming_manufacturer_name"],
                                                          context.user_data['console_target_price']
                                                          )
            except ValueError:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text("❌ Invalid price! Please enter a valid number:")
        elif stage == 'awaiting_mobile_price':
            try:
                target_price = float(update.message.text)
                context.user_data['mobile_target_price'] = target_price
                await self._confirm_mobile_product_search(update, context, context.user_data['category'],
                                                          context.user_data['product_name'],
                                                          context.user_data["mobile_manufacturer_name"],
                                                          context.user_data["model_name"],
                                                          context.user_data["mobile_storage"],
                                                          context.user_data['mobile_target_price']
                                                          )
            except ValueError:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text("❌ Invalid price! Please enter a valid number:")
        elif stage == 'awaiting_laptop_price':
            try:
                target_price1 = float(update.message.text)
                context.user_data['laptop_target_price'] = target_price1
                await self._confirm_laptop_product_search(update, context,
                                                          context.user_data['category'],
                                                          context.user_data['product_name'],
                                                          context.user_data["laptop_manufacturer_name"],
                                                          context.user_data["laptop_ram"],
                                                          context.user_data["laptop_storage"],
                                                          context.user_data["laptop_processor"],
                                                          context.user_data["laptop_target_price"]
                                                          )
            except ValueError:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text("❌ Invalid price! Please enter a valid number:")
        elif stage == 'awaiting_price':
            try:
                target_price = float(update.message.text)
                context.user_data['target_price'] = target_price
                await self._confirm_product_search(update, context,
                                                   context.user_data['product_name'],
                                                   context.user_data.get('category'))
            except ValueError:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text("❌ Invalid price! Please enter a valid number \n"
                                                "don't include $!!:")
        else:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(2)
            await update.message.reply_text(
                "Hmm I'm not sure I understand .\n\n"
                "You can try `/help` to see available commands"
            )
            # await self._handle_help(update, context)

    async def _ask_for_mobile_manufacturer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        choose = [["Skip Manufacturer"]]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "Please enter the name of the manufacturer\n"
            " (e.g., Samsung, Apple, Sony):",
            reply_markup=ReplyKeyboardMarkup(
                choose,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_mobile_manufacturer'

    async def _ask_for_console_manufacturer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        choose = [["Skip Manufacturer"]]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "Who is the manufacturer of the console you're looking for?\n"
            "(e.g., Sony, Microsoft, Nintendo):",
            reply_markup=ReplyKeyboardMarkup(
                choose,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_console_manufacturer'

    async def _ask_for_laptop_manufacturer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        choose = [["Skip Manufacturer"]]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "Who is the manufacturer of the Laptop you're looking for?\n"
            "(e.g., HP, Dell, Apple, Lenovo):",
            reply_markup=ReplyKeyboardMarkup(
                choose,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_laptop_manufacturer'

    async def _ask_for_laptop_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "💻 Awesome! Now, please type the laptop name or series you want to track."
            "\n\nFor example: Legion 7, MacBook Air, Dell XPS 15"
        )
        context.user_data['tracking_stage'] = 'awaiting_laptop_model'

    async def _ask_for_ram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        rams = [
            ["8 GB", "12 GB", "16 GB"],
            ["32 GB", "64 GB", "128 GB"],
            ["Skip RAM"]
        ]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "How much RAM do you want?",
            reply_markup=ReplyKeyboardMarkup(
                rams,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_laptop_ram'

    async def _ask_for_processor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        processor_options = [
            ["Intel Celeron", "Intel Pentium"],
            ["Intel Core i3", "Intel Core i5"],
            ["Intel Core i7", "Intel Core i9"],
            ["AMD Athlon", "AMD A-Series"],
            ["AMD Ryzen 3", "AMD Ryzen 5"],
            ["AMD Ryzen 7", "AMD Ryzen 9"],
            ["Apple M1", "Apple M2", "Apple M3"],
            ["Skip Processor"]
        ]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "Please choose a processor type that applies to your laptop search:",
            reply_markup=ReplyKeyboardMarkup(
                processor_options,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data["tracking_stage"] = "awaiting_laptop_processor"

    async def _ask_for_mobile_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        model_keywords = [
            ["Pro Max", "Pro", "Ultra"],
            ["Plus", "Max", "Mini"],
            ["5G", "Fold", "Flip"],
            ["Note", "Edge", "FE"],
            ["Gaming", "Lite", "SE"],
            ["Skip Model"]
        ]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "Choose a common model keyword to help narrow your search or enter model that applies:\n",
            reply_markup=ReplyKeyboardMarkup(
                model_keywords,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_mobile_model'

    async def _ask_for_mobile_storage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        storages = [
            ["32 GB", "64 GB", "128 GB"],
            ["256 GB", "512 GB", "1 TB"],
            ["Skip Storage"]
        ]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "Enter Storage capacity that applies:\n",
            reply_markup=ReplyKeyboardMarkup(
                storages,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_mobile_storage'

    async def _ask_for_laptop_storage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        storage_options = [
            ["128 GB SSD", "256 GB SSD", "512 GB SSD"],
            ["1 TB SSD", "2 TB SSD", "4 TB SSD"],
            ["500 GB HDD", "1 TB HDD", "2 TB HDD"],
            ["256 GB SSD + 1 TB HDD", "512 GB SSD + 1 TB HDD"],
            ["Skip Storage"]
        ]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "please select the storage option that applies to your search:",
            reply_markup=ReplyKeyboardMarkup(
                storage_options,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_laptop_storage'

    async def _ask_for_headphones_manufacturer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Who makes the headphones you're looking for?\n"
            "(e.g., Sony, Bose, Apple, JBL, Beats)"
        )
        context.user_data['tracking_stage'] = 'awaiting_headphones_manufacturer'

    async def _ask_for_headphones_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Enter the headphone model you're looking for\n"
            "(e.g., WH-1000XM5, AirPods Pro).\n"
            "I'll try to match it with known models and offer suggestions if needed."
        )
        context.user_data['tracking_stage'] = 'awaiting_headphones_model'

    async def _handle_headphone_model_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = update.message.text.strip()
        normalized_input = normalize(user_input)
        known_models = [
            "WH-1000XM5", "WH-1000XM4", "WH-CH520", "WH-XB910N", "WH-RF400", "WF-1000XM5", "WF-1000XM4",
            "WH-CH720N", "WF-C700N", "WF-C510", "MDR-ZX110", "QuietComfort 45", "QuietComfort Ultra", "Bose 700",
            "SoundLink II", "QuietComfort Earbuds II", "Ultra Open-Ear", "Studio3 Wireless", "Solo3 Wireless", "Solo4",
            "Powerbeats Pro", "Beats Fit Pro", "Studio Buds", "Solo Buds", "AirPods 2nd Gen", "AirPods 3rd Gen",
            "AirPods Pro 2nd Gen", "AirPods Max", "AirPods 4", "AirPods Max USB-C", "Momentum 4 Wireless",
            "Momentum True Wireless 3", "Momentum Sport", "HD 660S", "HD 569", "HD 600", "HD 560S", "Accentum Over-Ear",
            "Accentum Plus", "RS 175", "IE 200", "Momentum True Wireless 4", "Tune 510BT", "Tune 520BT", "Tune 670NC",
            "Tune 770NC", "Live 460NC", "Live 660NC", "Vibe Flex", "T110", "Endurance Race", "Hesh 2 Wireless",
            "Crusher Evo", "Grind Fuel", "Smokin Buds", "Hesh Evo", "Life Q20", "Life Q30", "Space One", "Aerofit 2",
            "Life Dot 3i", "JBuds Lux", "Go Air Pop", "Flex Open-Ear", "Major IV", "Monitor II ANC", "OpenRun Pro",
            "OpenRun Pro 2", "OpenMove", "HA-S31M", "HA-A10T", "G733 LIGHTSPEED", "Astro A50", "Astro A40 TR",
            "Galaxy Buds FE", "Galaxy Buds3", "Galaxy Buds3 Pro", "Elite 10 Gen 2", "Elite 4", "HS80 Max",
            "Virtuoso RGB Wireless XT", "Kraken V3 X", "Stealth Pro", "ROG Delta", "Achieve 100 Airlinks", "Dobuds ONE"
        ]
        normalized_models = {normalize(m): m for m in known_models}
        match = process.extractOne(normalized_input, list(normalized_models.keys()))
        if match:
            normalized_match, score = match
            original_model = normalized_models[normalized_match]
            if score >= 85:
                context.user_data["suggested_model"] = original_model
                context.user_data["tracking_stage"] = "confirm_headphones_model"
                await update.message.reply_text(
                    f"🔍 Did you mean: *{original_model}*?\n\n"
                    "Reply with 'yes' to confirm or type the correct model name.",
                    parse_mode="Markdown"
                )
            else:
                suggestions = process.extract(normalized_input, list(normalized_models.keys()), limit=3)
                readable_suggestions = [normalized_models[s[0]] for s in suggestions]
                suggestion_text = "\n".join(f"• {s}" for s in readable_suggestions)
                await update.message.reply_text(
                    f"❌ Couldn't confidently match your input.\n"
                    f"Did you mean:\n{suggestion_text}\n\n"
                    "Please type one of the options or try again."
                )

    async def _confirm_headphones_model_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_reply = update.message.text.strip().lower()
        if user_reply == "yes":
            model_name = context.user_data.get("suggested_model")
            context.user_data["headphones_model"] = model_name
            await update.message.reply_text(
                f"✅ Great! Proceeding with *{model_name}*.",
                parse_mode="Markdown"
            )
            context.user_data["tracking_stage"] = "awaiting_price"
            await self._ask_for_price(update, context)
        else:
            await update.message.reply_text(
                "❌ Okay! Please type the correct model name you'd like to track."
            )
            context.user_data["tracking_stage"] = "awaiting_headphones_model"

    async def _ask_for_laptop_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        randint = random.randint(800, 1000)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "💵 Enter your target price:\n"
            f"Example: {randint}.99"
        )
        context.user_data['tracking_stage'] = 'awaiting_laptop_price'

    async def _ask_for_console_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        randint = random.randint(450, 900)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "💵 Enter your target price:\n"
            f"Example: {randint}.99"
        )
        context.user_data['tracking_stage'] = 'awaiting_console_price'

    async def _ask_for_mobile_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        randint = random.randint(450, 900)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "💵 Enter your target price:\n"
            f"Example: {randint}.99"
        )
        context.user_data['tracking_stage'] = 'awaiting_mobile_price'

    async def _ask_for_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        categories = [
            ["Phones", "Gaming", "Laptops"],
            ["TVs", "Cameras", "Headphones"]
        ]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1.2)
        await update.message.reply_text(
            "🎯 Let's set up tracking!\n\n"
            "First, please choose the category of the product you want to track:",
            reply_markup=ReplyKeyboardMarkup(
                categories,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        context.user_data['tracking_stage'] = 'awaiting_category'

    async def _handle_unimplemented_category(self, user_input, update: Update, context: ContextTypes.DEFAULT_TYPE):
        randint = random.randint(0, 3)
        friendly_responses = [
            f"Oops! I’m not tracking products in the *{user_input}* category just yet.",
            f"Thanks for your interest in *{user_input}* — I'm working on adding support for that soon!",
            f"*{user_input}* is not available at the moment, but it's on my radar!",
            f"I'm not tracking *{user_input}* yet, but stay tuned — it's coming!"
        ]
        support_note = "\n\nIf you like this bot and want to support what I do, you can [buy me a coffee](https://buymeacoffee.com/yiosa)."
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(3)
        await update.message.reply_text(friendly_responses[randint] + support_note)
        await self._ask_for_category(update, context)

    async def _confirm_console_product_search(self, update, context, category, product_name, manufacturer, target):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🔍 Searching for the best match...")
        results, search_query = self.rainforest._search_console_product(category, product_name, manufacturer)
        if not results:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(2)
            await update.message.reply_text(
                f"❌ No matching products found for *{product_name}*.\n\n"
                "Please double-check the spelling, make sure it's a real product name, "
                "and try again with more accurate details.\n\n"
                "I can only search for *real products* that exist in the system."
                "\n\nExample: 'iPhone 14 Pro Max 256GB', not just 'iPhone 14'.\n\n"
                "Let me know when you're ready to try again!",
                parse_mode="Markdown"
            )
            await self._handle_cancel(update, context)
            await self._start_advanced_tracking(update, context)
            return
        else:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            await asyncio.sleep(1.5)
            selected_product = results[0]
            found_product_name = selected_product.get("title")
            escaped_name = self.escape_markdown(found_product_name)
            price = self._parse_price(selected_product.get("price", {}).get("raw"))
            image_url = selected_product.get("image")
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
                    InlineKeyboardButton("❌ Cancel Search", callback_data="cancel_search")
                ]
            ])
            caption = (
                f"🛒 *Product:* {escaped_name}\n"
                f"💰 *Current Price:* {self.escape_markdown(f'${price}')}\n\n"
                "✅ *I'll use these details to track this item\\.*\n"
                "❌ *If this is NOT the product you meant, click below or type* `/cancel` *to stop\\.*"
            )
            if image_url:
                try:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
                    await asyncio.sleep(2)
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        parse_mode="MarkdownV2",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                    await asyncio.sleep(1)
                    await update.message.reply_text(
                        f"✅ *Found:* {found_product_name}\n"
                        f"💰 *Price:* ${price}\n"
                        "✅ *Tracking will start.*\n"
                        "❌ *If this is not correct, type* `/cancel`.",
                        parse_mode="MarkdownV2"
                    )
            else:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text(
                    f"✅ *Found:* {found_product_name}\n"
                    f"💰 *Current Price:* {self.escape_markdown(f'${price}')}\n\n"
                    "✅ *Tracking will start.*\n"
                    "❌ *If this is not correct, type* `/cancel`.",
                    parse_mode="MarkdownV2"
                )
            context.user_data["search_query"] = search_query
            context.user_data["tracking_stage"] = "end_conversation"

    async def _confirm_laptop_product_search(self, update, context, category, product_name, manufacturer, ram, storage,
                                             processor, target_price):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🔍 Searching for the best match...")
        results, search_query = self.rainforest._search_laptop_product(category, product_name, manufacturer,
                                                                       ram, storage, processor, target_price)
        if not results:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(2)
            await update.message.reply_text(
                f"❌ No matching products found for *{product_name}*.\n\n"
                "Please double-check the spelling, make sure it's a real product name, "
                "and try again with more accurate details.\n\n"
                "I can only search for *real products* that exist in the system."
                "\n\nExample: 'iPhone 14 Pro Max 256GB', not just 'iPhone 14'.\n\n"
                "Let me know when you're ready to try again!",
                parse_mode="Markdown"
            )
            await self._handle_cancel(update, context)
            await self._start_advanced_tracking(update, context)
            return
        else:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            await asyncio.sleep(1.5)
            selected_product = results[0]
            found_product_name = selected_product.get("title")
            escaped_name = self.escape_markdown(found_product_name)
            price = self._parse_price(selected_product.get("price", {}).get("raw"))
            image_url = selected_product.get("image")
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
                    InlineKeyboardButton("❌ Cancel Search", callback_data="cancel_search")
                ]
            ])
            caption = (
                f"🛒 *Product:* {escaped_name}\n"
                f"💰 *Current Price:* {self.escape_markdown(f'${price}')}\n\n"
                "✅ *I'll use these details to track this item\\.*\n"
                "❌ *If this is NOT the product you meant, click below or type* `/cancel` *to stop\\.*"
            )
            if image_url:
                try:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
                    await asyncio.sleep(2)
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        parse_mode="MarkdownV2",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                    await asyncio.sleep(1)
                    await update.message.reply_text(
                        f"✅ *Found:* {found_product_name}\n"
                        f"💰 *Price:* ${price}\n"
                        "✅ *Tracking will start.*\n"
                        "❌ *If this is not correct, type* `/cancel`.",
                        parse_mode="MarkdownV2"
                    )
            else:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text(
                    f"✅ *Found:* {found_product_name}\n"
                    f"💰 *Current Price:* {self.escape_markdown(f'${price}')}\n\n"
                    "✅ *Tracking will start.*\n"
                    "❌ *If this is not correct, type* `/cancel`.",
                    parse_mode="MarkdownV2"
                )
            context.user_data["search_query"] = search_query
            context.user_data["tracking_stage"] = "end_conversation"

    async def _confirm_mobile_product_search(self, update, context, category, product_name, manufacturer, model_name,
                                             storage, target_price):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🔍 Searching for the best match...")
        results, search_query = self.rainforest._search_mobile_product(
            category, product_name, manufacturer, model_name, storage, target_price)
        if not results:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(2)
            await update.message.reply_text(
                f"❌ No matching products found for *{product_name}*.\n\n"
                "Please double-check the spelling, make sure it's a real product name, "
                "and try again with more accurate details.\n\n"
                "I can only search for *real products* that exist in the system."
                "\n\nExample: 'iPhone 14 Pro Max 256GB', not just 'iPhone 14'.\n\n"
                "Let me know when you're ready to try again!",
                parse_mode="Markdown"
            )
            await self._handle_cancel(update, context)
            await self._start_advanced_tracking(update, context)
            return
        else:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            await asyncio.sleep(1.5)
            selected_product = results[0]
            found_product_name = selected_product.get("title")
            escaped_name = self.escape_markdown(found_product_name)
            price = self._parse_price(selected_product.get("price", {}).get("raw"))
            image_url = selected_product.get("image")
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
                    InlineKeyboardButton("❌ Cancel Search", callback_data="cancel_search")
                ]
            ])
            caption = (
                f"🛒 *Product:* {escaped_name}\n"
                f"💰 *Current Price:* {self.escape_markdown(f'${price}')}\n\n"
                "✅ *I'll use these details to track this item\\.*\n"
                "❌ *If this is NOT the product you meant, click below or type* `/cancel` *to stop\\.*"
            )
            if image_url:
                try:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
                    await asyncio.sleep(2)
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        parse_mode="MarkdownV2",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                    await asyncio.sleep(1)
                    await update.message.reply_text(
                        f"✅ *Found:* {found_product_name}\n"
                        f"💰 *Price:* ${price}\n"
                        "✅ *Tracking will start.*\n"
                        "❌ *If this is not correct, type* `/cancel`.",
                        parse_mode="MarkdownV2"
                    )
            else:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(1.2)
                await update.message.reply_text(
                    f"✅ *Found:* {found_product_name}\n"
                    f"💰 *Current Price:* {self.escape_markdown(f'${price}')}\n\n"
                    "✅ *Tracking will start.*\n"
                    "❌ *If this is not correct, type* `/cancel`.",
                    parse_mode="MarkdownV2"
                )
            context.user_data["search_query"] = search_query
            context.user_data["tracking_stage"] = "end_conversation"

    async def _handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
        await query.answer()
        user_id = query.from_user.id
        if query.data == "cancel_search":
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(1)
            await context.bot.send_message(chat_id=user_id, text="❌ Cancelled current operation")
            return
        if query.data == "confirm":
            await self._save_advanced_tracking(update, context)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(2)
            await context.bot.send_message(chat_id=user_id, text="✅ Product confirmed and tracking started.")

    async def _handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        args = context.args
        if not args:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(1)
            await update.message.reply_text("❌ Please specify a product to stop tracking")
            return
        product_name = " ".join(args)
        success = self.user_manager.remove_tracking(user_id, product_name)
        if success:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(1)
            await update.message.reply_text(f"✅ Stopped tracking {product_name}")
        else:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(1)
            await update.message.reply_text(f"❌ Not tracking {product_name}")

    async def _handle_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        tracked_items = self.user_manager.get_tracked_items(user_id)
        if not tracked_items:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(1)
            await update.message.reply_text("You're not tracking any products yet!")
            return
        response = "📋 Currently Tracking:\n" + "\n\n".join(
            [f"- {item['name']} (Target: ${item['target_price']})"
             for item in tracked_items])
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(2)
        await update.message.reply_text(response)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "💡 *Help Menu — What I Can Do*\n\n"
            "Here are the main commands you can use:\n\n"
            "• `/track` – Start tracking a new product 📦. I’ll guide you step-by-step to set your target price and notify you when I find a match!\n\n"
            "• `/list` – View all the products you're currently tracking 🧾.\n\n"
            "• `/stop [product name]` – Stop tracking a product from your list ❌\n"
            "   _Example: `/stop iPhone 14 Pro Max`_\n\n"
            "• `/help` – Show this help menu anytime you need it 🤖.\n\n"
            "• `/cancel` – Cancel the current tracking setup process ⛔."
        )
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(2.5)
        await update.message.reply_text(help_text)

    async def _handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.logger.error(f"Update {update} caused error: {context.error}")

    async def _start_price_checks(self):
        while True:
            try:
                await self._check_all_prices()
            except Exception as e:
                self.logger.error(f"Price check failed: {str(e)}")
            await asyncio.sleep(3600)

    def _clean_mobile_text(self, text):
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
        text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
        return re.sub(r'\s+', ' ', text).strip()

    def intended_mobile_product(self, search_query, title):
        match_threshold = 0.9
        if not search_query or not title:
            return False
        cleaned_query = self._clean_mobile_text(search_query)
        cleaned_title = self._clean_mobile_text(title)
        query_words = cleaned_query.split()
        if not query_words:
            return False
        match_count = 0
        for word in query_words:
            safe_word = re.escape(word)
            pattern = rf'\b{safe_word}\b'
            if re.search(pattern, cleaned_title):
                match_count += 1
        match_ratio = match_count / len(query_words)
        return match_ratio >= match_threshold

    def _clean_laptop_product_text(self, text):
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
        text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
        return re.sub(r'\s+', ' ', text).strip()

    def intended_laptop_product(self, search_query, title):
        if not search_query or not title:
            return False
        cleaned_query = self._clean_laptop_product_text(search_query)
        cleaned_title = self._clean_laptop_product_text(title)
        query_words = cleaned_query.split()
        if not query_words:
            return False
        match_count = 0
        match_threshold = 0.9
        for word in query_words:
            safe_word = re.escape(word)
            pattern = rf'\b{safe_word}\b'
            if re.search(pattern, cleaned_title):
                match_count += 1
        match_ratio = match_count / len(query_words)
        return match_ratio >= match_threshold

    def _clean_product_text(self, text):
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
        text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
        return re.sub(r'\s+', ' ', text).strip()

    def intended_gaming_product(self, search_query, title):
        if not search_query or not title:
            return False
        cleaned_query = self._clean_product_text(search_query)
        cleaned_title = self._clean_product_text(title)
        query_words = cleaned_query.split()
        if len(query_words) == 1:
            pattern = rf'\b{re.escape(query_words[0])}\b'
            return bool(re.search(pattern, cleaned_title))
        match_count = 0
        match_threshold = 0.9
        for word in query_words:
            safe_word = re.escape(word)
            pattern = rf'\b{safe_word}\b'
            if word in ['limited', 'special', 'collectors', 'edition', 'bundle']:
                continue
            if re.search(pattern, cleaned_title):
                match_count += 1
        base_words = [w for w in query_words if w not in
                      ['limited', 'special', 'collectors', 'edition', 'bundle']]
        if not base_words:
            return False
        match_ratio = match_count / len(base_words)
        return match_ratio >= match_threshold

    # def intended_gaming_product(self, search_query, title):
    #     if not search_query or not title:
    #         return False
    #
    #     cleaned_query = self._clean_product_text(search_query)
    #     cleaned_title = self._clean_product_text(title)
    #
    #     # NEW: Strict accessory blocking layer
    #     if self._is_accessory(cleaned_title):
    #         return False
    #
    #     # ORIGINAL MATCHING ALGORITHM (unchanged)
    #     query_words = cleaned_query.split()
    #     if len(query_words) == 1:
    #         pattern = rf'\b{re.escape(query_words[0])}\b'
    #         return bool(re.search(pattern, cleaned_title))
    #
    #     match_count = 0
    #     match_threshold = 0.9
    #     for word in query_words:
    #         safe_word = re.escape(word)
    #         pattern = rf'\b{safe_word}\b'
    #         if word in ['limited', 'special', 'collectors', 'edition', 'bundle']:
    #             continue
    #         if re.search(pattern, cleaned_title):
    #             match_count += 1
    #
    #     base_words = [w for w in query_words if w not in
    #                   ['limited', 'special', 'collectors', 'edition', 'bundle']]
    #     if not base_words:
    #         return False
    #
    #     match_ratio = match_count / len(base_words)
    #     return match_ratio >= match_threshold
    #
    # # NEW ACCESSORY DETECTION METHOD
    # def _is_accessory(self, cleaned_title):
    #     """Determine if title is an accessory (cord, case, etc.)"""
    #     # Block based on product type indicators
    #     accessory_types = {
    #         'cord', 'cable', 'wire', 'charger', 'adapter', 'case', 'cover',
    #         'skin', 'protector', 'stand', 'mount', 'dock', 'grip', 'holder',
    #         'remote', 'battery', 'power bank', 'stylus', 'pen', 'controller',
    #         'headset', 'earbud', 'headphone', 'keyboard', 'mouse', 'mat'
    #     }
    #
    #     # Block based on size/package indicators
    #     size_indicators = {
    #         'pack', 'set', 'kit', 'bundle', '2 pack', '3 pack', '4 pack',
    #         'multi pack', 'twin pack', 'value pack', 'combo'
    #     }
    #
    #     # Block based on material/color focus
    #     material_focus = {
    #         'silicone', 'rubber', 'plastic', 'metal', 'fabric', 'leather',
    #         'nylon', 'carbon fiber', 'transparent', 'clear', 'colorful'
    #     }
    #
    #     # Block if any accessory indicator is present
    #     return (any(acc in cleaned_title for acc in accessory_types) or
    #             any(size in cleaned_title for size in size_indicators) or
    #             any(mat in cleaned_title for mat in material_focus))
    #
    # # ENHANCED CLEANING METHOD
    # def _clean_product_text(self, text):
    #     """Improved cleaning with accessory detection enhancements"""
    #     if not text:
    #         return ""
    #     text = text.lower()
    #
    #     # Remove common accessory phrases that might be embedded in titles
    #     accessory_phrases = [
    #         "charging cable", "usb cable", "controller charger",
    #         "protective case", "screen protector", "gaming headset",
    #         "remote control", "battery pack", "skin decal"
    #     ]
    #     for phrase in accessory_phrases:
    #         text = text.replace(phrase, "")
    #
    #     # Standard cleaning
    #     text = re.sub(r'[^a-z0-9\s]', ' ', text)
    #     text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
    #     text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
    #     return re.sub(r'\s+', ' ', text).strip()


    async def _check_all_prices(self):
        trackings = self.user_manager.get_all_trackings()
        if not trackings:
            return

        alerts_to_send = []
        products_to_remove = []

        for tracking in trackings:
            search_query = tracking['product_data'].get("search_query").lower()
            category = tracking['product_data'].get("category")
            target_price = tracking['target_price']
            user_id = tracking['user_id']
            intended_title = tracking["product_name"].lower()
            original_product_name = tracking["product_name"]  # Keep original name for removal

            results = self.rainforest.track_product(search_query, target_price, category)

            if category == "Phones":
                if results:
                    for item in results:
                        title = item.get("title", "").lower()
                        if self.intended_laptop_product(search_query, title):
                            current_price = item.get("price")
                            if isinstance(current_price, dict):
                                current_price = current_price.get("value")

                            # Collect alert instead of sending immediately
                            alerts_to_send.append({
                                'user_id': user_id,
                                'product_name': item.get("title"),
                                'current_price': current_price,
                                'target_price': target_price,
                                'url': item.get("link", ""),
                                'original_name': original_product_name
                            })
                else:
                    print(f"❌ Target not met for: {search_query}")

            elif category == "Laptops":
                if results:
                    for item in results:
                        title = item.get("title", "").lower()
                        if self.intended_laptop_product(search_query, title):
                            current_price = item.get("price")
                            if isinstance(current_price, dict):
                                current_price = current_price.get("value")

                            # Collect alert instead of sending immediately
                            alerts_to_send.append({
                                'user_id': user_id,
                                'product_name': item.get("title"),
                                'current_price': current_price,
                                'target_price': target_price,
                                'url': item.get("link", ""),
                                'original_name': original_product_name
                            })
            elif category == "Gaming":
                if results:
                    for item in results:
                        title = item.get("title", "").lower()
                        print(search_query)
                        print(title)
                        if self.intended_gaming_product(search_query, title):
                            current_price = item.get("price")
                            if isinstance(current_price, dict):
                                current_price = current_price.get("value")

                            alerts_to_send.append({
                                'user_id': user_id,
                                'product_name': item.get("title"),
                                'current_price': current_price,
                                'target_price': target_price,
                                'url': item.get("link", ""),
                                'original_name': original_product_name})
            else:
                print(f"❌ Target not met for: {search_query}")

        # Send all collected alerts first
        for alert in alerts_to_send:
            await self._send_price_alert(
                alert['user_id'],
                alert['product_name'],
                alert['current_price'],
                alert['target_price'],
                alert['url']
            )

            products_to_remove.append((alert['user_id'], alert['original_name']))


        for user_id, product_name in products_to_remove:
            if self.user_manager.remove_tracking(user_id, product_name):

                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ We found a deal for {product_name} and have stopped tracking it. "
                         "You can track it again anytime with /track."
                )

    async def _send_price_alert(self, user_id: int, product_name: str,
                                current_price: float, target_price: float, url: str):
        message = (
            f"🚨 Price Alert: {product_name}\n\n"
            f"💰 Price Found: ${current_price}\n"
            f"🎯 Your Target: ${target_price}\n"
            f"🔗 {url}"
        )
        await self.application.bot.send_message(
            chat_id=user_id,
            text=message
        )

    async def _handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1)
        await update.message.reply_text("❌ Cancelled current operation")

    async def run(self):
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        asyncio.create_task(self._start_price_checks())
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await self.application.stop()
            await self.application.shutdown()

    async def _save_advanced_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        product_name = context.user_data.get("product_name")
        target_price = context.user_data.get("mobile_target_price") or context.user_data.get(
            "laptop_target_price") or context.user_data.get("target_price") or context.user_data.get("console_target_price")
        product_data = {
            "category": context.user_data.get("category"),
            "manufacturer": context.user_data.get("mobile_manufacturer_name") or context.user_data.get(
                "laptop_manufacture_name") or context.user_data.get("gaming_manufacturer_name"),
            "model_name": context.user_data.get("model_name") or context.user_data.get(
                "laptop_model_name") or context.user_data.get("headphones_model"),
            "storage": context.user_data.get("mobile_storage") or context.user_data.get("laptop_storage"),
            "ram": context.user_data.get("laptop_ram"),
            "processor": context.user_data.get("laptop_processor"),
            "search_query": context.user_data.get("search_query")
        }
        product_data = {k: v for k, v in product_data.items() if v is not None}
        self.user_manager.add_tracking(
            user_id=user_id,
            product_name=product_name,
            target_price=target_price,
            sku="",
            product_data=product_data
        )


if __name__ == "__main__":
    import asyncio
    # load_dotenv()
    bot = PriceTrackerBot()
    asyncio.run(bot.run())
