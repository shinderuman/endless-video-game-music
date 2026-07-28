from endless_vgm.__main__ import build_parser


def test_short_command_line_options() -> None:
    args = build_parser().parse_args(["-H", "0.0.0.0", "-p", "9000", "-o", "-v"])

    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.open_browser is True
    assert args.verbose is True
