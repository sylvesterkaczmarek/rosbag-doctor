import rosbag_doctor


def test_public_inspect_bag_api(healthy_bag):
    assert rosbag_doctor.__all__ == ["inspect_bag"]

    report = rosbag_doctor.inspect_bag(healthy_bag)

    assert report.storage == "sqlite3"
    assert report.total_messages == 650
    assert report.topics
