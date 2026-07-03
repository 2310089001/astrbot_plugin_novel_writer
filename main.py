import json
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from astrbot.api.star import Context, Star, StarTools
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api import logger

class NovelWriterPlugin(Star):
    """
    小暖小说工坊 - AstrBot 插件
    辅助小说创作，支持灵感笔记、章节管理、智能检索与导出功能。
    """

    def __init__(self, context: Context, config: Dict[str, Any]):
        super().__init__(context)
        self.config = config
        
        # 配置项解析
        self.auto_backup = config.get("auto_backup", True)
        self.backup_format = config.get("backup_format", "timestamp")
        self.max_backups = config.get("max_backups", 10)
        self.default_project = config.get("default_project", "default")
        
        # 使用 StarTools 获取规范的数据目录
        self.data_dir = StarTools.get_data_dir()
        self.projects_dir = self.data_dir / "projects"
        
        # 确保目录结构存在
        self._ensure_dirs()
        
        # 当前活动项目ID
        self.current_project_id = self.default_project
        
        # 加载当前项目配置
        self._load_project()

    def _ensure_dirs(self):
        """确保必要的目录结构存在"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.projects_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Storage directory ensured at: {self.data_dir}")
        except Exception as e:
            logger.error(f"Failed to create storage directories: {e}")

    def _load_project(self):
        """加载当前项目配置"""
        project_dir = self.projects_dir / self.current_project_id
        config_file = project_dir / "settings.json"
        
        if not project_dir.exists():
            # 如果项目不存在，创建新项目
            logger.info(f"Project '{self.current_project_id}' not found. Creating new project...")
            self._create_project(self.current_project_id)
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    logger.info(f"Loaded project settings for '{self.current_project_id}'")
                    # 可以在这里加载更多项目状态
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse project settings JSON: {e}. Using default settings.")
            except Exception as e:
                logger.error(f"Failed to load project settings: {e}")
        else:
            logger.warning(f"Settings file not found for project '{self.current_project_id}'")

    def _create_project(self, project_id: str):
        """创建一个新小说项目"""
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        (project_dir / "notes").mkdir(exist_ok=True)
        (project_dir / "chapters").mkdir(exist_ok=True)
        
        # 创建默认设置文件
        settings = {
            "project_id": project_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "title": f"Novel Project {project_id}",
            "author": "Anonymous",
            "description": ""
        }
        
        settings_file = project_dir / "settings.json"
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Created new project: {project_id}")
        return project_dir

    def _get_project_dir(self) -> Path:
        """获取当前项目目录"""
        return self.projects_dir / self.current_project_id

    def _save_note(self, category: str, tags: List[str], content: str) -> Dict[str, Any]:
        """保存一条笔记到notes.json"""
        project_dir = self._get_project_dir()
        notes_file = project_dir / "notes.json"
        
        # 加载现有笔记
        notes = []
        if notes_file.exists():
            try:
                with open(notes_file, 'r', encoding='utf-8') as f:
                    notes = json.load(f)
            except:
                notes = []
        
        # 创建新笔记
        note_id = f"{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        new_note = {
            "id": note_id,
            "category": category,
            "tags": tags,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        notes.append(new_note)
        
        # 保存回文件
        with open(notes_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Added new note: {note_id} in category '{category}'")
        return new_note

    def _search_notes(self, keyword: str, tag: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索笔记"""
        project_dir = self._get_project_dir()
        notes_file = project_dir / "notes.json"
        
        if not notes_file.exists():
            return []
        
        try:
            with open(notes_file, 'r', encoding='utf-8') as f:
                notes = json.load(f)
        except:
            return []
        
        results = []
        for note in notes:
            match = True
            
            # 搜索关键词
            if keyword and keyword.lower() not in note.get("content", "").lower() and keyword.lower() not in note.get("id", "").lower():
                match = False
                
            # 搜索标签
            if tag and tag not in note.get("tags", []):
                match = False
                
            # 搜索分类
            if category and note.get("category") != category:
                match = False
                
            if match:
                results.append(note)
                
        return results

    def _get_chapter_path(self, volume: int, chapter: int) -> Path:
        """获取章节文件路径"""
        project_dir = self._get_project_dir()
        return project_dir / "chapters" / f"vol{volume}_ch{chapter}.md"

    def _backup_chapter(self, volume: int, chapter: int):
        """备份章节内容"""
        if not self.auto_backup:
            return
            
        chapter_file = self._get_chapter_path(volume, chapter)
        if not chapter_file.exists():
            return
            
        backup_dir = chapter_file.parent / f"vol{volume}_ch{chapter}_backup"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{timestamp}.md"
        
        try:
            with open(chapter_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.debug(f"Backed up chapter vol{volume} ch{chapter} to {backup_file}")
            
            # 清理旧备份
            self._cleanup_backups(backup_dir)
            
        except Exception as e:
            logger.error(f"Failed to backup chapter: {e}")

    def _cleanup_backups(self, backup_dir: Path):
        """清理多余的备份文件"""
        if not backup_dir.exists():
            return
            
        backups = sorted(backup_dir.glob("*.md"))
        if len(backups) > self.max_backups:
            # 删除最老的备份
            for old_backup in backups[:-self.max_backups]:
                try:
                    old_backup.unlink()
                    logger.debug(f"Deleted old backup: {old_backup}")
                except Exception as e:
                    logger.error(f"Failed to delete old backup: {e}")

    def _read_chapter(self, volume: int, chapter: int) -> Optional[str]:
        """读取章节内容"""
        chapter_file = self._get_chapter_path(volume, chapter)
        if not chapter_file.exists():
            return None
            
        try:
            with open(chapter_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read chapter: {e}")
            return None

    def _write_chapter(self, volume: int, chapter: int, content: str):
        """写入章节内容"""
        chapter_file = self._get_chapter_path(volume, chapter)
        chapter_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 备份现有内容
        self._backup_chapter(volume, chapter)
        
        try:
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Wrote chapter vol{volume} ch{chapter}")
        except Exception as e:
            logger.error(f"Failed to write chapter: {e}")

    def _export_notes(self) -> str:
        """导出所有笔记为Markdown格式"""
        project_dir = self._get_project_dir()
        notes_file = project_dir / "notes.json"
        
        if not notes_file.exists():
            return "No notes found."
            
        try:
            with open(notes_file, 'r', encoding='utf-8') as f:
                notes = json.load(f)
        except:
            return "Failed to read notes."
            
        markdown = "# Novel Notes\n\n"
        
        # 按分类分组
        categories = {}
        for note in notes:
            cat = note.get("category", "Uncategorized")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(note)
            
        for category, category_notes in categories.items():
            markdown += f"## {category}\n\n"
            for note in category_notes:
                markdown += f"### {note['id']}\n"
                markdown += f"**Tags:** {', '.join(note.get('tags', []))}\n"
                markdown += f"**Created:** {note.get('created_at', 'Unknown')}\n\n"
                markdown += f"{note['content']}\n\n---\n\n"
                
        return markdown

    def _export_chapter(self, volume: int, chapter: int) -> str:
        """导出指定章节"""
        content = self._read_chapter(volume, chapter)
        if content is None:
            return f"Chapter vol{volume} ch{chapter} not found."
        return content

    @filter.command_group("novel")
    def novel(self):
        """小说创作助手命令组"""
        pass

    @novel.command("add")
    async def add_note(self, event: AstrMessageEvent, category: str = "灵感", tags: str = "", content: str = ""):
        """添加灵感或设定
        
        Args:
            category: 分类 (人物/世界观/情节/灵感)，默认为"灵感"
            tags: 标签，用逗号分隔
            content: 具体内容 (剩余部分)
        """
        # 获取原始消息字符串以提取完整内容
        msg_str = event.get_message_str()
        
        # 提取命令后的部分
        prefix = "/novel add"
        if msg_str.startswith(prefix):
            remainder = msg_str[len(prefix):].strip()
        else:
            remainder = ""
            
        # 如果 content 参数未被自动填充（通常是因为它是最后一个且可能包含空格），
        # 我们尝试从 remainder 中解析。
        # 但如果 AstrBot 已经正确注入了 content，我们优先使用它。
        # 然而，AstrBot 的默认行为是将剩余所有文本作为最后一个参数。
        # 为了确保 robustness，我们直接使用 remainder 作为 content，
        # 因为 category 和 tags 已经在前面被解析了。
        # 但这里有个问题：如果用户输入 /novel add 灵感 标签 内容
        # AstrBot 可能将 "灵感" 给 category, "标签" 给 tags, "内容" 给 content。
        # 如果用户输入 /novel add 灵感 内容 (没有标签)
        # AstrBot 可能将 "灵感" 给 category, "内容" 给 tags, content 为空。
        
        # 为了简化并符合直觉，我们假设命令格式为:
        # /novel add [category] [tags] [content]
        # 其中 [tags] 和 [content] 是可选的，但 [content] 是必须的。
        # 如果 content 为空，我们尝试从 remainder 中重新构建。
        
        # 实际上，最简单的做法是：
        # 1. 如果 content 不为空，直接使用。
        # 2. 如果 content 为空，说明用户可能没提供，或者格式不对。
        
        if not content:
            # 尝试从 remainder 中解析
            # 假设 remainder 格式: "category [tags] content"
            # 如果 tags 默认为空字符串，且 content 也为空，说明用户可能只输了 category
            # 或者 AstrBot 解析出了问题。
            
            # 让我们直接处理 remainder
            parts = remainder.split(None, 2)
            if len(parts) == 0:
                yield event.plain_result("❌ 请提供至少分类和内容。用法: /novel add [分类] [标签] [内容]")
                return
            elif len(parts) == 1:
                # 只有分类，没有内容
                yield event.plain_result("❌ 请提供内容。用法: /novel add [分类] [标签] [内容]")
                return
            elif len(parts) == 2:
                # 分类 + 内容 (tags 为空)
                # 注意：如果用户输入 "分类 标签 内容"，parts 会是 3 个
                # 如果用户输入 "分类 内容"，parts 会是 2 个
                # 这里假设第二个部分是 content
                final_category = parts[0]
                final_tags = ""
                final_content = parts[1]
            else:
                # 分类 + 标签 + 内容
                final_category = parts[0]
                final_tags = parts[1]
                final_content = parts[2]
        else:
            # AstrBot 自动解析成功
            final_category = category
            final_tags = tags
            final_content = content
            
        # 验证内容是否为空
        if not final_content:
            yield event.plain_result("❌ 请提供内容。用法: /novel add [分类] [标签] [内容]")
            return

        # 解析标签
        tag_list = [t.strip() for t in final_tags.split(",") if t.strip()] if final_tags else []
        
        # 保存笔记
        note = self._save_note(final_category, tag_list, final_content)
        
        yield event.plain_result(f"✅ 已添加{final_category}笔记:\nID: {note['id']}\n标签: {', '.join(tag_list) if tag_list else '无'}")

    @novel.command("search")
    async def search_notes(self, event: AstrMessageEvent, keyword: str = "", tag: str = "", category: str = ""):
        """搜索笔记
        
        Args:
            keyword: 关键词
            tag: 标签
            category: 分类
        """
        if not keyword and not tag and not category:
            yield event.plain_result("❌ 请提供搜索条件。用法: /novel search [关键词] [标签=xxx] [分类=xxx]")
            return
            
        # 执行搜索
        results = self._search_notes(keyword, tag if tag else None, category if category else None)
        
        if not results:
            yield event.plain_result("🔍 未找到匹配的笔记。")
            return
            
        output = f"🔍 找到 {len(results)} 条结果:\n\n"
        for note in results[:10]:  # 限制显示数量
            output += f"• [{note['category']}] {note['id']}\n"
            output += f"  标签: {', '.join(note.get('tags', []))}\n"
            output += f"  内容: {note['content'][:100]}{'...' if len(note['content']) > 100 else ''}\n\n"
            
        if len(results) > 10:
            output += f"... 还有 {len(results) - 10} 条结果"
            
        yield event.plain_result(output)

    @novel.command("chapter")
    async def manage_chapter(self, event: AstrMessageEvent, action: str = "view", volume: int = 1, chapter: int = 1, content: str = ""):
        """管理章节
        
        Args:
            action: 操作 (view/edit)
            volume: 卷号
            chapter: 章号
            content: 章节内容 (编辑时需要)
        """
        if action == "view":
            chapter_content = self._read_chapter(volume, chapter)
            if chapter_content is None:
                yield event.plain_result(f"📖 第{volume}卷第{chapter}章尚未创建。")
            else:
                yield event.plain_result(f"📖 第{volume}卷第{chapter}章:\n\n{chapter_content}")
                
        elif action == "edit":
            if not content:
                yield event.plain_result("❌ 编辑章节需要提供内容。用法: /novel chapter edit [卷号] [章号] [内容]")
                return
                
            self._write_chapter(volume, chapter, content)
            yield event.plain_result(f"✏️ 已编辑第{volume}卷第{chapter}章。")
            
        else:
            yield event.plain_result("❌ 未知操作。请使用 view 或 edit。")

    @novel.command("export")
    async def export_content(self, event: AstrMessageEvent, export_type: str = "settings", volume: int = 1, chapter: int = 1):
        """导出内容
        
        Args:
            export_type: 导出类型 (settings/chapter)
            volume: 卷号 (章节导出时需要)
            chapter: 章号 (章节导出时需要)
        """
        if export_type == "settings":
            content = self._export_notes()
            yield event.plain_result(f"📤 设定导出:\n\n{content}")
            
        elif export_type == "chapter":
            content = self._export_chapter(volume, chapter)
            if content.startswith("Chapter") and "not found" in content:
                yield event.plain_result(content)
            else:
                yield event.plain_result(f"📤 第{volume}卷第{chapter}章:\n\n{content}")
                
        else:
            yield event.plain_result("❌ 未知导出类型。请使用 settings 或 chapter。")

    @novel.command("project")
    async def manage_project(self, event: AstrMessageEvent, action: str = "info", project_id: str = ""):
        """项目管理
        
        Args:
            action: 操作 (info/create/switch)
            project_id: 项目ID
        """
        if action == "info":
            project_dir = self._get_project_dir()
            settings_file = project_dir / "settings.json"
            
            if settings_file.exists():
                try:
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    
                    yield event.plain_result(f"📁 当前项目: {settings.get('title', project_id)}\n"
                                           f"   ID: {settings.get('project_id', self.current_project_id)}\n"
                                           f"   作者: {settings.get('author', 'Unknown')}\n"
                                           f"   描述: {settings.get('description', 'No description')}")
                except Exception as e:
                    yield event.plain_result(f"❌ 读取项目信息失败: {e}")
            else:
                yield event.plain_result(f"❌ 项目 '{self.current_project_id}' 不存在。")
                
        elif action == "create":
            if not project_id:
                yield event.plain_result("❌ 请提供项目ID。用法: /novel project create [项目ID]")
                return
                
            project_dir = self._create_project(project_id)
            yield event.plain_result(f"✅ 已创建新项目: {project_id}")
            
        elif action == "switch":
            if not project_id:
                yield event.plain_result("❌ 请提供要切换到的项目ID。用法: /novel project switch [项目ID]")
                return
                
            target_project_dir = self.projects_dir / project_id
            # 先检查是否存在，再切换
            if not target_project_dir.exists():
                yield event.plain_result(f"❌ 项目 '{project_id}' 不存在，请先创建。")
                return
                
            self.current_project_id = project_id
            self._load_project()
            yield event.plain_result(f"🔄 已切换到项目: {project_id}")
                
        else:
            yield event.plain_result("❌ 未知操作。请使用 info, create 或 switch。")

    async def terminate(self):
        """插件终止时的清理工作"""
        logger.info("Novel Writer plugin terminated.")