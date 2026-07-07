# -*- coding: utf-8 -*-
"""配置方法库管理模块 - 存储和检索网络配置的标准流程"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigMethodStore:
    """配置方法库存储管理器"""
    
    def __init__(self, kb_folder: str):
        """
        初始化配置方法库
        
        Args:
            kb_folder: 知识库根目录路径
        """
        self.methods_dir = os.path.join(kb_folder, 'config_methods')
        self.index_path = os.path.join(self.methods_dir, '_index.json')
        self._methods_cache: Dict[str, dict] = {}
        self._ensure_dir()
        self._load_all_methods()
    
    def _ensure_dir(self):
        """确保目录存在"""
        os.makedirs(self.methods_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            self._create_index()
    
    def _create_index(self):
        """创建索引文件"""
        index = {
            "version": "1.0",
            "description": "eNSP配置方法库 - 存储网络配置的标准流程和方法论",
            "categories": {
                "routing": "路由协议配置（OSPF、静态路由、RIP等）",
                "switching": "交换配置（VLAN、STP、LACP等）",
                "security": "安全配置（ACL、防火墙策略等）",
                "wireless": "无线配置（WLAN、AP管理等）",
                "services": "网络服务（DHCP、NAT、VRRP等）",
                "management": "管理配置（Telnet、SNMP、NTP等）"
            },
            "methods_count": 0,
            "last_updated": self._now()
        }
        self._save_json(self.index_path, index)
    
    def _now(self) -> str:
        """获取当前时间"""
        return datetime.now(timezone.utc).isoformat()
    
    def _load_json(self, path: str) -> dict:
        """加载JSON文件"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning('加载JSON失败 %s: %s', path, e)
            return {}
    
    def _save_json(self, path: str, data: dict):
        """保存JSON文件"""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error('保存JSON失败 %s: %s', path, e)
            raise
    
    def _load_all_methods(self):
        """加载所有配置方法到缓存"""
        try:
            for filename in os.listdir(self.methods_dir):
                if filename.endswith('.json') and not filename.startswith('_'):
                    method_id = filename[:-5]  # 去掉.json后缀
                    filepath = os.path.join(self.methods_dir, filename)
                    method_data = self._load_json(filepath)
                    if method_data and 'id' in method_data:
                        self._methods_cache[method_id] = method_data
            logger.info('已加载 %d 个配置方法', len(self._methods_cache))
        except Exception as e:
            logger.error('加载配置方法失败: %s', e)
    
    def get_method(self, method_id: str) -> Optional[dict]:
        """
        获取指定配置方法
        
        Args:
            method_id: 配置方法ID
            
        Returns:
            配置方法数据，不存在返回None
        """
        return self._methods_cache.get(method_id)
    
    def list_methods(self, category: str = None) -> List[dict]:
        """
        列出所有配置方法
        
        Args:
            category: 可选，按分类过滤
            
        Returns:
            配置方法列表
        """
        methods = list(self._methods_cache.values())
        if category:
            methods = [m for m in methods if m.get('category') == category]
        return sorted(methods, key=lambda x: x.get('name', ''))
    
    def search_methods(self, keyword: str) -> List[dict]:
        """
        搜索配置方法
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            匹配的配置方法列表
        """
        keyword_lower = keyword.lower()
        results = []
        for method in self._methods_cache.values():
            # 搜索名称、描述、步骤
            searchable_text = ' '.join([
                method.get('name', ''),
                method.get('description', ''),
                method.get('category', ''),
                ' '.join(m.get('name', '') for m in method.get('steps', [])),
                ' '.join(cmd for step in method.get('steps', []) for cmd in step.get('commands', []))
            ]).lower()
            
            if keyword_lower in searchable_text:
                results.append(method)
        
        return sorted(results, key=lambda x: x.get('name', ''))
    
    def add_method(self, method_data: dict) -> dict:
        """
        添加新的配置方法
        
        Args:
            method_data: 配置方法数据
            
        Returns:
            添加结果 {'success': bool, 'method_id': str, 'error': str}
        """
        try:
            # 验证必填字段
            required_fields = ['id', 'name', 'category', 'steps']
            for field in required_fields:
                if field not in method_data:
                    return {'success': False, 'error': f'缺少必填字段: {field}'}
            
            method_id = method_data['id']
            
            # 设置默认值
            method_data.setdefault('created_at', self._now())
            method_data.setdefault('updated_at', self._now())
            method_data.setdefault('usage_count', 0)
            method_data.setdefault('success_rate', 0.0)
            method_data.setdefault('device_types', [])
            method_data.setdefault('prerequisites', [])
            method_data.setdefault('verification', [])
            method_data.setdefault('common_errors', [])
            method_data.setdefault('tips', [])
            method_data.setdefault('related_methods', [])
            
            # 保存文件
            filepath = os.path.join(self.methods_dir, f'{method_id}.json')
            self._save_json(filepath, method_data)
            
            # 更新缓存
            self._methods_cache[method_id] = method_data
            
            # 更新索引
            self._update_index()
            
            logger.info('添加配置方法: %s', method_id)
            return {'success': True, 'method_id': method_id}
            
        except Exception as e:
            logger.error('添加配置方法失败: %s', e)
            return {'success': False, 'error': str(e)}
    
    def update_method(self, method_id: str, updates: dict) -> dict:
        """
        更新配置方法
        
        Args:
            method_id: 配置方法ID
            updates: 要更新的字段
            
        Returns:
            更新结果
        """
        try:
            method = self._methods_cache.get(method_id)
            if not method:
                return {'success': False, 'error': f'配置方法不存在: {method_id}'}
            
            # 更新字段
            method.update(updates)
            method['updated_at'] = self._now()
            
            # 保存文件
            filepath = os.path.join(self.methods_dir, f'{method_id}.json')
            self._save_json(filepath, method)
            
            # 更新缓存
            self._methods_cache[method_id] = method
            
            logger.info('更新配置方法: %s', method_id)
            return {'success': True, 'method_id': method_id}
            
        except Exception as e:
            logger.error('更新配置方法失败: %s', e)
            return {'success': False, 'error': str(e)}
    
    def record_usage(self, method_id: str, success: bool = True):
        """
        记录配置方法使用情况
        
        Args:
            method_id: 配置方法ID
            success: 是否成功
        """
        method = self._methods_cache.get(method_id)
        if method:
            method['usage_count'] = method.get('usage_count', 0) + 1
            # 更新成功率（简单移动平均）
            old_rate = method.get('success_rate', 0.0)
            old_count = method.get('usage_count', 1) - 1
            if old_count > 0:
                method['success_rate'] = (old_rate * old_count + (1 if success else 0)) / (old_count + 1)
            else:
                method['success_rate'] = 1.0 if success else 0.0
            method['updated_at'] = self._now()
            
            # 保存到文件
            filepath = os.path.join(self.methods_dir, f'{method_id}.json')
            self._save_json(filepath, method)
    
    def _update_index(self):
        """更新索引文件"""
        index = self._load_json(self.index_path)
        index['methods_count'] = len(self._methods_cache)
        index['last_updated'] = self._now()
        self._save_json(self.index_path, index)
    
    def get_method_commands(self, method_id: str) -> List[str]:
        """
        获取配置方法的所有命令（按步骤顺序）
        
        Args:
            method_id: 配置方法ID
            
        Returns:
            命令列表
        """
        method = self.get_method(method_id)
        if not method:
            return []
        
        commands = []
        for step in method.get('steps', []):
            commands.extend(step.get('commands', []))
        return commands
    
    def get_method_steps(self, method_id: str) -> List[dict]:
        """
        获取配置方法的步骤列表
        
        Args:
            method_id: 配置方法ID
            
        Returns:
            步骤列表
        """
        method = self.get_method(method_id)
        if not method:
            return []
        return method.get('steps', [])
    
    def get_verification_commands(self, method_id: str) -> List[str]:
        """
        获取配置方法的验证命令
        
        Args:
            method_id: 配置方法ID
            
        Returns:
            验证命令列表
        """
        method = self.get_method(method_id)
        if not method:
            return []
        return method.get('verification', [])
    
    def get_troubleshooting(self, method_id: str) -> List[dict]:
        """
        获取配置方法的常见问题排查
        
        Args:
            method_id: 配置方法ID
            
        Returns:
            常见问题列表
        """
        method = self.get_method(method_id)
        if not method:
            return []
        return method.get('common_errors', [])
    
    def export_methods_summary(self) -> str:
        """
        导出配置方法摘要
        
        Returns:
            格式化的摘要文本
        """
        lines = ["=== eNSP配置方法库摘要 ===\n"]
        
        # 按分类组织
        categories = {}
        for method in self._methods_cache.values():
            cat = method.get('category', '其他')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(method)
        
        for cat, methods in sorted(categories.items()):
            lines.append(f"\n【{cat}】")
            for method in sorted(methods, key=lambda x: x.get('name', '')):
                name = method.get('name', '未知')
                steps_count = len(method.get('steps', []))
                usage = method.get('usage_count', 0)
                rate = method.get('success_rate', 0.0)
                lines.append(f"  - {name} ({steps_count}步, 使用{usage}次, 成功率{rate:.0%})")
        
        lines.append(f"\n共 {len(self._methods_cache)} 个配置方法")
        return '\n'.join(lines)
