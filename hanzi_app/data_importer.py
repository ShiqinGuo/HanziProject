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
        f"{base_name}.jpg",     
        f"{base_name}.png",     
    ]
    
    # 尝试所有可能的文件名
    for key in possible_keys:
        if key in json_data:
            return json_data[key]
    
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
    # 读取等级JSON数据
    if json_level_path and os.path.exists(json_level_path):
        try:
            level_data = load_json_data(json_level_path)
            logger.info(f"已加载等级JSON数据，包含 {len(level_data)} 条记录")
            
        except Exception as e:
            logger.warning(f"加载等级JSON数据失败: {str(e)}")
    
    # 读取评论JSON数据
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
                            if f.lower().endswith(('.png', '.jpg'))])
        
    except Exception as e:
        raise ValueError(f"读取图片文件夹失败: {str(e)}")
    
    update_status(25, "准备处理图片...")
    
    # 处理图片并识别文字
    results = []
    success_count = 0
    failed_count = 0
    total_count = len(image_files)
    failed_files = []
    
    # 确保导出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成Excel文件名称
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    excel_file_name = f"hanzi_import_{timestamp}.xlsx"
    excel_path = os.path.join(output_dir, excel_file_name)
    
    # 生成日志文件名称
    log_file_name = f"hanzi_import_{timestamp}_failed.log"
    log_path = os.path.join(output_dir, log_file_name)
    
    # 创建日志文件
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"汉字导入处理开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"图片文件夹: {image_folder_path}\n")
        log_file.write(f"等级JSON文件: {json_level_path}\n")
        log_file.write(f"评论JSON文件: {json_comment_path}\n")
        log_file.write(f"总图片数量: {total_count}\n\n")
        log_file.write("===== 处理失败的图片 =====\n\n")
    
    # 进度计算变量
    last_progress_update = 0
    update_interval = max(1, min(total_count // 20, 5))  # 至少有20个进度更新点
    
    # 处理每个图片
    for index, image_file in enumerate(image_files):
        # 更新进度（约每5%更新一次）
        current_progress = int(25 + (index / total_count) * 70)  # 进度从25%到95%
        if current_progress >= last_progress_update + 2 or index % update_interval == 0:
            update_status(current_progress, f"正在处理第 {index+1}/{total_count} 个图片 ({(index/total_count*100):.1f}%)...")
            last_progress_update = current_progress
        
        img_path = os.path.join(image_folder_path, image_file)
        file_name_without_ext = os.path.splitext(image_file)[0]
        
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
            if not recognized_char or recognized_char == "识别失败" :
                logger.warning(f"图片识别结果无效: {image_file}")
                failed_count += 1
                failed_files.append((image_file, "汉字识别失败"))
                
            else:
                # 成功识别，创建结果行
                result_row = {
                    'character': recognized_char,
                    'structure': "未知结构",  # 默认结构
                    'variant': variant,
                    'level': "D",  # 默认等级
                    'comment': "无",  # 默认评论
                    'image_path': file_name_without_ext,
                    'file_name': file_name_without_ext
                }
                success_count += 1
            
            # 获取level数据
            level_value = get_json_value(level_data, image_file)
            if level_value:
                logger.info(f"文件 {image_file} 的等级值: {level_value}")
                result_row['level'] = level_value
            
            # 获取comment数据
            comment_value = get_json_value(comment_data, image_file)
            if comment_value:
                logger.info(f"文件 {image_file} 的评论值: {comment_value}")
                result_row['comment'] = comment_value
            
            results.append(result_row)
            
        except Exception as e:
            logger.error(f"图片识别异常: {image_file}, 错误: {str(e)}")
            failed_count += 1
            failed_files.append((image_file, str(e)))
            
            # 如果识别失败，跳过当前图片
            continue
    
    update_status(95, "正在生成Excel结果文件...")
       
    logger.info(f"处理完成：共 {total_count} 张图片，成功 {success_count} 张，失败 {failed_count} 张")
    
    # 将识别结果写入Excel表格
    try:
        # 创建DataFrame
        df = pd.DataFrame(results)
        
        # 确保输出目录使用绝对路径
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(settings.MEDIA_ROOT, output_dir)
            
        # 检查目录是否可写
        if not os.access(output_dir, os.W_OK):
            raise ValueError(f"输出目录不可写: {output_dir}")
        
        # 生成Excel文件
        df.to_excel(excel_path, index=False)
        
        # 获取相对URL路径
        excel_url = f"/media/import_results/{excel_file_name}"
        logger.info(f"生成的Excel URL: {excel_url}")
        logger.info(f"实际Excel路径: {excel_path}")
        
        # 将失败的文件记录到日志文件
        if failed_files:
            with open(log_path, 'a', encoding='utf-8') as log_file:
                for failed_file, reason in failed_files:
                    log_file.write(f"文件: {failed_file}\n")
                    log_file.write(f"失败原因: {reason}\n")
                    log_file.write("-" * 40 + "\n")
            logger.warning(f"已创建失败日志: {log_path}")
        
        # 更新完成状态
        update_status(100, "导入完成！")
        
        return {
            'success': True,
            'message': '导入处理完成',
            'excel_url': excel_url,
            'total_count': total_count,
            'success_count': success_count,
            'failed_count': failed_count,
            'excel_path': excel_path,
            'log_path': log_path if failed_files else None
        }
        
    except Exception as e:
        error_msg = f"生成Excel文件失败: {str(e)}"
        logger.error(error_msg)
        
        # 更新错误状态
        update_status(95, f"导入失败: {error_msg}")
        
        return {
            'success': False,
            'message': error_msg,
            'total_count': total_count,
            'success_count': success_count,
            'failed_count': failed_count
        }