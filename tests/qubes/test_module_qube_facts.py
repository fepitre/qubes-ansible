import pytest

from ansible_collections.qubesos.core.plugins.modules.qube_facts import core
from tests.qubes.ansible_test_utils import (
    AnsibleFailJson,
    run_module_qubesos_core_qube_facts as run_module,
)
from tests.qubes.conftest import qubes


def test_qube_not_found(qubes):
    with pytest.raises(AnsibleFailJson) as exc:
        run_module({"name": "this-qube-does-not-exist"})
    assert "not found" in exc.value.args[0]["msg"]


def test_returns_facts_structure(vm):
    res = run_module({"name": vm.name})
    facts = res["ansible_facts"]["qubes_facts"]
    assert "name" in facts
    assert "state" in facts
    assert "properties" in facts
    assert "default_properties" in facts
    assert "features" in facts
    assert "services" in facts


def test_name_matches(vm):
    res = run_module({"name": vm.name})
    facts = res["ansible_facts"]["qubes_facts"]
    assert facts["name"] == vm.name


def test_state_halted(vm):
    res = run_module({"name": vm.name})
    facts = res["ansible_facts"]["qubes_facts"]
    assert facts["state"] == "halted"


def test_state_running(qubes, vm):
    vm.start()
    res = run_module({"name": vm.name})
    facts = res["ansible_facts"]["qubes_facts"]
    assert facts["state"] == "running"


def test_facts_contains_properties(vm):
    vm.autostart = True
    res = run_module({"name": vm.name})
    props = res["ansible_facts"]["qubes_facts"]["properties"]
    assert props["klass"] == "AppVM"
    assert props["autostart"]


def test_no_changed(vm):
    res = run_module({"name": vm.name})
    assert res["changed"] is False


def test_services_are_subset_of_features(vm):
    res = run_module({"name": vm.name})
    facts = res["ansible_facts"]["qubes_facts"]
    for service_name in facts["services"]:
        assert f"service.{service_name}" in facts["features"]


def test_notes(vm):
    vm.set_notes("foo")
    res = run_module({"name": vm.name})
    assert res["ansible_facts"]["qubes_facts"]["notes"] == "foo"


def test_tags(vm):
    vm.tags.add("foo")
    res = run_module({"name": vm.name})
    tags = res["ansible_facts"]["qubes_facts"]["tags"]
    assert "foo" in tags
    assert sorted(tags) == sorted(list(vm.tags))


def test_volumes(vm):
    vm.volumes["private"].revisions_to_keep = 5
    res = run_module({"name": vm.name})
    private_vol = next(
        vol
        for vol in res["ansible_facts"]["qubes_facts"]["volumes"]
        if vol["name"] == "private"
    )
    assert private_vol["revisions_to_keep"] == 5
