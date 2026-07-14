"""
配置管理工具

实现配置查询和管理功能。
"""

from pathlib import Path
from typing import Dict, Optional, Any, TypedDict

import yaml

from ..services.data_service import DataService
from ..utils.validators import validate_config_section
from ..utils.errors import MCPError


class ErrorInfo(TypedDict, total=False):
    """错误信息结构"""
    code: str
    message: str
    suggestion: str


class ConfigResult(TypedDict):
    """配置查询结果 - success 字段必需，其他字段可选"""
    success: bool
    config: Optional[Dict[str, Any]]
    section: Optional[str]
    error: Optional[ErrorInfo]


class ConfigManagementTools:
    """配置管理工具类"""

    def __init__(self, project_root: str = None):
        """
        初始化配置管理工具

        Args:
            project_root: 项目根目录
        """
        self.project_root = (
            Path(project_root).resolve()
            if project_root
            else Path(__file__).resolve().parents[2]
        )
        self.data_service = DataService(str(self.project_root))

    def initialize_config(self) -> Dict[str, Any]:
        """Create config/config.yaml from the validated project template."""
        config_dir = self.project_root / "config"
        template_path = config_dir / "config.example.yaml"
        target_path = config_dir / "config.yaml"

        if target_path.exists():
            return self._existing_config_result(target_path)
        if not template_path.exists():
            return self._initialization_error(
                "TEMPLATE_NOT_FOUND",
                "配置模板 config/config.example.yaml 不存在",
                "请恢复项目自带配置模板后重试",
            )

        try:
            template_text = template_path.read_text(encoding="utf-8")
            metadata = self._validate_config_text(template_text)
        except (OSError, UnicodeError, yaml.YAMLError, ValueError) as ex:
            return self._initialization_error(
                "TEMPLATE_INVALID",
                f"配置模板无效: {ex}",
                "请修复 config/config.example.yaml 后重试",
            )

        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            with target_path.open("x", encoding="utf-8") as target:
                target.write(template_text)
        except FileExistsError:
            return self._existing_config_result(target_path)
        except OSError as ex:
            return self._initialization_error(
                "CONFIG_WRITE_ERROR",
                f"无法创建 config/config.yaml: {ex}",
                "请检查项目 config 目录写权限",
            )

        return self._initialization_success("created", True, metadata)

    def _existing_config_result(self, target_path: Path) -> Dict[str, Any]:
        try:
            metadata = self._validate_config_text(
                target_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, yaml.YAMLError, ValueError) as ex:
            return self._initialization_error(
                "CONFIG_EXISTS_INVALID",
                f"现有 config/config.yaml 无效，未执行覆盖: {ex}",
                "请备份并手动修复现有配置；初始化工具不会覆盖它",
            )
        return self._initialization_success("exists", False, metadata)

    @staticmethod
    def _validate_config_text(config_text: str) -> Dict[str, Any]:
        config = yaml.safe_load(config_text)
        if not isinstance(config, dict) or not config:
            raise ValueError("配置必须是非空 YAML 映射")

        required_sections = ("app", "platforms", "report", "notification", "advanced")
        missing_sections = [name for name in required_sections if name not in config]
        if missing_sections:
            raise ValueError(f"缺少必要配置节: {', '.join(missing_sections)}")

        platforms = config.get("platforms")
        sources = platforms.get("sources") if isinstance(platforms, dict) else None
        if not isinstance(sources, list) or not sources:
            raise ValueError("platforms.sources 必须是非空列表")
        if any(not isinstance(source, dict) or not source.get("id") for source in sources):
            raise ValueError("platforms.sources 中每项都必须包含 id")

        rss = config.get("rss") or {}
        feeds = rss.get("feeds") if isinstance(rss, dict) else []
        if feeds is None:
            feeds = []
        if not isinstance(feeds, list):
            raise ValueError("rss.feeds 必须是列表")

        return {
            "top_level_sections": sorted(config),
            "platform_count": len(sources),
            "rss_feed_count": len(feeds),
        }

    @staticmethod
    def _initialization_success(
        status: str,
        created: bool,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "summary": {
                "status": status,
                "created": created,
                "platform_count": metadata["platform_count"],
                "rss_feed_count": metadata["rss_feed_count"],
            },
            "data": {
                "status": status,
                "created": created,
                "config_path": "config/config.yaml",
                "template_path": "config/config.example.yaml",
                **metadata,
                "next_steps": [
                    "Review config/config.yaml before the first crawl",
                    "Run system_health to confirm configuration readiness",
                    "Run trigger_crawl to create local news data",
                ],
            },
        }

    @staticmethod
    def _initialization_error(
        code: str,
        message: str,
        suggestion: str,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "suggestion": suggestion,
            },
        }

    def get_current_config(self, section: Optional[str] = None) -> ConfigResult:
        """
        获取当前系统配置

        Args:
            section: 配置节 - all/crawler/push/keywords/weights，默认all

        Returns:
            配置字典

        Example:
            >>> tools = ConfigManagementTools()
            >>> result = tools.get_current_config(section="crawler")
            >>> print(result['crawler']['platforms'])
        """
        try:
            # 参数验证
            section = validate_config_section(section)

            # 获取配置
            config = self.data_service.get_current_config(section=section)

            return ConfigResult(
                success=True,
                config=config,
                section=section,
                error=None
            )

        except MCPError as e:
            return ConfigResult(
                success=False,
                config=None,
                section=None,
                error=e.to_dict()
            )
        except Exception as e:
            return ConfigResult(
                success=False,
                config=None,
                section=None,
                error={"code": "INTERNAL_ERROR", "message": str(e), "suggestion": "请查看服务日志获取详细信息"}
            )
