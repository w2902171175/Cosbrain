#!/usr/bin/env python3
"""
数据库畸形JSON修复脚本
修复因双重序列化导致的skills和required_skills字段问题
"""

import json
import re
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Student, Project


def _parse_malformed_json(malformed_str: str):
    """
    尝试解析各种畸形的JSON字符串，返回标准的Python对象
    """
    if not malformed_str or not isinstance(malformed_str, str):
        return []

    # 移除前后空白
    malformed_str = malformed_str.strip()

    # 如果已经是正常的JSON，直接解析
    try:
        parsed = json.loads(malformed_str)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return [parsed]
        else:
            return []
    except json.JSONDecodeError:
        pass

    # 处理嵌套字符串化的情况，如: '[{"name": "[{\'name\': \'计算机视觉\'"\''
    # 这种情况下，需要逐步解套
    current = malformed_str
    max_iterations = 5  # 防止无限循环
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # 尝试解析当前字符串
        try:
            parsed = json.loads(current)
            if isinstance(parsed, list):
                # 检查列表中的每个元素
                cleaned_list = []
                for item in parsed:
                    if isinstance(item, dict) and "name" in item:
                        # 正常的技能字典
                        cleaned_list.append({
                            "name": str(item["name"]).strip(),
                            "level": item.get("level", "初窥门径")
                        })
                    elif isinstance(item, str):
                        # 字符串形式的技能名或进一步的嵌套JSON
                        if item.startswith('[') or item.startswith('{'):
                            # 可能是嵌套的JSON字符串，递归处理
                            nested_result = _parse_malformed_json(item)
                            cleaned_list.extend(nested_result)
                        else:
                            # 纯技能名字符串
                            cleaned_list.append({
                                "name": item.strip(),
                                "level": "初窥门径"
                            })
                return cleaned_list
            elif isinstance(parsed, dict) and "name" in parsed:
                return [{
                    "name": str(parsed["name"]).strip(),
                    "level": parsed.get("level", "初窥门径")
                }]
            elif isinstance(parsed, str):
                # 字符串可能需要进一步解析
                current = parsed
                continue
            else:
                break
        except json.JSONDecodeError:
            # 尝试修复常见的JSON格式问题
            # 1. 替换单引号为双引号
            fixed_str = re.sub(r"'([^']*)'", r'"\1"', current)

            # 2. 处理Python的True/False/None
            fixed_str = fixed_str.replace("True", "true").replace("False", "false").replace("None", "null")

            if fixed_str != current:
                current = fixed_str
                continue
            else:
                break

    # 如果所有解析都失败，尝试从字符串中提取技能名称
    print(f"WARNING: 无法解析技能字符串，尝试提取技能名称: {malformed_str[:100]}...")

    # 使用正则表达式提取可能的技能名称
    skill_names = []

    # 匹配 "name": "技能名" 的模式
    name_matches = re.findall(r'"name"\s*:\s*"([^"]+)"', malformed_str)
    skill_names.extend(name_matches)

    # 匹配 'name': '技能名' 的模式
    name_matches_single = re.findall(r"'name'\s*:\s*'([^']+)'", malformed_str)
    skill_names.extend(name_matches_single)

    # 如果找到技能名称，返回标准格式
    if skill_names:
        return [{"name": name.strip(), "level": "初窥门径"} for name in skill_names if name.strip()]

    # 最后的回退：返回空列表
    return []


def fix_student_skills(db: Session):
    """修复学生表中的skills字段"""
    print("开始修复学生skills字段...")

    students = db.query(Student).all()
    fixed_count = 0

    for student in students:
        try:
            if student.skills is None:
                student.skills = []
                fixed_count += 1
                continue

            # 如果skills是字符串，说明可能存在序列化问题
            if isinstance(student.skills, str):
                print(f"发现字符串化的skills字段 - 学生ID {student.id}: {student.skills[:100]}...")
                fixed_skills = _parse_malformed_json(student.skills)
                student.skills = fixed_skills
                fixed_count += 1
            # 如果skills是列表，检查列表中的元素
            elif isinstance(student.skills, list):
                needs_fix = False
                fixed_skills = []

                for skill in student.skills:
                    if isinstance(skill, str):
                        # 技能项是字符串，可能需要解析
                        if skill.startswith('[') or skill.startswith('{'):
                            needs_fix = True
                            parsed_skills = _parse_malformed_json(skill)
                            fixed_skills.extend(parsed_skills)
                        else:
                            # 纯技能名字符串
                            fixed_skills.append({"name": skill.strip(), "level": "初窥门径"})
                    elif isinstance(skill, dict) and "name" in skill:
                        # 正常的技能字典
                        fixed_skills.append({
                            "name": str(skill["name"]).strip(),
                            "level": skill.get("level", "初窥门径")
                        })
                    else:
                        needs_fix = True
                        print(f"异常的技能项格式 - 学生ID {student.id}: {skill}")

                if needs_fix:
                    student.skills = fixed_skills
                    fixed_count += 1

        except Exception as e:
            print(f"修复学生ID {student.id} 的skills时出错: {e}")
            student.skills = []
            fixed_count += 1

    print(f"学生skills修复完成，共修复 {fixed_count} 条记录")
    return fixed_count


def fix_project_required_skills(db: Session):
    """修复项目表中的required_skills字段"""
    print("开始修复项目required_skills字段...")

    projects = db.query(Project).all()
    fixed_count = 0

    for project in projects:
        try:
            if project.required_skills is None:
                project.required_skills = []
                fixed_count += 1
                continue

            # 如果required_skills是字符串，说明可能存在序列化问题
            if isinstance(project.required_skills, str):
                print(f"发现字符串化的required_skills字段 - 项目ID {project.id}: {project.required_skills[:100]}...")
                fixed_skills = _parse_malformed_json(project.required_skills)
                project.required_skills = fixed_skills
                fixed_count += 1
            # 如果required_skills是列表，检查列表中的元素
            elif isinstance(project.required_skills, list):
                needs_fix = False
                fixed_skills = []

                for skill in project.required_skills:
                    if isinstance(skill, str):
                        # 技能项是字符串，可能需要解析
                        if skill.startswith('[') or skill.startswith('{'):
                            needs_fix = True
                            parsed_skills = _parse_malformed_json(skill)
                            fixed_skills.extend(parsed_skills)
                        else:
                            # 纯技能名字符串
                            fixed_skills.append({"name": skill.strip(), "level": "初窥门径"})
                    elif isinstance(skill, dict) and "name" in skill:
                        # 正常的技能字典
                        fixed_skills.append({
                            "name": str(skill["name"]).strip(),
                            "level": skill.get("level", "初窥门径")
                        })
                    else:
                        needs_fix = True
                        print(f"异常的技能项格式 - 项目ID {project.id}: {skill}")

                if needs_fix:
                    project.required_skills = fixed_skills
                    fixed_count += 1

        except Exception as e:
            print(f"修复项目ID {project.id} 的required_skills时出错: {e}")
            project.required_skills = []
            fixed_count += 1

    print(f"项目required_skills修复完成，共修复 {fixed_count} 条记录")
    return fixed_count


def fix_project_required_roles(db: Session):
    """修复项目表中的required_roles字段"""
    print("开始修复项目required_roles字段...")

    projects = db.query(Project).all()
    fixed_count = 0

    for project in projects:
        try:
            if project.required_roles is None:
                project.required_roles = []
                fixed_count += 1
                continue

            # 如果required_roles是字符串，尝试解析
            if isinstance(project.required_roles, str):
                try:
                    parsed_roles = json.loads(project.required_roles)
                    if isinstance(parsed_roles, list):
                        project.required_roles = [str(role).strip() for role in parsed_roles if str(role).strip()]
                    else:
                        project.required_roles = [str(parsed_roles).strip()] if str(parsed_roles).strip() else []
                    fixed_count += 1
                except json.JSONDecodeError:
                    # 如果不是JSON，按逗号分隔
                    roles = [role.strip() for role in project.required_roles.split(',') if role.strip()]
                    project.required_roles = roles
                    fixed_count += 1
            # 如果是列表，确保所有元素都是字符串
            elif isinstance(project.required_roles, list):
                cleaned_roles = []
                needs_fix = False

                for role in project.required_roles:
                    if isinstance(role, str):
                        cleaned_roles.append(role.strip())
                    else:
                        needs_fix = True
                        cleaned_roles.append(str(role).strip())

                if needs_fix:
                    project.required_roles = cleaned_roles
                    fixed_count += 1

        except Exception as e:
            print(f"修复项目ID {project.id} 的required_roles时出错: {e}")
            project.required_roles = []
            fixed_count += 1

    print(f"项目required_roles修复完成，共修复 {fixed_count} 条记录")
    return fixed_count


def main():
    """主修复函数"""
    print("开始数据库畸形JSON修复...")

    db = SessionLocal()
    try:
        total_fixed = 0

        # 修复学生skills
        total_fixed += fix_student_skills(db)

        # 修复项目required_skills
        total_fixed += fix_project_required_skills(db)

        # 修复项目required_roles
        total_fixed += fix_project_required_roles(db)

        # 提交修改
        db.commit()
        print(f"\n修复完成！总共修复了 {total_fixed} 个字段")

    except Exception as e:
        db.rollback()
        print(f"修复过程中出现错误，已回滚: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
