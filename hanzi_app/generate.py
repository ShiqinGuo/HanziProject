import sys
sys.path.append('d:\\hanzi_project')  # 添加项目根目录到Python路径
from pypinyin import pinyin, Style
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import os
from django.conf import settings
# 修正Django环境配置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hanzi_project.settings')
import django
django.setup()

def generate_hanzi_image(char, size=224):
    """
    生成汉字标准图片
    :param char: 单个汉字字符
    :param size: 图片尺寸(224x224)
    :return: 图片保存路径
    """
    # 创建输出目录
    output_dir = os.path.join(settings.MEDIA_ROOT, "standard_images")
    os.makedirs(output_dir, exist_ok=True)
    
    # 使用楷体字体
    font = ImageFont.truetype("simkai.ttf", size-20)  # 系统楷体
    
    # 创建白色背景图片
    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    
    # 居中绘制汉字
    draw.text((size//2, size//2), char, fill="black", font=font, anchor="mm")
    
    # 保存图片
    output_path = os.path.join(output_dir, f"{char}.jpg")
    img.save(output_path, "JPEG", quality=95)
    return output_path

def get_pinyin(hanzi):
    """
    获取汉字的拼音
    :param hanzi: 输入的汉字
    :return: 汉字对应的拼音列表
    """
    pinyin_list = pinyin(hanzi)
    result = [p[0] for p in pinyin_list]
    return result


def get_stroke_order(hanzi):
    """
    从本地文件获取汉字笔顺
    :param hanzi: 输入的汉字
    :return: 各字符对应的笔顺列表
    """
    stroke_data = {}
    # 读取笔顺文件
    with open("Strokes.txt", "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 5:
                character = parts[1]
                strokes = parts[4]
                stroke_data[character] = strokes
    return [stroke_data.get(char, None) for char in hanzi]


def get_pinyin_and_stroke(hanzi):
    """
    组合拼音和笔顺查询结果
    """
    return {
        "pinyin": get_pinyin(hanzi),
        "stroke_order": get_stroke_order(hanzi),
        "image_paths": [generate_hanzi_image(char) for char in hanzi]  # 新增图片路径字段
    }

def generate_all_standard_images():
    """
    批量生成所有标准汉字图片并更新数据库（从数据库读取汉字）
    """
    from hanzi_app.models import Hanzi
    # 从数据库获取所有汉字字符
    characters = Hanzi.objects.values_list('character', flat=True).distinct()
    
    save_dir =  "standard_images"
    os.makedirs(save_dir, exist_ok=True)

    for char in characters:
        try:
            save_path = os.path.join(save_dir, f"{char}.jpg")
            char_path = os.path.join(settings.MEDIA_ROOT, save_path)
            # 仅当图片不存在时才生成
            if not os.path.exists(char_path):
                # 修改生成函数调用路径
                generate_hanzi_image(char)  # 传入输出目录参数
                
            # 更新所有匹配字符的记录
            Hanzi.objects.filter(character=char).update(standard_image=save_path)
            
        except Exception as e:
            print(f"处理字符 {char} 时出错: {str(e)}")

# 测试代码
if __name__ == "__main__":
    generate_all_standard_images()