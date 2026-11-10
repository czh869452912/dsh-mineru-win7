import pytest

from mineru_win7.config import MinerUConfig
from mineru_win7.errors import NotConfigured


def test_proxy_prefix_and_task_identifier_stay_on_public_origin():
    config = MinerUConfig.from_mapping({"baseURL": "http://server:18080/mineru"}, {})
    assert config.endpoint("submit") == "http://server:18080/mineru/tasks"
    assert config.endpoint("health") == "http://server:18080/mineru/health"
    assert config.endpoint("result", "task/a?b") == "http://server:18080/mineru/tasks/task%2Fa%3Fb/result"
    assert config.endpoint("status", "one") == "http://server:18080/mineru/tasks/one"


@pytest.mark.parametrize("address", [
    "file:///C:/docs", "http://user:secret@server/", "http://@server/",
    "http://server/mineru/?key=secret", "http://server/#fragment",
    "http://server:bad/", "http://server/\r\nheader", "http://server\\tasks/",
])
def test_invalid_or_credential_bearing_api_bases_are_rejected(address):
    with pytest.raises(ValueError, match="baseURL"):
        MinerUConfig.from_mapping({"baseURL": address}, {})


def test_unconfigured_plugin_does_not_assume_localhost_or_a_cloud_service():
    config = MinerUConfig.from_mapping({}, {})
    with pytest.raises(NotConfigured):
        config.endpoint("submit")


def test_profile_address_overrides_environment_and_environment_preserves_prefix():
    env = {"MINERU_BASE_URL": "http://env-server:18080/mineru/"}
    assert MinerUConfig.from_mapping({}, env).endpoint("health") == "http://env-server:18080/mineru/health"
    configured = MinerUConfig.from_mapping({"baseURL": "https://profile-server/api/mineru/"}, env)
    assert configured.endpoint("health") == "https://profile-server/api/mineru/health"


@pytest.mark.parametrize("timeout", [True, 0, -1, 3601, float("nan"), float("inf")])
def test_request_deadline_must_be_finite_positive_and_bounded(timeout):
    with pytest.raises(ValueError, match="requestTimeoutSeconds"):
        MinerUConfig.from_mapping({"requestTimeoutSeconds": timeout}, {})


def test_other_protocols_and_unknown_options_do_not_silently_fall_back():
    with pytest.raises(ValueError, match="legacy-tasks-v2"):
        MinerUConfig.from_mapping({"protocol": "tasks-4.1"}, {})
    with pytest.raises(ValueError, match="Unknown"):
        MinerUConfig.from_mapping({"apiKey": "not-supported"}, {})


@pytest.mark.parametrize("task_id", [".", "..", "", "a\nheader"])
def test_task_identifiers_cannot_escape_task_resource(task_id):
    config = MinerUConfig.from_mapping({"baseURL": "http://server/mineru/"}, {})
    with pytest.raises(ValueError, match="task_id"):
        config.endpoint("result", task_id)
