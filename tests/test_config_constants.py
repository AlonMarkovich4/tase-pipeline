"""
#9 lock — TA-35 sane bounds are a single source of truth in config, and the
dead is_last_cycle in main.py is gone.
"""
import os
from decimal import Decimal

import config
import option_schema as osch

_REPO = os.path.dirname(os.path.dirname(__file__))


def test_bounds_defined_in_config():
    assert config.TA35_MIN == 1000
    assert config.TA35_MAX == 10000


def test_option_schema_derives_bounds_from_config():
    assert osch._STRIKE_MIN == Decimal(str(config.TA35_MIN))
    assert osch._STRIKE_MAX == Decimal(str(config.TA35_MAX))


def test_no_hardcoded_bounds_left_in_engine_and_main():
    for fn in ("strategy_engine.py", "main.py"):
        src = open(os.path.join(_REPO, fn), encoding="utf-8").read()
        assert "1000 <= " not in src
        assert "<= 10000" not in src
        assert "1000.0, 10000.0" not in src


def test_dead_is_last_cycle_removed_from_main():
    src = open(os.path.join(_REPO, "main.py"), encoding="utf-8").read()
    assert "def is_last_cycle" not in src   # the call site uses tase_api.is_last_cycle
