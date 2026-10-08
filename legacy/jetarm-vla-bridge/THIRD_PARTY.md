# 来源与第三方边界

- 此目录来自本项目历史 `jetarm_vla`、`jetarm_vla_common` 及相应测试。原 `package.xml` 已声明 MIT。公开版本仅包含项目接口和辅助工具，不包含厂家 SDK 源码或模型。
- Hiwonder JetArm ROS 1 的 `hiwonder_interfaces`、`jetarm_6dof_rgbd_cam`、`jetarm_6dof_app`、`track_and_grab`、`object_sortting` 与相机/运动学服务由运行时另行提供。厂家发行包未见覆盖全部源码的统一开放许可证，本项目不代为授权或分发。接口名和协议兼容信息只用于互操作。
- ROS、NumPy、Pillow、Requests、FastAPI、Pydantic、Uvicorn、HTTPX 和 pytest 为外部依赖；软件包自身许可随上游发行，未复制其实现。
- 可选的 [LeRobot](https://github.com/huggingface/lerobot) 与 PyTorch 由用户另行安装。训练脚本中的 SmolVLA 为上游架构，不是本项目原创模型；没有随包提供预训练权重、检查点或数据集。上游软件及模型各自的许可不因本仓库 MIT 许可发生改变。
- `prepare_env.sh` 是历史环境辅助脚本，会联网安装上游依赖，未锁定 LeRobot commit；训练与转换接口可能随上游版本变化，本次仅测试不依赖这些重型组件的代码。

发布审查对本地厂家 ROS1/ROS2 压缩包中可解析 Python 文件做了原文件与较长函数的精确匹配，并逐项检查本目录的导入及程序边界，未发现匹配的整文件或十行以上函数。此结果只是来源审查的辅助证据，不能单独证明任何文件的完整权属链。新增配置与文档由本项目整理；原始运行记录保留在私人工作区，未公开。
