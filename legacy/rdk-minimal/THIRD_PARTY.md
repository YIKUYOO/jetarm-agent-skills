# 来源与第三方边界

本目录来自项目历史 `jetarm_rdkx5_minimal` 的自定义封装与测试。它调用厂家 JetArm ROS 2/TROS 环境及 `ros_robot_controller`、`servo_controller`、`servo_controller_msgs`、`kinematics`、`sdk`、`peripherals` 等包，不包含上述包的实现、固件或厂商文档。

厂家发行压缩包未见覆盖全部源码的统一开放许可证，因此保留为使用者自行提供的运行时依赖，不将它们纳入本仓库 MIT 许可。`rclpy` 和 Paramiko 为外部依赖，适用各自上游许可；测试使用 pytest。

该封装目录原先没有独立 LICENSE 文件；本次按项目负责人授权，仅对项目封装代码采用主仓库 MIT 许可证。来源审查检查了导入边界，并与本地厂家 ROS1/ROS2 压缩包中可解析 Python 文件进行整文件及十行以上函数的精确匹配，未发现匹配。比较不能代替完整权属证明，也不把依赖厂家的能力计作项目自主算法成果。

公开副本仅改变私有配置、凭据默认值、SSH 主机校验及文档表述，保留历史动作限制，未真机复验。
