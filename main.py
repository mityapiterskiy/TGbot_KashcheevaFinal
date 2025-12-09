import asyncio
import logging
import sqlite3
import datetime
from contextlib import suppress
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from config import BOT_TOKEN, ADMIN_IDS, CHANNEL_ID, VIDEO_WELCOME_ID, VIDEO_LESSON_1_ID, VIDEO_LESSON_2_ID, VIDEO_LESSON_3_ID
from database import db

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
admin_router = Router()
dp.include_router(admin_router)
dp.include_router(router)



class SurveyStates(StatesGroup):
    check_sub = State()
    q1_sphere = State()
    q2_support = State()
    q3_group_attitude = State()
    intensive_intro = State()
    day_1 = State()
    day_2 = State()
    day_3 = State()
    sales_main = State()
    sales_group_select = State()
    sales_individual = State()

class AdminStates(StatesGroup):
    viewing_list = State()
    entering_id = State()

async def send_report_to_admins(user_id):
    user_info = db.get_user_info(user_id)
    username = user_info[0] if user_info else "Unknown"
    first_name = user_info[1] if user_info else "Unknown"
    
    logs = db.get_user_logs(user_id)
    report_text = f"Пользователь завершил воронку:\nID: {user_id}\nName: {first_name}\nUsername: @{username}\n\nИстория ответов:\n"
    
    for log in logs:
        event, content, time = log
        report_text += f"[{time}] {event}: {content}\n"

    for admin_id in ADMIN_IDS:
        try:
            file = BufferedInputFile(report_text.encode("utf-8"), filename=f"report_{user_id}.txt")
            await bot.send_document(admin_id, file, caption=f"Отчет по пользователю {first_name} (@{username})")
        except Exception:
            pass

async def reminder_scheduler():
    while True:
        try:
            users_to_remind = db.get_users_for_reminder()
            for user_id in users_to_remind:
                try:
                    await bot.send_message(
                        user_id, 
                        "Здравствуйте! Я заметила, что вы не завершили наш диалог. "
                        "Хотите продолжить путь к изменениям? Нажмите на последнюю кнопку или напишите /start, чтобы начать заново."
                    )
                    db.set_reminded(user_id)
                except Exception:
                    db.set_reminded(user_id) 
            await asyncio.sleep(3)
        except Exception:
            await asyncio.sleep(3)

@admin_router.message(Command("conv"))
async def cmd_admin_conv(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await show_users_page(message, 0)

async def show_users_page(message: types.Message, page: int):
    users = db.get_all_users_paginated(page)
    total_count = db.get_user_count()
    total_pages = (total_count + 9) // 10
    
    text = f"Всего пользователей: {total_count}. Страница {page + 1}/{total_pages}\n\n"
    
    kb_rows = []
    for u in users:
        u_id, u_name, u_username, u_date = u
        display_name = f"{u_name} (@{u_username})" if u_username else f"{u_name}"
        text += f"ID: <code>{u_id}</code> | {display_name} | {u_date}\n"
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_page_{page+1}"))
    
    if nav_buttons:
        kb_rows.append(nav_buttons)
    
    kb_rows.append([InlineKeyboardButton(text="🔎 Найти по ID", callback_data="adm_search_id")])
    
    if isinstance(message, types.CallbackQuery):
        message = message.message

    with suppress(TelegramBadRequest):
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("adm_page_"))
async def admin_pagination(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.answer()
    page = int(callback.data.split("_")[2])
    await show_users_page(callback.message, page)

@admin_router.callback_query(F.data == "adm_search_id")
async def admin_ask_id(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.answer()
    await state.set_state(AdminStates.entering_id)
    await callback.message.answer("Введите ID пользователя для просмотра логов:")

@admin_router.message(AdminStates.entering_id)
async def admin_show_logs(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(message.text.strip())
        logs = db.get_user_logs(target_id)
        if not logs:
            await message.answer("Логов по этому пользователю нет.")
        else:
            file_content = f"История диалога с {target_id}:\n\n"
            for log in logs:
                event, content, time = log
                file_content += f"[{time}] {event}: {content}\n"
            
            file = BufferedInputFile(file_content.encode("utf-8"), filename=f"log_{target_id}.txt")
            await message.answer_document(file)
            
    except ValueError:
        await message.answer("Некорректный ID.")
    
    await state.clear()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db.add_or_update_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    db.log_event(message.from_user.id, "Пользователь", "Запустил бота /start")
    
    await state.clear()
    text = (
        "Здравствуйте! Если вы здесь, значит хотите перемен – разобраться в себе, чувствах или привычках.\n"
        "Ответьте на несколько вопросов и я подскажу, какой путь подойдёт именно вам и открою доступ к "
        "3-х дневному мини-интенсиву, который поможет почувствовать первые изменения."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пройти опрос", callback_data="start_flow")]
    ])
    await message.answer(text, reply_markup=kb)
    db.log_event(message.from_user.id, "Бот", "Отправил приветствие")

@router.callback_query(F.data == "start_flow")
async def check_subscription(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    db.log_event(user_id, "Действие", "Нажал кнопку 'Пройти опрос'")
    
    await callback.answer()
    
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            await start_survey(callback, state)
        else:
            await ask_to_subscribe(callback)
    except Exception:
        await ask_to_subscribe(callback)

async def ask_to_subscribe(callback: types.CallbackQuery):
    text = (
        "Чтобы я могла вам помочь, сначала подпишитесь на мой ТГ канал, "
        "там вы найдёте много полезной информации."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписаться", url="https://t.me/doctor_kashcheeva")],
        [InlineKeyboardButton(text="Начать диагностику", callback_data="check_sub_again")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)
    db.log_event(callback.from_user.id, "Бот", "Попросил подписку")

@router.callback_query(F.data == "check_sub_again")
async def recheck_subscription(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    db.log_event(user_id, "Действие", "Нажал 'Начать диагностику' (проверка подписки)")
    
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            await callback.answer("Спасибо за подписку!")
            await start_survey(callback, state)
        else:
            await callback.answer("Вы еще не подписались!", show_alert=True)
            await ask_to_subscribe(callback)
    except Exception:
        await callback.answer("Вы еще не подписались!", show_alert=True)

async def start_survey(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SurveyStates.q1_sphere)
    text = "С какой сферой сейчас труднее всего справляться?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="С отношением к еде и телу", callback_data="q1_food")],
        [InlineKeyboardButton(text="С деньгами и ощущением стабильности", callback_data="q1_money")],
        [InlineKeyboardButton(text="С уверенностью в себе", callback_data="q1_confidence")],
        [InlineKeyboardButton(text="С отношениями с близкими", callback_data="q1_relations")],
        [InlineKeyboardButton(text="С привычками от которых сложно отказаться", callback_data="q1_habits")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)
        
    db.log_event(callback.from_user.id, "Бот", "Отправил вопрос 1 (Сфера)")

@router.callback_query(SurveyStates.q1_sphere)
async def process_q1(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    
    choice = callback.data
    
    readable_map = {
        "q1_food": "Еда и тело",
        "q1_money": "Деньги",
        "q1_confidence": "Уверенность",
        "q1_relations": "Отношения",
        "q1_habits": "Привычки"
    }
    log_text = readable_map.get(choice, choice)
    db.log_event(user_id, "Выбор сферы", log_text)
    
    await state.update_data(q1_choice=choice)
    await state.set_state(SurveyStates.q2_support)
    
    text_map = {
        "q1_food": "Это частая трудность. В программе можно научиться справляться с перееданием и критикой к себе.",
        "q1_money": "Деньги связаны не только с цифрами, но и с эмоциями. В программе о финансовой устойчивости мы работаем как раз с этим.",
        "q1_confidence": "Уверенность можно укрепить - в группе проще увидеть свои сильные стороны.",
        "q1_relations": "В терапии часто оказывается, что трудности в отношениях решаемы, если понимать свои эмоции и реакции.",
        "q1_habits": "Справляться с привычками одному сложно, а в группе появляется поддержка и конкретные шаги."
    }
    
    intro_text = text_map.get(choice, "")
    full_text = f"{intro_text}\n\nКогда вам становится тяжело, вы обычно ищете поддержку?"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Держу в себе", callback_data="q2_inside")],
        [InlineKeyboardButton(text="Стараюсь обсудить с близкими", callback_data="q2_friends")],
        [InlineKeyboardButton(text="Обращаюсь к специалисту", callback_data="q2_pro")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(full_text, reply_markup=kb)
    db.log_event(user_id, "Бот", "Отправил вопрос 2 (Поддержка)")

@router.callback_query(SurveyStates.q2_support)
async def process_q2(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    
    choice = callback.data
    
    readable_map = {
        "q2_inside": "Держу в себе",
        "q2_friends": "С близкими",
        "q2_pro": "К специалисту"
    }
    log_text = readable_map.get(choice, choice)
    db.log_event(user_id, "Выбор поддержки", log_text)
    
    await state.update_data(q2_choice=choice)
    await state.set_state(SurveyStates.q3_group_attitude)
    
    msg_text = ""
    if choice == "q2_inside":
        msg_text = "Это выматывает. В терапии не нужно тащить всё в одиночку."
    elif choice == "q2_friends":
        msg_text = "Это ценно, но они не всегда могут дать именно то, что поможет. Группа - безопасное пространство, где поддержка идет вместе с профессиональными инструментами."
    elif choice == "q2_pro":
        msg_text = "Отлично, значит вы уже заботитесь о себе. Групповой формат может стать дополнением и ускорить изменения."

    full_text = f"{msg_text}\n\nКак вы относитесь к идее пройти терапевтическую группу?"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Хочу начать уже сейчас", callback_data="q3_now")],
        [InlineKeyboardButton(text="Думаю, но пока откладываю", callback_data="q3_think")],
        [InlineKeyboardButton(text="Интересно, но нет уверенности", callback_data="q3_unsure")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_q2")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(full_text, reply_markup=kb)
    db.log_event(user_id, "Бот", "Отправил вопрос 3 (Отношение к группе)")

@router.callback_query(F.data == "back_to_q2")
async def back_to_q2_handler(callback: types.CallbackQuery, state: FSMContext):
    db.log_event(callback.from_user.id, "Навигация", "Назад к вопросу 2")
    await callback.answer()
    
    data = await state.get_data()
    q1_choice = data.get("q1_choice")
    await state.set_state(SurveyStates.q2_support)
    
    text_map = {
        "q1_food": "Это частая трудность. В программе можно научиться справляться с перееданием и критикой к себе.",
        "q1_money": "Деньги связаны не только с цифрами, но и с эмоциями. В программе о финансовой устойчивости мы работаем как раз с этим.",
        "q1_confidence": "Уверенность можно укрепить - в группе проще увидеть свои сильные стороны.",
        "q1_relations": "В терапии часто оказывается, что трудности в отношениях решаемы, если понимать свои эмоции и реакции.",
        "q1_habits": "Справляться с привычками одному сложно, а в группе появляется поддержка и конкретные шаги."
    }
    intro_text = text_map.get(q1_choice, "")
    full_text = f"{intro_text}\n\nКогда вам становится тяжело, вы обычно ищете поддержку?"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Держу в себе", callback_data="q2_inside")],
        [InlineKeyboardButton(text="Стараюсь обсудить с близкими", callback_data="q2_friends")],
        [InlineKeyboardButton(text="Обращаюсь к специалисту", callback_data="q2_pro")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(full_text, reply_markup=kb)

@router.callback_query(SurveyStates.q3_group_attitude, F.data.in_({"q3_now", "q3_think", "q3_unsure"}))
async def process_q3(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    
    choice = callback.data
    
    readable_map = {
        "q3_now": "Хочу сейчас",
        "q3_think": "Думаю",
        "q3_unsure": "Нет уверенности"
    }
    log_text = readable_map.get(choice, choice)
    db.log_event(user_id, "Отношение к группе", log_text)
    
    await state.set_state(SurveyStates.intensive_intro)
    
    msg_intro = ""
    if choice == "q3_now":
        msg_intro = "Это сильный шаг. Я расскажу какая из программ подойдёт вам: стройность, финансы, самооценка, отношения или работа с зависимостями."
    elif choice == "q3_think":
        msg_intro = "Это естественно. Но как раз в группе проще не откладывать, потому что есть поддержка и конкретный план."
    elif choice == "q3_unsure":
        msg_intro = "Можно начать с небольшой группы. Это безопасный способ попробовать терапию и увидеть первые результаты."
    
    text = (
        f"{msg_intro}\n\n"
        "Каждый ваш ответ - это про заботу о себе. Я предлагаю вам пройти небольшой бесплатный 3-х дневный интенсив, "
        "в котором вас ждут три коротких видео урока (по 20-30 мин) и простые практические задания, которые помогут:\n"
        "- понять что именно мешает вам двигаться вперед\n"
        "- научиться управлять внутренним саботажем и эмоциями\n"
        "- сделать первый шаг к устойчивым изменениям"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать интенсив", callback_data="start_intensive")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_q3")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)
    db.log_event(user_id, "Бот", "Предложил интенсив")

@router.callback_query(F.data == "back_to_q3")
async def back_to_q3_handler(callback: types.CallbackQuery, state: FSMContext):
    db.log_event(callback.from_user.id, "Навигация", "Назад к вопросу 3")
    await callback.answer()
    await state.set_state(SurveyStates.q3_group_attitude)
    data = await state.get_data()
    q2_choice = data.get("q2_choice")
    
    msg_text = ""
    if q2_choice == "q2_inside":
        msg_text = "Это выматывает. В терапии не нужно тащить всё в одиночку."
    elif q2_choice == "q2_friends":
        msg_text = "Это ценно, но они не всегда могут дать именно то, что поможет. Группа - безопасное пространство, где поддержка идет вместе с профессиональными инструментами."
    elif q2_choice == "q2_pro":
        msg_text = "Отлично, значит вы уже заботитесь о себе. Групповой формат может стать дополнением и ускорить изменения."

    full_text = f"{msg_text}\n\nКак вы относитесь к идее пройти терапевтическую группу?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Хочу начать уже сейчас", callback_data="q3_now")],
        [InlineKeyboardButton(text="Думаю, но пока откладываю", callback_data="q3_think")],
        [InlineKeyboardButton(text="Интересно, но нет уверенности", callback_data="q3_unsure")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_q2")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(full_text, reply_markup=kb)

@router.callback_query(F.data == "start_intensive")
async def start_intensive_day_1(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer() 
    db.log_event(user_id, "Интенсив", "Начал День 1")
    
    await state.set_state(SurveyStates.day_1)
    await bot.send_video(chat_id=user_id, video=VIDEO_WELCOME_ID, caption="Приветствие")
    await asyncio.sleep(1)
    
    await bot.send_video(chat_id=user_id, video=VIDEO_LESSON_1_ID, caption="Урок 1")
    await asyncio.sleep(1)
    big_text = (
        "Меня зовут Анастасия Кащеева – я психотерапевт, когнитивно-поведенческий терапевт и автор проектов о том, как вернуть себе опору, ясность и устойчивость в жизни.\n\n"
        "Добро пожаловать на бесплатный интенсив \"пять ключей к изменениям\".\n"
        "В течение нескольких дней мы разберём, почему даже сильные и умные люди часто застревают в теле, в отношениях, с деньгами, с привычками или самооценкой – и что с этим можно сделать.\n\n"
        "После интенсива вы увидите, в какой сфере сейчас ваша главная точка роста - И сможете выбрать подходящую группу для продолжения работы.\n\n"
        "Урок 1 (видео)\n"
        "Почему мы знаем что делать – но не делаем: как работает внутренний саботаж\n\n"
        "Я покажу вам, что причина не в слабой воле или лени, а в автоматических мыслях, страхи неудачи и неосознанных установках. Здесь работает простая схема КПТ: мысль-> эмоция-> поведение.\n\n"
        "Типичные формы самосаботажа: откладывание, переедание, избегание, раздражение, всё или ничего.\n\n"
        "Задание на самонаблюдение - поймать момент саботажа.\n"
        "Это затрагивает всех: и тех кто не может начать худеть, и тех кто застрял в отношениях, с деньгами или самооценкой.\n\n"
        "В течение дня замечаете ситуацию, где вы хотели сделать что-то полезное (например, заняться спортом, поговорить спокойно, не переесть, не тратить лишнего) но не смогли.\n\n"
        "Запишите три пункта:\n"
        "- что я собирался(лась) сделать?\n"
        "- какая мысль мелькнула в голове перед тем, как я передумал(а)?\n"
        "- какое чувство появилось?\n\n"
        "Коротко проанализируйте помогла ли вам эта мысль приблизиться к цели или отдалила?\n\n"
        "Цель: увидеть, что саботаж – не лень, а автоматическая мысль, которую можно заметить и поменять."
    )
    await bot.send_message(chat_id=user_id, text=big_text)
    
    prompt_text = "Нажмите Готово после того, как выполните задание."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово", callback_data="day1_done")]
    ])
    await bot.send_message(chat_id=user_id, text=prompt_text, reply_markup=kb)
    db.log_event(user_id, "Бот", "Отправил материалы Дня 1")

@router.callback_query(F.data == "day1_done")
async def intensive_day_2(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.log_event(user_id, "Интенсив", "Выполнил День 1, перешел ко Дню 2")
    
    await state.set_state(SurveyStates.day_2)
    
    await bot.send_video(chat_id=user_id, video=VIDEO_LESSON_2_ID, caption="Урок 2")
    
    text = (
        "Урок 2 (видео)\n\n"
        "Эмоции под контролем: как перестать жить на автопилоте.\n\n"
        "Покажу вам, что эмоции не враги, а сигналы, которые можно научиться понимать и использовать.\n\n"
        "Научу различать автоматическую эмоцию и её причину.\n\n"
        "Почему избегание чувств усиливает тревогу, переедания и конфликты.\n\n"
        "Эта тема универсальная для всех направлений потому что эмоции – главные триггеры поведения.\n\n"
        "Задание Стоп-кадр:\n"
        "В течение второго дня, когда почувствуете сильную эмоцию (тревога, раздражение, обида) - остановитесь на 30 секунд.\n\n"
        "Ответьте письменно:\n"
        "- что я сейчас чувствую (одним словом)?\n"
        "- что произошло перед этим?\n"
        "- о чем говорит эта эмоция, чего я хочу или чего мне не хватает?\n\n"
        "Сделайте глубокий вдох-выдох и выберите одно маленькое действие, которое поможет вам удовлетворить эту потребность экологично.\n\n"
        "Цель: научиться распознавать эмоцию до того, как она направит поведение."
    )
    await bot.send_message(chat_id=user_id, text=text)

    prompt = "Нажмите Готово после того, как выполните задание и смотрите завершающий урок интенсива"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово", callback_data="day2_done")]
    ])
    await bot.send_message(chat_id=user_id, text=prompt, reply_markup=kb)
    db.log_event(user_id, "Бот", "Отправил материалы Дня 2")

@router.callback_query(F.data == "day2_done")
async def intensive_day_3(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.log_event(user_id, "Интенсив", "Выполнил День 2, перешел ко Дню 3")
    
    await state.set_state(SurveyStates.day_3)
    
    await bot.send_video(chat_id=user_id, video=VIDEO_LESSON_3_ID, caption="Урок 3")
    
    text = (
        "Поздравляю вас, сегодня завершающий день мини интенсива.\n\n"
        "Урок 3 (видео)\n\n"
        "Как строятся устойчивые изменения: шаги, которые работают.\n\n"
        "Сегодня будем учиться переводить себя из позиции \"я опять не справлюсь\" в состояние \"я понимаю как работает процесс изменений\".\n\n"
        "Узнаем, как мозг реагирует на новое и почему быстро откатывает обратно.\n\n"
        "Задание: одно действие на сегодня.\n\n"
        "Выберите одну сферу, где вы давно хотите изменений (тело, отношения, финансы, привычки или самооценка).\n\n"
        "Запишите одно маленькое действие, которое реально сделать за 5-10 минут и которое немного приблизить вас к цели.\n\n"
        "Например: выпить стакан воды вместо кофе, написать сообщение, записать расходы, выйти на короткую прогулку, похвалить себя.\n\n"
        "Вечером отметьте, удалось ли сделать. Если да – замечайте чувство удовлетворения, если нет – мягко проанализируйте, что помешало.\n\n"
        "Цель: почувствовать, что изменения начинаются не с мотивации, а с маленьких, осознанных действий."
    )
    await bot.send_message(chat_id=user_id, text=text)

    prompt = "Нажмите Завершить после того, как выполните задание."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Завершить интенсив", callback_data="intensive_complete")]
    ])
    await bot.send_message(chat_id=user_id, text=prompt, reply_markup=kb)
    db.log_event(user_id, "Бот", "Отправил материалы Дня 3")

@router.callback_query(F.data == "intensive_complete")
async def sales_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.log_event(user_id, "Интенсив", "Полностью завершил интенсив")
    
    await state.set_state(SurveyStates.sales_main)
    
    text = (
        "Вы сделали первый шаг к решению вашей проблемы. Сейчас я веду набор в групповые программы по 5 направлениям: "
        "стройность, финансы, самооценка, отношения и зависимости.\n"
        "Хотите расскажу подробнее о той, которая подходит именно вам?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, хочу в группу", callback_data="sales_group")],
        [InlineKeyboardButton(text="Хочу работать индивидуально", callback_data="sales_indiv")],
        [InlineKeyboardButton(text="Есть вопросы", callback_data="sales_questions")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)
    db.log_event(user_id, "Бот", "Предложил платные продукты")

@router.callback_query(F.data == "sales_group")
async def sales_group_select(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.log_event(user_id, "Выбор", "Хочет в группу, смотрит направления")
    
    await state.set_state(SurveyStates.sales_group_select)
    text = (
        "Здорово! У меня есть несколько направлений терапевтических групп:\n"
        "- Стройность через КПТ-для тех, кто хочет наладить отношения с едой и телом\n"
        "- Финансовая устойчивость-про деньги и уверенность в себе\n"
        "- Самооценка и уверенность-чтобы чувствовать больше опоры в себе\n"
        "- Отношения-про близость, доверие и здоровые границы\n"
        "- Работа с зависимостями-для тех, кто устал жить \"по кругу\"\n\n"
        "Выберите какая тема ближе вам сейчас и я расскажу подробнее о ближайшем наборе."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Стройность", callback_data="topic_body")],
        [InlineKeyboardButton(text="Финансы", callback_data="topic_money")],
        [InlineKeyboardButton(text="Самооценка", callback_data="topic_self")],
        [InlineKeyboardButton(text="Отношения", callback_data="topic_rel")],
        [InlineKeyboardButton(text="Негативные привычки", callback_data="topic_habits")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sales_main")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "back_to_sales_main")
async def back_sales_main(callback: types.CallbackQuery, state: FSMContext):
    db.log_event(callback.from_user.id, "Навигация", "Назад к выбору формата")
    await callback.answer()
    await sales_start(callback, state)

@router.callback_query(F.data.startswith("topic_"))
async def show_topic_info(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    
    topic_key = callback.data.split("_")[1]
    
    topic_names = {
        "body": "Стройность",
        "money": "Финансы",
        "self": "Самооценка",
        "rel": "Отношения",
        "habits": "Негативные привычки"
    }
    
    topic_name = topic_names.get(topic_key, "Общий вопрос")
    db.log_event(user_id, "Интерес", f"Выбрал тему: {topic_name}")
    
    texts = {
        "body": (
            "Эта группа для тех, кто устал от диет, срывов и чувство вины. Мы работаем не с весами, а с привычками, мыслями и эмоциями.\n"
            "Вы научитесь понимать сигналы тела, справляться с перееданием и строить новые отношения с едой без жёстких ограничений.\n"
            "Хотите присоединиться к ближайшей группе?"
        ),
        "money": (
            "Финансовые трудности часто связаны не только с цифрами, но и с нашими мыслями, страхами и привычками. "
            "В группе мы работаем с тревогой о деньгах, откладыванием, с причинами Долгов и с внутренними запретами на доход. "
            "Это шаг к спокойствию и большой уверенности в завтрашнем дне. Хотите я расскажу о ближайшем наборе?"
        ),
        "self": (
            "Если вы часто сомневаетесь в себе, откладывайте из-за страха ошибки или живёте с внутренним критиком – эта группа поможет.\n"
            "Вы будете учиться замечать свои сильные стороны, справляться с самокритикой и шага за шагом укреплять уверенность."
        ),
        "rel": (
            "Близкие отношения это источник поддержки, но часто и боли. В группе мы работаем с доверием, умением строить здоровые границы, "
            "понимать свои чувства и не терять себя в отношениях.\n"
            "Это пространство, где можно увидеть привычные сценарии и начать строить новые, более здоровые.\n"
            "Хотите узнать о ближайшей группе?"
        ),
        "habits": (
            "Иногда привычки становится слишком сильными и начинают управлять нами – это могут быть еда, гаджеты, алкоголь или другие формы зависимости. "
            "В группе мы разбираем как устроены такие механизмы и учимся шаг за шагом возвращать себе контроль. Хотите присоединиться к ближайшей группе?"
        )
    }
    
    base_text = texts.get(topic_key, "")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, хочу в группу", callback_data="final_yes")],
        [InlineKeyboardButton(text="Задать вопрос", callback_data="final_q")]
    ])
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(base_text, reply_markup=kb)

@router.callback_query(F.data.in_({"final_yes", "final_q"}))
async def show_final_contact(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.mark_finished(user_id)

    if callback.data == "final_yes":
        text = "Если вы чувствуете, что формат группы вам подходит – можно занять место прямо сейчас. Напишите мне и я пришлю все детали: @doctorkashcheeva"
        db.log_event(user_id, "Финал", "Нажал: Хочу в группу")
    else:
        text = "Если у вас есть вопрос, напишите мне: @doctorkashcheeva"
        db.log_event(user_id, "Финал", "Нажал: Задать вопрос")

    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None)
    
    await send_report_to_admins(user_id)

@router.callback_query(F.data == "sales_indiv")
async def sales_individual_info(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.mark_finished(user_id)
    db.log_event(user_id, "Интерес", "Индивидуальная работа")
    
    text = (
        "Индивидуальная работа – это безопасное пространство, где все внимание уделяется только вам.\n\n"
        "На сессиях мы разбираем именно ваш запрос и шаг за шагом идём к изменениям. "
        "Индивидуальные консультации проходят онлайн и очно (в центре Москвы).\n"
        "Длительность консультации 50 минут. Рекомендуемая частота – обычно один раз в неделю. "
        "В среднем от 8 до 20 встреч уже достаточно чтобы почувствовать результат. "
        "Хотите я помогу подобрать удобное время для первой консультации?\n\n"
        "Чтобы согласовать удобное время и условия индивидуальной работы с вами, а также уточнить условия – напишите мне:\n"
        "@doctorkashcheeva"
    )

    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None)
    await send_report_to_admins(user_id)

@router.callback_query(F.data == "sales_questions")
async def sales_questions_info(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.update_interaction(user_id)
    await callback.answer()
    db.mark_finished(user_id)
    db.log_event(user_id, "Интерес", "Есть вопросы")

    text = (
        "Сомневаться и уточнять нормально. Можете просто написать мне, чтобы задать вопрос или обсудить, "
        "какой формат ближе именно вам:\n"
        "@doctorkashcheeva"
    )
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None)
    await send_report_to_admins(user_id)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(reminder_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass