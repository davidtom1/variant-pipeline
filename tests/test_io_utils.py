import json
import os

import pytest

from src.io_utils import write_json_atomic


def _tmp_files(directory):
    return set(os.listdir(directory))


def test_write_json_atomic_round_trips(tmp_path):
    target = tmp_path / "out.json"
    data = {"a": 1, "b": [1, 2, 3], "c": None}

    write_json_atomic(data, target)

    assert json.loads(target.read_text()) == data


def test_write_json_atomic_overwrites_existing_file(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic({"first": True}, target)
    write_json_atomic({"second": True}, target)

    assert json.loads(target.read_text()) == {"second": True}


def test_write_json_atomic_failure_leaves_no_partial_or_leftover_files(tmp_path):
    target = tmp_path / "out.json"

    with pytest.raises(TypeError):
        write_json_atomic({"bad": {1, 2, 3}}, target)

    assert not target.exists()
    assert _tmp_files(tmp_path) == set()


def test_write_json_atomic_failure_does_not_clobber_existing_file(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic({"good": True}, target)

    with pytest.raises(TypeError):
        write_json_atomic({"bad": {1, 2, 3}}, target)

    assert json.loads(target.read_text()) == {"good": True}
    assert _tmp_files(tmp_path) == {"out.json"}
