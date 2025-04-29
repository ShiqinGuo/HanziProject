import os
import urllib.request
import shutil
from pathlib import Path

def download_file(url, destination):
    """下载文件到指定目录"""
    print(f"正在下载: {url} 到 {destination}")
    try:
        with urllib.request.urlopen(url) as response:
            with open(destination, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
        print(f"下载完成: {destination}")
        return True
    except Exception as e:
        print(f"下载失败: {url}, 错误: {e}")
        return False

def main():
    # 定义项目根目录
    project_dir = Path(__file__).resolve().parent
    
    # 创建静态文件目录结构
    css_dir = project_dir / "static" / "css"
    js_dir = project_dir / "static" / "js"
    images_dir = project_dir / "static" / "images"
    
    # 确保目录存在
    for directory in [css_dir, js_dir, images_dir]:
        os.makedirs(directory, exist_ok=True)
    
    # 定义需要下载的文件
    files_to_download = [
        # CSS文件
        {
            "url": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
            "path": css_dir / "bootstrap.min.css"
        },
        {
            "url": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
            "path": css_dir / "all.min.css"
        },
        # JavaScript文件
        {
            "url": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js",
            "path": js_dir / "bootstrap.bundle.min.js"
        },
        {
            "url": "https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js",
            "path": js_dir / "jquery.min.js"
        },
        # 也可以添加网站图标
        {
            "url": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.0.0/svgs/solid/book-open.svg",
            "path": images_dir / "favicon.ico"
        },
    ]
    
    # 下载所有文件
    success_count = 0
    for file_info in files_to_download:
        if download_file(file_info["url"], file_info["path"]):
            success_count += 1
    
    # 下载Font Awesome webfonts（它们通常由all.min.css引用）
    webfonts_dir = project_dir / "static" / "webfonts"
    os.makedirs(webfonts_dir, exist_ok=True)
    
    # 常见的Font Awesome字体文件
    fa_files = [
        "fa-solid-900.woff2",
        "fa-solid-900.woff",
        "fa-solid-900.ttf",
        "fa-regular-400.woff2",
        "fa-regular-400.woff",
        "fa-regular-400.ttf",
        "fa-brands-400.woff2",
        "fa-brands-400.woff",
        "fa-brands-400.ttf"
    ]
    
    for fa_file in fa_files:
        url = f"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/webfonts/{fa_file}"
        path = webfonts_dir / fa_file
        if download_file(url, path):
            success_count += 1
    
    print(f"\n总计：成功下载 {success_count} 个文件")
    print(f"文件已保存到：{project_dir}/static/")
    
    # 更新Font Awesome CSS中的字体路径
    try:
        fa_css_path = css_dir / "all.min.css"
        if fa_css_path.exists():
            with open(fa_css_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换字体URL路径
            content = content.replace('../webfonts/', '../webfonts/')
            
            with open(fa_css_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("已更新Font Awesome CSS中的字体路径")
    except Exception as e:
        print(f"更新CSS字体路径时出错: {e}")

if __name__ == "__main__":
    main() 