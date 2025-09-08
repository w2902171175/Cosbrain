#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的认证API测试脚本
测试所有8个认证端点
"""

import requests
import json
import time
import uuid

class AuthAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
        self.test_user_data = None
        
    def generate_unique_user_data(self):
        """生成唯一的测试用户数据"""
        unique_id = str(int(time.time()))
        phone_suffix = ''.join([str(hash(unique_id + str(i)) % 10) for i in range(8)])
        
        return {
            "username": f"testuser_{unique_id}",
            "email": f"testuser_{unique_id}@example.com",
            "password": "Password123",
            "phone_number": f"138{phone_suffix}",
            "name": f"测试用户_{unique_id}",
            "school": "测试大学"
        }
    
    def test_health_check(self):
        """测试健康检查API"""
        print("\n1️⃣ 测试健康检查API")
        print("-" * 40)
        
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"响应: {data['status']} - {data['message']}")
                print("✅ 健康检查通过")
                return True
            else:
                print("❌ 健康检查失败")
                return False
                
        except Exception as e:
            print(f"❌ 健康检查异常: {str(e)}")
            return False
    
    def test_register(self):
        """测试用户注册API"""
        print("\n2️⃣ 测试用户注册API")
        print("-" * 40)
        
        self.test_user_data = self.generate_unique_user_data()
        
        try:
            response = self.session.post(
                f"{self.base_url}/register", 
                json=self.test_user_data, 
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"注册成功: 用户ID {data['id']}, 用户名 {data['username']}")
                # 更新实际的用户名（因为可能被系统修改）
                self.test_user_data['username'] = data['username']
                print("✅ 用户注册成功")
                return True
            else:
                print(f"❌ 注册失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 注册异常: {str(e)}")
            return False
    
    def test_login(self):
        """测试用户登录API"""
        print("\n3️⃣ 测试用户登录API")
        print("-" * 40)
        
        if not self.test_user_data:
            print("❌ 无测试用户数据，需要先注册")
            return False
        
        try:
            # 使用邮箱登录
            login_data = {
                "username": self.test_user_data["email"],
                "password": self.test_user_data["password"]
            }
            
            response = self.session.post(
                f"{self.base_url}/token",
                data=login_data,  # OAuth2PasswordRequestForm 需要 form data
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                print(f"登录成功: Token类型 {data['token_type']}")
                print("✅ 用户登录成功")
                return True
            else:
                print(f"❌ 登录失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 登录异常: {str(e)}")
            return False
    
    def test_get_current_user(self):
        """测试获取当前用户信息API"""
        print("\n4️⃣ 测试获取当前用户信息API")
        print("-" * 40)
        
        if not self.access_token:
            print("❌ 无访问令牌，需要先登录")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = self.session.get(
                f"{self.base_url}/users/me",  # 修正路径
                headers=headers,
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"当前用户: {data['username']} ({data['email']})")
                print("✅ 获取用户信息成功")
                return True
            else:
                print(f"❌ 获取用户信息失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 获取用户信息异常: {str(e)}")
            return False
    
    def test_update_user(self):
        """测试更新用户信息API"""
        print("\n5️⃣ 测试更新用户信息API")
        print("-" * 40)
        
        if not self.access_token:
            print("❌ 无访问令牌，需要先登录")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            update_data = {
                "name": "测试用户真实姓名",
                "school": "测试大学"
            }
            
            response = self.session.put(
                f"{self.base_url}/users/me",  # 修正路径
                headers=headers,
                json=update_data,
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"更新成功: 真实姓名已更新为 {update_data['name']}")
                print("✅ 更新用户信息成功")
                return True
            else:
                print(f"❌ 更新用户信息失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 更新用户信息异常: {str(e)}")
            return False
    
    def test_change_password(self):
        """测试修改密码API"""
        print("\n6️⃣ 测试修改密码API")
        print("-" * 40)
        
        if not self.access_token:
            print("❌ 无访问令牌，需要先登录")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            form_data = {
                "current_password": self.test_user_data["password"],
                "new_password": "NewPassword123"
            }
            
            response = self.session.post(
                f"{self.base_url}/change-password",  # 直接路径，无前缀
                headers=headers,
                data=form_data,  # 使用form data
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                # 更新本地密码
                self.test_user_data["password"] = "NewPassword123"
                print("密码修改成功")
                print("✅ 修改密码成功")
                
                # 添加延迟确保数据库变更生效
                import time
                time.sleep(1)
                print("等待数据库变更生效...")
                
                # 验证新密码能否登录
                print("验证新密码是否能登录...")
                verify_login_response = self.session.post(
                    f"{self.base_url}/token",  # 正确的登录路径
                    data={
                        "username": self.test_user_data["email"],  # 使用邮箱而不是用户名
                        "password": "NewPassword123"
                    },
                    timeout=30
                )
                
                if verify_login_response.status_code == 200:
                    print("✅ 新密码登录验证成功")
                else:
                    print(f"❌ 新密码登录验证失败: {verify_login_response.status_code} - {verify_login_response.text}")
                
                return True
            else:
                print(f"❌ 修改密码失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 修改密码异常: {str(e)}")
            return False
    
    def test_user_stats(self):
        """测试用户统计信息API"""
        print("\n7️⃣ 测试用户统计信息API")
        print("-" * 40)
        
        if not self.access_token:
            print("❌ 无访问令牌，需要先登录")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = self.session.get(
                f"{self.base_url}/users/me/stats",  # 修正路径
                headers=headers,
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"用户统计: 积分 {data.get('total_points', 0)}, 登录次数 {data.get('login_count', 0)}")
                print("✅ 获取用户统计成功")
                return True
            else:
                print(f"❌ 获取用户统计失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 获取用户统计异常: {str(e)}")
            return False
    
    def test_deactivate_account(self):
        """测试注销账户API"""
        print("\n8️⃣ 测试注销账户API")
        print("-" * 40)
        
        if not self.access_token:
            print("❌ 无访问令牌，需要先登录")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            current_password = self.test_user_data["password"]
            print(f"调试: 使用密码进行账户停用: {current_password}")
            
            form_data = {
                "password": current_password
            }
            
            response = self.session.post(
                f"{self.base_url}/deactivate",
                headers=headers,
                data=form_data,  # 使用form data
                timeout=30
            )
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                print("账户注销成功")
                print("✅ 注销账户成功")
                return True
            else:
                print(f"❌ 注销账户失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 注销账户异常: {str(e)}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始认证API完整测试")
        print("=" * 60)
        
        results = {}
        
        # 依次执行所有测试
        results["health"] = self.test_health_check()
        results["register"] = self.test_register()
        results["login"] = self.test_login()
        results["get_user"] = self.test_get_current_user()
        results["update_user"] = self.test_update_user()
        results["change_password"] = self.test_change_password()
        results["user_stats"] = self.test_user_stats()
        results["deactivate"] = self.test_deactivate_account()
        
        # 统计结果
        print("\n" + "=" * 60)
        print("🏁 测试结果汇总")
        print("=" * 60)
        
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        
        for test_name, result in results.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name.ljust(15)}: {status}")
        
        print(f"\n总计: {passed_tests}/{total_tests} 个测试通过")
        
        if passed_tests == total_tests:
            print("\n🎉 所有认证API测试通过！认证系统完全正常！")
        else:
            print(f"\n⚠️ {total_tests - passed_tests} 个测试失败，需要进一步修复")
        
        return passed_tests == total_tests

def main():
    """主函数"""
    tester = AuthAPITester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ 认证API完整性测试：全部通过")
    else:
        print("\n❌ 认证API完整性测试：部分失败")

if __name__ == "__main__":
    main()
