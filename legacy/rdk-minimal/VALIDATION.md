# Offline release verification

Verification date: 2026-10-08 (Asia/Shanghai). Original source directories were only read.

- Python: 3.12.10; Windows host.
- Command from this directory: `python -B -m pytest -q -p no:cacheprovider`.
- Result: `8 passed in 0.02s`.
- Historical test cases: **8**; release-only mock contract cases: **0**.
- Python syntax compilation (without imports/execution): **4 files**.
- `bash -n` with Git for Windows Bash: **3 files**.
- XML/launch parsing: **0 files**.
- Known private host/account/path and credential-pattern scan: no matches in the allowlisted candidate text.
- Original source SHA-256 values rechecked against the preparation manifest: unchanged.
- No robot, SSH target, GPU server, ROS stack, camera or real checkpoint was contacted or started.

Installed verification dependencies: `{"Pillow": "12.2.0", "fastapi": "0.142.4", "httpx": "0.28.1", "numpy": "2.4.4", "paramiko": "4.0.0", "pydantic": "2.13.5", "pytest": "9.0.3", "starlette": "1.7.0"}`.

The VLA suite may emit the historical Pydantic class-based-config and Starlette HTTPX deprecation warnings. Passing offline checks does not establish robot safety, hardware compatibility, a trained model, or task success. Dependencies were installed into a dedicated staging virtual environment; that environment is not release content. See `README.md` and `THIRD_PARTY.md` for capability and source boundaries.
