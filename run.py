import subprocess
import os
import datetime

def main():
    command = 'python manage.py runserver'
    print(f"执行命令: {command}")
    subprocess.run(command, check=True, shell=True)

if __name__ == '__main__':
    main()

"""
要捕获控制台输出，请使用以下PowerShell命令：

powershell -Command "python run.py | Tee-Object -FilePath .\logs\server_log.txt"

或者使用命令提示符：

python run.py > logs\server_log.txt 2>&1

这将把所有控制台输出重定向到日志文件中。
"""
