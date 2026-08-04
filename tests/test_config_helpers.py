from config import _ids

def test_ids_parses_numeric_values():
    assert _ids('1, 2,invalid,3') == frozenset({1,2,3})
