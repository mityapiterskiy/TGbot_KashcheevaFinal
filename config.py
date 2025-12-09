import os
import dotenv
dotenv.load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = [1015082973, 1931600027]

VIDEO_WELCOME_ID = os.getenv('VIDEO_WELCOME_ID')
VIDEO_LESSON_1_ID = os.getenv('VIDEO_LESSON_1_ID')
VIDEO_LESSON_2_ID = os.getenv('VIDEO_LESSON_2_ID')
VIDEO_LESSON_3_ID = os.getenv('VIDEO_LESSON_3_ID')