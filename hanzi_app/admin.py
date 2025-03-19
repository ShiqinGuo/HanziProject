from django.contrib import admin
from .models import Hanzi

@admin.register(Hanzi)
class HanziAdmin(admin.ModelAdmin):
    list_display = ['id', 'character', 'pinyin', 'stroke_count', 'level', 'structure']
    list_filter = ['level', 'structure', 'variant']
    search_fields = ['character', 'pinyin', 'id']
    ordering = ['stroke_count', 'character']