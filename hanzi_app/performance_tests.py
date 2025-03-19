import os
import time
from django.test import TestCase
from PIL import Image
from hanzi_app.models import Hanzi
from hanzi_app.generate import generate_hanzi_image, generate_all_standard_images

class ImageGenerationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 初始化测试数据（500个不同汉字）
        Hanzi.objects.bulk_create([
            Hanzi(id=f'1{i:04}', character=chr(0x4e00+i), stroke_count=10) 
            for i in range(500)
        ])

    def test_batch_generation(self):
        """批量生成性能测试"""
        start_time = time.time()
        
        # 执行批量生成
        generate_all_standard_images()
        
        # 验证结果
        elapsed = time.time() - start_time
        print(f"\n生成500张图片耗时: {elapsed:.2f}秒")
        
        # 验证文件系统
        img_path = generate_hanzi_image('一')
        with Image.open(img_path) as img:
            self.assertEqual(img.size, (224, 224))
            
        # 验证数据库更新
        sample = Hanzi.objects.get(character='一')
        self.assertIsNotNone(sample.standard_image)

class StressTest(TestCase):
    def test_high_concurrency(self):
        """高并发请求模拟"""
        from concurrent.futures import ThreadPoolExecutor
        
        # 创建测试用汉字记录
        test_chars = [Hanzi(id=f'9{i:04}', character=chr(0x4e00+i), stroke_count=9) 
                     for i in range(100)]
        Hanzi.objects.bulk_create(test_chars)
        
        # 并行生成图片
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(generate_hanzi_image, char.character) 
                      for char in test_chars]
            
            for future in futures:
                path = future.result()
                self.assertTrue(os.path.exists(path))
