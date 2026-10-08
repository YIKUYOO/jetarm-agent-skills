from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    account_file: str = "doc/account.txt"
    default_mode: str = "safe"
    motion_default_mode: str = "dry_run"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    vision_upload_url: str | None = None
    vision_upload_api_key: str | None = None
    ssh_host: str | None = None
    ssh_user: str | None = None
    ssh_password: str | None = None
    remote_executor_python: str = "python3"
    remote_executor_path: str = "jetarm_demo_agent_remote/executor_cli.py"
    allow_live_motion: bool = False

    model_config = SettingsConfigDict(
        env_prefix="JETARM_",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        account_path = Path(self.account_file).expanduser()
        if not account_path.exists():
            return

        content = account_path.read_text(encoding="utf-8")
        in_vision_section = False
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if "图像识别" in line:
                in_vision_section = True
                continue

            if line.startswith("IP") and not self.ssh_host:
                self.ssh_host = line.split(":", 1)[1].strip()
            elif line.startswith("用户名") and not self.ssh_user:
                self.ssh_user = line.split(":", 1)[1].strip()
            elif line.startswith("密码") and not self.ssh_password:
                self.ssh_password = line.split(":", 1)[1].strip()
            elif line.startswith("api-key"):
                value = line.split("=", 1)[1].strip()
                if in_vision_section and not self.openai_api_key:
                    self.openai_api_key = value
                elif not self.deepseek_api_key:
                    self.deepseek_api_key = value
            elif line.startswith("base_url") and in_vision_section and not self.openai_base_url.startswith("https://api.example.invalid"):
                self.openai_base_url = line.split("=", 1)[1].strip().rstrip("/")
            elif line.startswith("model") and in_vision_section and self.openai_model == "gpt-4.1-mini":
                self.openai_model = line.split("=", 1)[1].strip()
            elif line.startswith("openai-api-key") and not self.openai_api_key:
                self.openai_api_key = line.split("=", 1)[1].strip()
