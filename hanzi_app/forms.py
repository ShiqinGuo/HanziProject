from django import forms
from .models import Hanzi

class HanziForm(forms.ModelForm):
    class Meta:
        model = Hanzi
        fields = ['character', 'pinyin', 'stroke_count', 'structure', 
                 'variant', 'level', 'stroke_order', 'comment']
        
    def clean_character(self):
        character = self.cleaned_data.get('character')
        if len(character) != 1:
            raise forms.ValidationError('请输入单个汉字')
        return character
    
    def clean_stroke_count(self):
        stroke_count = self.cleaned_data.get('stroke_count')
        if stroke_count < 1 or stroke_count > 50:
            raise forms.ValidationError('笔画数必须在1-50之间')
        return stroke_count

class ImportForm(forms.Form):
    file = forms.FileField(
        label='选择文件',
        help_text='请选择JSON格式的数据文件'
    )
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if not file.name.endswith('.json'):
            raise forms.ValidationError('只支持JSON格式的文件')
        return file