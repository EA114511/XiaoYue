"""
小玥 AI 语音助手 — App 图标与启动画面生成器

生成符合「月夜 · 明珠」设计主题的 Android 素材：
- icon-only.png / icon-foreground.png / icon-background.png
- splash.png / splash-dark.png

设计元素：
- 背景色：#090C14（墨蓝）
- 主色调：#E4B56A（月光暖金）
- 辅助色：#9FD4CB（青瓷冷绿）
- 核心图形：呼吸光球（玥珠）+ 「玥」字印章
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

# 设计 Token
COLORS = {
    'ink_0': (9, 12, 20),        # #090C14
    'ink_1': (13, 18, 32),       # #0D1220
    'ink_2': (18, 24, 42),       # #12182A
    'ink_3': (27, 35, 64),       # #1B2340
    'gold': (228, 181, 106),     # #E4B56A
    'gold_2': (243, 217, 164),   # #F3D9A4
    'celadon': (159, 212, 203),  # #9FD4CB
    'pearl': (239, 231, 211),    # #EFE7D3
    'mist': (126, 142, 166),     # #7E8EA6
}

# 输出目录
OUTPUT_DIR = 'voice-assistant/frontend/assets'
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_background(size, color='ink_0'):
    """创建纯色背景"""
    img = Image.new('RGB', (size, size), COLORS[color])
    return img


def draw_glow_orb(draw, center, radius, color, glow_intensity=0.3):
    """绘制发光光球"""
    x, y = center

    # 外层光晕
    for i in range(10, 0, -1):
        alpha = int(glow_intensity * 255 * (i / 10))
        r = radius * (1 + i * 0.15)
        bbox = [x - r, y - r, x + r, y + r]
        draw.ellipse(bbox, fill=color + (alpha,))

    # 核心光球
    bbox = [x - radius, y - radius, x + radius, y + radius]
    draw.ellipse(bbox, fill=color + (255,))

    # 高光
    highlight_r = radius * 0.3
    highlight_offset = radius * 0.25
    bbox = [
        x - highlight_offset - highlight_r,
        y - highlight_offset - highlight_r,
        x - highlight_offset + highlight_r,
        y - highlight_offset + highlight_r
    ]
    draw.ellipse(bbox, fill=(255, 255, 255, 120))


def draw_seal_character(draw, center, char='玥', size=200, color=COLORS['gold']):
    """绘制印章字符"""
    x, y = center

    # 尝试加载中文字体（优先使用支持「玥」的字体）
    font_paths = [
        'C:/Windows/Fonts/simhei.ttf',      # 黑体（通常支持较全）
        'C:/Windows/Fonts/msyh.ttc',        # 微软雅黑
        'C:/Windows/Fonts/simsun.ttc',      # 宋体
        '/System/Library/Fonts/PingFang.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    ]

    font = None
    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                # 测试字体是否支持「玥」
                bbox = font.getbbox(char)
                if bbox[2] > 0 and bbox[3] > 0:  # 宽度和高度都大于0
                    break
            except:
                continue

    if font is None:
        font = ImageFont.load_default()
        size = size // 2

    # 绘制印章边框（圆角矩形）
    border_width = max(4, int(size * 0.04))
    border_radius = size * 0.55
    bbox = [x - border_radius, y - border_radius, x + border_radius, y + border_radius]

    # 边框
    draw.rounded_rectangle(bbox, radius=int(size * 0.08), outline=color + (220,), width=border_width)

    # 绘制字符
    bbox = draw.textbbox((0, 0), char, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = x - text_width // 2
    text_y = y - text_height // 2 - bbox[1]

    # 绘制字符外发光
    for offset in range(3, 0, -1):
        alpha = 40 * offset
        for dx in [-offset, 0, offset]:
            for dy in [-offset, 0, offset]:
                if dx != 0 or dy != 0:
                    draw.text((text_x + dx, text_y + dy), char, font=font, fill=color + (alpha,))

    # 绘制主字符
    draw.text((text_x, text_y), char, font=font, fill=color + (255,))


def draw_stars(draw, width, height, count=30, max_brightness=150):
    """绘制星空背景"""
    import random
    random.seed(42)  # 固定种子，确保可重复

    for _ in range(count):
        x = random.randint(0, width)
        y = random.randint(0, height)
        brightness = random.randint(80, max_brightness)
        size = random.randint(1, 3)

        # 星星颜色：偏暖白或偏冷白
        if random.random() > 0.5:
            color = (brightness, brightness, brightness, brightness)
        else:
            color = (brightness, brightness + 10, brightness + 20, brightness)

        draw.ellipse([x - size, y - size, x + size, y + size], fill=color)


def draw_moon(draw, center, radius, phase=0.7):
    """绘制月亮（带相位）"""
    x, y = center

    # 满月轮廓
    bbox = [x - radius, y - radius, x + radius, y + radius]
    draw.ellipse(bbox, fill=COLORS['pearl'] + (60,))

    # 暗部（模拟月相）
    shadow_offset = radius * (1 - phase)
    shadow_bbox = [x - radius - shadow_offset, y - radius, x + radius - shadow_offset, y + radius]
    draw.ellipse(shadow_bbox, fill=COLORS['ink_0'] + (100,))


def create_icon_only():
    """生成 icon-only.png（512x512）"""
    size = 512
    img = Image.new('RGBA', (size, size), COLORS['ink_0'] + (255,))
    draw = ImageDraw.Draw(img, 'RGBA')

    center = (size // 2, size // 2)
    orb_radius = size * 0.28

    # 绘制星空背景
    draw_stars(draw, size, size, count=20, max_brightness=100)

    # 绘制光球
    draw_glow_orb(draw, center, orb_radius, COLORS['gold'], glow_intensity=0.4)

    # 绘制印章
    draw_seal_character(draw, center, char='玥', size=int(size * 0.25))

    img.save(os.path.join(OUTPUT_DIR, 'icon-only.png'))
    print(f'✓ 生成 icon-only.png ({size}x{size})')


def create_icon_foreground():
    """生成 icon-foreground.png（512x512，透明背景）"""
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, 'RGBA')

    center = (size // 2, size // 2)
    orb_radius = size * 0.28

    # 绘制光球
    draw_glow_orb(draw, center, orb_radius, COLORS['gold'], glow_intensity=0.4)

    # 绘制印章
    draw_seal_character(draw, center, char='玥', size=int(size * 0.25))

    img.save(os.path.join(OUTPUT_DIR, 'icon-foreground.png'))
    print(f'✓ 生成 icon-foreground.png ({size}x{size})')


def create_icon_background():
    """生成 icon-background.png（512x512，纯色背景）"""
    size = 512
    img = Image.new('RGB', (size, size), COLORS['ink_0'])
    img.save(os.path.join(OUTPUT_DIR, 'icon-background.png'))
    print(f'✓ 生成 icon-background.png ({size}x{size})')


def create_splash(dark_mode=True):
    """生成启动画面（2732x2732）"""
    size = 2732
    img = Image.new('RGBA', (size, size), COLORS['ink_0'] + (255,))
    draw = ImageDraw.Draw(img, 'RGBA')

    center = (size // 2, size // 2)

    # 绘制星空背景
    draw_stars(draw, size, size, count=80, max_brightness=120)

    # 绘制月亮（右上角）
    moon_center = (int(size * 0.75), int(size * 0.25))
    moon_radius = size * 0.08
    draw_moon(draw, moon_center, moon_radius, phase=0.75)

    # 绘制主光球（中央偏下）
    orb_center = (size // 2, int(size * 0.45))
    orb_radius = size * 0.12
    draw_glow_orb(draw, orb_center, orb_radius, COLORS['gold'], glow_intensity=0.35)

    # 绘制印章
    draw_seal_character(draw, orb_center, char='玥', size=int(size * 0.10))

    # 绘制底部文字
    font_paths = [
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
    ]
    font = None
    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, int(size * 0.04))
                break
            except:
                continue

    if font:
        text = '小玥'
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = center[0] - text_width // 2
        text_y = center[1] + size * 0.15
        draw.text((text_x, text_y), text, font=font, fill=COLORS['pearl'] + (200,))

        # 副标题
        sub_font = ImageFont.truetype(path, int(size * 0.018)) if os.path.exists(path) else None
        if sub_font:
            sub_text = 'AI 语音助手'
            bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
            sub_width = bbox[2] - bbox[0]
            sub_x = center[0] - sub_width // 2
            sub_y = text_y + size * 0.05
            draw.text((sub_x, sub_y), sub_text, font=sub_font, fill=COLORS['mist'] + (150,))

    filename = 'splash-dark.png' if dark_mode else 'splash.png'
    img.save(os.path.join(OUTPUT_DIR, filename))
    print(f'✓ 生成 {filename} ({size}x{size})')


def main():
    print('=' * 50)
    print('小玥 AI 语音助手 — App 素材生成')
    print('=' * 50)

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 生成图标
    create_icon_only()
    create_icon_foreground()
    create_icon_background()

    # 生成启动画面
    create_splash(dark_mode=True)
    create_splash(dark_mode=False)

    print('=' * 50)
    print(f'素材已保存到：{OUTPUT_DIR}')
    print('下一步：')
    print('1. 检查生成的 PNG 文件')
    print('2. 运行 npx capacitor-assets generate --android')
    print('=' * 50)


if __name__ == '__main__':
    main()
