cmake_minimum_required(VERSION 3.0.2)
project(jetarm_vla)

find_package(catkin REQUIRED COMPONENTS
  geometry_msgs
  hiwonder_interfaces
  message_filters
  rospy
  sensor_msgs
  std_msgs
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/batch_expert_collect.py
  scripts/batch_rollout_collect.py
  scripts/label_rollouts.py
  scripts/jetarm_vla_capture.py
  scripts/jetarm_vla_client.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(PROGRAMS
  scripts/start_vla_tunnel.sh
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
