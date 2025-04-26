from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100)
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
        ('D', 'D'),
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

    @classmethod
    def search_by_stroke_order(cls, stroke_pattern):
        """
        根据笔顺模式搜索汉字
        :param stroke_pattern: 笔顺模式，如"横,竖"
        :return: 匹配的汉字QuerySet
        """
        if not stroke_pattern:
            return cls.objects.none()
            
        # 将搜索模式转换为列表
        pattern_list = [p.strip() for p in stroke_pattern.split(' ')]
        
        # 构建查询
        query = cls.objects.all()
        
        # 对每个笔画进行过滤
        for stroke in pattern_list:
            if stroke:
                # 使用包含查询，考虑到数据格式包含中括号和引号
                query = query.filter(stroke_order__contains=stroke)
                
        return query