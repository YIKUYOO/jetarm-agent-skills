# Legacy JetArm RGB-D VLA bridge

这是历史 ROS 1 数据采集与接口实验分支，公开范围为项目编写的数据格式、采集与写盘、HTTP 传输、动作数值检查、标注/转换辅助工具以及 mock 服务。它不是已经训练完成的 VLA 模型或经过验收的自主抓取策略。这里没有训练数据、模型权重、设备记录或厂家源码。

`gpu/server.py` 默认运行 `VLA_MODE=mock`，返回输入状态前六维的限幅值（保持姿态）；它不理解图像或语言，不完成抓取。可选的 `smolvla` 后端、训练入口和批次评估脚本是未完成验收的实验脚手架，必须另行提供兼容版本的 LeRobot、PyTorch、数据和检查点。存在这些文件不能证明训练、推理质量或真机成功率。发布前仅完成下述离线验证，未重新连接 Jetson、GPU 服务器或机械臂。

## 离线验证

在本目录、Python 3.12 环境运行：

```sh
python -m pip install -r requirements-offline.txt
python -m pytest -q -p no:cacheprovider
```

历史测试来自项目的 `test_jetarm_vla_*.py` 和数据转换筛选测试；新增 mock HTTP 测试单独列在 `tests/test_mock_api.py`。它们验证数据结构、深度显示、图像裁剪、动作数值检查、文件写盘、筛选及保持姿态接口，不覆盖 ROS、相机、设备通信、真实策略或物理安全。参见 `VALIDATION.md`。

启动本机 mock 服务：

```sh
python -m uvicorn gpu.server:app --host 127.0.0.1 --port 8008
```

`GET /health` 返回 `hold-current-pose`；`POST /select_action` 接受 `language_instruction` 和至少六维的 `observation.state`。ROS 采集记录的状态维数为 13，动作为 6，RGB/深度显示常用裁剪尺寸为 640×400。该 API 没有认证，应保持本机监听或通过经验证主机密钥的 SSH 隧道访问。

## 历史 ROS 1 部署边界

`scripts/jetarm_vla_capture.py` 订阅 RGB、深度、舵机状态及动作镜像；`scripts/jetarm_vla_client.py` 将观测送往 HTTP 服务，默认 `dry_run=true`。`query_ee_pose=false` 时末端位姿用零值占位，不能把这些占位量视为实测姿态。状态过期、相机编码/步长、坐标标定、网络延迟、碰撞约束和物理急停等仍需设备侧核查。

ROS 部分依赖厂家另行提供的 JetArm ROS 1 工作区（`hiwonder_interfaces`、相机驱动及相关应用）、ROS Melodic、`rospy`、`message_filters`、NumPy、Pillow 和 Requests。厂家包不在此仓库分发。`batch_expert_collect.py` 调用厂家 `track_and_grab`/`object_sortting` 应用采集示教，相关抓取算法属于厂家依赖，不是本项目新实现的 VLA。

将本目录复制到自己的 catkin overlay 的 `src/jetarm_vla`，保持其中 `jetarm_vla_common/` 子目录。先 source 自己的厂家工作区，再在 overlay 中构建。此发布只覆盖 source/devel 工作区使用方式；安装空间打包与 ROS Melodic 的系统 Python 版本兼容性未复验。

```sh
export JETARM_ROS_SETUP=/path/to/vendor-workspace/devel/setup.bash
export JETARM_VLA_SETUP=/path/to/overlay/devel/setup.bash
source "$JETARM_ROS_SETUP"
source "$JETARM_VLA_SETUP"
roslaunch jetarm_vla capture.launch output_dir:="$HOME/jetarm_vla_data/raw" episode_id:=ep_example duration_s:=20 query_ee_pose:=false
roslaunch jetarm_vla client.launch server_url:=http://127.0.0.1:8008/select_action dry_run:=true
```

批次示教脚本会调用厂家程序并可能驱动设备；`batch_rollout_collect.py` 历史默认会执行动作，只有显式 `--dry-run` 才禁用发布，而且该脚本只接受 `smolvla-checkpoint` 服务。此次仅归档这些历史入口，没有运行它们。先在受控现场人工核查相关参数。标注、合并和转换工具的显式 `--overwrite` 会覆盖指定数据目录，请只对另存的实验数据使用。

## 配置变化

公开副本去掉了历史设备地址、用户名、个人路径和身份信息。GPU 脚本的 `PROJECT_ROOT` 默认从脚本位置推导；`CONDA_SH`、`GPU_HOST`、`GPU_USER`、`KEY_PATH` 和真实后端的 `VLA_POLICY_PATH` 必须由使用者配置。数据输出默认在当前用户的 `jetarm_vla_data` 下；HF 数据缓存遵循 `HF_LEROBOT_HOME`。SSH 要求预先核验并登记主机密钥，HTTP 服务器默认绑定 `127.0.0.1`，模型下载端点默认官方 Hugging Face。旧路径可通过对应参数恢复，未据此声称真机兼容性已经复验。

项目接口代码按主仓库 MIT 许可证发布；第三方程序和模型不受本项目许可证重新授权。详见 `THIRD_PARTY.md`。
