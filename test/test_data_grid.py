from eikon.data_grid import get_data_value, get_data_frame


def test_get_data_value():
    assert get_data_value(value="Maffay") == "Maffay"
    assert get_data_value(value=5) == 5
