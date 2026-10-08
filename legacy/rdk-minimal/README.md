# Legacy JetArm RDK X5 minimal wrapper

这是历史 ROS 2 最小封装层，公开内容为项目编写的 SSH 部署/命令入口、环境与状态检查脚本、启动/停止厂家 SDK 的脚本和舵机指令数值检查器。厂家 JetArm ROS 2 SDK、相机驱动、运动学实现、模型和设备日志均不包含在此目录中。

代码现有能力以文件为准：状态检查、厂家进程启停、JSON 指令检查和可选 ROS 2 指令发布。早期计划中的独立 RGB-D 采集器、VLA 训练及完整安装技能没有在该目录实现，不能将计划文字计作已交付能力。

## 离线验证

在本目录运行：

```sh
python -m pip install -r requirements-offline.txt
python -m pytest -q -p no:cacheprovider
python board/jetarm_action.py --action-json '{"action_type":"servo_delta","duration_s":0.5,"values":{"1":8}}'
```

该分支的历史测试总数是 **8 项**，独立于主分支测试：5 项动作/JSON 测试和 3 项路径/状态解析测试。`VALIDATION.md` 给出本次复验结果。未连接 RDK X5 或机械臂，未复验 SSH、ROS 2、相机、物理动作及抓取成功率。

## 配置与运行边界

本地入口是 `local/rdk_minimal.py`。公开副本移除了真实主机、账户和默认口令。运行前自行配置 `JETARM_RDK_HOST`、`JETARM_RDK_USER`，部署时还需绝对路径 `JETARM_RDK_REMOTE_ROOT`。认证默认可用 SSH agent/密钥，必要时以环境变量 `JETARM_RDK_PASSWORD` 提供口令。SSH 主机密钥必须预先核验并记录在当前用户的 known_hosts 中。

```sh
export JETARM_RDK_HOST=your-board.example
export JETARM_RDK_USER=your-user
export JETARM_RDK_REMOTE_ROOT=/path/to/board/jetarm_codex_minimal
python local/rdk_minimal.py deploy
python local/rdk_minimal.py exec 'bash /path/to/board/jetarm_codex_minimal/board/jetarm_status.sh'
```

板端须先合法取得并配置厂家 SDK、相机依赖和 ROS 2/TROS。`JETARM_ROS_WS` 默认 `$HOME/jetarm_ros2_ws`，`JETARM_MINIMAL_ROOT` 默认 `$HOME/jetarm_codex_minimal`，都可按原部署覆盖。环境脚本使用 `/opt/tros/humble/setup.bash`，状态检测仍沿用历史 USB 产品 ID 和 `/dev/rrc` 名称，其他型号不保证适用。

`jetarm_action.py` 默认只检查 JSON，只有 `--execute` 会读取状态并可能发布动作。历史校验在缺失舵机状态时回退到默认位置，`stop` 仅返回“接受停止请求”，不会向硬件发送急停；NaN/无穷值等输入边界也没有完整处理。它不是经过安全认证的动作控制器。真正执行前须补齐设备状态、输入完整性及物理急停等现场核查。`jetarm_core.sh stop` 会结束同名厂家节点进程，因此只适用于专用实验板环境。

发布变化仅涉及路径、凭据配置及 SSH 主机身份校验，动作算法和上述历史能力边界保留；这些配置变化未真机复验。项目封装代码按主仓库 MIT 许可证发布，第三方包独立遵守原许可，见 `THIRD_PARTY.md`。
