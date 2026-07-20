
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
import schedule
from PIL import Image, ImageDraw, ImageFont
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
RECIPES_FILE = BASE_DIR / "recipes.json"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow").strip()
POST_TIMES = [
    x.strip() for x in os.getenv("POST_TIMES", "09:00,14:00,19:00").split(",")
    if x.strip()
]

if not BOT_TOKEN:
    raise RuntimeError("Не задана переменная TELEGRAM_BOT_TOKEN")
if not CHANNEL:
    raise RuntimeError("Не задана переменная TELEGRAM_CHANNEL")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def load_recipes():
    with RECIPES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        raise RuntimeError("Файл recipes.json пуст")
    return data


def load_index():
    if not STATE_FILE.exists():
        return 0
    try:
        return int(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("index", 0))
    except Exception:
        return 0


def save_index(index):
    STATE_FILE.write_text(
        json.dumps({"index": index}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def create_card(recipe, output_path):
    width = height = 1080
    img = Image.new("RGB", (width, height), (247, 239, 225))
    draw = ImageDraw.Draw(img)

    title_font = get_font(66, bold=True)
    subtitle_font = get_font(34)
    small_font = get_font(28)
    brand_font = get_font(30, bold=True)

    draw.rounded_rectangle((55, 55, 1025, 1025), radius=42, fill=(255, 252, 246))
    draw.rounded_rectangle((55, 55, 1025, 240), radius=42, fill=(233, 222, 197))

    emoji = recipe.get("emoji", "🍽️")
    draw.text((100, 100), emoji, font=get_font(86), fill=(60, 52, 45))

    title_lines = wrap_text(draw, recipe["title"], title_font, 750)
    y = 92
    for line in title_lines[:2]:
        draw.text((220, y), line, font=title_font, fill=(55, 48, 42))
        y += 78

    draw.text((100, 310), "Домашний рецепт для всей семьи", font=subtitle_font, fill=(95, 80, 67))

    info = f"⏱ {recipe.get('time', '30 минут')}   •   🍽 {recipe.get('servings', '4 порции')}"
    draw.text((100, 380), info, font=small_font, fill=(95, 80, 67))

    ingredients = recipe.get("ingredients", [])
    draw.text((100, 470), "Что понадобится:", font=get_font(34, bold=True), fill=(55, 48, 42))
    y = 530
    for item in ingredients[:6]:
        line = f"• {item}"
        for wrapped in wrap_text(draw, line, small_font, 820):
            draw.text((120, y), wrapped, font=small_font, fill=(70, 62, 55))
            y += 42
        y += 4

    draw.text((100, 940), "Рецепты для всей семьи", font=brand_font, fill=(95, 80, 67))
    img.save(output_path, quality=92)


def build_caption(recipe):
    ingredients = "\n".join(f"• {x}" for x in recipe["ingredients"])
    steps = "\n".join(f"{i + 1}. {x}" for i, x in enumerate(recipe["steps"]))

    return (
        f"<b>{recipe.get('emoji', '🍽️')} {recipe['title']}</b>\n\n"
        f"<b>Ингредиенты:</b>\n{ingredients}\n\n"
        f"<b>Приготовление:</b>\n{steps}\n\n"
        f"⏱ {recipe.get('time', '30 минут')}   "
        f"🍽 {recipe.get('servings', '4 порции')}\n\n"
        f"#рецепты #готовимдома #семейныйужин"
    )


def send_recipe():
    recipes = load_recipes()
    index = load_index() % len(recipes)
    recipe = recipes[index]

    image_path = BASE_DIR / "recipe_card.jpg"
    create_card(recipe, image_path)

    with image_path.open("rb") as photo:
        response = requests.post(
            f"{API_URL}/sendPhoto",
            data={
                "chat_id": CHANNEL,
                "caption": build_caption(recipe),
                "parse_mode": "HTML",
            },
            files={"photo": photo},
            timeout=60,
        )

    if not response.ok:
        raise RuntimeError(f"Ошибка Telegram: {response.status_code} {response.text}")

    save_index(index + 1)
    print(f"{datetime.now(ZoneInfo(TIMEZONE)).isoformat()} — опубликован рецепт: {recipe['title']}", flush=True)


def main():
    for post_time in POST_TIMES:
        schedule.every().day.at(post_time, TIMEZONE).do(send_recipe)
        print(f"Публикация запланирована на {post_time}, часовой пояс {TIMEZONE}", flush=True)

    if os.getenv("POST_ON_START", "false").lower() == "true":
        send_recipe()

    while True:
        schedule.run_pending()
        time.sleep(15)


if __name__ == "__main__":
    main()
