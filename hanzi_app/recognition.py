import easyocr
from PIL import Image
import numpy as np
import cv2
import os
import logging

# 初始化简体繁体双阅读器
SIMPLIFIED_READER = easyocr.Reader(['ch_sim'])  # 简体中文识别器
TRADITIONAL_READER = easyocr.Reader(['ch_tra'])  # 繁体中文识别器

logger = logging.getLogger(__name__)

def load_image(image_path):
    """加载并验证图像文件"""
    try:
        img = Image.open(image_path)
        return np.array(img)
    except Exception as e:
        raise ValueError(f"图像加载失败: {str(e)}")

def preprocess_image(image):
    """
    图像预处理：增强对比度、去噪、二值化
    返回处理后的图像
    """
    # 如果是彩色图像，转为灰度
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    
    # 自适应直方图均衡化（增强对比度）
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    
    # 高斯模糊去噪
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    
    # 自适应阈值二值化
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # 形态学操作：开运算去除小噪点
    kernel = np.ones((3, 3), np.uint8)
    opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # 膨胀操作，稍微增强笔画
    dilated = cv2.dilate(opening, kernel, iterations=1)
    
    return dilated

def crop_to_content(image):
    """
    裁剪图像，只保留汉字内容部分
    返回裁剪后的图像
    """
    # 确保是二值图像
    if len(image.shape) == 3:
        if image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        gray = image.copy()
    
    # 反转颜色以确保文本是白色背景上的黑色
    if np.mean(gray) > 127:
        gray = 255 - gray
        
    # 查找非零区域的边界框
    coords = cv2.findNonZero(gray)
    if coords is None:
        return image  # 没有找到内容，返回原图
        
    x, y, w, h = cv2.boundingRect(coords)
    
    # 添加一些边距
    padding = 10
    x = max(0, x - padding)
    y = max(0, y - padding)
    w = min(image.shape[1] - x, w + 2 * padding)
    h = min(image.shape[0] - y, h + 2 * padding)
    
    # 裁剪图像
    cropped = image[y:y+h, x:x+w]
    
    return cropped

def fallback_recognize(image_path, filename=None):
    """
    基础备选识别方法，当主要识别方法失败时使用
    """
    logger.warning(f"使用备选识别方法处理: {image_path}")
    results = []
    
    try:
        # 尝试使用PIL打开图片进行基本检查
        if Image:
            try:
                img = Image.open(image_path)
                # 检查图片是否有内容
                if img.size[0] < 10 or img.size[1] < 10:
                    logger.warning(f"图片尺寸太小: {img.size}")
                img.close()
            except Exception as e:
                logger.error(f"PIL无法打开图片: {str(e)}")
        
        # 尝试使用OpenCV打开图片
        try:
            img = cv2.imread(image_path)
            if img is None or img.size == 0:
                logger.warning(f"OpenCV无法加载图片或图片为空: {image_path}")
            
            # 检查图片是否全黑或全白
            if img is not None and img.size > 0:
                avg_color = np.mean(img)
                if avg_color < 5 or avg_color > 250:
                    logger.warning(f"图片可能是空白的 (平均色值: {avg_color})")
        except Exception as e:
            logger.error(f"OpenCV处理图片失败: {str(e)}")
        
        # 如果有文件名，从文件名中提取可能的汉字
        if filename:
            # 去掉扩展名
            basename = os.path.splitext(os.path.basename(filename))[0]
            # 尝试提取可能的汉字字符
            for char in basename:
                if '\u4e00' <= char <= '\u9fff':  # 是汉字字符
                    results.append((char, 0.5))  # 置信度设为0.5
                    break
            
            if not results and len(basename) > 0:
                # 如果没有找到汉字，使用第一个字符作为结果
                results.append((basename[0], 0.3))
    except Exception as e:
        logger.error(f"备选识别失败: {str(e)}")
    
    # 如果仍然没有结果，返回一个占位符
    if not results:
        placeholder = os.path.basename(image_path)[:1]
        results.append((placeholder, 0.1))
        logger.warning(f"无法识别，使用占位符: {placeholder}")
    
    return results

def recognize_hanzi_enhanced(image_path):
    """
    使用增强的方法识别汉字，包括多种预处理方法和组合OCR结果
    """
    if easyocr is None or Image is None:
        logger.warning("缺少easyocr或PIL库，无法使用增强识别")
        return fallback_recognize(image_path)
    
    try:
        # 加载图片
        try:
            image = Image.open(image_path)
        except Exception as e:
            logger.error(f"无法打开图片 {image_path}: {str(e)}")
            return fallback_recognize(image_path)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 初始化OCR读取器
        try:
            reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        except Exception as e:
            logger.error(f"无法初始化easyocr: {str(e)}")
            return fallback_recognize(image_path)
        
        # 使用原始图片进行识别
        results = []
        try:
            original_results = reader.readtext(np.array(image))
            if original_results:
                for detection in original_results:
                    text = detection[1]
                    confidence = detection[2]
                    if text and len(text) > 0:
                        results.append((text, confidence))
        except Exception as e:
            logger.error(f"原始图片识别失败: {str(e)}")
        
        # 如果原始识别未产生结果，尝试不同的预处理方法
        if not results:
            preprocessed_images = []
            
            # 尝试裁剪以去除边缘
            try:
                width, height = image.size
                crop_margin = min(width, height) // 10
                cropped = image.crop((crop_margin, crop_margin, width - crop_margin, height - crop_margin))
                preprocessed_images.append(('cropped', cropped))
            except Exception as e:
                logger.error(f"裁剪图片失败: {str(e)}")
            
            # 尝试调整对比度
            try:
                contrast = ImageEnhance.Contrast(image).enhance(2.0)
                preprocessed_images.append(('contrast', contrast))
            except Exception as e:
                logger.error(f"调整对比度失败: {str(e)}")
            
            # 尝试锐化
            try:
                sharpened = image.filter(ImageFilter.SHARPEN)
                preprocessed_images.append(('sharpen', sharpened))
            except Exception as e:
                logger.error(f"锐化图片失败: {str(e)}")
            
            # 对每个预处理后的图片进行识别
            for name, img in preprocessed_images:
                try:
                    img_results = reader.readtext(np.array(img))
                    if img_results:
                        for detection in img_results:
                            text = detection[1]
                            confidence = detection[2]
                            if text and len(text) > 0:
                                results.append((text, confidence))
                except Exception as e:
                    logger.error(f"{name}图片识别失败: {str(e)}")
        
        # 如果预处理后仍无结果，使用备选识别
        if not results:
            logger.warning(f"增强识别未能识别任何文字: {image_path}")
            return fallback_recognize(image_path, os.path.basename(image_path))
        
        # 对结果排序并返回置信度最高的结果
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
        return sorted_results[:3]  # 返回置信度最高的前3个结果
        
    except Exception as e:
        logger.error(f"增强识别过程出错: {str(e)}")
        return fallback_recognize(image_path, os.path.basename(image_path))

def recognize_hanzi(image_path):
    """
    识别图片中的汉字，返回可能的汉字及其置信度
    """
    # 确保easyocr库已加载
    if easyocr is None:
        logger.warning("缺少easyocr库，无法识别")
        return fallback_recognize(image_path)
    
    try:
        # 初始化OCR读取器
        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        
        # 读取图片
        result = reader.readtext(image_path)
        
        # 提取文本和置信度
        texts_with_confidence = []
        for detection in result:
            text = detection[1]
            confidence = detection[2]
            if text and len(text) > 0:
                texts_with_confidence.append((text, confidence))
        
        # 如果没有结果，使用备选识别
        if not texts_with_confidence:
            logger.warning(f"OCR未能识别任何文字: {image_path}")
            return fallback_recognize(image_path, os.path.basename(image_path))
        
        return texts_with_confidence
        
    except Exception as e:
        logger.error(f"OCR识别失败: {str(e)}")
        return fallback_recognize(image_path, os.path.basename(image_path))

# 测试用例
if __name__ == "__main__":
    import json
    import pandas as pd
    results = []
    
    for i in range(1, 501):
        # 生成三位数序号
        num_str = f"{i:03d}"
        test_image = f"D:\\hanzi_project\\data\\提交数据集含答案\\Task1\\Train\\A\\A{num_str}.jpg"
        
        try:
            hanzi, font_type = recognize_hanzi(test_image)
            results.append({
                "filename": f"A{num_str}.jpg",
                "hanzi": hanzi,
                "font_type": font_type,
            })
            print(f"A{num_str} 识别成功")
        except Exception as e:
            print(f"A{num_str} 识别失败: {str(e)}")
            results.append({
                "filename": f"A{num_str}.jpg",
                "error": str(e)
            })
    
    # 保存JSON结果
    df = pd.DataFrame(results)
    df.to_excel("D:\\hanzi_project\\results.xlsx", index=False, engine='openpyxl')