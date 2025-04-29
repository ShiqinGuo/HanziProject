import os
import json
import tempfile
import logging
import traceback
import shutil
from hanzi_project.celery import app
from .data_importer import import_hanzi_data, extract_zip_to_temp
from django.conf import settings
import redis
from hanzi_project.celery import app as celery_app
import datetime

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
    
    # 创建Redis客户端连接
    try:
        redis_client = redis.from_url(celery_app.conf.broker_url)
        task_log_key = f"task_logs:{self.request.id}"
        # 清除之前的日志记录
        redis_client.delete(task_log_key)
    except Exception as e:
        logger.error(f"创建Redis连接失败: {str(e)}")
        redis_client = None
    
    # 定义日志记录函数
    def log_progress(progress, message, status=None):
        logger.info(f"导入进度: {progress}%, {message}")
        if redis_client:
            try:
                log_entry = {
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'progress': progress,
                    'message': message
                }
                if status:
                    log_entry['status'] = status
                redis_client.rpush(task_log_key, json.dumps(log_entry))
                # 设置日志过期时间为24小时
                redis_client.expire(task_log_key, 86400)
            except Exception as e:
                logger.error(f"Redis记录日志失败: {str(e)}")
    
    # 记录任务开始
    log_progress(5, f"开始处理数据导入任务: {os.path.basename(image_zip_path)}", "started")
    
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
            error_msg = f"图片ZIP文件不存在: {image_zip_path}"
            log_progress(0, error_msg, "error")
            result['message'] = error_msg
            return result
        
        # 确保输出目录存在
        if not output_dir:
            output_dir = os.path.join(settings.MEDIA_ROOT, "import_results")
        os.makedirs(output_dir, exist_ok=True)
        log_progress(10, "正在准备输出目录", "processing")
        
        # 解压ZIP文件
        try:
            log_progress(15, "开始解压ZIP文件", "processing")
            temp_dir, image_folder = extract_zip_to_temp(image_zip_path)
            log_progress(20, f"ZIP文件解压完成，提取到目录: {os.path.basename(temp_dir)}", "processing")
            
            # 检查解压后的图片文件
            image_files = [f for f in os.listdir(image_folder) 
                         if f.lower().endswith(('.png', '.jpg'))]
            
            if not image_files:
                error_msg = "解压后未找到任何图片文件"
                log_progress(20, error_msg, "error")
                result['message'] = error_msg
                return result
            
            log_progress(25, f"找到 {len(image_files)} 个图片文件", "processing")
        except Exception as e:
            error_msg = f"解压ZIP文件失败: {str(e)}"
            log_progress(15, error_msg, "error")
            result['message'] = error_msg
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            # 尝试重试任务
            try:
                self.retry(exc=e)
            except Exception as retry_exc:
                logger.error(f"任务重试失败: {str(retry_exc)}")
            return result
        
        # 状态更新回调函数
        def update_status(progress, message):
            log_progress(progress, message, "processing")
        
        # 调用导入函数处理数据
        try:
            log_progress(30, "开始处理汉字数据", "processing")
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
            
            log_progress(100, f"导入完成！共处理 {result['processed_count']} 个图片，成功识别 {result['recognized_count']} 个汉字", "success")
            
            # 在结果中添加临时目录信息，以便后续可能的调试
            if temp_dir and os.path.exists(temp_dir):
                result['temp_dir'] = temp_dir
        except Exception as e:
            error_msg = f"数据导入处理失败: {str(e)}"
            log_progress(30, error_msg, "error")
            result['message'] = error_msg
            logger.error(result['message'])
            logger.error(traceback.format_exc())
            # 尝试重试任务
            try:
                self.retry(exc=e)
            except Exception as retry_exc:
                logger.error(f"任务重试失败: {str(retry_exc)}")
            return result
        
    except Exception as e:
        error_msg = f"导入任务执行出错: {str(e)}"
        log_progress(0, error_msg, "error")
        result['message'] = error_msg
        logger.error(result['message'])
        logger.error(traceback.format_exc())
    finally:
        # 处理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                # 在导入成功的情况下删除临时目录
                if result['status'] == 'success':
                    # 删除临时目录及其内容
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        logger.info(f"导入成功，已删除临时目录: {temp_dir}")
                        
                        # 清理原始ZIP文件
                        if os.path.exists(image_zip_path):
                            try:
                                os.remove(image_zip_path)
                                logger.info(f"已删除原始ZIP文件: {image_zip_path}")
                            except Exception as e:
                                logger.warning(f"无法删除原始ZIP文件: {str(e)}")
                        
                        # 清理JSON文件
                        for json_path in [json_level_path, json_comment_path]:
                            if json_path and os.path.exists(json_path):
                                try:
                                    os.remove(json_path)
                                    logger.info(f"已删除JSON文件: {json_path}")
                                except Exception as e:
                                    logger.warning(f"无法删除JSON文件: {str(e)}")
                    except Exception as e:
                        logger.error(f"删除临时文件失败: {str(e)}")
                else:
                    # 导入失败，保留临时目录用于调试
                    # 在Redis中保存临时目录路径
                    if redis_client:
                        redis_client.set(f"import_temp_dir:{self.request.id}", temp_dir, ex=86400)
                    
                    # 将临时目录重命名为更有意义的名称
                    parent_dir = os.path.dirname(temp_dir)
                    new_dir_name = f"import_task_{self.request.id}"
                    new_dir_path = os.path.join(parent_dir, new_dir_name)
                    
                    if not os.path.exists(new_dir_path):
                        try:
                            os.rename(temp_dir, new_dir_path)
                            logger.info(f"临时目录已重命名: {temp_dir} -> {new_dir_path}")
                            # 更新Redis中的路径
                            if redis_client:
                                redis_client.set(f"import_temp_dir:{self.request.id}", new_dir_path, ex=86400)
                        except Exception as e:
                            logger.error(f"重命名临时目录失败: {str(e)}")
                    
                    logger.info(f"导入失败，保留临时目录用于调试: {temp_dir}")
            except Exception as e:
                logger.error(f"处理临时目录失败: {str(e)}")
    
    return result 