# Third-party provenance

The project owns the wrapper structure, CLI/service integration, status reporting and release tests. This package's MIT license covers that project-authored material. It does not relicense any externally installed ROS, TROS, Hiwonder SDK, Orbbec driver or their configurations.

`jetarm_minimal_control/presets.py` explicitly attributes home, sorting-observation, placement and return postures to Hiwonder examples. The numerical pulse parameters correspond to the manufacturer's `bringup/actions.py`, `servo_controller/actions.py` and `app/object_sorting.py` examples. These factual compatibility parameters retain that attribution and are not claimed as project-invented motion planning. No manufacturer action function, kinematics implementation, visual detector, action database or SDK configuration is copied into this archive.

`control_bringup.launch.py` imports external package locations and reads the installed `servo_controller/config/servo_controller.yaml`. `legacy_depth_camera.launch.py` includes the independently installed Orbbec `astra_stereo_u3.launch.py`. Those external files must be obtained and calibrated separately. Optional vendor upper-application patches used in other experiments are not dependencies of this package and are excluded.

The local manufacturer distributions were used to identify these interfaces and parameter provenance, not as a source tree to publish under MIT. Public naming identifies compatibility and does not imply vendor endorsement. Hardware acceptance from earlier private experimental records applies to that historical environment only.
