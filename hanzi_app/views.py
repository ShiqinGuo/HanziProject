from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.paginator import Paginator
from django.http import JsonResponse, FileResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import transaction
from django.db.models import Value, F  
from django.db.models import IntegerField  
import json
import os
import shutil
import zipfile
from .models import Hanzi
from .forms import HanziForm
import time

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
    hanzi_list = Hanzi.objects.all().order_by('id')
    
    # 搜索功能
    search_char = request.GET.get('search', '')
    if search_char:
        hanzi_list = hanzi_list.filter(character__exact=search_char)
    
    # 筛选参数处理
    stroke_range = list(range(1, 21))
    stroke_count = request.GET.get('stroke_count', '所有')
    try:
        # 安全转换参数为整数
        if stroke_count.isdigit():
            stroke_count = int(stroke_count)
        else:
            stroke_count = '所有'
    except AttributeError:  # 处理空值情况
        stroke_count = '所有'
    
    # 应用筛选条件
    if stroke_count != '所有' and isinstance(stroke_count, int):
        hanzi_list = hanzi_list.filter(stroke_count=stroke_count)
    structure = request.GET.get('structure') or '所有'
    variant = request.GET.get('variant') or '所有'
    level = request.GET.get('level') or '所有'
    
    # 应用筛选条件
    if stroke_count != '所有' and isinstance(stroke_count, int):
        hanzi_list = hanzi_list.filter(stroke_count=stroke_count)
    if structure != '所有':
        hanzi_list = hanzi_list.filter(structure=structure)
    if variant != '所有':
        hanzi_list = hanzi_list.filter(variant=variant)
    if level != '所有':
        hanzi_list = hanzi_list.filter(level=level)
    
    # 分页处理
    paginator = Paginator(hanzi_list, 25)  # 每页显示25条
    
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # 修复模板上下文变量
    context = {
        'page_obj': page_obj,  # 使用标准分页对象
        'stroke_count_options': stroke_range,
        'search_char': request.GET.get('search', ''),
        'selected_stroke': stroke_count,
        'selected_structure': structure,
        'selected_variant': variant,
        'selected_level': level,
        # 添加排序参数
        'order_by': 'stroke_count'
    }
    return render(request, 'hanzi_app/index.html', context)
def get_stroke_count(request, char):
    count = stroke_dict.get(char, '0')
    return JsonResponse({'stroke_count': count})
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
            structure = request.POST.get('structure')
            variant = request.POST.get('variant')
            level = request.POST.get('level')
            pinyin = request.POST.get('pinyin')
            comment = request.POST.get('comment', '')
            stroke_order = request.POST.get('stroke_order')
            
            
            raw_stroke_count = request.POST.get('stroke_count')
            
            try:
                stroke_count = int(raw_stroke_count)
            except (ValueError, TypeError) as e:
                return HttpResponse("无效的笔画数格式", status=400)
            # Validate required fields
            image_file = request.FILES.get('image_file')
            standard_file = request.FILES.get('standard_file')
            if not all([stroke_order, pinyin, level, variant, image_file, standard_file]):
                return HttpResponse("所有必填字段都必须填写", status=400)
            # Create form with properly ordered data
            form = HanziForm({
                'character': character,
                'stroke_count': stroke_count,
                'structure': structure,
                'variant': variant,
                'level': level,
                'pinyin': pinyin,
                'comment': comment
            })
            if not form.is_valid():
                return HttpResponse(f"表单验证失败: {form.errors.as_text()}", status=400)
                hanzi = form.save(commit=False)
                hanzi.id = generated_id
                hanzi.stroke_order = stroke_order
                hanzi.pinyin = pinyin
                hanzi.level = level
                hanzi.comment = request.POST.get('comment', '')
                hanzi.variant = variant
                if not allowed_file(image_file.name) or not allowed_file(standard_file.name):
                    return HttpResponse("不支持的文件类型", status=400)
            # 生成文件名
            user_filename = generate_filename(generated_id, "0", image_file.name)
            standard_filename = generate_filename(generated_id, "1", standard_file.name)
            # 保存文件
            user_path = os.path.join(UPLOAD_FOLDER, user_filename)
            standard_path = os.path.join(UPLOAD_FOLDER, standard_filename)
            with open(user_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)
                    
            with open(standard_path, 'wb+') as destination:
                for chunk in standard_file.chunks():
                    destination.write(chunk)
            # 创建记录
            hanzi = Hanzi(
                id=generated_id,
                character=character,
                image_path=f"uploads/{user_filename}",  
                stroke_count=stroke_count,
                structure=structure,
                stroke_order=stroke_order,
                pinyin=pinyin,
                level=level,
                comment=comment,
                variant=variant,
                standard_image=f"uploads/{standard_filename}"  
            )
            hanzi.save()
            return redirect('hanzi_app:index')
            
        except Exception as e:
            return HttpResponse(f"系统错误: {str(e)}", status=500)
    
    structure_options = [choice[0] for choice in Hanzi.STRUCTURE_CHOICES]
    variant_options = [choice[0] for choice in Hanzi.VARIANT_CHOICES]
    return render(request, 'hanzi_app/add.html', {
        'structure_options': structure_options,
        'variant_options': variant_options
    })

def hanzi_detail(request, hanzi_id):
    hanzi = get_object_or_404(Hanzi, pk=hanzi_id)
    return render(request, 'hanzi_app/detail.html', {'hanzi': hanzi})

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
            
            # 如果结构类型发生变化
            if old_structure != new_structure:
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
                    
                    # 更新数据库ID
                    hanzi.id = generated_id
            
            # 更新基本信息
            hanzi.character = request.POST.get('character')
            hanzi.stroke_count = int(request.POST.get('stroke_count'))
            hanzi.structure = new_structure
            hanzi.stroke_order = request.POST.get('stroke_order')
            hanzi.pinyin = request.POST.get('pinyin')
            hanzi.level = request.POST.get('level')
            hanzi.comment = request.POST.get('comment', '')
            hanzi.variant = request.POST.get('variant')
            
            # 处理新图片（原有逻辑保持不变）
            new_image_file = request.FILES.get('new_image_file')
            new_standard_file = request.FILES.get('new_standard_file')
            
            if new_image_file and allowed_file(new_image_file.name):
                # 删除旧图片
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
                remove_existing_files(hanzi.standard_image.replace('uploads/', ''))
                
                # 保存新图片
                standard_filename = generate_filename(hanzi.id, "1", new_standard_file.name)
                standard_path = os.path.join(UPLOAD_FOLDER, standard_filename)
                
                with open(standard_path, 'wb+') as destination:
                    for chunk in new_standard_file.chunks():
                        destination.write(chunk)
                
                hanzi.standard_image = f"uploads/{standard_filename}"
            
            hanzi.save()
            return redirect('hanzi_app:index')
            
        except Exception as e:
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

@csrf_exempt
def import_data(request):
    if request.method == 'POST':
        # 新增Excel文件处理逻辑
        if 'excel_file' not in request.FILES:
            return JsonResponse({'success': False, 'message': '未选择Excel文件'})
        
        excel_file = request.FILES['excel_file']
        zip_file = request.FILES['image_zip']
        
        # 创建临时解压目录
        image_dir = os.path.join(settings.MEDIA_ROOT, 'temp_images', str(time.time()))
        os.makedirs(image_dir, exist_ok=True)
        
        # 解压ZIP文件
        with zipfile.ZipFile(zip_file, 'r') as zf:
            zf.extractall(image_dir)
        
        def generate_events():
            try:
                import pandas as pd
                import sys
                sys.path.append(str(settings.BASE_DIR))
                from hanzi_app.generate import get_pinyin, get_stroke_order
                # 读取Excel数据
                df = pd.read_excel(excel_file, header=1)
                total = len(df)
                processed = 0
                success_count = 0
                errors = []
                
                # 遍历Excel
                for index, row in df.iterrows():
                    try:
                        # 调用ID生成函数
                        structure = row.get('structure', '未知结构')
                        fake_request = type('', (object,), {
                            'body': json.dumps({'structure': structure}),
                            'method': 'POST'  
                        })()
                        id_response = generate_id(fake_request)
                        new_id = json.loads(id_response.content)['id']
                        
                        # 获取预加载数据
                        char = row['character']
                        stroke_count = int(stroke_dict.get(char, 0))
                        
                        # 调用generate.py中的功能
                        pinyin_result = get_pinyin(char)[0]  # 取第读音
                        stroke_order = get_stroke_order(char)[0]  # 取笔顺数据
                        
                        # 处理图片文件
                        image_filename = f"{row['image_path']}.jpg"
                        src_path = os.path.join(image_dir, os.listdir(image_dir)[0],image_filename)
                        if not os.path.exists(src_path):
                            raise FileNotFoundError(f"图片文件 {src_path} 不存在")
                        # 保存用户图片
                        user_filename = f"{new_id}0.jpg"
                        dest_path = os.path.join(UPLOAD_FOLDER, user_filename)
                        shutil.copy(src_path, dest_path)
                        
                        # 创建数据库记录
                        new_hanzi = Hanzi(
                            id=new_id,
                            character=char,
                            image_path=f"uploads/{user_filename}",
                            stroke_count=stroke_count,
                            structure=structure,
                            stroke_order=stroke_order,
                            pinyin=pinyin_result,
                            level=row['level'],
                            variant=row.get('variant', '简体'),
                            standard_image=f"uploads/{user_filename}",  ####后续修改
                            comment=row.get('comment', '')
                        )
                        new_hanzi.save()
                        
                        success_count += 1
                        
                    except Exception as e:
                        errors.append(f"行{index+2}: {str(e)}")
                    
                    processed += 1
                    progress = (processed / total * 100)
                    yield f"data: {json.dumps({'progress': progress, 'processed': processed, 'success': success_count, 'errors': len(errors)})}\n\n"
                
                yield f"data: {json.dumps({'success': True, 'message': f'成功导入 {success_count} 条记录，失败 {len(errors)} 条', 'errors': errors})}\n\n"
            
            except Exception as e:
                yield f"data: {json.dumps({'success': False, 'message': f'导入失败: {str(e)}'})}\n\n"
        
        return EventStreamResponse(generate_events())
    
    return render(request, 'hanzi_app/import.html')

@csrf_exempt
def export_data(request):
    try:
        # 获取选中的ID
        ids_param = request.GET.get('ids', '')
        include_images = request.GET.get('include_images', 'false') == 'true'
        
        # 创建导出目录
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # 准备数据
        if ids_param:
            ids = ids_param.split(',')
            hanzi_list = Hanzi.objects.filter(id__in=ids)
        else:
            hanzi_list = Hanzi.objects.all()
        
        # 导出数据
        export_data = []
        for hanzi in hanzi_list:
            export_data.append({
                'id': hanzi.id,
                'character': hanzi.character,
                'stroke_count': hanzi.stroke_count,
                'structure': hanzi.structure,
                'stroke_order': hanzi.stroke_order,
                'pinyin': hanzi.pinyin,
                'level': hanzi.level,
                'comment': hanzi.comment,
                'variant': hanzi.variant,
                'image_path': hanzi.image_path,
                'standard_image': hanzi.standard_image
            })
        
        # 创建JSON文件
        timestamp = int(time.time())
        json_filename = f'hanzi_export_{timestamp}.json'
        json_path = os.path.join(export_dir, json_filename)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        # 创建ZIP文件
        zip_filename = f'hanzi_export_{timestamp}.zip'
        zip_path = os.path.join(export_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # 添加JSON数据
            zf.write(json_path, os.path.basename(json_path))
            
            # 添加图片文件
            if include_images:
                for hanzi in hanzi_list:
                    # 用户上传图片
                    if hanzi.image_path:
                        image_path = os.path.join(settings.MEDIA_ROOT, hanzi.image_path)
                        if os.path.exists(image_path):
                            zf.write(image_path, f'images/{os.path.basename(image_path)}')
                    
                    # 标准图片
                    if hanzi.standard_image:
                        standard_path = os.path.join(settings.MEDIA_ROOT, hanzi.standard_image)
                        if os.path.exists(standard_path):
                            zf.write(standard_path, f'images/{os.path.basename(standard_path)}')
        
        # 返回下载链接
        return JsonResponse({'file': zip_filename})
        
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
            response['Content-Type'] = 'application/zip'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def clear_selected(request):
    """清除所有选中的条目"""
    return JsonResponse({'success': True})