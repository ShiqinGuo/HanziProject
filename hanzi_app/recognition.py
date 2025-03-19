import easyocr
from PIL import Image
import numpy as np

# 初始化简体繁体双阅读器
SIMPLIFIED_READER = easyocr.Reader(['ch_sim'])  # 简体中文识别器
TRADITIONAL_READER = easyocr.Reader(['ch_tra'])  # 繁体中文识别器

def load_image(image_path):
    """加载并验证图像文件"""
    try:
        img = Image.open(image_path)
        return np.array(img)
    except Exception as e:
        raise ValueError(f"图像加载失败: {str(e)}")

def recognize_hanzi(image_path):
    """
    通过可信度比较选择简繁识别结果
    返回格式: (汉字, 字体类型, 可信度)
    """
    # 加载并预处理图像
    image = load_image(image_path)
    
    # 双引擎并行识别
    sim_results = SIMPLIFIED_READER.readtext(image, detail=1)
    trad_results = TRADITIONAL_READER.readtext(image, detail=1)
    
    # 提取最佳候选（取置信度最高结果）
    best_sim = max(sim_results, key=lambda x: x[2], default=None)
    if best_sim[2] < 0.35:
        best_trad = max(trad_results, key=lambda x: x[2], default=None)
        if best_trad[2] > best_sim[2]+0.35:
            return (best_trad[1], '繁体')
        else:
            return (best_sim[1],'简体')
    else:
        return (best_sim[1],'简体')

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