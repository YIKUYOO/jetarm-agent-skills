# Historical bus-servo readback guard

`readback_guard.py` preserves a project-authored addition to the historical Hiwonder ROS2 driver integration. It is supplied separately so the manufacturer's full driver does not need to be copied into this MIT repository. The source was the project's deployment patch for `ros_robot_controller/ros_robot_controller_node.py`, compared with the local manufacturer's original file.

The problem addressed is a position readback outside the unsigned 16-bit range being assigned to a generated ROS message. The helper converts returned values to integers and returns `None` after logging when a value is outside 0–65535. The historical integration calls it immediately after reading a servo position and before assigning the message's `position` field. If it returns `None`, the existing absent-readback path must be used instead of assigning invalid values.

To adapt a legally obtained compatible driver, import or install this helper at a module path available to that driver, then insert the call at that readback-to-message boundary. Supply the driver's returned sequence, field name `position`, logger and servo ID. Review the installed driver version first. This document supplies the integration location and contract; it is not an automatic patcher or a replacement driver.

The helper alone is not comprehensive device validation: conversions can raise for malformed input, empty sequences remain empty and in-range values do not prove physical state. Its offline checks cover the unsigned-range behavior only. No patched driver or robot was executed during publication. Manufacturer code and configuration keep their original terms.
