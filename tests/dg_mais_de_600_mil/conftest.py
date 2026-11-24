import pytest

from tests.djen.conftest import _fazer_zip, _item


@pytest.fixture
def item():
    return _item


@pytest.fixture
def fazer_zip():
    return _fazer_zip
