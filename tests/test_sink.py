import json
import subprocess
from pathlib import Path

import pytest

from skill_warden import sink
from skill_warden.errors import SinkError

pytestmark = pytest.mark.docker

NETWORK = sink.NETWORK_NAME
SINK_IP = sink.SINK_IP
GATEWAY = sink.GATEWAY
LABEL_KEY = "skill-warden.component"
LABEL_VAL = "sink"
SINK_CONTAINER = sink.SINK_CONTAINER_NAME
PROBE_IMAGE = sink.PROBE_IMAGE
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _build_sink_image():
    sink.build_image()


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=False, capture_output=True, text=True)


def _network_exists(name: str) -> bool:
    r = _docker("network", "inspect", name)
    return r.returncode == 0


def _labeled_network() -> bool:
    r = _docker("network", "inspect", NETWORK, "--format", "{{index .Labels \"skill-warden.component\"}}")
    return r.returncode == 0 and r.stdout.strip() == LABEL_VAL


def test_docker_info_required():
    info = _docker("info")
    if info.returncode != 0:
        pytest.fail(info.stderr or "docker info failed")


def test_jailnet_internal_isolated_ipv4():
    with sink.session() as sess:
        r = _docker("network", "inspect", NETWORK)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)[0]
        assert data["Internal"] is True
        assert data["EnableIPv6"] is False
        opts = data.get("Options") or {}
        assert opts.get("com.docker.network.bridge.gateway_mode_ipv4") == "isolated"
        assert sess.network_name == NETWORK


def test_sink_container_inspect_hardening():
    with sink.session() as sess:
        r = _docker("inspect", SINK_CONTAINER)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)[0]
        nets = data["NetworkSettings"]["Networks"]
        assert nets[NETWORK]["IPAddress"] == SINK_IP
        assert not data["HostConfig"]["PortBindings"]
        assert not data["HostConfig"]["Binds"]
        assert data["HostConfig"]["Privileged"] is False
        home = str(Path.home())
        mounts = json.dumps(data.get("Mounts", []))
        assert "docker.sock" not in mounts
        assert str(REPO_ROOT) not in mounts
        assert home not in mounts
        assert sess.sink_container_id


def test_probe_nslookup_evil_resolves_to_sink():
    with sink.session() as sess:
        result = sink.run_probe(sess, ["nslookup", "evil.example"])
        assert SINK_IP in result.stdout
        assert "1.1.1.1" not in result.stdout


def test_dns_log_contains_evil_example():
    with sink.session() as sess:
        sink.run_probe(sess, ["nslookup", "evil.example"])
        log = sink.dns_log(sess)
        assert "evil.example" in log


def test_wildcard_not_nxdomain():
    with sink.session() as sess:
        result = sink.run_probe(sess, ["nslookup", "no-such-name.invalid"])
        assert SINK_IP in result.stdout
        assert "NXDOMAIN" not in result.stdout.upper()


def test_public_name_resolves_to_sink_and_logged():
    with sink.session() as sess:
        result = sink.run_probe(sess, ["nslookup", "api.github.com"])
        assert SINK_IP in result.stdout
        log = sink.dns_log(sess)
        assert "api.github.com" in log


def test_dns_log_appends_two_names():
    with sink.session() as sess:
        sink.run_probe(sess, ["nslookup", "first.example.invalid"])
        sink.run_probe(sess, ["nslookup", "second.example.invalid"])
        log = sink.dns_log(sess)
        assert "first.example.invalid" in log
        assert "second.example.invalid" in log


def test_aaaa_query_no_public_ipv6():
    with sink.session() as sess:
        result = sink.run_probe(sess, ["nslookup", "-type=AAAA", "evil.example"])
        combined = result.stdout + result.stderr
        assert "2001:" not in combined
        assert "2606:" not in combined


def test_probe_uses_only_sink_dns():
    with sink.session() as sess:
        result = sink.run_probe(sess, ["nslookup", "evil.example"])
        assert result.dns_servers == [SINK_IP]


def test_probe_no_default_route():
    with sink.session() as sess:
        result = sink.run_probe(sess, ["ip", "route"])
        assert "default" not in result.stdout


def test_tcp_1_1_1_1_443_unreachable():
    with sink.session() as sess:
        result = sink.run_probe(
            sess,
            ["wget", "-T", "2", "-q", "-O", "/dev/null", "https://1.1.1.1/"],
        )
        assert result.exit_code != 0


def test_tcp_8_8_8_8_53_unreachable():
    with sink.session() as sess:
        result = sink.run_probe(
            sess,
            ["wget", "-T", "2", "-q", "-O", "/dev/null", "http://8.8.8.8:53/"],
        )
        assert result.exit_code != 0


def test_tcp_gateway_80_unreachable():
    with sink.session() as sess:
        result = sink.run_probe(
            sess,
            ["wget", "-T", "2", "-q", "-O", "/dev/null", f"http://{GATEWAY}:80/"],
        )
        assert result.exit_code != 0


def test_sink_port_80_catch_all():
    with sink.session() as sess:
        result = sink.run_probe(
            sess,
            ["wget", "-T", "2", "-q", "-O", "-", f"http://{SINK_IP}:80/collect"],
        )
        assert result.exit_code == 0
        assert '{"ok":true}' in result.stdout
        log = sink.http_log(sess)
        assert "GET" in log or "POST" in log
        assert "collect" in log
        top = _docker("top", SINK_CONTAINER)
        assert top.returncode == 0
        assert "dnsmasq" in top.stdout.lower()


def test_sink_dnsmasq_config_no_upstream():
    with sink.session():
        r = _docker("exec", SINK_CONTAINER, "cat", "/etc/dnsmasq.conf")
        assert r.returncode == 0, r.stderr
        conf = r.stdout
        assert "no-resolv" in conf
        assert f"address=/#/{SINK_IP}" in conf
        assert "server=" not in conf


def test_session_context_removes_labeled_resources():
    with sink.session():
        assert _network_exists(NETWORK)
    assert not _network_exists(NETWORK)
    listed = _docker("ps", "-aq", "--filter", f"label={LABEL_KEY}={LABEL_VAL}")
    assert listed.stdout.strip() == ""


def test_session_cleanup_on_exception():
    try:
        with sink.session():
            assert _network_exists(NETWORK)
            raise RuntimeError("probe failure")
    except RuntimeError:
        pass
    assert not _network_exists(NETWORK)


def test_stop_idempotent():
    sess = sink.start()
    try:
        sink.stop(sess)
        sink.stop(sess)
    finally:
        if _network_exists(NETWORK) and _labeled_network():
            sink.stop(sess)


def test_unlabeled_jailnet_refused():
    create = _docker(
        "network",
        "create",
        "--driver",
        "bridge",
        NETWORK,
    )
    assert create.returncode == 0, create.stderr
    try:
        with pytest.raises(SinkError):
            sink.start()
        assert _network_exists(NETWORK)
    finally:
        _docker("network", "rm", NETWORK)
