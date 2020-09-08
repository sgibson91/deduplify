import os
from unittest.mock import patch, call
from deduplify.del_empty_dirs import empty_dir_search


@patch("deduplify.del_empty_dirs.os.rmdir")
def test_del_empty_dirs(mock):
    test_dir = os.path.join("tests", "testdir")
    os.mkdir(test_dir)
    test_call = [call(os.path.abspath(test_dir))]

    here = os.path.dirname(__file__)
    empty_dir_search(here)

    assert mock.call_count == 1
    mock.assert_has_calls(test_call)
