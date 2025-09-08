#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite 数据库交互式查看工具
支持查看表结构、数据内容、执行自定义查询等
"""

import sqlite3
import json
import sys
from datetime import datetime

class DatabaseViewer:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        
    def connect(self):
        """连接数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
            return True
        except Exception as e:
            print(f"连接数据库失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
    
    def get_tables(self):
        """获取所有表名"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [row[0] for row in cursor.fetchall()]
    
    def get_table_info(self, table_name):
        """获取表结构信息"""
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name});")
        return cursor.fetchall()
    
    def get_table_count(self, table_name):
        """获取表中记录数"""
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        return cursor.fetchone()[0]
    
    def query_table(self, table_name, limit=10, offset=0, where_clause=""):
        """查询表数据"""
        cursor = self.conn.cursor()
        sql = f"SELECT * FROM {table_name}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        sql += f" LIMIT {limit} OFFSET {offset};"
        
        cursor.execute(sql)
        return cursor.fetchall()
    
    def execute_query(self, sql):
        """执行自定义查询"""
        cursor = self.conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    
    def show_summary(self):
        """显示数据库概要信息"""
        print("="*60)
        print(f"数据库文件: {self.db_path}")
        print("="*60)
        
        tables = self.get_tables()
        print(f"表的数量: {len(tables)}")
        
        for table in tables:
            count = self.get_table_count(table)
            print(f"  📊 {table}: {count} 条记录")
        
        print("\n" + "="*60)
    
    def show_table_details(self, table_name):
        """显示表的详细信息"""
        print(f"\n📋 表: {table_name}")
        print("-" * 40)
        
        # 表结构
        columns = self.get_table_info(table_name)
        print("字段信息:")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, primary_key = col
            flags = []
            if primary_key:
                flags.append("PK")
            if not_null:
                flags.append("NOT NULL")
            if default_val is not None:
                flags.append(f"DEFAULT {default_val}")
            
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  • {col_name}: {col_type}{flag_str}")
        
        # 记录数
        count = self.get_table_count(table_name)
        print(f"\n记录总数: {count}")
        
        # 示例数据
        if count > 0:
            print("\n前5条记录:")
            rows = self.query_table(table_name, limit=5)
            for i, row in enumerate(rows, 1):
                print(f"\n  记录 #{i}:")
                for key in row.keys():
                    value = row[key]
                    # 格式化 JSON 数据
                    if key == 'extra_data' and value:
                        try:
                            json_data = json.loads(value)
                            value = json.dumps(json_data, indent=2, ensure_ascii=False)
                        except:
                            pass
                    print(f"    {key}: {value}")
        
        print("-" * 40)
    
    def show_log_analysis(self):
        """分析日志数据"""
        if 'log_entries' not in self.get_tables():
            print("未找到 log_entries 表")
            return
        
        print("\n📊 日志分析")
        print("="*50)
        
        # 按级别统计
        print("1. 日志级别统计:")
        cursor = self.conn.cursor()
        cursor.execute("SELECT level, COUNT(*) as count FROM log_entries GROUP BY level ORDER BY count DESC;")
        for row in cursor.fetchall():
            print(f"   {row[0]}: {row[1]} 条")
        
        # 按logger统计
        print("\n2. 日志来源统计:")
        cursor.execute("SELECT logger, COUNT(*) as count FROM log_entries GROUP BY logger ORDER BY count DESC LIMIT 10;")
        for row in cursor.fetchall():
            print(f"   {row[0]}: {row[1]} 条")
        
        # 最新的日志
        print("\n3. 最新的5条日志:")
        cursor.execute("SELECT timestamp, level, logger, message FROM log_entries ORDER BY timestamp DESC LIMIT 5;")
        for row in cursor.fetchall():
            print(f"   [{row[0]}] {row[1]} - {row[2]}: {row[3][:100]}...")
    
    def interactive_mode(self):
        """交互式模式"""
        if not self.connect():
            return
        
        self.show_summary()
        
        while True:
            print("\n" + "="*50)
            print("选择操作:")
            print("1. 查看表详细信息")
            print("2. 执行自定义查询")
            print("3. 日志分析")
            print("4. 显示概要信息")
            print("0. 退出")
            print("="*50)
            
            choice = input("请输入选择 (0-4): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                tables = self.get_tables()
                print("\n可用的表:")
                for i, table in enumerate(tables, 1):
                    print(f"  {i}. {table}")
                
                try:
                    table_idx = int(input("选择表编号: ")) - 1
                    if 0 <= table_idx < len(tables):
                        self.show_table_details(tables[table_idx])
                except:
                    print("无效的选择")
            
            elif choice == '2':
                sql = input("输入SQL查询: ").strip()
                if sql:
                    try:
                        results = self.execute_query(sql)
                        print(f"\n查询结果 ({len(results)} 条记录):")
                        for i, row in enumerate(results[:20], 1):  # 最多显示20条
                            print(f"  {i}. {dict(row)}")
                    except Exception as e:
                        print(f"查询错误: {e}")
            
            elif choice == '3':
                self.show_log_analysis()
            
            elif choice == '4':
                self.show_summary()
            
            else:
                print("无效的选择")
        
        self.close()

def main():
    db_path = "logs/analysis.db"
    viewer = DatabaseViewer(db_path)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--summary':
            if viewer.connect():
                viewer.show_summary()
                viewer.close()
        elif sys.argv[1] == '--analysis':
            if viewer.connect():
                viewer.show_log_analysis()
                viewer.close()
    else:
        viewer.interactive_mode()

if __name__ == "__main__":
    main()
