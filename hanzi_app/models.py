from django.db import models

class Category(models.Model):
    name = models.CharField('类别名称', max_length=50)
    description = models.TextField('描述', blank=True)
    
    class Meta:
        verbose_name = '汉字类别'
        verbose_name_plural = verbose_name
        
    def __str__(self):
        return self.name


class Hanzi(models.Model):
    STRUCTURE_CHOICES = [
        ('未知结构', '未知结构'),
        ('左右结构', '左右结构'),
        ('上下结构', '上下结构'),
        ('包围结构', '包围结构'),
        ('独体结构', '独体结构'),
        ('品字结构', '品字结构'),
        ('穿插结构', '穿插结构'),
    ]
    VARIANT_CHOICES = [
        ('简体', '简体'),
        ('繁体', '繁体'),
    ]
    LEVEL_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
    ]

    id = models.CharField('编号', primary_key=True, max_length=5)
    character = models.CharField('汉字', max_length=1)  
    image_path = models.CharField('图片路径', max_length=255)
    stroke_count = models.IntegerField('笔画数')
    structure = models.CharField('结构类型', max_length=20, choices=STRUCTURE_CHOICES, default='未知结构')
    stroke_order = models.CharField('笔顺', max_length=100, blank=True, null=True)
    pinyin = models.CharField('拼音', max_length=50, blank=True, null=True)
    level = models.CharField('等级', max_length=1, choices=LEVEL_CHOICES)
    comment = models.TextField('评语', blank=True, null=True)
    variant = models.CharField('简繁体', max_length=10, choices=VARIANT_CHOICES, default='简体')
    standard_image = models.CharField('标准图片路径', max_length=255, blank=True, null=True)
    crt_time = models.DateTimeField('创建时间', auto_now_add=True)
    upd_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        managed = True  # 启用迁移管理
        db_table = 'hanzi'
        verbose_name = '汉字数据'
        verbose_name_plural = '汉字数据'
        
    def __str__(self):
        return f'{self.character}({self.id})'