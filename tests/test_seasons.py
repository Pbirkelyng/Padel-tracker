"""Season ELO soft-reset math (no DB required)."""


def test_soft_reset_midpoint():
    default = 1000.0
    before = 1080.0
    after = (before + default) / 2
    assert after == 1040.0


def test_soft_reset_at_default_unchanged():
    default = 1000.0
    before = 1000.0
    assert (before + default) / 2 == 1000.0
