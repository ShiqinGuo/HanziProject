import os
import json
import tempfile
import logging
import traceback
from hanzi_project.celery import app
from .data_importer import import_hanzi_data, extract_zip_to_temp
from django.conf import settings

logger = logging.getLogger(__name__)

@app.task
def process_import_data_task(image_zip_path, json_file_path, output_dir=None, json_mappings=None, 
                            test_mode=False, enhanced_recognition=False):
    """
    异步处理汉字数据导入的Celery任务
    
    Args:
        image_zip_path: 图片ZIP文件路径
        json_file_path: JSON数据文件路径
        output_dir: 输出目录，默认为media/import_results
        json_mappings: JSON字段映射，例如 {'level': 'levels', 'comment': 'comments'}
        test_mode: 是否为测试模式
        enhanced_recognition: 是否启用增强识别
        
    Returns:
        一个字典，包含任务状态信息和结果文件路径
    """
    logger.info(f"开始处理数据导入任务: {image_zip_path}, {json_file_path}")
    print(f"开始处理数据导入任务: {image_zip_path}, {json_file_path}")
    
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
            logger.error(error_msg)
            print(error_msg)
            result['message'] = error_msg
            return result
            
        if not os.path.exists(json_file_path):
            error_msg = f"JSON数据文件不存在: {json_file_path}"
            logger.error(error_msg)
            print(error_msg)
            result['message'] = error_msg
            return result
        
        # 确保输出目录存在
        if not output_dir:
            output_dir = os.path.join(settings.MEDIA_ROOT, "import_results")
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"使用输出目录: {output_dir}")
        print(f"使用输出目录: {output_dir}")
        
        # 解压ZIP文件
        try:
            temp_dir, image_folder = extract_zip_to_temp(image_zip_path)
            logger.info(f"ZIP文件解压成功，临时目录: {temp_dir}，图片文件夹: {image_folder}")
            print(f"ZIP文件解压成功，临时目录: {temp_dir}，图片文件夹: {image_folder}")
            
            # 检查解压后的图片文件是否存在
            image_files = [f for f in os.listdir(image_folder) 
                         if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif'))]
            logger.info(f"找到 {len(image_files)} 个图片文件")
            print(f"找到 {len(image_files)} 个图片文件")
            
            if not image_files:
                error_msg = f"解压后未找到任何图片文件"
                logger.error(error_msg)
                print(error_msg)
                result['message'] = error_msg
                return result
        except Exception as e:
            error_msg = f"解压ZIP文件失败: {str(e)}"
            logger.error(error_msg)
            print(error_msg)
            result['message'] = error_msg
            return result
        
        # 状态更新回调函数
        def update_status(progress, message):
            logger.info(f"导入进度: {progress}%, {message}")
            print(f"导入进度: {progress}%, {message}")
        
        # 处理数据导入
        try:
            result_data = import_hanzi_data(
                image_folder,
                json_file_path,
                output_dir,
                json_mappings,
                test_mode,
                enhanced_recognition,
                update_status
            )
            logger.info(f"数据导入成功，输出文件: {result_data['excel_url']}")
            print(f"数据导入成功，输出文件: {result_data['excel_url']}")
            
            # 检查Excel文件是否存在
            if 'excel_path' in result_data and os.path.exists(result_data['excel_path']):
                file_size = os.path.getsize(result_data['excel_path'])
                print(f"Excel文件大小: {file_size} 字节")
            else:
                print(f"警告：Excel文件不存在: {result_data.get('excel_path', '未知')}")
        except Exception as e:
            error_msg = f"数据导入处理失败: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            print(error_msg)
            print(traceback.format_exc())
            result['message'] = error_msg
            return result
        
        result['status'] = 'success'
        result['message'] = '数据导入成功'
        result['file_url'] = result_data.get('excel_url')
        
        # 使用返回的统计数据
        result['processed_count'] = result_data.get('total_count', 0)
        result['recognized_count'] = result_data.get('success_count', 0)
        
        # 检查输出文件是否真的创建
        if 'excel_path' in result_data:
            excel_file_path = result_data['excel_path']
            if not os.path.exists(excel_file_path):
                logger.warning(f"警告：输出的Excel文件未找到: {excel_file_path}")
                print(f"警告：输出的Excel文件未找到: {excel_file_path}")
            else:
                logger.info(f"Excel文件已创建: {excel_file_path}, 大小: {os.path.getsize(excel_file_path)} 字节")
                print(f"Excel文件已创建: {excel_file_path}, 大小: {os.path.getsize(excel_file_path)} 字节")
        
        logger.info(f"数据导入任务完成: {result['file_url']}")
        print(f"数据导入任务完成: {result['file_url']}")
        
    except Exception as e:
        error_msg = f"数据导入任务失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        print(error_msg)
        print(traceback.format_exc())
        result['status'] = 'error'
        result['message'] = error_msg
    finally:
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"已清理临时目录: {temp_dir}")
                print(f"已清理临时目录: {temp_dir}")
            except Exception as e:
                logger.error(f"清理临时目录失败: {str(e)}")
                print(f"清理临时目录失败: {str(e)}")
    
    return result 