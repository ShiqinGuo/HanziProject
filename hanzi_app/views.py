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

# 在文件顶部添加日志配置
logger = logging.getLogger(__name__)

# 预加载笔画数据
stroke_dict = {}
stoke_file_path = os.path.join(settings.BASE_DIR, 'data\ch_match\stoke.txt')
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
@login_required
def index(request):
    # 移除缓存相关代码，直接查询数据库
    hanzi_list = Hanzi.objects.all().order_by('id')
    
    # 获取筛选参数
    search = request.GET.get('search', '')
    structure = request.GET.get('structure', '')
    level = request.GET.get('level', '')
    variant = request.GET.get('variant', '')
    stroke_count = request.GET.get('stroke_count', '')
    
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
    page_number = request.GET.get('page', 1)
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
    hanzi = get_object_or_404(Hanzi, pk=hanzi_id)
    
    # 处理笔顺格式
    if hanzi.stroke_order:
        # 去除中括号和引号，只保留实际的笔顺内容
        stroke_order = hanzi.stroke_order.strip("[]'")
    else:
        stroke_order = ""
    
    context = {
        'hanzi': hanzi,
        'stroke_order': stroke_order
    }
    return render(request, 'hanzi_app/detail.html', context)

def delete_hanzi(request, hanzi_id):
    hanzi = get_object_or_404(Hanzi, pk=hanzi_id)
    try:
        # 删除关联的图片文件
        remove_existing_files(hanzi.image_path.replace('uploads/', ''))
        remove_existing_files(hanzi.standard_image.replace('uploads/', ''))
        
        # 删除数据库记录
        hanzi.delete()
        return redirect(f"{reverse('hanzi_app:index')}?{request.GET.urlencode()}")
    except Exception as e:
        return HttpResponse(f"删除失败: {str(e)}", status=500)
def edit_hanzi(request, hanzi_id):
    hanzi = get_object_or_404(Hanzi, pk=hanzi_id)
    
    if request.method == 'POST':
        try:
            # 获取新旧结构类型
            old_structure = hanzi.structure
            new_structure = request.POST.get('structure')
            generated_id = request.POST.get('generated_id')
            character = request.POST.get('character')
            
            # 自动获取笔顺
            stroke_order = request.POST.get('stroke_order', '')
            if not stroke_order and character:
                # 如果用户没有输入笔顺，尝试自动获取
                stroke_orders = get_stroke_order(character)
                if stroke_orders and stroke_orders[0]:
                    stroke_order = stroke_orders[0]
            
            # 如果结构类型发生变化且ID也变化
            if old_structure != new_structure and hanzi.id != generated_id:
                # 使用事务保证数据一致性
                with transaction.atomic():
                    # 生成新文件名前缀
                    new_prefix = generated_id
                    old_prefix = hanzi.id
                    
                    # 更新所有关联文件路径
                    for field in ['image_path', 'standard_image']:
                        old_path = getattr(hanzi, field)
                        if old_path:
                            # 修复路径处理：使用os.path规范化路径
                            old_full_path = os.path.normpath(os.path.join(settings.MEDIA_ROOT, old_path))
                            # 添加文件存在性检查
                            if not os.path.exists(old_full_path):
                                print(f"警告：文件 {old_full_path} 不存在，跳过重命名")
                                continue
                            # 提取原文件后缀（0或1）
                            suffix = old_path.split('/')[-1].split('.')[0][-1]
                            # 构建新文件名
                            new_filename = f"{new_prefix}{suffix}.{old_path.split('.')[-1]}"
                            # 重命名文件
                            new_full_path = os.path.join(UPLOAD_FOLDER, new_filename)
                            
                            os.rename(old_full_path, new_full_path)
                            # 更新为相对路径
                            setattr(hanzi, field, f"uploads/{new_filename}")
                    
                    # 检查是否已存在相同ID的记录
                    if Hanzi.objects.filter(id=generated_id).exists():
                        # 如果存在，则使用原ID
                        logger.warning(f"ID {generated_id} 已存在，保持原ID {hanzi.id}")
                    else:
                        # 更新数据库ID
                        old_id = hanzi.id
                        hanzi.id = generated_id
                        # 删除旧记录（如果存在）
                        Hanzi.objects.filter(id=old_id).exclude(pk=hanzi.pk).delete()
            
            # 更新基本信息
            hanzi.character = character
            hanzi.stroke_count = int(request.POST.get('stroke_count'))
            hanzi.structure = new_structure
            hanzi.stroke_order = stroke_order
            hanzi.pinyin = request.POST.get('pinyin')
            hanzi.level = request.POST.get('level')
            hanzi.comment = request.POST.get('comment', '')
            hanzi.variant = request.POST.get('variant')
            
            # 处理新图片
            new_image_file = request.FILES.get('new_image_file')
            new_standard_file = request.FILES.get('new_standard_file')
            
            if new_image_file and allowed_file(new_image_file.name):
                # 删除旧图片
                if hanzi.image_path:
                    remove_existing_files(hanzi.image_path.replace('uploads/', ''))
                
                # 保存新图片
                user_filename = generate_filename(hanzi.id, "0", new_image_file.name)
                user_path = os.path.join(UPLOAD_FOLDER, user_filename)
                
                with open(user_path, 'wb+') as destination:
                    for chunk in new_image_file.chunks():
                        destination.write(chunk)
                
                hanzi.image_path = f"uploads/{user_filename}"
            
            if new_standard_file and allowed_file(new_standard_file.name):
                # 删除旧图片
                if hanzi.standard_image:
                    remove_existing_files(hanzi.standard_image.replace('uploads/', ''))
                
                # 保存新图片
                standard_filename = generate_filename(hanzi.id, "1", new_standard_file.name)
                standard_path = os.path.join(UPLOAD_FOLDER, standard_filename)
                
                with open(standard_path, 'wb+') as destination:
                    for chunk in new_standard_file.chunks():
                        destination.write(chunk)
                
                hanzi.standard_image = f"uploads/{standard_filename}"
            
            # 保存更新后的汉字对象
            hanzi.save()
            
            # 修改：不再重定向，而是返回成功消息
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': '保存成功', 'id': hanzi.id})
            else:
                # 重新获取更新后的汉字对象
                hanzi = get_object_or_404(Hanzi, pk=hanzi.id)
                structure_options = [choice[0] for choice in Hanzi.STRUCTURE_CHOICES]
                variant_options = [choice[0] for choice in Hanzi.VARIANT_CHOICES]
                context = {
                    'hanzi': hanzi,
                    'structure_options': structure_options,
                    'variant_options': variant_options,
                    'success_message': '保存成功！'
                }
                return render(request, 'hanzi_app/edit.html', context)
            
        except Exception as e:
            logger.error(f"更新汉字失败: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            else:
                return HttpResponse(f"更新失败: {str(e)}", status=500)
    
    # 原有返回逻辑保持不变
    structure_options = [choice[0] for choice in Hanzi.STRUCTURE_CHOICES]
    variant_options = [choice[0] for choice in Hanzi.VARIANT_CHOICES]
    return render(request, 'hanzi_app/edit.html', {
        'hanzi': hanzi,
        'structure_options': structure_options,
        'variant_options': variant_options
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

@require_http_methods(["GET", "POST"])
def import_data(request):
    if request.method == 'POST':
        try:
            # 处理Excel文件导入
            if 'excel_file' in request.FILES:
                excel_file = request.FILES['excel_file']  # 使用excel_file变量名
                zip_file = request.FILES.get('image_zip')
                
                # 创建临时解压目录
                image_dir = os.path.join(settings.MEDIA_ROOT, 'temp_images', str(time.time()))
                os.makedirs(image_dir, exist_ok=True)
                
                # 如果有ZIP文件，解压它
                if zip_file:
                    with zipfile.ZipFile(zip_file, 'r') as zf:
                        zf.extractall(image_dir)
                
                def generate_events():
                    try:
                        # 读取Excel文件
                        df = pd.read_excel(excel_file, header=1)  # 使用excel_file而不是file
                        total = len(df)
                        processed = 0
                        success_count = 0
                        errors = []
                        
                        for index, row in df.iterrows():
                            try:
                                # 提取必要字段
                                char = str(row.get('character', ''))
                                if not char or len(char.strip()) != 1:
                                    errors.append(f"记录缺少有效的汉字字符: {row}")
                                    continue
                                
                                # 处理ID，如果没有则生成
                                structure = row.get('structure', '未知结构')
                                new_id = generate_new_id(structure)
                                
                                # 处理图片文件
                                image_path = ""
                                if zip_file and 'image_path' in row and row['image_path']:
                                    # 直接使用Excel中的image_path值作为文件名
                                    image_filename = f"{row['image_path']}.jpg"
                                    
                                    # 查找图片文件
                                    found = False
                                    for root, dirs, files in os.walk(image_dir):
                                        for file in files:
                                            if file.lower() == image_filename.lower():
                                                src_path = os.path.join(root, file)
                                                # 保存用户图片到uploads目录
                                                dest_path = os.path.join(UPLOAD_FOLDER, image_filename)
                                                shutil.copy(src_path, dest_path)
                                                image_path = f"uploads/{image_filename}"
                                                found = True
                                                break
                                        if found:
                                            break
                                
                                # 自动获取笔顺
                                pinyin = get_pinyin(char)[0]
                                stroke_orders = get_stroke_order(char)
                                if stroke_orders and stroke_orders[0]:
                                    stroke_order = stroke_orders[0]
                                else:
                                    stroke_order = ''
                                
                                # 创建新汉字对象
                                new_hanzi = Hanzi(
                                    id=new_id,
                                    character=char,
                                    stroke_count=int(row.get('stroke_count', stroke_dict.get(char, 0))),
                                    structure=structure,
                                    pinyin=pinyin,
                                    level=row.get('level', 'A'),
                                    variant=row.get('variant', '简体'),
                                    comment=row.get('comment', ''),
                                    image_path=image_path,
                                    stroke_order=stroke_order
                                )
                                
                                # 保存到数据库
                                new_hanzi.save()
                                
                                # 自动生成标准图片并更新数据库
                                standard_path = generate_hanzi_image(char)
                                if standard_path:
                                    # 提取相对路径并更新数据库
                                    rel_path = os.path.join("standard_images", f"{char}.jpg")
                                    Hanzi.objects.filter(id=new_id).update(standard_image=rel_path)
                                
                                success_count += 1
                                
                            except Exception as e:
                                errors.append(f"处理记录时出错: {str(e)}, 记录: {row}")
                            
                            processed += 1
                            progress = (processed / total * 100)
                            yield f"data: {json.dumps({'progress': progress, 'processed': processed, 'success': success_count, 'errors': len(errors)})}\n\n"
                        
                        # 导入完成后返回结果
                        yield f"data: {json.dumps({'success': True, 'message': f'成功导入 {success_count} 条记录，失败 {len(errors)} 条', 'errors': errors})}\n\n"
                        
                        # 导入完成后自动生成所有标准图片
                        from .generate import generate_all_standard_images
                        generate_all_standard_images()
                        
                    except Exception as e:
                        yield f"data: {json.dumps({'success': False, 'message': f'导入失败: {str(e)}'})}\n\n"
                
                return EventStreamResponse(generate_events())
            
            # 处理JSON文件导入
            elif 'file' in request.FILES:
                json_file = request.FILES['file']  # 使用json_file变量名
                zip_file = request.FILES.get('image_zip')
                
                # 创建临时解压目录
                image_dir = os.path.join(settings.MEDIA_ROOT, 'temp_images', str(time.time()))
                os.makedirs(image_dir, exist_ok=True)
                
                # 如果有ZIP文件，解压它
                if zip_file:
                    with zipfile.ZipFile(zip_file, 'r') as zf:
                        zf.extractall(image_dir)
                
                def generate_events():
                    try:
                        data = json.loads(json_file.read().decode('utf-8'))  # 使用json_file而不是file
                        total = len(data)
                        processed = 0
                        success_count = 0
                        errors = []
                        
                        for item in data:
                            try:
                                # 提取必要字段
                                char = item.get('character')
                                if not char or len(str(char).strip()) != 1:
                                    errors.append(f"记录缺少有效的汉字字符: {item}")
                                    continue
                                
                                # 处理ID，如果没有则生成
                                new_id = str(item.get('id', ''))
                                if not new_id:
                                    # 生成ID的逻辑
                                    structure = item.get('structure', '未知结构')
                                    new_id = generate_new_id(structure)
                                
                                # 处理图片文件 - 使用JSON中的image_path字段
                                image_path = ""
                                if zip_file and 'image_path' in item and item['image_path']:
                                    # 直接使用JSON中的image_path值作为文件名
                                    image_filename = f"{item['image_path']}.jpg"
                                    
                                    # 查找图片文件
                                    found = False
                                    for root, dirs, files in os.walk(image_dir):
                                        for file in files:
                                            if file.lower() == image_filename.lower():
                                                src_path = os.path.join(root, file)
                                                # 保存用户图片到uploads目录
                                                dest_path = os.path.join(UPLOAD_FOLDER, image_filename)
                                                shutil.copy(src_path, dest_path)
                                                image_path = f"uploads/{image_filename}"
                                                found = True
                                                break
                                        if found:
                                            break
                                
                                # 自动获取笔顺
                                stroke_order = item.get('stroke_order', '')
                                if not stroke_order:
                                    # 如果JSON中没有笔顺，尝试自动获取
                                    stroke_orders = get_stroke_order(char)
                                    if stroke_orders and stroke_orders[0]:
                                        stroke_order = stroke_orders[0]
                                
                                # 创建新汉字对象
                                new_hanzi = Hanzi(
                                    id=new_id,
                                    character=str(char),
                                    stroke_count=int(item.get('stroke_count', 0)),
                                    structure=item.get('structure', '未知结构'),
                                    pinyin=item.get('pinyin', ''),
                                    level=item.get('level', 'A'),
                                    variant=item.get('variant', '简体'),
                                    comment=item.get('comment', ''),
                                    image_path=image_path,
                                    stroke_order=stroke_order
                                )
                                
                                # 保存到数据库
                                new_hanzi.save()
                                
                                # 自动生成标准图片并更新数据库
                                standard_path = generate_hanzi_image(char)
                                if standard_path:
                                    # 提取相对路径并更新数据库
                                    rel_path = os.path.join("standard_images", f"{char}.jpg")
                                    Hanzi.objects.filter(id=new_id).update(standard_image=rel_path)
                                
                                success_count += 1
                                
                            except Exception as e:
                                errors.append(f"处理记录时出错: {str(e)}, 记录: {item}")
                            
                            processed += 1
                            progress = (processed / total * 100)
                            yield f"data: {json.dumps({'progress': progress, 'processed': processed, 'success': success_count, 'errors': len(errors)})}\n\n"
                        
                        # 导入完成后返回结果
                        yield f"data: {json.dumps({'success': True, 'message': f'成功导入 {success_count} 条记录，失败 {len(errors)} 条', 'errors': errors})}\n\n"
                        
                        # 导入完成后自动生成所有标准图片
                        from .generate import generate_all_standard_images
                        generate_all_standard_images()
                        
                    except Exception as e:
                        yield f"data: {json.dumps({'success': False, 'message': f'导入失败: {str(e)}'})}\n\n"
                
                return EventStreamResponse(generate_events())
            
            else:
                return JsonResponse({'success': False, 'message': '未选择文件'})
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return render(request, 'hanzi_app/import.html')

def export_hanzi(request):
    """导出汉字数据为JSON和ZIP文件"""
    try:
        # 获取筛选参数
        search = request.GET.get('search', '')
        structure = request.GET.get('structure', '')
        level = request.GET.get('level', '')
        variant = request.GET.get('variant', '')
        stroke_count = request.GET.get('stroke_count', '')
        ids = request.GET.get('ids', '')
        
        # 查询数据库
        hanzi_list = Hanzi.objects.all().order_by('id')
        
        # 如果提供了ID列表，优先使用ID列表筛选
        if ids:
            id_list = ids.split(',')
            hanzi_list = hanzi_list.filter(id__in=id_list)
        else:
            # 应用其他筛选条件
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
        
        # 准备导出数据
        export_data = []
        for hanzi in hanzi_list:
            export_data.append({
                'id': hanzi.id,
                'character': hanzi.character,
                'pinyin': hanzi.pinyin,
                'stroke_count': hanzi.stroke_count,
                'structure': hanzi.structure,
                'level': hanzi.level,
                'variant': hanzi.variant,
                'stroke_order': hanzi.stroke_order,
                'comment': hanzi.comment,
                'image_path': hanzi.image_path,
                'standard_image': hanzi.standard_image
            })
        
        # 创建导出目录
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成时间戳文件名
        timestamp = int(time.time())
        json_filename = f'hanzi_export_{timestamp}.json'
        zip_filename = f'hanzi_images_{timestamp}.zip'
        
        # 保存JSON文件
        json_path = os.path.join(export_dir, json_filename)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=4)
        
        # 创建ZIP文件
        zip_path = os.path.join(export_dir, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # 添加所有图片到ZIP
            for hanzi in hanzi_list:
                if hanzi.image_path:
                    image_path = os.path.join(settings.MEDIA_ROOT, hanzi.image_path)
                    if os.path.exists(image_path):
                        zf.write(image_path, f'images/{os.path.basename(image_path)}')
                
                if hanzi.standard_image:
                    standard_path = os.path.join(settings.MEDIA_ROOT, hanzi.standard_image)
                    if os.path.exists(standard_path):
                        zf.write(standard_path, f'images/{os.path.basename(standard_path)}')
        
        # 返回下载链接
        return JsonResponse({
            'json_file': json_filename,
            'zip_file': zip_filename,
            'count': hanzi_list.count()
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def download_file(request, filename):
    if not filename:
        return JsonResponse({'error': '未指定文件名'}, status=400)
    
    file_path = os.path.join(settings.MEDIA_ROOT, 'exports', filename)
    if not os.path.exists(file_path):
        return JsonResponse({'error': '文件不存在'}, status=404)
    
    try:
        with open(file_path, 'rb') as f:
            response = FileResponse(f)
            
            # 设置正确的Content-Type
            if filename.endswith('.json'):
                response['Content-Type'] = 'application/json'
            elif filename.endswith('.zip'):
                response['Content-Type'] = 'application/zip'
            else:
                response['Content-Type'] = 'application/octet-stream'
            
            # 设置Content-Disposition为attachment，强制浏览器下载
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # 设置一个标记，表示这个文件已经被下载
            request.session[f'downloaded_{filename}'] = True
            
            return response
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def cleanup_exports(request):
    """清理已下载的导出文件"""
    try:
        files_to_delete = []
        
        # 检查会话中标记为已下载的文件
        for key in list(request.session.keys()):
            if key.startswith('downloaded_'):
                filename = key.replace('downloaded_', '')
                files_to_delete.append(filename)
                # 删除会话中的标记
                del request.session[key]
        
        # 删除文件
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        for filename in files_to_delete:
            file_path = os.path.join(export_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"已删除临时导出文件: {filename}")
        
        return JsonResponse({'success': True, 'deleted': len(files_to_delete)})
    except Exception as e:
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