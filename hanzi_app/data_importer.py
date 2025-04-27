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
import time

from hanzi_app.recognition import recognize_hanzi
from django.conf import settings

logger = logging.getLogger(__name__)

def extract_zip_to_temp(zip_path: str) -> Tuple[str, str]:
    """解压ZIP文件到临时目录，只提取图片文件"""
    # 创建临时目录
    relative_temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_import')
    os.makedirs(relative_temp_dir, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=relative_temp_dir)
    img_folder = os.path.join(temp_dir, "img")
    os.makedirs(img_folder, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 只提取图片文件到img子文件夹
            for file in zip_ref.namelist():
                if file.lower().endswith(('.jpg', '.png')):
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

def get_json_value(json_data, file_name):
    """
    从JSON数据中获取指定文件名对应的值
    
    Args:
        json_data: JSON数据字典
        file_name: 文件名
        
    Returns:
        获取到的值，如果没有找到则返回None
    """
    if not json_data or not file_name:
        return None
        
    base_name = os.path.splitext(file_name)[0]  # 不带扩展名的文件名
    
    # 尝试多种可能的键格式
    possible_keys = [
        base_name,              # 不带扩展名
        f"{base_name}.jpg",     # 带.jpg扩展名
        f"{base_name}.png",     # 带.png扩展名
        file_name               # 完整文件名
    ]
    
    # 尝试所有可能的键
    for key in possible_keys:
        if key in json_data:
            return json_data[key]
    
    # 如果找不到，记录警告并返回None
    logger.warning(f"在JSON数据中找不到与文件 {file_name} 匹配的键，尝试了 {possible_keys}")
    return None

def clean_import_results():
    """清理import_results目录中的文件"""
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
    json_level_path: str = None,
    json_comment_path: str = None,
    output_dir: str = "media/import_results",
    test_mode: bool = False,
    status_callback = None
) -> dict:
    """
    导入汉字图片数据并与JSON答案进行匹配，生成Excel文件
    
    Args:
        image_folder_path: 图片文件夹路径
        json_level_path: 包含等级信息的JSON文件路径 
        json_comment_path: 包含评论信息的JSON文件路径
        output_dir: 输出目录，默认为media/import_results
        test_mode: 是否为测试模式（只处理少量图片）
        status_callback: 状态更新回调函数，格式为 fn(progress, message)
        
    Returns:
        包含更多信息的结果字典
        
    Raises:
        FileNotFoundError: 如果图片文件夹不存在
        ValueError: 如果没有有效的识别结果
    """
    # 检查图片文件夹是否存在
    if not os.path.exists(image_folder_path):
        raise FileNotFoundError(f"图片文件夹不存在: {image_folder_path}")
    
    # 状态回调
    def update_status(progress, message):
        if status_callback:
            status_callback(progress, message)
        logger.info(f"导入进度: {progress}%, {message}")
    
    update_status(5, "正在准备识别模块...")
    
    # 读取JSON数据
    level_data = {}
    comment_data = {}
    
    update_status(10, "正在读取JSON数据...")
    
    if json_level_path and os.path.exists(json_level_path):
        try:
            level_data = load_json_data(json_level_path)
            logger.info(f"已加载等级JSON数据，包含 {len(level_data)} 条记录")
            
            # 检查是否为标准答案格式（值为A/B/C等级）
            is_standard_answer_format = False
            if level_data and len(level_data) > 0:
                sample_key = next(iter(level_data))
                sample_value = level_data[sample_key]
                if isinstance(sample_value, str) and sample_value in ["A", "B", "C", "D"]:
                    is_standard_answer_format = True
                    logger.info("检测到标准答案格式，值为等级字母")
            
            # 打印一些键值对样本用于调试
            sample_items = list(level_data.items())[:5] if level_data else []
            logger.info(f"等级数据样本: {sample_items}")
            
        except Exception as e:
            logger.warning(f"加载等级JSON数据失败: {str(e)}")
    
    if json_comment_path and os.path.exists(json_comment_path):
        try:
            comment_data = load_json_data(json_comment_path)
            logger.info(f"已加载评论JSON数据，包含 {len(comment_data)} 条记录")
        except Exception as e:
            logger.warning(f"加载评论JSON数据失败: {str(e)}")
    
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
            # 使用recognition.py中的recognize_hanzi函数进行识别
            recognition_result = recognize_hanzi(img_path)
            
            # 处理返回结果
            if isinstance(recognition_result, tuple) and len(recognition_result) >= 2:
                recognized_char = recognition_result[0]
                variant = recognition_result[1]
            else:
                recognized_char = str(recognition_result)
                variant = "简体"  # 默认变体类型
            
            # 验证识别结果
            if not recognized_char or recognized_char == "未识别" or recognized_char == "识别错误":
                logger.warning(f"图片识别结果无效: {img_file}")
                failed_count += 1
                failed_files.append((img_file, "识别结果无效"))
                
            else:
                # 成功识别，创建结果行
                result_row = {
                    'character': recognized_char,
                    'structure': "未知结构",  # 默认结构
                    'variant': variant,
                    'level': "D",  # 默认等级
                    'comment': "无",  # 默认评论
                    'image_path': img_path,
                    'file_name': file_name_without_ext
                }
                success_count += 1
            
            # 获取level数据
            level_value = get_json_value(level_data, img_file)
            if level_value:
                # 如果获取到了值，记录日志
                logger.info(f"文件 {img_file} 的等级值: {level_value}")
                result_row['level'] = level_value
            else:
                # 尝试直接用完整文件名查找
                level_value = level_data.get(img_file)
                if level_value:
                    logger.info(f"直接用文件名 {img_file} 找到等级值: {level_value}")
                    result_row['level'] = level_value
                else:
                    logger.warning(f"无法找到文件 {img_file} 的等级值")
            
            # 获取comment数据
            comment_value = get_json_value(comment_data, file_name_without_ext)
            if comment_value:
                result_row['comment'] = comment_value
            
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
            
            # 获取level数据
            level_value = get_json_value(level_data, img_file)
            if level_value:
                result_row['level'] = level_value
            
            # 获取comment数据
            comment_value = get_json_value(comment_data, file_name_without_ext)
            if comment_value:
                result_row['comment'] = comment_value
            
            results.append(result_row)
    
    update_status(95, "正在生成结果文件...")
    
    # 检查是否有处理成功的图片，改为警告而非错误
    if success_count == 0 and len(image_files) > 0:
        logger.warning("没有图片成功识别，但仍会生成结果文件")
    
    logger.info(f"处理完成：共 {total_count} 张图片，成功 {success_count} 张，失败 {failed_count} 张")
    print(f"处理完成：共 {total_count} 张图片，成功 {success_count} 张，失败 {failed_count} 张")
    
    # 创建输出目录
    try:
        # 确保output_dir是绝对路径
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(settings.MEDIA_ROOT, output_dir)
            
        # 创建目录及其父目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 检查目录是否可写
        if not os.access(output_dir, os.W_OK):
            print(f"警告：输出目录不可写: {output_dir}")
            # 尝试设置权限
            try:
                os.chmod(output_dir, 0o755)
                print(f"已尝试修改目录权限")
            except Exception as e:
                print(f"修改目录权限失败: {str(e)}")
        
        print(f"已创建或确认输出目录存在: {output_dir}")
    except Exception as e:
        print(f"创建输出目录失败: {str(e)}")
        raise ValueError(f"创建输出目录失败: {str(e)}")
    
    # 创建Excel文件
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    excel_filename = f"hanzi_import_{timestamp}.xlsx"
    
    # 确保output_dir是绝对路径
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(settings.MEDIA_ROOT, output_dir)
        
    # 创建规范化的Excel文件路径
    excel_path = os.path.normpath(os.path.join(output_dir, excel_filename))
    
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
            file_size = os.path.getsize(excel_path)
            print(f"Excel文件创建成功，大小: {file_size} 字节")
            # 确保文件权限正确
            try:
                os.chmod(excel_path, 0o644)  # 确保文件可读
            except Exception as e:
                print(f"设置文件权限时出错: {str(e)}")
        else:
            print(f"警告：Excel文件未能创建，路径不存在: {excel_path}")
            # 尝试在不同位置写入
            fallback_path = os.path.normpath(os.path.join(settings.MEDIA_ROOT, "import_results", excel_filename))
            if excel_path != fallback_path:
                print(f"尝试写入备用位置: {fallback_path}")
                os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
                # 使用异常处理确保写入成功
                try:
                    df.to_excel(fallback_path, index=False)
                    # 强制刷新文件缓冲
                    time.sleep(1)  # 给文件系统一点时间
                    if os.path.exists(fallback_path):
                        excel_path = fallback_path
                        print(f"成功写入备用位置: {excel_path}")
                except Exception as e:
                    print(f"备用位置写入失败: {str(e)}")
        
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
        # 构建一个标准化的相对于MEDIA_ROOT的路径
        if output_dir.startswith(settings.MEDIA_ROOT):
            # 使用os.path.relpath获取相对路径
            relative_path = os.path.relpath(excel_path, settings.MEDIA_ROOT)
            # 确保URL中全部使用正斜杠
            excel_url = f"/media/{relative_path.replace(os.sep, '/')}"
        else:
            # 直接使用文件名作为相对URL
            excel_url = f"/media/import_results/{excel_filename}"
            
        logger.info(f"生成的Excel URL: {excel_url}")
        logger.info(f"实际Excel路径: {excel_path}")
        
        # 清理旧文件（保留当前生成的文件）
        clean_files_except(output_dir, excel_filename)
        if failed_files:
            clean_files_except(output_dir, log_filename, exclude_files=[excel_filename])
        
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

def clean_files_except(directory, exception_file=None, exclude_files=None):
    """
    清理目录中除了指定文件外的所有文件
    
    Args:
        directory: 要清理的目录
        exception_file: 要保留的文件名（如果为None则清空整个目录）
        exclude_files: 要排除的文件列表（如果为None则不排除任何文件）
    """
    try:
        if not os.path.exists(directory):
            return
            
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if exception_file and filename == exception_file:
                continue
            if exclude_files and filename in exclude_files:
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
    parser.add_argument('--json_level', type=str, help='包含等级信息的JSON文件路径')
    parser.add_argument('--json_comment', type=str, help='包含评论信息的JSON文件路径')
    parser.add_argument('--output_dir', type=str, default='media/import_results', help='输出目录路径')
    parser.add_argument('--clean', action='store_true', help='清理旧导入结果文件')
    
    args = parser.parse_args()
    
    try:
        # 使用新的函数签名
        result = import_hanzi_data(
            args.image_folder,
            args.json_level,
            args.json_comment,
            args.output_dir
        )
        
        print(f"数据导入完成，结果已保存到: {result['excel_url']}")
    except Exception as e:
        print(f"数据导入失败: {str(e)}")
        import traceback
        traceback.print_exc() 