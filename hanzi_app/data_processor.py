import json
import os
import pandas as pd
import importlib.util

def import_recognition_module():
    """
    动态导入recognition模块，降低耦合度
    """
    try:
        from hanzi_app.recognition import recognize_hanzi
        return recognize_hanzi
    except ImportError:
        # 如果无法直接导入，尝试动态导入
        try:
            spec = importlib.util.find_spec('hanzi_app.recognition')
            if spec is None:
                # 尝试当前目录
                current_dir = os.path.dirname(os.path.abspath(__file__))
                recognition_path = os.path.join(current_dir, 'recognition.py')
                if os.path.exists(recognition_path):
                    spec = importlib.util.spec_from_file_location('recognition', recognition_path)
                    
            if spec:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.recognize_hanzi
        except Exception as e:
            print(f"动态导入recognition模块失败: {str(e)}")
    
    # 如果都失败了，返回一个模拟函数
    return lambda image_path: ('未识别', '简体')

def get_json_value(json_file, key):
    """
    从JSON文件中获取指定键的值
    
    Args:
        json_file: JSON文件路径
        key: 需要获取值的键
        
    Returns:
        键对应的值，如果键不存在返回None
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get(key)
    except Exception as e:
        print(f"获取JSON数据失败: {str(e)}")
        return None

def process_hanzi_data(image_folder, level_json=None, comment_json=None, output_excel=None, test_mode=False):
    """
    处理汉字数据，包括识别图片中的汉字、获取等级和评语
    
    Args:
        image_folder: 图片文件夹路径
        level_json: 等级JSON文件路径
        comment_json: 评语JSON文件路径
        output_excel: 输出Excel文件路径
        test_mode: 测试模式，只处理少量图片
        
    Returns:
        处理结果DataFrame
    """
    if not os.path.exists(image_folder):
        raise ValueError(f"图片文件夹不存在: {image_folder}")
    
    # 动态导入recognize_hanzi函数
    recognize_hanzi = import_recognition_module()
    
    results = []
    failed_images = []
    
    # 获取文件夹中的所有jpg文件
    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith('.jpg')]
    
    # 测试模式只处理前5张图片
    if test_mode and len(image_files) > 5:
        image_files = image_files[:5]
        print("测试模式：只处理前5张图片")
    
    for image_file in image_files:
        image_path = os.path.join(image_folder, image_file)
        file_name_without_ext = os.path.splitext(image_file)[0]
        
        # 默认值
        character = ""
        structure = "未知结构"
        variant = "简体"
        level = "D"
        comment = "无"
        recognition_success = False
        
        # 识别汉字
        try:
            hanzi_result = recognize_hanzi(image_path)
            if hanzi_result:
                character, font_type = hanzi_result
                variant = font_type
                recognition_success = True
        except Exception as e:
            failed_images.append(f"{image_file}: {str(e)}")
        
        # 获取等级
        if level_json and os.path.exists(level_json):
            level_value = get_json_value(level_json, image_file)
            if level_value:
                level = level_value
        
        # 获取评语
        if comment_json and os.path.exists(comment_json):
            comment_value = get_json_value(comment_json, image_file)
            if comment_value:
                comment = comment_value
        
        # 添加结果
        results.append({
            "image_file": file_name_without_ext,
            "character": character,
            "structure": structure,
            "variant": variant,
            "level": level,
            "comment": comment,
            "recognition_success": recognition_success
        })
    
    # 创建DataFrame
    df = pd.DataFrame(results)
    
    # 保存到Excel
    if output_excel:
        df.to_excel(output_excel, index=False, engine='openpyxl')
        print(f"结果已保存到: {output_excel}")
        
        # 如果有识别失败的图片，将其写入到日志文件
        if failed_images:
            log_file = f"{os.path.splitext(output_excel)[0]}_failed.log"
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(failed_images))
            print(f"识别失败的图片列表已保存到: {log_file}")
    
    return df

if __name__ == "__main__":
    # 示例用法 - 可用于独立测试
    import argparse
    
    parser = argparse.ArgumentParser(description='汉字数据处理器')
    parser.add_argument('--image_folder', type=str, required=True, help='图片文件夹路径')
    parser.add_argument('--level_json', type=str, help='等级JSON文件路径')
    parser.add_argument('--comment_json', type=str, help='评语JSON文件路径')
    parser.add_argument('--output_excel', type=str, required=True, help='输出Excel文件路径')
    parser.add_argument('--test', action='store_true', help='测试模式')
    
    args = parser.parse_args()
    
    df = process_hanzi_data(
        args.image_folder, 
        args.level_json, 
        args.comment_json, 
        args.output_excel,
        test_mode=args.test
    )
    print(f"处理完成，共处理 {len(df)} 个文件") 