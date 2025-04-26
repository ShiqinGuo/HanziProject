import json
import os
import zipfile
import pandas as pd
import tempfile
import shutil
import logging
import argparse
from typing import Dict, Optional, Union, List, Tuple, Any
from datetime import datetime

from hanzi_app.data_processor import import_recognition_module
from django.conf import settings

logger = logging.getLogger(__name__)

def extract_zip_to_temp(zip_path: str) -> Tuple[str, str]:
    """
    解压ZIP文件到临时目录
    
    Args:
        zip_path: ZIP文件路径
        
    Returns:
        临时目录路径和创建的图片文件夹路径
    """
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="hanzi_import_")
    img_folder = os.path.join(temp_dir, "img")
    os.makedirs(img_folder, exist_ok=True)
    
    # 解压文件
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 只提取图片文件到img子文件夹
            for file in zip_ref.namelist():
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    # 只获取文件名，不要路径
                    filename = os.path.basename(file)
                    if filename:  # 跳过目录
                        source = zip_ref.open(file)
                        target = open(os.path.join(img_folder, filename), "wb")
                        with source, target:
                            shutil.copyfileobj(source, target)
    except Exception as e:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError(f"解压ZIP文件失败: {str(e)}")
        
    return temp_dir, img_folder

def load_json_data(json_path: str) -> Dict:
    """
    加载JSON数据
    
    Args:
        json_path: JSON文件路径
        
    Returns:
        JSON数据字典
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise ValueError(f"加载JSON文件失败: {str(e)}")

def detect_json_type(json_data: Dict) -> Dict[str, str]:
    """
    自动检测JSON数据类型，判断是否包含level或comment
    
    Args:
        json_data: JSON数据
        
    Returns:
        包含检测结果的字典，键为'level'或'comment'，值为对应的JSON键
    """
    detected_types = {}
    
    # 检查是否是扁平结构，键为文件名，值为简单值
    if json_data and isinstance(json_data, dict):
        # 取第一个键值对作为样本
        sample_key = next(iter(json_data))
        sample_value = json_data[sample_key]
        
        # 如果值是简单类型（字符串、数字等）
        if isinstance(sample_value, (str, int)):
            # 判断值是否为level（A、B、C、D等级）
            if isinstance(sample_value, str) and len(sample_value) == 1 and sample_value in ['A', 'B', 'C', 'D']:
                detected_types['level'] = None  # 直接使用顶级结构
                
            # 如果值看起来是评论（多于一个字符的文本）
            elif isinstance(sample_value, str) and len(sample_value) > 1:
                detected_types['comment'] = None  # 直接使用顶级结构
    
    # 检查是否是复杂结构，拥有专门的level或comment键
    for key in json_data.keys():
        # 检查常见的level键名
        if key.lower() in ['level', 'levels', 'grade', 'grades', '等级']:
            # 检查该键的值是否是字典
            if isinstance(json_data[key], dict):
                # 取第一个键值对作为样本
                if json_data[key]:
                    sample_inner_key = next(iter(json_data[key]))
                    sample_inner_value = json_data[key][sample_inner_key]
                    
                    # 如果值看起来像等级（A、B、C、D）
                    if isinstance(sample_inner_value, str) and len(sample_inner_value) == 1 and sample_inner_value in ['A', 'B', 'C', 'D']:
                        detected_types['level'] = key
        
        # 检查常见的comment键名
        elif key.lower() in ['comment', 'comments', 'remark', 'remarks', '评论', '评语', '备注']:
            # 检查该键的值是否是字典
            if isinstance(json_data[key], dict):
                # 如果有内容，假定这是comments
                if json_data[key]:
                    detected_types['comment'] = key
    
    return detected_types

def clean_import_results_folder(output_dir: str) -> None:
    """
    清理导入结果文件夹
    
    Args:
        output_dir: 输出目录路径
    """
    try:
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                file_path = os.path.join(output_dir, filename)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
        print(f"已清理导入结果文件夹: {output_dir}")
    except Exception as e:
        print(f"清理导入结果文件夹失败: {str(e)}")

def get_json_value(json_data, file_name, key=None):
    """
    从JSON数据中获取指定文件名对应的值
    
    Args:
        json_data: JSON数据字典
        file_name: 文件名
        key: 如果JSON是嵌套结构，则需要提供要获取的键名
        
    Returns:
        获取到的值，如果没有找到则返回None
    """
    if not json_data or not file_name:
        return None
        
    # 尝试不同方式获取数据
    base_name = os.path.splitext(file_name)[0]  # 不带扩展名的文件名
    
    # 方式1: 直接以完整文件名为键
    if file_name in json_data:
        value = json_data[file_name]
        if key and isinstance(value, dict):
            return value.get(key)
        return value
        
    # 方式2: 以不带扩展名的文件名为键
    if base_name in json_data:
        value = json_data[base_name]
        if key and isinstance(value, dict):
            return value.get(key)
        return value
    
    # 方式3: 模糊匹配，查找包含文件名的键
    for json_key in json_data:
        if file_name in json_key or base_name in json_key:
            value = json_data[json_key]
            if key and isinstance(value, dict):
                return value.get(key)
            return value
            
    # 如果以上方式都找不到，记录警告并返回None
    logger.warning(f"在JSON数据中找不到与文件 {file_name} 匹配的键")
    return None

def clean_import_results():
    """
    清理media/import_results目录中的文件
    
    Returns:
        bool: 是否成功清理
    """
    try:
        import_results_dir = os.path.join(settings.MEDIA_ROOT, "import_results")
        if os.path.exists(import_results_dir):
            for file_name in os.listdir(import_results_dir):
                file_path = os.path.join(import_results_dir, file_name)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            logger.info("已清理导入结果目录")
            return True
        return False
    except Exception as e:
        logger.error(f"清理导入结果目录失败: {str(e)}")
        return False

def import_hanzi_data(
    image_folder_path: str,
    json_file_path: str,
    output_dir: str = "media/import_results",
    json_mappings: dict = None,
    test_mode: bool = False,
    enhanced_recognition: bool = False,
    status_callback = None
) -> dict:
    """
    导入汉字图片数据并与JSON答案进行匹配，生成Excel文件
    
    Args:
        image_folder_path: 图片文件夹路径
        json_file_path: JSON答案文件路径
        output_dir: 输出目录，默认为media/import_results
        json_mappings: JSON字段映射，例如 {'level': 'levels', 'comment': 'comments'}
        test_mode: 是否为测试模式（只处理少量图片）
        enhanced_recognition: 是否启用增强识别模式
        status_callback: 状态更新回调函数，格式为 fn(progress, message)
        
    Returns:
        包含更多信息的结果字典
        
    Raises:
        FileNotFoundError: 如果图片文件夹或JSON文件不存在
        ImportError: 如果无法导入文本识别模块
        ValueError: 如果没有有效的识别结果或JSON格式不支持
    """
    # 检查图片文件夹是否存在
    if not os.path.exists(image_folder_path):
        raise FileNotFoundError(f"图片文件夹不存在: {image_folder_path}")
        
    # 检查JSON文件是否存在
    if not os.path.exists(json_file_path):
        raise FileNotFoundError(f"JSON文件不存在: {json_file_path}")
    
    # 状态回调
    def update_status(progress, message):
        if status_callback:
            status_callback(progress, message)
        logger.info(f"导入进度: {progress}%, {message}")
    
    update_status(5, "正在加载识别模块...")
    
    # 导入文本识别模块
    try:
        # 首先尝试从data_processor导入
        from hanzi_app.data_processor import import_recognition_module
        recognize_text = import_recognition_module()
        
        # 如果启用增强识别，尝试使用增强版本
        if enhanced_recognition:
            try:
                from hanzi_app.recognition import recognize_hanzi_enhanced
                recognize_text = recognize_hanzi_enhanced
                logger.info("使用增强识别模式")
            except ImportError:
                logger.warning("增强识别模块不可用，使用标准识别")
        
        if not recognize_text:
            logger.warning("标准识别模块加载失败，尝试使用备用识别")
            # 尝试导入备用识别函数
            try:
                from hanzi_app.recognition import fallback_recognize
                recognize_text = fallback_recognize
                logger.info("使用备用识别模式")
            except ImportError:
                raise ImportError("所有识别模块导入失败")
    except ImportError:
        # 如果失败，尝试直接导入
        try:
            if enhanced_recognition:
                from hanzi_app.recognition import recognize_hanzi_enhanced as recognize_text
            else:
                try:
                    from hanzi_app.text_recognizer import recognize_text
                except ImportError:
                    from hanzi_app.recognition import fallback_recognize as recognize_text
                    logger.info("使用备用识别模式")
        except ImportError:
            # 如果仍然失败，使用模拟函数
            logger.warning("无法导入文本识别模块，使用模拟函数")
            recognize_text = lambda img_path: ("未识别", "未知")
    
    update_status(10, "正在读取JSON数据...")
        
    # 读取JSON数据
    try:
        with open(json_file_path, 'r', encoding='utf-8') as file:
            json_data = json.load(file)
    except Exception as e:
        raise ValueError(f"读取JSON文件失败: {str(e)}")
        
    if not json_data:
        raise ValueError("JSON文件为空或格式不正确")
    
    update_status(15, "正在分析JSON结构...")
    
    # 自动检测JSON结构类型
    detected_types = detect_json_type(json_data)
    logger.info(f"检测到JSON结构类型: {detected_types}")
    
    # 应用JSON映射
    if json_mappings:
        # 如果提供了映射，应用映射转换
        mapped_data = {}
        for file_key in json_data:
            if isinstance(json_data[file_key], dict):
                # 对于嵌套字典，应用键映射
                mapped_item = {}
                for orig_key, mapped_key in json_mappings.items():
                    if mapped_key in json_data[file_key]:
                        mapped_item[orig_key] = json_data[file_key][mapped_key]
                mapped_data[file_key] = mapped_item
            else:
                # 对于简单值，直接复制
                mapped_data[file_key] = json_data[file_key]
        json_data = mapped_data
    
    # 自动判断JSON字段类型
    json_type = {}
    sample_key = list(json_data.keys())[0] if json_data else ""
    sample_value = json_data.get(sample_key, {})
    
    if isinstance(sample_value, dict):
        # 检查嵌套字典的字段
        available_fields = []
        for field in ['level', 'comment', 'structure', 'variant']:
            if field in sample_value:
                json_type[field] = True
                available_fields.append(field)
        
        if not available_fields:
            logger.warning(f"JSON数据格式不包含已知字段")
            
        logger.info(f"检测到JSON字段: {', '.join(available_fields)}")
    else:
        # 如果是简单值，假设为level
        json_type['level'] = True
        logger.info("检测到JSON格式: 单一值格式 (默认为level)")
    
    update_status(20, "正在获取图片列表...")
    
    # 获取图片文件列表并排序
    try:
        image_files = sorted([f for f in os.listdir(image_folder_path) 
                            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif'))])
        
        if not image_files:
            raise ValueError(f"图片文件夹中没有支持的图片文件: {image_folder_path}")
            
        # 测试模式只处理少量图片
        if test_mode and len(image_files) > 5:
            image_files = image_files[:5]
            logger.info("测试模式：只处理前5张图片")
    except Exception as e:
        raise ValueError(f"读取图片文件夹失败: {str(e)}")
    
    update_status(25, "准备处理图片...")
    
    # 构建文件名和JSON键的映射字典
    file_key_map = build_file_key_map(image_files, json_data)
    logger.info(f"文件名映射构建完成，共找到 {len(file_key_map)} 个映射")
    
    # 处理图片并识别文字
    results = []
    success_count = 0
    failed_count = 0
    total_count = len(image_files)
    failed_files = []
    
    for idx, img_file in enumerate(image_files):
        # 更新进度
        current_progress = 25 + int(70 * idx / total_count)
        update_status(current_progress, f"正在处理图片 {idx+1}/{total_count}: {img_file}")
        
        img_path = os.path.join(image_folder_path, img_file)
        file_name_without_ext = os.path.splitext(img_file)[0]
        
        # 识别文字
        try:
            if enhanced_recognition:
                # 增强识别模式会返回更多信息
                recognition_result = recognize_text(img_path)
                
                # 处理返回结果格式
                if isinstance(recognition_result, list) and len(recognition_result) > 0:
                    # 获取置信度最高的结果
                    char_data = recognition_result[0]
                    recognized_char = char_data[0] if isinstance(char_data, tuple) else str(char_data)
                    confidence = char_data[1] if isinstance(char_data, tuple) and len(char_data) > 1 else 0.5
                elif isinstance(recognition_result, tuple):
                    recognized_char = recognition_result[0]
                    confidence = recognition_result[1] if len(recognition_result) > 1 else 0.5
                else:
                    recognized_char = str(recognition_result)
                    confidence = 0.5
                
                logger.info(f"图片 {img_file} 识别结果: {recognized_char}, 置信度: {confidence}")
            else:
                recognition_result = recognize_text(img_path)
                
                # 处理返回结果格式
                if isinstance(recognition_result, list) and len(recognition_result) > 0:
                    # 获取置信度最高的结果
                    char_data = recognition_result[0]
                    recognized_char = char_data[0] if isinstance(char_data, tuple) else str(char_data)
                    confidence = char_data[1] if isinstance(char_data, tuple) and len(char_data) > 1 else 0.5
                elif isinstance(recognition_result, tuple):
                    recognized_char = recognition_result[0]
                    confidence = recognition_result[1] if len(recognition_result) > 1 else 0.5
                else:
                    recognized_char = str(recognition_result)
                    confidence = 0.5
            
            # 验证识别结果
            if not recognized_char or recognized_char == "未识别" or recognized_char == "识别错误":
                logger.warning(f"图片识别结果无效: {img_file}")
                failed_count += 1
                failed_files.append((img_file, "识别结果无效"))
                
                # 添加一个带默认值的结果记录
                result_row = {
                    'character': "识别失败",
                    'structure': "未知结构",
                    'variant': "简体",
                    'level': "D",
                    'comment': "无",
                    'image_path': img_path,
                    'file_name': file_name_without_ext,
                    'recognition_error': "无有效文字"
                }
            else:
                # 成功识别，创建结果行
                result_row = {
                    'character': recognized_char,
                    'structure': "未知结构",  # 默认结构
                    'variant': "简体",  # 默认变体
                    'level': "D",
                    'comment': "无",
                    'image_path': img_path,
                    'file_name': file_name_without_ext
                }
                success_count += 1
            
            # 根据映射查找对应的JSON键
            json_key = file_key_map.get(file_name_without_ext) or file_name_without_ext
            
            # 根据JSON类型获取对应的值并覆盖默认值
            for field in ['level', 'comment', 'structure', 'variant']:
                if json_type.get(field):
                    field_value = get_json_value(json_data, json_key, field if isinstance(sample_value, dict) else None)
                    if field_value:
                        result_row[field] = field_value
            
            results.append(result_row)
            
        except Exception as e:
            logger.error(f"图片识别异常: {img_file}, 错误: {str(e)}")
            failed_count += 1
            failed_files.append((img_file, str(e)))
            
            # 即使识别失败，添加带默认值的记录
            result_row = {
                'character': "识别失败",
                'structure': "未知结构",
                'variant': "简体",
                'level': "D",
                'comment': "无",
                'image_path': img_path,
                'file_name': file_name_without_ext,
                'recognition_error': str(e)
            }
            
            # 根据映射查找对应的JSON键
            json_key = file_key_map.get(file_name_without_ext) or file_name_without_ext
            
            # 根据JSON类型获取对应的值
            for field in ['level', 'comment', 'structure', 'variant']:
                if json_type.get(field):
                    field_value = get_json_value(json_data, json_key, field if isinstance(sample_value, dict) else None)
                    if field_value:
                        result_row[field] = field_value
            
            results.append(result_row)
    
    update_status(95, "正在生成结果文件...")
    
    # 检查是否有处理成功的图片，改为警告而非错误
    if success_count == 0 and len(image_files) > 0:
        logger.warning("没有图片成功识别，但仍会生成结果文件")
    
    logger.info(f"处理完成：共 {total_count} 张图片，成功 {success_count} 张，失败 {failed_count} 张")
    print(f"处理完成：共 {total_count} 张图片，成功 {success_count} 张，失败 {failed_count} 张")
    
    # 创建输出目录
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"已创建或确认输出目录存在: {output_dir}")
    except Exception as e:
        print(f"创建输出目录失败: {str(e)}")
        raise ValueError(f"创建输出目录失败: {str(e)}")
    
    # 创建Excel文件
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    excel_filename = f"hanzi_import_{timestamp}.xlsx"
    excel_path = os.path.join(output_dir, excel_filename)
    
    print(f"准备创建Excel文件: {excel_path}")
    
    # 写入Excel - 确保字段顺序正确
    try:
        # 提取特定顺序的字段数据
        ordered_results = []
        for row in results:
            ordered_row = {
                'character': row.get('character', "识别失败"),
                'structure': row.get('structure', "未知结构"),
                'variant': row.get('variant', "简体"),
                'level': row.get('level', "D"),
                'comment': row.get('comment', "无"),
                'image_path': row.get('image_path', "")
            }
            ordered_results.append(ordered_row)
        
        # 创建DataFrame并保持指定顺序
        columns = ['character', 'structure', 'variant', 'level', 'comment', 'image_path']
        df = pd.DataFrame(ordered_results, columns=columns)
        
        print(f"DataFrame创建成功，行数: {len(df)}")
        
        # 检查DataFrame是否为空
        if df.empty:
            print("警告：DataFrame为空，无数据写入Excel")
        
        # 写入Excel文件
        df.to_excel(excel_path, index=False)
        
        print(f"Excel文件已写入: {excel_path}")
        
        # 验证文件是否存在
        if os.path.exists(excel_path):
            print(f"Excel文件创建成功，大小: {os.path.getsize(excel_path)} 字节")
        else:
            print(f"警告：Excel文件未能创建，路径不存在: {excel_path}")
        
        # 创建失败日志
        if failed_files:
            log_filename = f"hanzi_import_{timestamp}_failed.log"
            log_path = os.path.join(output_dir, log_filename)
            
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"处理失败的图片列表 ({len(failed_files)}/{total_count}):\n")
                for file_name, error in failed_files:
                    f.write(f"{file_name}: {error}\n")
            
            logger.info(f"已创建失败日志: {log_path}")
            print(f"已创建失败日志: {log_path}")
        
        # 获取可访问的URL
        if output_dir.startswith(settings.MEDIA_ROOT):
            # 相对于media目录的路径
            relative_path = os.path.relpath(excel_path, settings.MEDIA_ROOT)
            excel_url = f"/media/{relative_path.replace('\\', '/')}"
        else:
            # 直接使用文件名作为相对URL
            excel_url = f"/media/import_results/{excel_filename}"
            
        print(f"生成的Excel URL: {excel_url}")
        print(f"实际Excel路径: {excel_path}")
        
        # 清理旧文件（保留当前生成的文件）
        clean_files_except(output_dir, excel_filename)
        if failed_files:
            clean_files_except(output_dir, log_filename)
        
        update_status(100, "导入完成！")
        
        # 返回包含更多信息的结果
        result = {
            'excel_url': excel_url,
            'excel_path': excel_path,
            'total_count': total_count,
            'success_count': success_count,
            'failed_count': failed_count,
            'timestamp': timestamp
        }
        
        return result
    except Exception as e:
        print(f"创建Excel文件失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise ValueError(f"创建Excel文件失败: {str(e)}")

def build_file_key_map(image_files, json_data):
    """
    构建图片文件名与JSON键的映射关系
    使用模糊匹配来提高映射准确率
    
    Args:
        image_files: 图片文件名列表
        json_data: JSON数据
        
    Returns:
        文件名到JSON键的映射字典
    """
    file_key_map = {}
    
    # 获取所有JSON键
    json_keys = list(json_data.keys())
    
    for img_file in image_files:
        # 去除文件扩展名
        file_name = os.path.splitext(img_file)[0]
        
        # 1. 直接精确匹配
        if file_name in json_keys:
            file_key_map[file_name] = file_name
            continue
            
        # 2. 尝试去除前缀的字母（如A001 -> 001）
        if len(file_name) > 1 and not file_name[0].isdigit() and file_name[1:].isdigit():
            numeric_part = file_name[1:]
            for key in json_keys:
                if key.endswith(numeric_part):
                    file_key_map[file_name] = key
                    break
            
            # 如果找到了匹配项，继续下一个文件
            if file_name in file_key_map:
                continue
        
        # 3. 尝试使用部分匹配
        best_match = None
        best_score = 0
        
        for key in json_keys:
            # 计算相似度 - 简单使用最长公共子串长度
            common_len = longest_common_substring_length(file_name, key)
            score = common_len / max(len(file_name), len(key))
            
            if score > best_score and score > 0.5:  # 至少50%相似
                best_score = score
                best_match = key
        
        if best_match:
            file_key_map[file_name] = best_match
            
    return file_key_map

def longest_common_substring_length(s1, s2):
    """
    计算两个字符串的最长公共子串长度
    用于文件名匹配
    """
    m = len(s1)
    n = len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    max_len = 0
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
                max_len = max(max_len, dp[i][j])
    
    return max_len

def clean_files_except(directory, exception_file=None):
    """
    清理目录中除了指定文件外的所有文件
    
    Args:
        directory: 要清理的目录
        exception_file: 要保留的文件名（如果为None则清空整个目录）
    """
    try:
        if not os.path.exists(directory):
            return
            
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if exception_file and filename == exception_file:
                continue
                
            if os.path.isfile(file_path):
                os.unlink(file_path)
                logger.info(f"已删除文件: {file_path}")
    except Exception as e:
        logger.error(f"清理文件夹失败: {str(e)}")

if __name__ == "__main__":
    # 示例用法 - 可用于独立测试
    parser = argparse.ArgumentParser(description='汉字数据导入工具')
    parser.add_argument('--image_folder', type=str, required=True, help='图片文件夹路径')
    parser.add_argument('--json_file', type=str, help='JSON数据文件路径')
    parser.add_argument('--output_dir', type=str, default='media/import_results', help='输出目录路径')
    parser.add_argument('--level_key', type=str, help='JSON中表示等级的键名')
    parser.add_argument('--comment_key', type=str, help='JSON中表示评语的键名')
    parser.add_argument('--clean', action='store_true', help='清理旧导入结果文件')
    
    args = parser.parse_args()
    
    try:
        # 构建JSON映射
        json_mappings = {}
        if args.level_key:
            json_mappings['level'] = args.level_key
        if args.comment_key:
            json_mappings['comment'] = args.comment_key
            
        # 使用新的函数签名
        result = import_hanzi_data(
            args.image_folder,
            args.json_file,
            args.output_dir,
            json_mappings if json_mappings else None
        )
        
        print(f"数据导入完成，结果已保存到: {result['excel_url']}")
    except Exception as e:
        print(f"数据导入失败: {str(e)}")
        import traceback
        traceback.print_exc() 