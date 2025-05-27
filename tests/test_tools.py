import pytest
from eikon.tools import (
    check_for_int,
    check_for_string,
    is_list_of_string,
    is_string_type,
    tz_replacer,
)


def test_check_for_int():
    check_for_int(parameter=5, name="Maffay")

    with pytest.raises(ValueError):
        check_for_int(parameter="Peter", name="Maffay")


def test_check_for_string():
    check_for_string(parameter="Peter", name="Maffay")

    with pytest.raises(ValueError):
        check_for_string(parameter=5, name="Maffay")


def test_is_list_of_string():
    assert is_list_of_string(values=["Peter", "Maffay"])
    assert not is_list_of_string(values=["Peter", 5])


def test_is_string_type():
    assert is_string_type("Peter")
    assert not is_string_type(5)


def test_tz_replacer():
    assert tz_replacer(s="2019-05-05 20:00:00Z") == "2019-05-05 20:00:00"
    assert tz_replacer(s="2019-05-05 20:00:00-0000") == "2019-05-05 20:00:00"
    assert tz_replacer(s="2019-05-05 20:00:00.000Z") == "2019-05-05 20:00:00"
