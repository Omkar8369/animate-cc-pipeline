"""Pose-estimation backends.

Each backend exposes a class with `.name` + `.estimate_pose(image,
bbox) -> JointSet`. See `pose_estimator.py` for the Protocol +
factory.
"""
