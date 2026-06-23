from slutop.api import parse_gres, parse_mem, parse_tres


def test_parse_mem_units():
    assert parse_mem("1024M") == 1024
    assert parse_mem("1G") == 1024
    assert parse_mem("1T") == 1024 * 1024
    assert parse_mem("512K") == 0.5
    assert parse_mem(2048) == 2048
    assert parse_mem("") == 0.0
    assert parse_mem(None) == 0.0


def test_parse_tres_flattens_gres_and_normalises_mem():
    tres = parse_tres("cpu=128,mem=1031898M,billing=128,gres/gpu=8")
    assert tres["cpu"] == 128
    assert tres["gpu"] == 8  # gres/gpu -> gpu
    assert tres["mem"] == 1031898
    assert tres["billing"] == 128


def test_parse_tres_empty():
    assert dict(parse_tres("")) == {}
    assert dict(parse_tres(None)) == {}


def test_parse_gres_variants():
    assert parse_gres("gpu:8")["gpu"] == 8
    assert parse_gres("gpu:a100:8")["gpu"] == 8  # typed gres
    assert parse_gres("gpu:8(IDX:0-7)")["gpu"] == 8  # allocation annotation stripped
    assert dict(parse_gres("(null)")) == {}
    assert dict(parse_gres(None)) == {}
