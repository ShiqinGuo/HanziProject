from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.paginator import Paginator
from django.http import JsonResponse, FileResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import transaction
from django.core.cache import cache
from django.db.models import Q, Count, Prefetch
from django.db.models import Value, F  
from django.db.models import IntegerField  
import json
import os
import shutil
import zipfile
from .models import Hanzi
from .forms import HanziForm
import time
from django.views.decorators.cache import cache_page
from .generate import generate_hanzi_image, get_stroke_order,get_pinyin
import pandas as pd
from io import BytesIO
import logging
import traceback
import random
import csv
import tempfile
from datetime import datetime
from rest_framework.serializers import ModelSerializer
from django.contrib import messages
from rest_framework import serializers
from urllib.parse import urlencode
import re
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage
import io

# 在文件顶部添加日志配置
logger = logging.getLogger(__name__)

# 为导出功能添加序列化器
class HanziSerializer(ModelSerializer):
    # 自定义字段，处理image_path格式
    image_path = serializers.SerializerMethodField()
    
    class Meta:
        model = Hanzi
        fields = ['character', 'structure', 'variant', 'level', 'comment', 'image_path']
    
    def get_image_path(self, obj):
        """处理图片路径，只返回文件名部分（不含后缀）"""
        if not obj.image_path:
            return ""
        filename = os.path.basename(obj.image_path)
        return os.path.splitext(filename)[0]  # 不含后缀的文件名

# 预加载笔画数据
stroke_dict = {}
stoke_file_path = os.path.join(settings.BASE_DIR, 'data\\ch_match\\stoke.txt')
try:
    with open(stoke_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 3:
                stroke_dict[parts[1]] = parts[2]
except FileNotFoundError:
    print(f"文件未找到: {stoke_file_path}")

# 定义上传文件夹路径
UPLOAD_FOLDER = os.path.join(settings.MEDIA_ROOT, 'uploads')  # 直接使用media根目录
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 定义前端日志目录
FRONTEND_LOGS_FOLDER = os.path.join(settings.BASE_DIR, 'logs', 'frontend')
if not os.path.exists(FRONTEND_LOGS_FOLDER):
    os.makedirs(FRONTEND_LOGS_FOLDER, exist_ok=True)

# 添加前端日志捕获视图
@csrf_exempt
def capture_frontend_logs(request):
    """捕获前端控制台日志并保存到服务器"""
    if request.method == 'POST':
        try:
            log_data = json.loads(request.body)
            log_level = log_data.get('level', 'info')  # 日志级别：info, warn, error等
            log_message = log_data.get('message', '')
            page_url = log_data.get('url', '')
            user_agent = log_data.get('userAgent', '')
            timestamp = log_data.get('timestamp', datetime.now().isoformat())
            
            # 创建对应日期的日志文件
            today = datetime.now().strftime('%Y-%m-%d')
            log_file_path = os.path.join(FRONTEND_LOGS_FOLDER, f'frontend-logs-{today}.log')
            
            # 格式化日志消息
            formatted_log = f"[{timestamp}] [{log_level.upper()}] [{page_url}] {log_message}\n"
            
            # 写入日志文件
            with open(log_file_path, 'a', encoding='utf-8') as f:
                f.write(formatted_log)
            
            # 记录到Django日志系统
            if log_level == 'error':
                logger.error(f"前端错误: {log_message}")
            elif log_level == 'warn':
                logger.warning(f"前端警告: {log_message}")
            else:
                logger.info(f"前端日志: {log_message}")
                
            return JsonResponse({'success': True, 'message': '日志已记录'})
            
        except Exception as e:
            logger.error(f"捕获前端日志失败: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'error': '仅支持POST请求'}, status=405)

@csrf_exempt
@login_required
def delete_logs(request):
    """删除前端日志文件"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持POST请求'}, status=405)
    
    try:
        # 清空所有日志
        if request.POST.get('all') == 'true':
            log_files = [f for f in os.listdir(FRONTEND_LOGS_FOLDER) 
                         if f.startswith('frontend-logs-') and f.endswith('.log')]
            deleted_count = 0
            
            for file in log_files:
                file_path = os.path.join(FRONTEND_LOGS_FOLDER, file)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_count += 1
            
            return JsonResponse({
                'success': True, 
                'message': f'已清空所有{deleted_count}个日志文件',
                'count': deleted_count
            })
        
        # 删除指定日期的日志
        date = request.POST.get('date')
        level = request.POST.get('level', 'all')
        
        if date:
            log_file_path = os.path.join(FRONTEND_LOGS_FOLDER, f'frontend-logs-{date}.log')
            
            # 如果是按级别删除，则需要读取日志内容，过滤掉指定级别的日志，然后重写文件
            if level and level != 'all' and os.path.exists(log_file_path):
                with open(log_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 按级别过滤日志
                filtered_lines = []
                deleted_count = 0
                
                for line in lines:
                    match = re.match(r'\[(.*?)\] \[(.*?)\] \[(.*?)\] (.*)', line.strip())
                    if match:
                        log_level = match.group(2).lower()
                        if log_level != level.lower():
                            filtered_lines.append(line)
                        else:
                            deleted_count += 1
                    else:
                        filtered_lines.append(line)
                
                # 如果有删除操作，重写文件
                if deleted_count > 0:
                    with open(log_file_path, 'w', encoding='utf-8') as f:
                        f.writelines(filtered_lines)
                    
                    return JsonResponse({
                        'success': True, 
                        'message': f'已删除{date}日志中的{deleted_count}条{level.upper()}级别日志',
                        'count': deleted_count
                    })
                else:
                    return JsonResponse({
                        'success': False, 
                        'message': f'未找到{date}日志中的{level.upper()}级别日志'
                    })
            
            # 如果删除整个日期的日志文件
            elif os.path.exists(log_file_path):
                os.remove(log_file_path)
                return JsonResponse({
                    'success': True, 
                    'message': f'已删除{date}的日志文件',
                    'count': 1
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'message': f'未找到{date}的日志文件'
                })
        
        return JsonResponse({'success': False, 'message': '缺少必要的参数'})
    
    except Exception as e:
        logger.error(f"删除日志失败: {str(e)}")
        return JsonResponse({'success': False, 'message': f'删除日志时发生错误: {str(e)}'}, status=500)

@login_required
def view_frontend_logs(request):
    """查看前端日志文件列表及内容"""
    date = request.GET.get('date')
    level = request.GET.get('level', 'all')
    search = request.GET.get('search', '')
    
    log_files = []
    logs = []
    
    # 获取所有日志文件
    for file in os.listdir(FRONTEND_LOGS_FOLDER):
        if file.startswith('frontend-logs-') and file.endswith('.log'):
            log_date = file[14:-4]  # 提取日期部分
            log_files.append({
                'date': log_date,
                'file': file,
                'size': os.path.getsize(os.path.join(FRONTEND_LOGS_FOLDER, file)) // 1024,  # KB
                'last_modified': datetime.fromtimestamp(os.path.getmtime(os.path.join(FRONTEND_LOGS_FOLDER, file)))
            })
    
    # 按日期降序排序
    log_files.sort(key=lambda x: x['date'], reverse=True)
    
    # 如果没有指定日期，使用最新的日志文件
    if not date and log_files:
        date = log_files[0]['date']
    
    # 如果指定了日期，则显示该日期的日志内容
    if date:
        log_file_path = os.path.join(FRONTEND_LOGS_FOLDER, f'frontend-logs-{date}.log')
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                # 解析和过滤日志
                for line in lines:
                    try:
                        # 解析日志行
                        match = re.match(r'\[(.*?)\] \[(.*?)\] \[(.*?)\] (.*)', line.strip())
                        if match:
                            timestamp, log_level, url, message = match.groups()
                            log_level = log_level.lower()
                            
                            # 应用过滤器
                            if (level == 'all' or log_level.lower() == level) and \
                               (not search or search.lower() in message.lower() or search.lower() in url.lower()):
                                logs.append({
                                    'timestamp': timestamp,
                                    'level': log_level.lower(),
                                    'url': url,
                                    'message': message
                                })
                        else:
                            # 如果不匹配格式，将整行作为消息处理
                            if not search or search.lower() in line.lower():
                                logs.append({
                                    'timestamp': '',
                                    'level': 'info',
                                    'url': '',
                                    'message': line.strip()
                                })
                    except Exception as e:
                        logger.error(f"解析日志行失败: {str(e)}, 行内容: {line}")
                        logs.append({
                            'timestamp': '',
                            'level': 'error',
                            'url': '',
                            'message': f"解析错误: {line.strip()}"
                        })
            except Exception as e:
                logger.error(f"读取日志文件失败: {str(e)}")
                messages.error(request, f"读取日志文件失败: {str(e)}")
    
    context = {
        'log_files': log_files,
        'logs': logs,
        'selected_date': date,
        'selected_level': level,
        'search_query': search
    }
    
    return render(request, 'hanzi_app/view_logs.html', context)

@login_required
def index(request):
    # 获取筛选参数
    search = request.GET.get('search', '')
    structure = request.GET.get('structure', '')
    level = request.GET.get('level', '')
    variant = request.GET.get('variant', '')
    stroke_count = request.GET.get('stroke_count', '')
    page_number = request.GET.get('page', 1)
    
    # 如果是从详情页返回，且没有筛选参数，尝试从会话中恢复
    is_returning = request.GET.get('returning', '0') == '1'
    if is_returning and not any([search, structure, level, variant, stroke_count]) and 'last_filter' in request.session:
        last_filter = request.session['last_filter']
        search = last_filter.get('search', '')
        structure = last_filter.get('structure', '')
        level = last_filter.get('level', '')
        variant = last_filter.get('variant', '')
        stroke_count = last_filter.get('stroke_count', '')
        page_number = last_filter.get('page', 1)
    
    # 保存当前筛选条件到会话
    request.session['last_filter'] = {
        'search': search,
        'structure': structure,
        'level': level,
        'variant': variant,
        'stroke_count': stroke_count,
        'page': page_number
    }
    
    # 移除缓存相关代码，直接查询数据库
    hanzi_list = Hanzi.objects.all().order_by('id')
    
    # 应用筛选条件
    if search:
        hanzi_list = hanzi_list.filter(
            Q(character__contains=search) | 
            Q(pinyin__contains=search) |
            Q(id__contains=search)
        )
    
    if structure and structure != '所有':
        hanzi_list = hanzi_list.filter(structure=structure)
    
    if level and level != '所有':
        hanzi_list = hanzi_list.filter(level=level)
        
    if variant and variant != '所有':
        hanzi_list = hanzi_list.filter(variant=variant)
    
    if stroke_count and stroke_count != '所有':
        hanzi_list = hanzi_list.filter(stroke_count=int(stroke_count))
    
    # 为每个汉字添加动画延迟
    for i, hanzi in enumerate(hanzi_list):
        page_i = i % 20
        hanzi.animation_delay = page_i * 100  
    
    # 分页处理
    paginator = Paginator(hanzi_list, 20)  # 每页显示20条
    page_obj = paginator.get_page(page_number)
    
    # 准备上下文数据
    context = {
        'page_obj': page_obj,
        'search': search,
        'structure': structure,
        'level': level,
        'variant': variant,
        'selected_structure': structure,
        'selected_level': level,
        'selected_variant': variant,
        'selected_stroke': stroke_count,
        'structure_choices': Hanzi.STRUCTURE_CHOICES,
        'level_choices': Hanzi.LEVEL_CHOICES,
        'variant_choices': Hanzi.VARIANT_CHOICES,
        'stroke_count_options': list(range(1, 21)),  # 1-20的笔画范围
        'total_count': hanzi_list.count(),
        'hanzi_list': hanzi_list,
    }
    
    return render(request, 'hanzi_app/index.html', context)

@cache_page(60 * 15)  # 缓存15分钟
def get_stroke_count(request, char):
    # 使用缓存键
    cache_key = f'stroke_count_{char}'
    stroke_count = cache.get(cache_key)
    
    if stroke_count is None:
        # 缓存未命中，从数据库或文件获取
        stroke_count = stroke_dict.get(char, '0')
        # 存入缓存，有效期1天
        cache.set(cache_key, stroke_count, 60*60*24)
    
    return JsonResponse({'stroke_count': stroke_count})

@csrf_exempt
@require_http_methods(['POST'])
def generate_id(request):
    structure_map = {
        "未知结构": "0",
        "左右结构": "1",  # 结构类型映射前缀
        "上下结构": "2",
        "包围结构": "3",
        "独体结构": "4",
        "品字结构": "5",
        "穿插结构": "6"
    }
    
    try:
        # 从前端请求的JSON body中获取结构类型
        data = json.loads(request.body)
        structure = data.get('structure')
        # 验证结构类型有效性
        if structure not in structure_map:
            return JsonResponse({"error": "无效结构类型"}, status=400)
        # 获取该结构类型的最新ID
        prefix = structure_map[structure]
        last_entry = Hanzi.objects.filter(id__startswith=prefix).order_by('-id').first()
        
        # 核心逻辑：自增编号
        if last_entry:
            # 示例：最后ID是"10015" → 提取"0015" → 转换为15 → +1=16
            last_num = int(last_entry.id[1:])  # id[1:]获取前缀后的部分
            new_num = last_num + 1
        else:
            # 该结构首次使用时从1开始
            new_num = 1
        
        # 生成新ID（前缀+4位数字）
        new_id = f"{prefix}{new_num:04d}"
        return JsonResponse({"id": new_id})
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def generate_filename(generated_id, suffix, filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown'
    return f"{generated_id}{suffix}.{ext}"

def remove_existing_files(filepath):
    try:
        full_path = os.path.join(UPLOAD_FOLDER, filepath)  # 直接使用MEDIA_ROOT
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception as e:
        print(f"删除文件失败: {e}")

@csrf_exempt
def add_hanzi(request):
    if request.method == 'POST':
        try:
            character = request.POST.get('character')
            generated_id = request.POST.get('generated_id')
            
            # 验证汉字字符
            if not character or len(character) != 1:
                return JsonResponse({'error': '请输入单个汉字字符'}, status=400)
            
            # 验证ID
            if not generated_id:
                return JsonResponse({'error': '请生成有效的ID'}, status=400)
            
            # 处理用户上传的图片
            image_file = request.FILES.get('image_file')
            if not image_file:
                return JsonResponse({'error': '请上传用户书写的汉字图片'}, status=400)
            
            # 验证图片格式
            if not allowed_file(image_file.name):
                return JsonResponse({'error': '不支持的图片格式'}, status=400)
            
            # 保存用户图片
            filename = generate_filename(generated_id, "0", image_file.name)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            
            with open(file_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)
            
            # 自动获取笔顺
            stroke_order = request.POST.get('stroke_order', '')
            if not stroke_order:
                # 如果用户没有输入笔顺，尝试自动获取
                stroke_orders = get_stroke_order(character)
                if stroke_orders and stroke_orders[0]:
                    stroke_order = stroke_orders[0]
            
            # 创建汉字对象
            hanzi = Hanzi(
                id=generated_id,
                character=character,
                stroke_count=int(request.POST.get('stroke_count', 0)),
                structure=request.POST.get('structure', '未知结构'),
                pinyin=request.POST.get('pinyin', ''),
                level=request.POST.get('level', 'A'),
                variant=request.POST.get('variant', '简体'),
                comment=request.POST.get('comment', ''),
                image_path=f"uploads/{filename}",
                stroke_order=stroke_order
            )
            hanzi.save()
            
            # 自动生成标准图片并更新数据库
            standard_path = generate_hanzi_image(hanzi.character)
            if standard_path:
                # 提取相对路径并更新数据库
                rel_path = os.path.join("standard_images", f"{hanzi.character}.jpg")
                Hanzi.objects.filter(id=hanzi.id).update(standard_image=rel_path)
            
            return redirect('hanzi_app:index')
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return render(request, 'hanzi_app/add.html')

def hanzi_detail(request, hanzi_id):
    hanzi = get_object_or_404(Hanzi, id=hanzi_id)
    
    # 获取返回URL，添加返回标记
    back_url = reverse('hanzi_app:index') + '?returning=1'
    
    # 获取汉字的笔画顺序
    if hanzi.stroke_order:
        stroke_order = hanzi.stroke_order
    else:
        stroke_order = get_auto_stroke_order(hanzi.character)
        
    # 获取拼音
    pinyin = hanzi.pinyin if hanzi.pinyin else get_pinyin(hanzi.character)
    
    context = {
        'hanzi': hanzi,
        'stroke_order': stroke_order,
        'pinyin': pinyin,
        'back_url': back_url
    }
    return render(request, 'hanzi_app/detail.html', context)

def delete_hanzi(request, hanzi_id):
    try:
        hanzi = get_object_or_404(Hanzi, id=hanzi_id)
        
        # 删除对应的图片文件
        if hanzi.image_path:
            try:
                file_path = os.path.join(UPLOAD_FOLDER, os.path.basename(hanzi.image_path))
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"删除文件失败: {e}")
        
        # 删除数据库记录
        hanzi.delete()
        
        # 成功后重定向，添加返回标记
        return redirect(reverse('hanzi_app:index') + '?returning=1')
    except Exception as e:
        # 记录异常
        logger.error(f"删除汉字失败: {e}")
        return HttpResponse(f"删除失败: {str(e)}", status=500)

def edit_hanzi(request, hanzi_id):
    hanzi = get_object_or_404(Hanzi, id=hanzi_id)
    
    # 构建返回链接，包含returning参数
    back_url = reverse('hanzi_app:index') + '?returning=1'
    
    if request.method == 'POST':
        form = HanziForm(request.POST, request.FILES, instance=hanzi)
        if form.is_valid():
            try:
                # 开启事务处理
                with transaction.atomic():
                    hanzi_instance = form.save(commit=False)
                    
                    # 处理图片上传
                    if 'image' in request.FILES:
                        # 先删除旧图片
                        if hanzi.image_path:
                            old_image_path = os.path.join(UPLOAD_FOLDER, os.path.basename(hanzi.image_path))
                            if os.path.exists(old_image_path):
                                os.remove(old_image_path)
                        
                        image_file = request.FILES['image']
                        filename = f"{hanzi_instance.id}.{image_file.name.split('.')[-1]}"
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        
                        with open(file_path, 'wb+') as destination:
                            for chunk in image_file.chunks():
                                destination.write(chunk)
                        
                        # 更新图片路径
                        hanzi_instance.image_path = filename
                    
                    # 保存汉字实例
                    hanzi_instance.save()
                    
                    # 重定向到详情页，保留返回参数
                    return redirect(back_url)
            
            except Exception as e:
                # 处理异常
                logger.error(f"保存汉字时出错: {e}")
                logger.error(traceback.format_exc())
                return render(request, 'hanzi_app/edit.html', {
                    'form': form,
                    'hanzi': hanzi,
                    'error': f"保存失败: {str(e)}",
                    'back_url': back_url
                })
    else:
        form = HanziForm(instance=hanzi)
    
    return render(request, 'hanzi_app/edit.html', {
        'form': form,
        'hanzi': hanzi,
        'back_url': back_url
    })

@csrf_exempt
def update_hanzi(request, hanzi_id):
    if request.method == 'POST':
        return edit_hanzi(request, hanzi_id)
    return HttpResponse("不支持的请求方法", status=405)

class EventStreamResponse(StreamingHttpResponse):
    def __init__(self, streaming_content=(), **kwargs):
        super().__init__(streaming_content, content_type='text/event-stream', **kwargs)
        self['Cache-Control'] = 'no-cache'
        self['X-Accel-Buffering'] = 'no'

def process_import_image(image_filename, image_dir, found_image_path=None):
    """处理导入的图片文件
    
    Args:
        image_filename: 图片文件名
        image_dir: 解压的临时目录
        found_image_path: 如果已知路径，可以直接传入
        
    Returns:
        str: 图片的相对路径，如果未找到则返回空字符串
    """
    if not image_filename:
        return ""
        
    # 确保文件名包含扩展名
    if not image_filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        image_filename = f"{image_filename}.jpg"
    
    # 如果已知路径，直接使用
    if found_image_path:
        src_path = found_image_path
        found = True
    else:
        # 查找图片文件
        found = False
        src_path = None
        for root, dirs, files in os.walk(image_dir):
            for file in files:
                if file.lower() == image_filename.lower():
                    src_path = os.path.join(root, file)
                    found = True
                    break
            if found:
                break
    
    if found and src_path:
        # 保存用户图片到uploads目录
        dest_path = os.path.join(UPLOAD_FOLDER, image_filename)
        shutil.copy(src_path, dest_path)
        return f"uploads/{image_filename}"
    
    return ""

def get_auto_stroke_order(character):
    """获取汉字的自动笔顺
    
    Args:
        character: 汉字字符
        
    Returns:
        str: 笔顺字符串
    """
    if not character:
        return ""
        
    stroke_orders = get_stroke_order(character)
    if stroke_orders and stroke_orders[0]:
        return stroke_orders[0]
    return ""

def process_hanzi_data(data_item, image_dir=None, zip_file=None, is_json=True):
    """处理单个汉字数据项，用于导入
    
    Args:
        data_item: 数据项（字典或DataFrame行）
        image_dir: 解压的临时目录
        zip_file: 上传的ZIP文件
        is_json: 是否是JSON格式(True)或Excel格式(False)
        
    Returns:
        tuple: (成功标志, 汉字对象或错误消息)
    """
    try:
        # 提取汉字字符（必须字段）和ID
        if is_json:
            char = data_item.get('character')
            hanzi_id = str(data_item.get('id', '')).strip()
        else:
            # Excel处理：检查数据格式是否字典格式的字符串
            # 当Excel中的数据是字典格式的情况（如{'00001': 2, '柃': '言', ...}）
            id_key = None
            char_value = None
            
            # 尝试根据列名找到ID和字符
            if 'id' in data_item:
                # 重要：确保ID保留前导零
                if isinstance(data_item['id'], (int, float)) and not pd.isna(data_item['id']):
                    # 如果是数字类型，格式化为5位数，保留前导零
                    hanzi_id = f"{int(data_item['id']):05d}"
                else:
                    hanzi_id = str(data_item['id']).strip()
            else:
                hanzi_id = ''
                
            if 'character' in data_item and not pd.isna(data_item['character']):
                char = str(data_item['character']).strip()
                # 检查是否是有效的单个汉字
                if len(char) != 1:
                    # 可能是Excel导入的特殊格式，需要进一步处理
                    pass
            else:
                char = ''
                
            # 如果没有找到有效的字符，尝试从第一行数据中提取
            if not char or len(char) != 1:
                # 查找字典格式的数据
                for key, value in data_item.items():
                    # 跳过空值
                    if pd.isna(key) or pd.isna(value):
                        continue
                        
                    str_key = str(key).strip()
                    str_value = str(value).strip()
                    
                    # 尝试找出ID和汉字
                    if len(str_key) == 5 and str_key.startswith('0'):  # 可能是ID
                        id_key = str_key
                    elif len(str_key) == 1 and '\u4e00' <= str_key <= '\u9fff':  # 是汉字
                        char = str_key
                    elif len(str_value) == 1 and '\u4e00' <= str_value <= '\u9fff':  # 值是汉字
                        char = str_value
                        
                # 如果找到了ID但没有hanzi_id
                if id_key and not hanzi_id:
                    hanzi_id = id_key
                    
            # 额外检查：如果是数字ID，确保格式化为5位带前导零的字符串
            if hanzi_id and hanzi_id.isdigit() and len(hanzi_id) < 5:
                hanzi_id = f"{int(hanzi_id):05d}"
        
        # 如果仍然没有有效的汉字字符
        if not char or len(str(char).strip()) != 1 or not '\u4e00' <= char <= '\u9fff':
            return False, f"记录缺少有效的汉字字符: {data_item}"
        
        char = str(char).strip()
        
        # 确保ID格式正确（5位，带前导零）
        if hanzi_id and hanzi_id.isdigit() and len(hanzi_id) < 5:
            hanzi_id = f"{int(hanzi_id):05d}"
        
        # 获取结构信息
        if is_json:
            structure = data_item.get('structure', '未知结构')
        else:
            structure = data_item.get('structure', '未知结构')
            if pd.isna(structure):
                structure = '未知结构'
        
        # 检查ID是否存在
        existing_hanzi = None
        is_update = False
        
        if hanzi_id:
            try:
                # 首先尝试精确匹配ID
                existing_hanzi = Hanzi.objects.get(id=hanzi_id)
                is_update = True
                logger.info(f"找到ID为 {hanzi_id} 的现有记录，将进行更新")
            except Hanzi.DoesNotExist:
                # 如果ID没有找到，再尝试匹配数字部分（移除前导零后比较）
                try:
                    if hanzi_id.isdigit():
                        # 尝试查找数值相同但格式可能不同的ID
                        numeric_id = int(hanzi_id)
                        potential_ids = [f"{numeric_id:d}", f"{numeric_id:05d}"]
                        existing_hanzi = Hanzi.objects.filter(id__in=potential_ids).first()
                        if existing_hanzi:
                            is_update = True
                            logger.info(f"通过数值匹配找到ID {existing_hanzi.id}，将进行更新")
                            # 使用找到的ID格式
                            hanzi_id = existing_hanzi.id
                except Exception as e:
                    logger.warning(f"尝试匹配数字ID时出错: {str(e)}")
                    
                if not existing_hanzi:
                    # 如果仍然没有找到匹配的ID，则创建新记录
                    logger.info(f"未找到ID为 {hanzi_id} 的记录，将创建新记录")
        else:
            # 没有提供ID，生成新ID
            hanzi_id = generate_new_id(structure)
            logger.info(f"未提供ID，生成新ID: {hanzi_id}")
            
            # 检查是否已存在相同汉字的记录（不考虑ID）
            existing_by_char = Hanzi.objects.filter(character=char).first()
            if existing_by_char:
                # 使用现有记录进行更新
                existing_hanzi = existing_by_char
                is_update = True
                hanzi_id = existing_by_char.id
                logger.info(f"找到字符 '{char}' 的现有记录 {hanzi_id}，将进行更新")
        
        # 处理图片文件
        image_path = ""
        if zip_file:
            if is_json and 'image_path' in data_item and data_item['image_path']:
                image_path = process_import_image(data_item['image_path'], image_dir)
            elif not is_json:
                # 处理Excel中的image_path
                if 'image_path' in data_item and not pd.isna(data_item['image_path']):
                    image_filename = str(data_item['image_path'])
                    image_path = process_import_image(image_filename, image_dir)
                # 如果未找到，尝试查找格式为A开头的值作为图片路径
                else:
                    for key, value in data_item.items():
                        if pd.isna(value):
                            continue
                        str_value = str(value).strip()
                        if str_value.startswith('A') and str_value[1:].isdigit():
                            image_path = process_import_image(str_value, image_dir)
                            break
        
        # 尝试使用现有图片路径（如果是更新操作）
        if is_update and not image_path and existing_hanzi.image_path:
            image_path = existing_hanzi.image_path
            
        # 处理笔顺
        if is_json:
            stroke_order = data_item.get('stroke_order', '')
        else:
            stroke_order = data_item.get('stroke_order', '')
            if pd.isna(stroke_order):
                stroke_order = ''
            
        if not stroke_order:
            stroke_order = get_auto_stroke_order(char)
            
        # 获取拼音（如果未提供）
        if is_json:
            pinyin = data_item.get('pinyin', '')
        else:
            pinyin = data_item.get('pinyin', '')
            if pd.isna(pinyin):
                pinyin = ''
            
        if not pinyin:
            pinyin = get_pinyin(char)[0] if get_pinyin(char) else ''
            
        # 获取笔画数（如果未提供）
        try:
            if is_json:
                stroke_count = int(data_item.get('stroke_count', 0))
            else:
                stroke_count_value = data_item.get('stroke_count')
                if pd.isna(stroke_count_value):
                    stroke_count = stroke_dict.get(char, 0)
                else:
                    stroke_count = int(stroke_count_value)
        except (ValueError, TypeError):
            stroke_count = stroke_dict.get(char, 0)
        
        # 获取其他字段
        if is_json:
            level = data_item.get('level', 'A')
            variant = data_item.get('variant', '简体')
            comment = data_item.get('comment', '')
        else:
            level = data_item.get('level', 'A')
            if pd.isna(level):
                level = 'A'
                
            variant = data_item.get('variant', '简体')
            if pd.isna(variant):
                variant = '简体'
                
            comment = data_item.get('comment', '')
            if pd.isna(comment):
                comment = ''
                
        # 准备汉字数据
        hanzi_data = {
            'id': hanzi_id,
            'character': char,
            'stroke_count': stroke_count,
            'structure': structure,
            'pinyin': pinyin,
            'level': level,
            'variant': variant,
            'comment': comment,
            'image_path': image_path,
            'stroke_order': stroke_order
        }
        
        # 创建或更新汉字对象
        if is_update:
            # 更新现有记录
            for key, value in hanzi_data.items():
                setattr(existing_hanzi, key, value)
            hanzi_obj = existing_hanzi
            logger.info(f"更新汉字记录: ID={hanzi_id}, 字符={char}")
        else:
            # 创建新记录
            hanzi_obj = Hanzi(**hanzi_data)
            logger.info(f"创建新汉字记录: ID={hanzi_id}, 字符={char}")
            
        # 保存到数据库
        hanzi_obj.save()
        
        # 自动生成标准图片并更新数据库
        standard_path = generate_hanzi_image(char)
        if standard_path:
            # 提取相对路径并更新数据库
            rel_path = os.path.join("standard_images", f"{char}.jpg")
            Hanzi.objects.filter(id=hanzi_id).update(standard_image=rel_path)
            
        return True, hanzi_obj
        
    except Exception as e:
        error_msg = f"处理记录时出错: {str(e)}, 记录: {data_item}"
        logger.error(error_msg)
        return False, error_msg

def handle_import_file(file_obj, zip_file=None, is_json=True):
    """处理导入文件并返回事件生成器
    
    Args:
        file_obj: 文件对象（JSON或Excel）
        zip_file: ZIP压缩文件（可选）
        is_json: 是否为JSON文件（True）或Excel文件（False）
        
    Returns:
        generator: 事件生成器函数
    """
    # 创建临时解压目录
    image_dir = os.path.join(settings.MEDIA_ROOT, 'temp_images', str(time.time()))
    os.makedirs(image_dir, exist_ok=True)
    
    # 如果有ZIP文件，解压它
    if zip_file:
        with zipfile.ZipFile(zip_file, 'r') as zf:
            zf.extractall(image_dir)
            
    def generate_events():
        try:
            # 解析文件
            if is_json:
                data = json.loads(file_obj.read().decode('utf-8'))
            else:
                # 尝试不同的header选项，找到合适的解析方式
                try:
                    # 首先尝试使用第一行作为列名
                    df = pd.read_excel(file_obj)
                    # 检查解析后的数据结构是否合理
                    if 'id' not in df.columns and 'character' not in df.columns:
                        # 如果没有正确的列名，尝试使用第二行作为列名
                        df = pd.read_excel(file_obj, header=1)
                except Exception as e:
                    logger.warning(f"Excel解析失败，尝试备用方法: {str(e)}")
                    df = pd.read_excel(file_obj, header=None)
                    # 尝试检测并处理列名
                    if df.shape[0] > 0:
                        first_row = df.iloc[0]
                        if any(str(col).lower() == 'id' for col in first_row) or any(str(col).lower() == 'character' for col in first_row):
                            df.columns = first_row
                            df = df.iloc[1:]
                
                # 转换为字典列表
                data = df.to_dict('records')
                
            total = len(data)
            processed = 0
            success_count = 0
            errors = []
            
            for item in data:
                success, result = process_hanzi_data(item, image_dir, zip_file, is_json)
                
                if success:
                    success_count += 1
                else:
                    errors.append(result)
                
                processed += 1
                progress = (processed / total * 100)
                yield f"data: {json.dumps({'progress': progress, 'processed': processed, 'success': success_count, 'errors': len(errors)})}\n\n"
            
            # 导入完成后返回结果
            yield f"data: {json.dumps({'success': True, 'message': f'成功导入 {success_count} 条记录，失败 {len(errors)} 条', 'errors': errors})}\n\n"
            
            # 导入完成后自动生成所有标准图片
            from .generate import generate_all_standard_images
            generate_all_standard_images()
            
            # 清理临时目录
            try:
                shutil.rmtree(image_dir)
            except Exception as e:
                logger.error(f"清理临时目录失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"导入失败: {str(e)}")
            yield f"data: {json.dumps({'success': False, 'message': f'导入失败: {str(e)}'})}\n\n"
            
    return generate_events

# 修改导入数据视图函数
@require_http_methods(["GET", "POST"])
def import_data(request):
    if request.method == 'POST':
        try:
            # 处理Excel文件导入
            if 'excel_file' in request.FILES:
                excel_file = request.FILES['excel_file']
                zip_file = request.FILES.get('image_zip')
                
                # 使用通用处理函数
                events_generator = handle_import_file(excel_file, zip_file, is_json=False)
                return EventStreamResponse(events_generator())
            
            # 处理JSON文件导入
            elif 'file' in request.FILES:
                json_file = request.FILES['file']
                zip_file = request.FILES.get('image_zip')
                
                # 使用通用处理函数
                events_generator = handle_import_file(json_file, zip_file, is_json=True)
                return EventStreamResponse(events_generator())
            
            else:
                return JsonResponse({'success': False, 'message': '未选择文件'})
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return render(request, 'hanzi_app/import.html')

def export_hanzi(request):
    """导出汉字数据"""
    if request.method == 'POST':
        # 从POST获取用户选择的字段和图片选项
        selected_fields = request.POST.getlist('fields', [])
        
        # 确保character字段始终被包含
        if 'character' not in selected_fields:
            selected_fields.append('character')
        
        # 至少需要选择一个字段
        if not selected_fields:
            messages.error(request, "请至少选择一个导出字段")
            return redirect(request.path)
        
        include_images = 'include_images' in request.POST
        include_standard_images = 'include_standard_images' in request.POST
        
        # 从会话获取筛选参数
        export_filters = request.session.get('export_filters', {})
        
        # 获取筛选后的汉字列表
        filtered_hanzi = get_filtered_hanzi_list(
            export_filters.get('search', ''),
            export_filters.get('structure', ''),
            export_filters.get('level', ''),
            export_filters.get('variant', ''),
            export_filters.get('stroke_count', ''),
            export_filters.get('ids', ''),
            export_filters.get('stroke_count_min', ''),
            export_filters.get('stroke_count_max', '')
        )
        
        # 生成导出文件
        export_files = generate_export_files(
            filtered_hanzi, 
            include_images,
            include_standard_images,
            selected_fields
        )
        export_files['count'] = filtered_hanzi.count()  # 添加记录数量
        
        # 保存导出文件信息到会话
        request.session['export_files'] = export_files
        request.session['export_timestamp'] = int(time.time())
        
        # 构建导出页面URL
        export_page_url = reverse('hanzi_app:export_page')
        
        # 获取返回URL
        return_url = request.POST.get('return_url', reverse('hanzi_app:index'))
        
        # 构建完整URL
        if return_url:
            params = {'return_url': return_url}
            export_page_url += '?' + urlencode(params)
        
        # 重定向到导出页面
        return redirect(export_page_url)
    else:
        # 直接在export_hanzi函数中处理GET请求，显示导出选项页面
        # 获取筛选条件
        ids = request.GET.get('ids', '')
        search = request.GET.get('search', '')
        structure = request.GET.get('structure', '')
        level = request.GET.get('level', '')
        variant = request.GET.get('variant', '')
        stroke_count = request.GET.get('stroke_count', '')
        stroke_count_min = request.GET.get('stroke_count_min', '')
        stroke_count_max = request.GET.get('stroke_count_max', '')
        return_url = request.GET.get('return_url', reverse('hanzi_app:index'))
        
        # 获取筛选后的汉字列表
        filtered_hanzi = get_filtered_hanzi_list(
            search, structure, level, variant, stroke_count, 
            ids, stroke_count_min, stroke_count_max
        )
        
        # 保存筛选参数到会话，供后续使用
        request.session['export_filters'] = {
            'ids': ids,
            'search': search,
            'structure': structure,
            'level': level,
            'variant': variant,
            'stroke_count': stroke_count,
            'stroke_count_min': stroke_count_min,
            'stroke_count_max': stroke_count_max
        }
        
        # 构建筛选信息对象，用于显示在前端
        filter_info = {
            'structure': structure if structure and structure != '所有' else None,
            'variant': variant if variant and variant != '所有' else None,
            'level': level if level and level != '所有' else None,
            'search_term': search if search else None,
            'stroke_count': stroke_count if stroke_count and stroke_count != '所有' else None,
        }
        
        # 可选字段列表
        available_fields = [
            {'id': 'id', 'name': '编号'},
            {'id': 'character', 'name': '汉字', 'checked': True},
            {'id': 'structure', 'name': '结构', 'checked': True},
            {'id': 'variant', 'name': '简繁体', 'checked': True},
            {'id': 'level', 'name': '等级', 'checked': True},
            {'id': 'stroke_count', 'name': '笔画数'},
            {'id': 'pinyin', 'name': '拼音'},
            {'id': 'stroke_order', 'name': '笔顺'},
            {'id': 'comment', 'name': '评价', 'checked': True},
            {'id': 'image_path', 'name': '图片路径', 'checked': True}
        ]
        
        # 图片选项
        image_options = [
            {'id': 'include_images', 'name': '包含手写图片'},
            {'id': 'include_standard_images', 'name': '包含标准楷体图片'}
        ]
        
        context = {
            'available_fields': available_fields,
            'image_options': image_options,
            'filtered_hanzi_count': filtered_hanzi.count(),
            'filter_info': filter_info,
            'return_url': return_url
        }
        
        return render(request, 'hanzi_app/export_options.html', context)

def export_page(request):
    """导出页面"""
    # 获取会话中的导出文件信息
    export_files = request.session.get('export_files', {})
    export_timestamp = request.session.get('export_timestamp', 0)
    return_url = request.GET.get('return_url', reverse('hanzi_app:index'))
    
    # 检查文件是否存在
    export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    
    # 准备文件列表
    file_list = []
    
    for file_type in ['json', 'excel', 'zip']:
        if file_type in export_files:
            file_path = os.path.join(export_dir, export_files[file_type])
            if os.path.exists(file_path):
                # 文件存在，添加到文件列表
                file_info = {
                    'name': export_files[file_type],
                    'size': f"{os.path.getsize(file_path) / (1024 * 1024):.2f} MB",
                    'type': '数据文件' if file_type == 'json' else ('表格文件' if file_type == 'excel' else '图片压缩包'),
                    'icon': 'fa-file-code' if file_type == 'json' else ('fa-file-excel' if file_type == 'excel' else 'fa-file-archive')
                }
                file_list.append(file_info)
    
    # 检查是否有导出数据
    export_count = export_files.get('count', 0)
    
    # 如果没有记录，显示警告信息
    if export_count == 0:
        messages.warning(request, "没有符合筛选条件的汉字数据")
    
    context = {
        'export_files': export_files,
        'export_timestamp': datetime.fromtimestamp(export_timestamp) if export_timestamp else None,
        'return_url': return_url,
        'current_time': int(time.time()),
        'file_list': file_list,
        'export_count': export_count
    }
    
    return render(request, 'hanzi_app/export.html', context)

def delete_export_file(request, filename):
    """删除单个导出文件"""
    try:
        if not filename:
            return JsonResponse({'error': '未指定文件名'}, status=400)
        
        file_path = os.path.join(settings.MEDIA_ROOT, 'exports', filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"已删除导出文件: {filename}")
            
            # 更新session中的文件信息
            export_files = request.session.get('export_files', {})
            for key in ['json_file', 'excel_file', 'zip_file']:
                if key in export_files and export_files[key] == filename:
                    del export_files[key]
                    request.session.modified = True
            
            return JsonResponse({
                'success': True,
                'message': f'已删除文件: {filename}'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': '文件不存在'
            })
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

def get_filtered_hanzi_list(search, structure, level, variant, stroke_count, ids, stroke_count_min, stroke_count_max):
    """根据筛选条件获取汉字列表"""
    queryset = Hanzi.objects.all()
    
    # 如果指定了ID列表，则使用ID列表筛选
    if ids:
        id_list = ids.split(',')
        queryset = queryset.filter(id__in=id_list)
        return queryset
    
    # 否则使用其他筛选条件
    if search:
        queryset = queryset.filter(
            Q(id__icontains=search) | 
            Q(character__icontains=search) | 
            Q(pinyin__icontains=search) | 
            Q(comment__icontains=search)
        )
    
    if structure and structure != '所有':
        queryset = queryset.filter(structure=structure)
    
    if level and level != '所有':
        queryset = queryset.filter(level=level)
    
    if variant and variant != '所有':
        queryset = queryset.filter(variant=variant)
    
    if stroke_count and stroke_count != '所有':
        try:
            stroke_count_int = int(stroke_count)
            queryset = queryset.filter(stroke_count=stroke_count_int)
        except ValueError:
            pass
    
    if stroke_count_min and stroke_count_max:
        try:
            stroke_count_min_int = int(stroke_count_min)
            stroke_count_max_int = int(stroke_count_max)
            queryset = queryset.filter(stroke_count__range=(stroke_count_min_int, stroke_count_max_int))
        except ValueError:
            pass
    
    return queryset

def generate_export_files(filtered_hanzi, include_images=False, include_standard_images=False, selected_fields=[]):
    """生成导出文件"""
    try:
        # 创建导出目录
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        
        # 时间戳
        timestamp = int(time.time())
        file_prefix = f'hanzi_export_{timestamp}'
        
        # 确保至少包含字符字段
        if 'character' not in selected_fields:
            selected_fields.append('character')
        
        # 构建返回结果
        result = {
            'timestamp': timestamp,
            'count': filtered_hanzi.count(),
            'filter_info': {
                'total_hanzi': Hanzi.objects.count(),
                'filtered_hanzi': filtered_hanzi.count()
            },
            'selected_fields': selected_fields
        }
        
        # 导出JSON文件
        json_file_path = os.path.join(export_dir, f'{file_prefix}.json')
        json_data = custom_serialize_hanzi(filtered_hanzi, selected_fields)
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        result['json'] = os.path.basename(json_file_path)
        
        # 导出Excel文件
        excel_file_path = os.path.join(export_dir, f'{file_prefix}.xlsx')
        export_to_excel(filtered_hanzi, excel_file_path, selected_fields)
        result['excel'] = os.path.basename(excel_file_path)
        
        # 如果包含图片，创建ZIP文件
        if include_images or include_standard_images:
            zip_file_path = os.path.join(export_dir, f'{file_prefix}_with_images.zip')
            with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                # 添加JSON文件
                zipf.write(json_file_path, os.path.basename(json_file_path))
                
                # 添加Excel文件
                zipf.write(excel_file_path, os.path.basename(excel_file_path))
                
                # 添加图片文件
                images_added = 0
                
                # 添加手写图片
                if include_images:
                    for hanzi in filtered_hanzi:
                        if hanzi.image_path:
                            image_path = os.path.join(settings.MEDIA_ROOT, hanzi.image_path)
                            if os.path.exists(image_path):
                                # 获取不带后缀的文件名
                                filename = os.path.basename(hanzi.image_path)
                                base_filename = os.path.splitext(filename)[0]
                                # 使用不带后缀的文件名作为目标文件名
                                zipf.write(image_path, f'images/{base_filename}' + os.path.splitext(image_path)[1])
                                images_added += 1
                
                # 添加标准楷体图片
                if include_standard_images:
                    for hanzi in filtered_hanzi:
                        if hanzi.standard_image:
                            standard_image_path = os.path.join(settings.MEDIA_ROOT, hanzi.standard_image)
                            if os.path.exists(standard_image_path):
                                # 获取不带后缀的文件名
                                filename = os.path.basename(hanzi.standard_image)
                                base_filename = os.path.splitext(filename)[0]
                                # 使用不带后缀的文件名作为目标文件名
                                zipf.write(standard_image_path, f'images/standard_{base_filename}' + os.path.splitext(standard_image_path)[1])
                                images_added += 1
                
                result['zip'] = os.path.basename(zip_file_path)
                result['images_included'] = images_added
        
        return result
    except Exception as e:
        logger.error(f"导出文件生成失败: {str(e)}")
        return {'error': str(e)}

def custom_serialize_hanzi(queryset, fields):
    """自定义序列化汉字对象，根据选择的字段"""
    result = []
    for hanzi in queryset:
        item = {}
        for field in fields:
            if field == 'image_path' and hanzi.image_path:
                # 处理图片路径，只返回文件名部分（不含后缀）
                filename = os.path.basename(hanzi.image_path)
                item[field] = os.path.splitext(filename)[0]
            else:
                # 获取其他字段值
                value = getattr(hanzi, field, '')
                # 对于可能为None的值，提供默认空字符串
                item[field] = value if value is not None else ''
        result.append(item)
    return result

def export_to_excel(filtered_hanzi, excel_file_path, selected_fields):
    """将汉字数据导出到Excel文件"""
    try:
        # 创建一个DataFrame来存储数据
        data = []
        for hanzi in filtered_hanzi:
            item = {}
            for field in selected_fields:
                if field == 'image_path' and hanzi.image_path:
                    # 处理图片路径，只保留文件名部分（不含后缀）
                    filename = os.path.basename(hanzi.image_path)
                    item[field] = os.path.splitext(filename)[0]  # 不含后缀的文件名
                else:
                    # 获取其他字段值
                    value = getattr(hanzi, field, '')
                    # 对于可能为None的值，提供默认空字符串
                    item[field] = value if value is not None else ''
            data.append(item)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 创建一个工作簿和工作表
        wb = Workbook()
        ws = wb.active
        ws.title = '汉字数据'
        
        # 添加表头
        headers = list(df.columns)
        # 如果需要在Excel中显示图片，添加图片列
        if 'character' in headers:
            headers.append('手写图片')
        
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
        
        # 添加数据行
        for row_num, hanzi_data in enumerate(data, 2):
            for col_num, field in enumerate(df.columns, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = hanzi_data.get(field, '')
        
        # 如果需要添加图片列
        if 'character' in headers:
            char_col_idx = headers.index('character') + 1  # 汉字列的索引
            img_col_idx = len(headers)  # 图片列的索引
            
            for row_num, hanzi_data in enumerate(data, 2):
                # 获取当前汉字对象
                char = hanzi_data.get('character', '')
                hanzi_obj = filtered_hanzi.filter(character=char).first()
                
                if hanzi_obj and hanzi_obj.image_path:
                    image_path = os.path.join(settings.MEDIA_ROOT, hanzi_obj.image_path)
                    if os.path.exists(image_path):
                        try:
                            # 使用PIL打开图片并调整大小
                            pil_img = PILImage.open(image_path)
                            # 调整图片大小以适合单元格
                            max_width = 100
                            max_height = 100
                            pil_img.thumbnail((max_width, max_height))
                            
                            # 创建临时内存文件保存调整后的图片
                            img_byte_arr = io.BytesIO()
                            pil_img.save(img_byte_arr, format=pil_img.format or 'PNG')
                            img_byte_arr.seek(0)
                            
                            # 创建Excel图片对象
                            img = XLImage(img_byte_arr)
                            
                            # 计算图片位置
                            cell = ws.cell(row=row_num, column=img_col_idx)
                            cell_addr = f'{get_column_letter(img_col_idx)}{row_num}'
                            
                            # 添加图片到单元格
                            ws.add_image(img, cell_addr)
                            
                            # 调整行高以适应图片
                            ws.row_dimensions[row_num].height = 75
                        except Exception as e:
                            logger.error(f"添加图片到Excel失败: {str(e)}")
                            cell = ws.cell(row=row_num, column=img_col_idx)
                            cell.value = "图片加载失败"
        
        # 调整列宽
        for col_num, field in enumerate(headers, 1):
            column_width = 15  # 默认列宽
            if field == '手写图片':
                column_width = 20  # 图片列宽度更大
            ws.column_dimensions[get_column_letter(col_num)].width = column_width
        
        # 保存工作簿
        wb.save(excel_file_path)
        
        return True
    except Exception as e:
        logger.error(f"Excel导出失败: {str(e)}")
        traceback.print_exc()
        return False

def download_file(request, filename):
    """处理文件下载，并设置下载后删除文件标记"""
    if not filename:
        return JsonResponse({'error': '未指定文件名'}, status=400)
    
    file_path = os.path.join(settings.MEDIA_ROOT, 'exports', filename)
    if not os.path.exists(file_path):
        return JsonResponse({'error': '文件不存在'}, status=404)
    
    try:
        # 处理include_images选项
        include_images = request.GET.get('include_images') == 'true'
        
        # 如果是Excel文件且需要包含图片，并且文件没有被之前处理过
        if filename.endswith('.xlsx') and include_images and not request.session.get(f'image_processed_{filename}', False):
            # 读取文件内容
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # 从会话获取筛选参数
            export_filters = request.session.get('export_filters', {})
            
            # 获取筛选后的汉字列表
            filtered_hanzi = get_filtered_hanzi_list(
                export_filters.get('search', ''),
                export_filters.get('structure', ''),
                export_filters.get('level', ''),
                export_filters.get('variant', ''),
                export_filters.get('stroke_count', ''),
                export_filters.get('ids', ''),
                export_filters.get('stroke_count_min', ''),
                export_filters.get('stroke_count_max', '')
            )
            
            # 重新生成包含图片的Excel文件
            if not export_to_excel(filtered_hanzi, file_path, request.session.get('export_files', {}).get('selected_fields', [])):
                logger.error(f"重新生成Excel文件失败: {filename}")
            
            # 标记文件已处理
            request.session[f'image_processed_{filename}'] = True
            request.session.modified = True
        
        # 使用FileResponse自动处理文件关闭
        response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
        
        # 设置正确的Content-Type
        if filename.endswith('.json'):
            response['Content-Type'] = 'application/json'
        elif filename.endswith('.zip'):
            response['Content-Type'] = 'application/zip'
        elif filename.endswith('.xlsx'):
            response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            response['Content-Type'] = 'application/octet-stream'
        
        # 记录下载标记，但不立即删除文件
        request.session[f'downloaded_{filename}'] = True
        
        return response
    except Exception as e:
        logger.error(f"文件下载失败: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

def cleanup_exports(request):
    """清理所有导出文件"""
    try:
        # 删除所有导出文件夹中的文件
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        if os.path.exists(export_dir):
            deleted_count = 0
            for file in os.listdir(export_dir):
                file_path = os.path.join(export_dir, file)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        logger.info(f"已删除临时导出文件: {file}")
                    except Exception as file_error:
                        logger.error(f"删除文件 {file} 失败: {str(file_error)}")
        
        return JsonResponse({
            'success': True, 
            'message': f'已清理导出文件夹，删除了 {deleted_count} 个文件'
        })
    except Exception as e:
        logger.error(f"清理导出文件失败: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

def clear_selected(request):
    """清除所有选中的条目"""
    return JsonResponse({'success': True})

def generate_new_id(structure):
    """根据结构生成新的汉字ID"""
    structure_map = {
        "未知结构": "0",
        "左右结构": "1",
        "上下结构": "2",
        "包围结构": "3",
        "独体结构": "4",
        "品字结构": "5",
        "穿插结构": "6"
    }
    
    prefix = structure_map.get(structure, "0")
    
    # 找到该结构的最大ID
    max_id_obj = Hanzi.objects.filter(id__startswith=prefix).order_by('-id').first()
    
    if max_id_obj:
        # 从现有ID中提取数字部分并递增
        try:
            current_num = int(max_id_obj.id[1:])
            new_num = current_num + 1
            new_id = f"{prefix}{new_num:04d}"
        except ValueError:
            # 如果现有ID不符合预期格式，则生成新的
            new_id = f"{prefix}0001"
    else:
        # 如果没有该结构的汉字，从1开始
        new_id = f"{prefix}0001"
    
    return new_id

@cache_page(60 * 15)  # 缓存15分钟
def get_stroke_order_api(request, char):
    # 使用缓存键
    cache_key = f'stroke_order_{char}'
    stroke_order = cache.get(cache_key)
    
    if stroke_order is None:
        # 缓存未命中，从数据库或文件获取
        from .generate import get_stroke_order
        stroke_orders = get_stroke_order(char)
        if stroke_orders and stroke_orders[0]:
            # 去除中括号和引号
            stroke_order = stroke_orders[0].strip("[]'")
        else:
            stroke_order = ''
        # 存入缓存，有效期1天
        cache.set(cache_key, stroke_order, 60*60*24)
    
    return JsonResponse({'stroke_order': stroke_order})

# 添加笔顺搜索视图
def stroke_search(request):
    """笔顺搜索页面"""
    stroke_pattern = request.GET.get('stroke_pattern', '')
    results = []
    
    # 常用笔画列表，用于快速选择
    common_strokes = ['横','竖','点','撇','横折',
                      '捺','横撇/横钩','提','横折钩','撇折',
                      '竖钩','竖弯钩','竖折/竖弯','竖提','斜钩',
                      '撇点','竖折折钩','横折弯钩/横斜钩','横折折折钩/横撇弯钩','横折折撇',
                      '弯钩','横折折/横折弯','横折提','竖折撇/竖折折','横折折折']

    if stroke_pattern:
        # 执行搜索
        results = Hanzi.search_by_stroke_order(stroke_pattern)
        
        # 分页处理
        paginator = Paginator(results, 24)  # 每页显示25条
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # 为每个汉字添加动画延迟值
        for i, hanzi in enumerate(page_obj.object_list):
            hanzi.animation_delay = (i + 8) * 100
    else:
        page_obj = None
    
    context = {
        'stroke_pattern': stroke_pattern,
        'common_strokes': common_strokes,
        'page_obj': page_obj,
        'results_count': len(results) if results else 0
    }
    
    return render(request, 'hanzi_app/stroke_search.html', context)

@csrf_exempt
def apply_export_options(request):
    """处理导出选项设置"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持POST请求'}, status=405)
    
    try:
        # 解析JSON数据
        data = json.loads(request.body)
        include_images = data.get('include_images', False)
        
        # 保存选项到会话
        request.session['export_options'] = {
            'include_images': include_images
        }
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'message': '导出选项已保存'
        })
    except Exception as e:
        logger.error(f"保存导出选项失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'保存导出选项失败: {str(e)}'
        }, status=500)