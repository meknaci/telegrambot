import telebot
from telebot.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np
import io
import math
import os
import tempfile
import time
import requests
import logging
import threading

# إعدادات البوت
TOKEN = "7703562539:AAGsAYWvC24jBtkwwP6tljVMiSFXMfcjjYY"
ASCII_CHARS = ["@", "#", "S", "%", "?", "*", "+", ";", ":", ",", "."]
bot = telebot.TeleBot(TOKEN)

# إعدادات متقدمة
MAX_WIDTH = 150  # أقصى عرض للصورة
MIN_WIDTH = 40   # أدنى عرض للصورة
FONT_SIZE = 12   # حجم الخط للصور النصية
MAX_CHARS = 3900  # الحد الأقصى للأحرف لتجنب اقتطاع النص

# مسارات الخطوط المفضلة (Monospace للحصول على نتائج أفضل)
FONT_PATHS = [
    "DejaVuSansMono.ttf",
    "Courier_New.ttf",
    "consola.ttf",
    "arial.ttf"
]

# تخزين مؤقت للبيانات
user_data = {}
logger = logging.getLogger("ASCIIBot")
logger.setLevel(logging.INFO)

# إعداد المسجل
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def get_best_font(font_size):
    """الحصول على أفضل خط متاح"""
    for font_path in FONT_PATHS:
        try:
            return ImageFont.truetype(font_path, font_size)
        except IOError:
            continue
    # استخدام الخط الافتراضي إذا لم يتم العثور على أي خط
    return ImageFont.load_default()

def calculate_optimal_size(image):
    """حساب الحجم الأمثل للصورة بناءً على جودة الناتج"""
    width, height = image.size
    ratio = height / width
    
    # حساب العرض بناءً على تعقيد الصورة
    total_pixels = width * height
    
    if total_pixels < 100000:  # صور صغيرة
        new_width = min(MAX_WIDTH, max(MIN_WIDTH, int(width * 0.5)))
    elif total_pixels < 500000:  # صور متوسطة
        new_width = min(MAX_WIDTH, max(MIN_WIDTH, int(width * 0.3)))
    else:  # صور كبيرة
        new_width = min(MAX_WIDTH, max(MIN_WIDTH, int(width * 0.15)))
    
    return new_width

def enhance_image_quality(image):
    """تحسين جودة الصورة قبل المعالجة"""
    # تحسين التباين
    image = ImageOps.autocontrast(image)
    
    # تحويل إلى تدرج الرمادي مع الحفاظ على التفاصيل
    if image.mode != 'L':
        image = image.convert('L')
    
    return image

def resize_image(image, new_width):
    """تغيير حجم الصورة مع الحفاظ على النسب"""
    width, height = image.size
    ratio = height / width
    new_height = int(new_width * ratio * 0.55)  # تعديل النسبة بسبب شكل الأحرف
    
    # استخدام خوارزمية إعادة الحجم عالية الجودة
    return image.resize((new_width, new_height), Image.LANCZOS)

def pixels_to_ascii(image):
    """تحويل البكسلات إلى أحرف ASCII بدقة عالية"""
    pixels = np.array(image)
    ascii_str = ""
    
    # تحسين توزيع الأحرف حسب كثافة البكسل
    for row in pixels:
        for pixel in row:
            # تحويل أكثر دقة مع مراعاة التوزيع
            index = min(int(pixel / 25.5), len(ASCII_CHARS) - 1)
            ascii_str += ASCII_CHARS[index]
        ascii_str += "\n"
    
    return ascii_str

def ascii_to_image(ascii_text, font_size=FONT_SIZE):
    """تحويل النص ASCII إلى صورة عالية الجودة"""
    font = get_best_font(font_size)
    
    # حساب أبعاد الصورة بناءً على النص
    lines = ascii_text.split('\n')
    max_line_length = max(len(line) for line in lines)
    num_lines = len(lines)
    
    # حساب أبعاد الصورة بدقة
    test_image = Image.new('RGB', (10, 10))
    test_draw = ImageDraw.Draw(test_image)
    
    # حساب عرض الخط
    if hasattr(font, 'getbbox'):
        char_width = font.getbbox("A")[2] - font.getbbox("A")[0]
    else:
        char_width = font_size // 2  # تقدير تقريبي
    
    char_height = int(font_size * 1.2)
    
    img_width = int(max_line_length * char_width * 1.1)  # هامش 10%
    img_height = num_lines * char_height + 20
    
    # إنشاء صورة جديدة مع خلفية سوداء
    img = Image.new('RGB', (img_width, img_height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # رسم النص على الصورة
    y_position = 10
    for line in lines:
        if hasattr(font, 'getbbox'):
            bbox = draw.textbbox((10, y_position), line, font=font)
            text_width = bbox[2] - bbox[0]
            x_position = (img_width - text_width) // 2
        else:
            x_position = 10
        
        draw.text((x_position, y_position), line, fill=(255, 255, 255), font=font)
        y_position += char_height
    
    return img

def split_long_text(text, max_length=MAX_CHARS):
    """تقسيم النص الطويل إلى أجزاء مع الحفاظ على الأسطر الكاملة"""
    parts = []
    current_part = ""
    
    for line in text.split('\n'):
        if len(current_part) + len(line) + 1 > max_length:
            parts.append(current_part)
            current_part = line + "\n"
        else:
            current_part += line + "\n"
    
    if current_part:
        parts.append(current_part)
    
    return parts

def download_font_if_missing():
    """تنزيل خط افتراضي إذا لم يتم العثور على أي خط"""
    if not os.path.exists("DejaVuSansMono.ttf"):
        try:
            url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSansMono.ttf"
            response = requests.get(url)
            with open("DejaVuSansMono.ttf", "wb") as f:
                f.write(response.content)
            logger.info("تم تنزيل خط DejaVuSansMono.ttf بنجاح")
        except Exception as e:
            logger.error(f"فشل تنزيل الخط: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: Message):
    """معالجة أمر البدء"""
    welcome_text = (
        "🎨 *مرحباً بكم في بوت ASCII Art المتقدم!*\n\n"
        "أنا أقوم بتحويل الصور إلى فن نصي ASCII بدقة عالية:\n"
        "📝 كـ *نص* يمكن نسخه واستخدامه في أي مكان\n"
        "🖼️ كـ *صورة* عالية الجودة\n\n"
        "🌟 *كيفية الاستخدام:*\n"
        "1. أرسل لي أي صورة\n"
        "2. اختر طريقة الإخراج المفضلة\n\n"
        "✨ *مزايا البوت:*\n"
        "- جودة عالية مع تفاصيل دقيقة\n"
        "- تحسين تلقائي للتباين والسطوع\n"
        "- دعم الصور الكبيرة والصغيرة\n"
        "- واجهة مستخدم سهلة\n\n"
        "💡 *نصائح للحصول على أفضل النتائج:*\n"
        "- استخدم صورًا ذات تباين عالي\n"
        "- تجنب الصور المعقدة جداً\n"
        "- الصور الشخصية تعطي نتائج ممتازة\n\n"
        "📱 *الأوامر المتاحة:*\n"
        "/start - عرض رسالة الترحيب\n"
        "/help - عرض المساعدة\n"
        "/settings - إعدادات متقدمة (قريباً)"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_image(message: Message):
    """معالجة الصور المرسلة"""
    try:
        # إعلام المستخدم بأن المعالجة جارية
        processing_msg = bot.reply_to(message, "⏳ جاري معالجة صورتك وتحسين جودتها...")
        
        # الحصول على أعلى دقة للصورة
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # فتح الصورة
        image = Image.open(io.BytesIO(downloaded_file))
        
        # تحسين جودة الصورة
        image = enhance_image_quality(image)
        
        # حساب الحجم الأمثل للصورة
        optimal_width = calculate_optimal_size(image)
        logger.info(f"تم اختيار العرض الأمثل: {optimal_width} بكسل")
        
        # تغيير حجم الصورة
        image = resize_image(image, optimal_width)
        
        # التحويل إلى ASCII بدقة عالية
        ascii_art = pixels_to_ascii(image)
        logger.info(f"تم إنشاء فن ASCII بحجم {len(ascii_art)} حرف")
        
        # حذف رسالة "جاري المعالجة"
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except Exception as e:
            logger.warning(f"لم يتمكن من حذف الرسالة: {e}")
        
        # تخزين النتيجة مؤقتًا
        user_data[message.message_id] = {
            'ascii_art': ascii_art,
            'width': image.width,
            'height': image.height,
            'timestamp': time.time()
        }
        
        # إنشاء لوحة اختيار متطورة
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("📝 النص (للنسخ)", callback_data=f"text_{message.message_id}"),
            InlineKeyboardButton("🖼️ صورة عالية الجودة", callback_data=f"image_{message.message_id}")
        )
        
        # إرسال خيارات الإخراج
        bot.send_message(
            message.chat.id,
            f"✅ تم تحويل صورتك بنجاح!\n"
            f"📏 الحجم: {image.width}×{image.height} بكسل\n"
            f"📝 عدد الأحرف: {len(ascii_art)}\n\n"
            "🎯 اختر طريقة الإخراج المفضلة:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {e}")
        error_text = (
            "⚠️ حدث خطأ غير متوقع أثناء معالجة الصورة:\n"
            f"```\n{str(e)}\n```\n\n"
            "يرجى المحاولة بصور أخرى أو التواصل مع المطور"
        )
        bot.reply_to(message, error_text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """معالجة اختيارات المستخدم"""
    try:
        # استخراج نوع الطلب ومعرف الرسالة
        parts = call.data.split('_')
        callback_type = parts[0]
        message_id = int(parts[1])
        
        # استرجاع البيانات المحفوظة
        data = user_data.get(message_id)
        if not data:
            bot.answer_callback_query(call.id, "⏱️ انتهت صلاحية الخيارات، يرجى إرسال الصورة مرة أخرى")
            return
            
        ascii_art = data.get('ascii_art', '')
        width = data.get('width', 0)
        height = data.get('height', 0)
        
        if callback_type == 'text':
            # إرسال النص
            bot.answer_callback_query(call.id, "📝 جاري إعداد النص...")
            
            if len(ascii_art) > MAX_CHARS:
                parts = split_long_text(ascii_art, MAX_CHARS)
                for i, part in enumerate(parts):
                    bot.send_message(call.message.chat.id, f"<pre>{part}</pre>", parse_mode='HTML')
                    time.sleep(0.5)  # تجنب الحدود
            else:
                bot.send_message(call.message.chat.id, f"<pre>{ascii_art}</pre>", parse_mode='HTML')
            
            # إرسال معلومات إضافية
            info_text = (
                f"🖼️ **معلومات الصورة الأصلية**\n"
                f"- الأبعاد: {width}×{height} بكسل\n"
                f"- عدد الأحرف: {len(ascii_art)}\n\n"
                "💡 يمكنك نسخ النص واستخدامه في أي مكان\n"
                "✨ جرب تحويله إلى NFT أو طباعته على قميص!"
            )
            bot.send_message(call.message.chat.id, info_text, parse_mode="Markdown")
            
        elif callback_type == 'image':
            # تحويل النص إلى صورة
            bot.answer_callback_query(call.id, "🎨 جاري إنشاء صورة عالية الجودة...")
            
            # إرسال إشعار بأن العملية جارية
            bot.send_chat_action(call.message.chat.id, 'upload_photo')
            
            try:
                # إنشاء الصورة
                ascii_image = ascii_to_image(ascii_art)
                
                # حفظ الصورة في كائن بايتس بدلاً من ملف مؤقت
                img_byte_arr = io.BytesIO()
                ascii_image.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                
                # إرسال الصورة مباشرة من الذاكرة
                bot.send_photo(call.message.chat.id, img_byte_arr)
                
                # إرسال معلومات إضافية
                info_text = (
                    f"🖼️ **معلومات الصورة النصية**\n"
                    f"- الأبعاد: {ascii_image.width}×{ascii_image.height} بكسل\n\n"
                    "💾 يمكنك تنزيل الصورة ومشاركتها\n"
                    "✨ مثالية للمشاركة على وسائل التواصل الاجتماعي!"
                )
                bot.send_message(call.message.chat.id, info_text, parse_mode="Markdown")
                
            except Exception as e:
                logger.error(f"خطأ في إنشاء الصورة: {e}")
                error_text = (
                    "⚠️ حدث خطأ أثناء إنشاء الصورة:\n"
                    f"```\n{str(e)}\n```\n\n"
                    "يرجى المحاولة بصور أخرى أو اختيار خيار النص"
                )
                bot.send_message(call.message.chat.id, error_text, parse_mode="Markdown")
        
        # حذف رسالة الخيارات بعد 5 ثوانٍ
        time.sleep(2)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # تنظيف البيانات المؤقتة
        if message_id in user_data:
            del user_data[message_id]
        
    except Exception as e:
        logger.error(f"خطأ في معالجة الاستدعاء: {e}")
        bot.answer_callback_query(call.id, f"⚠️ حدث خطأ: {str(e)}")

# تنظيف البيانات المؤقتة بشكل دوري
def clean_temp_data():
    while True:
        current_time = time.time()
        keys_to_delete = []
        
        for key, data in user_data.items():
            # البيانات تنتهي بعد 10 دقائق
            if current_time - data.get('timestamp', 0) > 600:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del user_data[key]
            logger.info(f"تم تنظيف البيانات المؤقتة لـ {key}")
        
        time.sleep(300)  # تشغيل كل 5 دقائق

# بدء تشغيل البوت
if __name__ == "__main__":
    # تنزيل الخطوط إذا لزم الأمر
    download_font_if_missing()
    
    # بدء خيط لتنظيف البيانات المؤقتة
    cleaner_thread = threading.Thread(target=clean_temp_data, daemon=True)
    cleaner_thread.start()
    
    logger.info("✅ البوت يعمل الآن...")
    bot.infinity_polling()