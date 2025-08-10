import os
import sys
import subprocess
import time

def execute_scripts():
    """执行数据库相关脚本"""
    print("开始执行数据库初始化脚本...")

    # 切换到project目录
    project_dir = os.path.join(os.getcwd(), 'project')

    scripts = ['database.py', 'import_data.py', 'reset_sequences.py']

    for script in scripts:
        script_path = os.path.join(project_dir, script)
        if os.path.exists(script_path):
            print(f"正在执行 {script}...")
            try:
                result = subprocess.run([sys.executable, script_path],
                                      cwd=project_dir,
                                      capture_output=True,
                                      text=True,
                                      encoding='utf-8',
                                      errors='ignore')
                if result.returncode == 0:
                    print(f"✓ {script} 执行成功")
                    if result.stdout:
                        print(f"输出: {result.stdout}")
                else:
                    print(f"\n{'='*60}")
                    print(f"❌ 错误：{script} 文件执行失败！")
                    print(f"{'='*60}")
                    print(f"返回码: {result.returncode}")
                    if result.stderr:
                        print(f"错误详情:\n{result.stderr}")
                    print(f"{'='*60}")
                    print(f"由于 {script} 执行失败，停止执行后续脚本")
                    return False  # 返回失败状态
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"❌ 异常：{script} 文件执行时发生异常！")
                print(f"{'='*60}")
                print(f"异常详情: {e}")
                print(f"{'='*60}")
                print(f"由于 {script} 执行异常，停止执行后续脚本")
                return False  # 返回失败状态
        else:
            print(f"\n{'='*60}")
            print(f"❌ 文件缺失：{script} 文件不存在！")
            print(f"{'='*60}")
            print(f"请检查文件路径: {script_path}")
            print(f"{'='*60}")
            print(f"由于 {script} 文件不存在，停止执行后续脚本")
            return False  # 返回失败状态

        time.sleep(1)  # 给每个脚本之间一些间隔时间

    print("✓ 所有数据库初始化脚本执行完毕！")
    return True  # 返回成功状态

def main():
    """主函数"""
    print("="*50)
    print("           数据库初始化工具")
    print("="*50)

    try:
        success = execute_scripts()
        if success:
            print("\n程序执行成功，自动退出。")
        else:
            print("\n程序执行失败，请检查错误信息。")

    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()
