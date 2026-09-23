import os
import io
import datetime
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    font_names = [
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    for fn in font_names:
        try:
            return ImageFont.truetype(fn, size)
        except Exception:
            pass
    return ImageFont.load_default()

def generate_receipt_image(
    order_id: str,
    username: str,
    product_name: str,
    amount_str: str,
    price_str: str,
    date_str: str | None = None,
    status: str = "TO'LANDI"
) -> Image.Image:
    """Generate a sleek, high-resolution dark-themed receipt image."""
    if not date_str:
        date_str = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M")

    width = 800
    height = 1020

    # Base background #0d1117
    img = Image.new("RGBA", (width, height), (13, 17, 23, 255))
    draw = ImageDraw.Draw(img)

    # Outer Card Frame
    card_x0, card_y0 = 35, 35
    card_x1, card_y1 = width - 35, height - 35

    # Card Body #161b22 with cyan accent border #38bdf8
    draw.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=26,
        fill=(22, 27, 34, 255),
        outline=(56, 189, 248, 140),
        width=2
    )

    # Top Header Gradient Banner
    header_h = 120
    draw.rounded_rectangle(
        [card_x0 + 15, card_y0 + 15, card_x1 - 15, card_y0 + header_h],
        radius=18,
        fill=(30, 41, 59, 255),
        outline=(56, 189, 248, 90),
        width=1
    )

    font_title = get_font(36, bold=True)
    font_sub = get_font(20, bold=False)
    font_badge = get_font(22, bold=True)
    font_item = get_font(30, bold=True)
    font_price = get_font(38, bold=True)
    font_label = get_font(21, bold=False)
    font_value = get_font(23, bold=True)
    font_foot = get_font(18, bold=True)
    font_small = get_font(15, bold=False)

    # Header branding
    draw.text((width // 2, card_y0 + 48), "COINSTAT UZ", fill=(255, 255, 255), font=font_title, anchor="mm")
    draw.text((width // 2, card_y0 + 90), "RASMIY TO'LOV KVITANSIYASI", fill=(147, 197, 253), font=font_sub, anchor="mm")

    # Status Pill
    pill_w = 340
    pill_h = 46
    pill_x0 = (width - pill_w) // 2
    pill_y0 = card_y0 + 145
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x0 + pill_w, pill_y0 + pill_h],
        radius=23,
        fill=(16, 185, 129, 35),
        outline=(52, 211, 153, 220),
        width=2
    )

    # Vector green circle with white checkmark
    circle_r = 13
    circle_cx = pill_x0 + 35
    circle_cy = pill_y0 + pill_h // 2
    draw.ellipse([circle_cx - circle_r, circle_cy - circle_r, circle_cx + circle_r, circle_cy + circle_r], fill=(16, 185, 129, 255))
    chk_pts = [(circle_cx - 6, circle_cy), (circle_cx - 2, circle_cy + 5), (circle_cx + 6, circle_cy - 4)]
    draw.line(chk_pts, fill=(255, 255, 255), width=3)

    draw.text((pill_x0 + 55 + (pill_w - 65) // 2, pill_y0 + pill_h // 2), f"{status}", fill=(52, 211, 153), font=font_badge, anchor="mm")

    # Amount & Price Display Box
    box_y0 = pill_y0 + 70
    box_y1 = box_y0 + 155
    draw.rounded_rectangle(
        [card_x0 + 25, box_y0, card_x1 - 25, box_y1],
        radius=20,
        fill=(30, 36, 46, 255),
        outline=(255, 255, 255, 25),
        width=1
    )

    draw.text((width // 2, box_y0 + 44), f"{product_name} • {amount_str}", fill=(251, 191, 36), font=font_item, anchor="mm")
    draw.text((width // 2, box_y0 + 104), f"{price_str}", fill=(255, 255, 255), font=font_price, anchor="mm")

    # Divider
    div_y = box_y1 + 30
    draw.line([(card_x0 + 35, div_y), (card_x1 - 35, div_y)], fill=(48, 54, 61), width=2)

    # Clean username display
    clean_user = str(username).strip()
    if clean_user and not clean_user.startswith("@") and not clean_user.isdigit():
        clean_user = f"@{clean_user}"

    # Key-Value details
    rows = [
        ("Buyurtma ID:", f"#{order_id}"),
        ("Xaridor / Qabul qiluvchi:", clean_user),
        ("Sana va vaqt:", date_str),
        ("To'lov usuli:", "CoinStat Balans"),
        ("Yetkazib berish:", "Avtomatik (Fragment)"),
        ("Tekshiruvchi / Admin:", "@cofeature"),
        ("Rasmiy Kanal:", "@CoinStatUz")
    ]

    cur_y = div_y + 35
    for label, val in rows:
        draw.text((card_x0 + 40, cur_y), label, fill=(139, 148, 158), font=font_label, anchor="lm")
        draw.text((card_x1 - 40, cur_y), val, fill=(240, 246, 252), font=font_value, anchor="rm")
        cur_y += 44

    # Bottom Divider
    bot_y = cur_y + 15
    draw.line([(card_x0 + 35, bot_y), (card_x1 - 35, bot_y)], fill=(48, 54, 61), width=2)

    # Footer
    draw.text((width // 2, bot_y + 35), "XARIDINGIZ UCHUN RAHMAT!", fill=(56, 189, 248), font=font_foot, anchor="mm")
    draw.text((width // 2, bot_y + 65), "Ishonchli va Tezkor Xizmat • https://t.me/CoinStatUz", fill=(110, 118, 129), font=font_small, anchor="mm")

    return img

def generate_receipt_bytes(
    order_id: str,
    username: str,
    product_name: str,
    amount_str: str,
    price_str: str,
    date_str: str | None = None,
    status: str = "TO'LANDI"
) -> bytes:
    """Generate receipt PNG image as bytes buffer."""
    img = generate_receipt_image(order_id, username, product_name, amount_str, price_str, date_str, status)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
