import os
import json
import tempfile
import logging
import traceback
import shutil
from hanzi_project.celery import app
from .data_importer import import_hanzi_data, extract_zip_to_temp
from django.conf import settings

logger = logging.getLogger(__name__)

def ensure_media_directories():
    """确保所有必要的媒体目录都存在且可写"""
    dirs_to_check = [
        settings.MEDIA_ROOT,
        os.path.join(settings.MEDIA_ROOT, "import_results"), 
        os.path.join(settings.MEDIA_ROOT, "temp_import")
    ]
    
    for directory in dirs_to_check:
        try:
            # 创建目录（如果不存在）
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logger.info(f"创建目录: {directory}")
        except Exception as e:
            logger.error(f"目录操作失败: {directory}, 错误: {str(e)}")
    
    # 返回有关目录的信息
    return {d: {"exists": os.path.exists(d), "writable": os.access(d, os.W_OK)} for d in dirs_to_check}

@app.task(bind=True, max_retries=3, default_retry_delay=5, soft_time_limit=1800, time_limit=3600)
def process_import_data_task(self, image_zip_path, json_level_path=None, json_comment_path=None, 
                            output_dir=None, test_mode=False):
    """异步处理汉字数据导入的Celery任务"""
    # 确保媒体目录存在
    ensure_media_directories()
    
    logger.info(f"开始处理数据导入任务: {image_zip_path}")
    
    result = {
        'status': 'error',
        'message': '',
        'file_url': None,
        'processed_count': 0,
        'recognized_count': 0
    }
    
    temp_dir = None
    
    try:
        # 检查文件是否存在
        if not os.path.exists(image_zip_path):
            result['message'] = f"图片ZIP文件不存在: {image_zip_path}"
            return result
        
        # 确保输出目录存在
        if not output_dir:
            output_dir = os.path.join(settings.MEDIA_ROOT, "import_results")
        os.makedirs(output_dir, exist_ok=True)
        
        # 解压ZIP文件
        try:
            temp_dir, image_folder = extract_zip_to_temp(image_zip_path)
            
            # 检查解压后的图片文件
            image_files = [f for f in os.listdir(image_folder) 
                         if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            
            if not image_files:
                result['message'] = "解压后未找到任何图片文件"
                return result
        except Exception as e:
            result['message'] = f"解压ZIP文件失败: {str(e)}"
            logger.error(f"解压ZIP文件失败: {str(e)}")
            logger.error(traceback.format_exc())
            # 尝试重试任务
            try:
                self.retry(exc=e)
            except Exception as retry_exc:
                logger.error(f"任务重试失败: {str(retry_exc)}")
            return result
        
        # 状态更新回调函数
        def update_status(progress, message):
            logger.info(f"导入进度: {progress}%, {message}")
        
        # 调用导入函数处理数据
        try:
            result_data = import_hanzi_data(
                image_folder, json_level_path, json_comment_path,
                output_dir, test_mode, update_status
            )
            
            # 更新返回结果
            result['status'] = 'success'
            result['message'] = '数据导入成功'
            result['file_url'] = result_data.get('excel_url')
            result['processed_count'] = result_data.get('total_count', 0)
            result['recognized_count'] = result_data.get('success_count', 0)
        except Exception as e:
            result['message'] = f"数据导入处理失败: {str(e)}"
            logger.error(result['message'])
            logger.error(traceback.format_exc())
            # 尝试重试任务
            try:
                self.retry(exc=e)
            except Exception as retry_exc:
                logger.error(f"任务重试失败: {str(retry_exc)}")
            return result
        
    except Exception as e:
        result['message'] = f"导入任务执行出错: {str(e)}"
        logger.error(result['message'])
        logger.error(traceback.format_exc())
    finally:
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"清理临时目录: {temp_dir}")
            except Exception as e:
                logger.error(f"清理临时目录失败: {str(e)}")
    
    return result 