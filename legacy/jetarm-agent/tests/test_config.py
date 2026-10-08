from pathlib import Path

from jetarm_demo_agent.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.default_mode == "safe"
    assert settings.motion_default_mode == "dry_run"


def test_settings_load_credentials_from_account_file(tmp_path: Path):
    account_file = tmp_path / "account.txt"
    account_file.write_text(
        "IP : 192.0.2.1\n用户名 : robot\n密码 : secret\napi-key = example-test-key\nopenai-api-key = example-openai-key\n",
        encoding="utf-8",
    )

    settings = Settings(account_file=str(account_file))

    assert settings.ssh_host == "192.0.2.1"
    assert settings.ssh_user == "robot"
    assert settings.ssh_password == "secret"
    assert settings.deepseek_api_key == "example-test-key"
    assert settings.openai_api_key == "example-openai-key"


def test_settings_load_vision_section_defaults_from_account_file(tmp_path: Path):
    account_file = tmp_path / "account.txt"
    account_file.write_text(
        "IP : 192.0.2.1\n用户名 : robot\n密码 : secret\napi-key = example-deepseek-key\n\n图像识别：\napi-key = example-vision-key\nbase_url = https://api.example.invalid\nmodel = gpt-5.4-mini\n",
        encoding="utf-8",
    )

    settings = Settings(account_file=str(account_file))

    assert settings.deepseek_api_key == "example-deepseek-key"
    assert settings.openai_api_key == "example-vision-key"
    assert settings.openai_base_url == "https://api.example.invalid"
    assert settings.openai_model == "gpt-5.4-mini"
