import subprocess
import os
import datetime
import time
import threading
import sys
import signal
import atexit

# 存储所有进程，以便在退出时关闭
processes = []

def check_redis_running():
    """检查Redis是否已经在运行"""
    try:
        result = subprocess.run('tasklist | findstr redis-server.exe', shell=True, capture_output=True, text=True)
        return result.returncode == 0 and 'redis-server.exe' in result.stdout
    except Exception:
        return False

def start_redis():
    """启动Redis服务器"""
    if check_redis_running():
        print("Redis已经在运行中")
        return None
    
    print("正在启动Redis服务...")
    redis_server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'redis', 'redis-server.exe')
    
    if not os.path.exists(redis_server_path):
        print(f"错误: Redis服务器不存在于路径: {redis_server_path}")
        return None
    
    try:
        redis_process = subprocess.Popen(redis_server_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Redis服务启动成功，进程ID: {redis_process.pid}")
        return redis_process
    except Exception as e:
        print(f"启动Redis失败: {str(e)}")
        return None

def start_celery():
    """启动Celery worker"""
    print("正在启动Celery worker...")
    # 使用当前Python解释器启动Celery
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 构建Celery命令 - 使用hanzi_project而不是hanzi_app
    celery_cmd = f"{sys.executable} -m celery -A hanzi_project worker -l info -P solo"
    
    try:
        # 在Windows上，我们使用shell=True
        celery_process = subprocess.Popen(celery_cmd, shell=True, cwd=current_dir)
        print(f"Celery worker启动成功，进程ID: {celery_process.pid}")
        return celery_process
    except Exception as e:
        print(f"启动Celery失败: {str(e)}")
        return None

def start_django():
    """启动Django服务器"""
    print("正在启动Django服务器...")
    command = 'python manage.py runserver'
    print(f"执行命令: {command}")
    
    try:
        django_process = subprocess.Popen(command, shell=True)
        print(f"Django服务器启动成功，进程ID: {django_process.pid}")
        return django_process
    except Exception as e:
        print(f"启动Django失败: {str(e)}")
        return None

def stop_processes():
    """停止所有服务进程"""
    print("\n正在关闭所有服务...")
    for process in processes:
        if process and process.poll() is None:  # 如果进程还在运行
            try:
                process.terminate()  # 尝试优雅地终止
                process.wait(timeout=5)  # 等待进程结束
            except:
                try:
                    process.kill()  # 如果无法终止，则强制杀死
                except:
                    pass
    print("所有服务已关闭")

def main():
    """主函数，启动所有服务"""
    # 创建logs目录
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # 记录启动时间
    start_time = datetime.datetime.now()
    print(f"=== 服务器启动于 {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 启动Redis
    redis_process = start_redis()
    if redis_process:
        processes.append(redis_process)
    
    # 等待Redis完全启动
    time.sleep(1)
    
    # 启动Celery
    celery_process = start_celery()
    if celery_process:
        processes.append(celery_process)
    
    # 等待Celery完全启动
    time.sleep(2)
    
    # 启动Django并等待其结束
    django_process = start_django()
    if django_process:
        processes.append(django_process)
        django_process.wait()  # 等待Django进程结束

    # 停止其他进程
    stop_processes()

if __name__ == '__main__':
    # 注册退出处理函数
    atexit.register(stop_processes)
    
    # 注册信号处理
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda s, f: sys.exit(0))
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n接收到中断信号，正在关闭服务...")
    except Exception as e:
        print(f"发生错误: {str(e)}")
    finally:
        stop_processes()

