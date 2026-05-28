# -*- coding: utf-8 -*-
"""
test_download.py

核心职责：
此文件是专用的集成自动化测试脚本，旨在通过指定参数一键下载 YouTube 特定视频的特定片段。

测试用例详情：
- 目标链接: https://www.youtube.com/watch?v=TnG89ChN9LQ
- 切片时间: 10秒 到 20秒（总长度10秒）
- 机制: 导入主运行模块 `download_clip` 并触发其命令行接口进行全业务流程的端到端（E2E）集成测试。

执行方式：
venv\Scripts\python test_download.py
"""

import sys
import download_clip

# 重定向本地 print，复用下载器的安全输出，保障测试报告防乱码
print = download_clip.safe_print

if __name__ == "__main__":
    test_runs = [
        ["20", "30"]
    ]
    
    print("[*] 正在启动自动化多片段集成测试用例...")
    
    for i, (start_t, end_t) in enumerate(test_runs, 1):
        test_args = [
            "https://www.youtube.com/watch?v=TnG89ChN9LQ",
            "-s", start_t,
            "-e", end_t,
            "-p", "127.0.0.1:7890",
            "-c", "0d24036b-958b-437b-a104-e9b0338dafc6.txt",
            "-r", "2k"
        ]
        print(f"\n======================================================")
        print(f"[*] [任务 {i}/{len(test_runs)}] 开始执行：{start_t} 到 {end_t}")
        print(f"[*] 执行参数: python download_clip.py {' '.join(test_args)}\n")
        
        try:
            download_clip.main(test_args)
            print(f"\n[SUCCESS] 片段 {start_t}-{end_t} 下载成功！")
        except SystemExit as e:
            if e.code == 0:
                print(f"\n[SUCCESS] 片段 {start_t}-{end_t} 下载成功！")
            else:
                print(f"\n[FAIL] 片段 {start_t}-{end_t} 下载失败，状态码: {e.code}")
                sys.exit(e.code)
        except Exception as ex:
            print(f"\n[FAIL] 执行片段 {start_t}-{end_t} 时发生未捕获异常: {ex}")
            sys.exit(1)
            
    print("\n======================================================")
    print("[SUCCESS] 恭喜！所有片段下载任务均已圆满完成！")
