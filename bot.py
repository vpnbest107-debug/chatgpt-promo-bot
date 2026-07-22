import requests
import json
import time
import random
import re
import base64
import threading
import os
import logging
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ============================================
# الإعدادات
# ============================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "1015595599")
MAX_WORKERS = 8
TIMEOUT = 5
BATCH_SIZE = 200

# ============================================
# إعدادات التسجيل
# ============================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

# ============================================
# ChatGPT Token Extractor
# ============================================

class ChatGPT_Token_Extractor:
    @staticmethod
    def extract_access_token_from_json(data):
        try:
            if isinstance(data, str):
                data = json.loads(data)
            if 'accessToken' in data:
                return data['accessToken']
            for key, value in data.items():
                if isinstance(value, dict):
                    result = ChatGPT_Token_Extractor.extract_access_token_from_json(value)
                    if result:
                        return result
                elif key == 'accessToken' or 'access_token' in key.lower():
                    return value
            return None
        except:
            return None

    @staticmethod
    def extract_from_text(text):
        pattern = r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'
        match = re.search(pattern, text)
        return match.group(0) if match else None

    @staticmethod
    def decode_token_payload(token):
        try:
            parts = token.split('.')
            if len(parts) >= 2:
                payload = parts[1]
                padding = '=' * (4 - len(payload) % 4)
                decoded = base64.b64decode(payload + padding)
                return json.loads(decoded)
            return None
        except:
            return None

# ============================================
# ChatGPT Promo Scanner
# ============================================

class ChatGPT_Promo_Scanner:
    def __init__(self):
        self.access_token = None
        self.results = []
        self.token_valid = False
        self.total_checked = 0
        self.token_file = 'chatgpt_token.txt'
        self.stop_scan = False
        self.scanning = False
        self.user_info = {}
        self.results_lock = threading.Lock()
        self.found_codes = []
        self.session = None
        self.executor = None

    def get_session(self):
        if not self.session:
            self.session = requests.Session()
        return self.session

    def get_executor(self):
        if not self.executor:
            self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        return self.executor

    def load_saved_token(self):
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token = f.read().strip()
                if token:
                    return token
            return None
        except:
            return None

    def save_token(self, token):
        try:
            with open(self.token_file, 'w') as f:
                f.write(token)
            return True
        except:
            return False

    def validate_token(self, token):
        results = {
            'valid': False,
            'user': None,
            'plan': None,
            'expires': None
        }
        
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            payload = ChatGPT_Token_Extractor.decode_token_payload(token)
            if payload:
                exp = payload.get('exp', 0)
                current_time = int(time.time())
                if exp > current_time:
                    results['valid'] = True
                    results['expires'] = datetime.fromtimestamp(exp).strftime('%Y-%m-%d %H:%M:%S')
                    results['user'] = payload.get('email', 'Unknown')
            
            try:
                response = requests.get('https://api.openai.com/v1/account', headers=headers, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    results['user'] = data.get('email', results['user'])
                    results['plan'] = data.get('plan', 'Unknown')
            except:
                pass
                
            return results
        except:
            return results

    def check_promo_code_light(self, code):
        if not self.access_token:
            return None
        try:
            session = self.get_session()
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            url = f"https://api.openai.com/v1/promotions/{code}/validate"
            response = session.get(url, headers=headers, timeout=TIMEOUT)
            self.total_checked += 1
            
            if response.status_code == 200:
                result = {'code': code, 'status': 'VALID', 'valid': True}
                with self.results_lock:
                    if code not in self.found_codes:
                        self.found_codes.append(code)
                return result
            else:
                return None
        except:
            return None

    def generate_codes(self, base_name, country_codes=None):
        if country_codes is None:
            country_codes = ['in', 'us', 'uk', 'ca', 'au', 'de', 'fr', 'es', 'it']
        
        codes = []
        base = base_name.lower().replace(' ', '').replace('-', '').replace('_', '')
        patterns = [base, f"{base}8", f"{base}9"]
        
        for country in country_codes:
            for pattern in patterns:
                codes.append(f"{pattern}{country}")
        return list(set(codes))

    def find_working_codes(self):
        """البحث عن كوبونات دفعة واحدة"""
        print("🔍 جاري البحث عن الكوبونات...")
        
        all_partners = [
            'thinkingmachines', 'tata', 'reliance', 'airtel', 'jio',
            'google', 'microsoft', 'amazon', 'facebook', 'apple',
            'ibm', 'oracle', 'salesforce', 'adobe', 'cisco',
            'dell', 'hp', 'lenovo', 'samsung', 'sony',
            'infosys', 'wipro', 'tcs', 'hcl', 'techmahindra',
            'accenture', 'capgemini', 'deloitte', 'pwc', 'ey'
        ]
        
        all_codes = []
        main_countries = ['in', 'us', 'uk', 'ca', 'au', 'de', 'fr', 'es', 'it']
        
        for partner in all_partners[:20]:
            codes = self.generate_codes(partner, main_countries)
            all_codes.extend(codes[:15])
        
        known_codes = [
            'THINKINGMACHINESIN', 'TATAIN', 'RELIANCEIN',
            'JIOIN', 'AIRTELIN', 'GOOGLEIN', 'MICROSOFTIN'
        ]
        all_codes.extend(known_codes)
        all_codes = list(set(all_codes))[:BATCH_SIZE]
        
        valid = self.scan_codes_batch_light(all_codes)
        
        if valid:
            print(f"✅ تم العثور على {len(valid)} كوبون")
        else:
            print("❌ لم يتم العثور على كوبونات")
        
        return valid

    def scan_codes_batch_light(self, codes_list, callback=None):
        if not codes_list:
            return []
            
        valid_results = []
        new_codes = []
        executor = self.get_executor()
        futures = []
        
        for code in codes_list[:BATCH_SIZE]:
            if self.stop_scan:
                break
            futures.append(executor.submit(self.check_promo_code_light, code))
        
        for future in as_completed(futures):
            if self.stop_scan:
                break
            try:
                result = future.result(timeout=TIMEOUT + 1)
                if result and result.get('valid'):
                    valid_results.append(result)
                    if result['code'] not in self.found_codes:
                        new_codes.append(result['code'])
            except:
                pass
        
        if new_codes and callback:
            callback(new_codes)
        
        del futures
        return valid_results

    def continuous_scan_light(self, callback=None, promo_callback=None):
        self.stop_scan = False
        self.scanning = True
        total_found = 0
        batch_num = 1
        
        all_partners = [
            'thinkingmachines', 'tata', 'reliance', 'airtel', 'jio',
            'google', 'microsoft', 'amazon', 'facebook', 'apple',
            'ibm', 'oracle', 'salesforce', 'adobe', 'cisco',
            'dell', 'hp', 'lenovo', 'samsung', 'sony',
            'infosys', 'wipro', 'tcs', 'hcl', 'techmahindra'
        ]
        
        while not self.stop_scan:
            batch_partners = random.sample(all_partners, min(10, len(all_partners)))
            all_codes = []
            main_countries = ['in', 'us', 'uk', 'ca', 'au', 'de', 'fr', 'es', 'it']
            
            for partner in batch_partners:
                codes = self.generate_codes(partner, main_countries)
                all_codes.extend(codes[:15])
            
            known_codes = [
                'THINKINGMACHINESIN', 'TATAIN', 'RELIANCEIN',
                'JIOIN', 'AIRTELIN', 'GOOGLEIN', 'MICROSOFTIN'
            ]
            all_codes.extend(known_codes)
            all_codes = list(set(all_codes))[:BATCH_SIZE]
            
            def found_callback(new_codes):
                if promo_callback:
                    promo_callback(new_codes)
            
            valid = self.scan_codes_batch_light(all_codes, found_callback)
            
            if valid:
                total_found += len(valid)
                if callback:
                    callback(valid, total_found, self.total_checked, batch_num)
            
            batch_num += 1
            
            if self.stop_scan:
                break
            
            time.sleep(1)
            del all_codes
        
        self.scanning = False
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        return self.results

    def get_all_found_codes(self):
        with self.results_lock:
            return self.found_codes.copy()

    def generate_payment_link(self, code):
        if code:
            return f"https://buy.stripe.com/CHATGPT?promo={code.upper()}"
        return None

    def cleanup(self):
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        if self.session:
            self.session.close()
            self.session = None

# ============================================
# متغيرات البوت
# ============================================

scanner = ChatGPT_Promo_Scanner()
last_message_id = None
last_chat_id = None

# ============================================
# دوال البوت
# ============================================

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📁 إرسال ملف التوكن", callback_data="send_token_file")],
        [InlineKeyboardButton("🔍 بحث سريع", callback_data="search_once")],
        [InlineKeyboardButton("🔄 بحث مستمر", callback_data="search_continuous")],
        [InlineKeyboardButton("✅ التحقق من التوكن", callback_data="check_token")],
        [InlineKeyboardButton("📊 عرض الكوبونات", callback_data="show_results")],
        [InlineKeyboardButton("🔗 روابط الدفع", callback_data="generate_links")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_scanning_keyboard():
    keyboard = [
        [InlineKeyboardButton("⏹️ إيقاف البحث", callback_data="stop_scan")],
        [InlineKeyboardButton("📊 عرض التقدم", callback_data="show_progress")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_main_interface():
    token_status = "✅" if scanner.access_token else "❌"
    token_valid = "✅" if scanner.token_valid else "❌"
    
    interface = f"""
╔═══════════════════════════════════════╗
║         🚀 ChatGPT SCANNER            ║
╠═══════════════════════════════════════╣
║  🔑 {token_status} التوكن
║  ✅ {token_valid} الصلاحية
║  📊 {scanner.total_checked} كود
║  🎯 {len(scanner.found_codes)} كوبون
║  ⚡ {MAX_WORKERS} خيط
╚═══════════════════════════════════════╝
"""
    return interface

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_message_id, last_chat_id
    last_message_id = None
    last_chat_id = None
    
    saved_token = scanner.load_saved_token()
    if saved_token:
        validation = scanner.validate_token(saved_token)
        if validation['valid']:
            scanner.access_token = saved_token
            scanner.token_valid = True
    
    await update.message.reply_text(
        "🤖 **ChatGPT Promo Scanner**\n\n"
        f"⚡ {MAX_WORKERS} خيط\n"
        "💡 أرسل ملف التوكن للبدء",
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ أرسل ملف `.txt`", reply_markup=get_main_keyboard())
        return
    
    waiting = await update.message.reply_text("📥 جاري القراءة...")
    file = await document.get_file()
    file_path = f"temp_{document.file_name}"
    await file.download_to_drive(file_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        token = ChatGPT_Token_Extractor.extract_from_text(content)
        if not token:
            try:
                data = json.loads(content)
                token = ChatGPT_Token_Extractor.extract_access_token_from_json(data)
            except:
                pass
        
        if token:
            scanner.access_token = token
            scanner.save_token(token)
            validation = scanner.validate_token(token)
            scanner.token_valid = validation['valid']
            
            await waiting.delete()
            await update.message.reply_text(
                f"✅ **تم الحفظ!**\n\n"
                f"👤 {validation.get('user', 'Unknown')}\n"
                f"📋 {validation.get('plan', 'Unknown')}",
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown'
            )
        else:
            await waiting.delete()
            await update.message.reply_text("❌ **لم يتم العثور على توكن!**", reply_markup=get_main_keyboard())
    except:
        await waiting.delete()
        await update.message.reply_text("❌ **خطأ في القراءة!**", reply_markup=get_main_keyboard())
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global scanner
    
    if query.data == "send_token_file":
        await query.edit_message_text(
            "📁 أرسل ملف `.txt` يحتوي على التوكن",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        
    elif query.data == "search_once":
        if not scanner.access_token:
            await query.edit_message_text("❌ لا يوجد توكن!", reply_markup=get_main_keyboard())
            return
        
        await query.edit_message_text("🔍 جاري البحث...", parse_mode='Markdown')
        
        def scan():
            results = scanner.find_working_codes()
            asyncio.run(show_results(query, results))
        
        thread = threading.Thread(target=scan)
        thread.daemon = True
        thread.start()
        
    elif query.data == "search_continuous":
        if not scanner.access_token:
            await query.edit_message_text("❌ لا يوجد توكن!", reply_markup=get_main_keyboard())
            return
        
        if scanner.scanning:
            await query.edit_message_text("🔄 جاري البحث!", reply_markup=get_scanning_keyboard())
            return
        
        await query.edit_message_text(
            "🔄 بدء البحث...\n⚡ سيتم الإرسال فوراً",
            reply_markup=get_scanning_keyboard(),
            parse_mode='Markdown'
        )
        
        def scan_cont():
            def progress(valid, total, checked, batch):
                asyncio.run(update_progress(query, valid, total, checked, batch))
            
            def promo(codes):
                asyncio.run(send_codes(context, codes))
            
            scanner.continuous_scan_light(progress, promo)
            asyncio.run(scan_complete(query))
        
        thread = threading.Thread(target=scan_cont)
        thread.daemon = True
        thread.start()
        
    elif query.data == "stop_scan":
        scanner.stop_scan = True
        await query.edit_message_text("⏹️ جاري الإيقاف...", reply_markup=get_main_keyboard())
        scanner.cleanup()
        
    elif query.data == "check_token":
        if not scanner.access_token:
            await query.edit_message_text("❌ لا يوجد توكن!", reply_markup=get_main_keyboard())
            return
        
        validation = scanner.validate_token(scanner.access_token)
        status = "✅ صالح" if validation['valid'] else "❌ غير صالح"
        msg = f"🔍 **التحقق**\n\n📌 {status}"
        if validation.get('user'):
            msg += f"\n👤 {validation['user']}"
        if validation.get('plan'):
            msg += f"\n📋 {validation['plan']}"
        if validation.get('expires'):
            msg += f"\n⏰ {validation['expires']}"
        
        await query.edit_message_text(msg, reply_markup=get_main_keyboard(), parse_mode='Markdown')
        
    elif query.data == "show_results":
        codes = scanner.get_all_found_codes()
        if not codes:
            await query.edit_message_text("📋 لا توجد كوبونات!", reply_markup=get_main_keyboard())
            return
        
        msg = "📊 **الكوبونات**\n\n"
        for i, code in enumerate(codes[:10], 1):
            msg += f"{i}. `{code}`\n"
        if len(codes) > 10:
            msg += f"\n... و {len(codes) - 10} أخرى"
        
        await query.edit_message_text(msg, reply_markup=get_main_keyboard(), parse_mode='Markdown')
        
    elif query.data == "generate_links":
        codes = scanner.get_all_found_codes()
        if not codes:
            await query.edit_message_text("❌ لا توجد كوبونات!", reply_markup=get_main_keyboard())
            return
        
        msg = "🔗 **روابط الدفع**\n\n"
        for code in codes[:5]:
            link = scanner.generate_payment_link(code)
            msg += f"🔑 {code}\n🔗 {link}\n\n"
        if len(codes) > 5:
            msg += f"... و {len(codes) - 5} أخرى"
        
        await query.edit_message_text(msg, reply_markup=get_main_keyboard(), parse_mode='Markdown')
        
    elif query.data == "show_progress":
        status = "🔄 يعمل" if scanner.scanning else "⏸️ متوقف"
        msg = f"📊 **الحالة**\n\n📌 {status}\n📊 {scanner.total_checked}\n🎯 {len(scanner.get_all_found_codes())}"
        await query.edit_message_text(msg, reply_markup=get_scanning_keyboard(), parse_mode='Markdown')

async def show_results(query, results):
    if results:
        msg = "✅ **تم العثور على كوبونات!**\n\n"
        for r in results[:5]:
            link = scanner.generate_payment_link(r['code'])
            msg += f"🔑 `{r['code']}`\n🔗 {link}\n\n"
        if len(results) > 5:
            msg += f"\n... و {len(results) - 5} أخرى"
    else:
        msg = "❌ **لم يتم العثور على كوبونات**"
    
    await query.edit_message_text(msg, reply_markup=get_main_keyboard(), parse_mode='Markdown')

async def send_codes(context, codes):
    if codes:
        msg = "🎉 **كوبونات جديدة!**\n\n"
        for code in codes[:3]:
            link = scanner.generate_payment_link(code)
            msg += f"🔑 `{code}`\n🔗 {link}\n\n"
        if len(codes) > 3:
            msg += f"... و {len(codes) - 3} أخرى"
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode='Markdown')

async def update_progress(query, valid, total, checked, batch):
    msg = f"🔄 **دفعة {batch}**\n\n"
    if valid:
        msg += f"✅ {len(valid)} جديد!\n"
    msg += f"📊 {total} كوبون\n📊 {checked} كود"
    
    try:
        await query.edit_message_text(msg, reply_markup=get_scanning_keyboard(), parse_mode='Markdown')
    except:
        pass

async def scan_complete(query):
    codes = scanner.get_all_found_codes()
    msg = f"⏹️ **تم الإيقاف**\n\n📊 {len(codes)} كوبون\n📊 {scanner.total_checked} كود"
    
    try:
        await query.edit_message_text(msg, reply_markup=get_main_keyboard(), parse_mode='Markdown')
    except:
        pass

# ============================================
# التشغيل
# ============================================

def main():
    print("\n" + "=" * 60)
    print("🚀 ChatGPT SCANNER")
    print("=" * 60)
    print(f"⚡ {MAX_WORKERS} خيط")
    print(f"📦 {BATCH_SIZE} كود/دفعة")
    print("=" * 60)
    
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN غير موجود!")
        print("📌 يرجى إضافته في متغيرات البيئة")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("✅ يعمل!")
    application.run_polling()

if __name__ == "__main__":
    main()
