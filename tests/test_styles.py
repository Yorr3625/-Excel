from modules.styles import blue_fill, fills_for, green_fill, purple_fill, yellow_fill


def test_fills_for_first_four_match_named_fills():
    fills = fills_for(4)

    assert [fill.start_color.rgb[-6:] for fill in fills] == [
        green_fill.start_color.rgb[-6:],
        yellow_fill.start_color.rgb[-6:],
        blue_fill.start_color.rgb[-6:],
        purple_fill.start_color.rgb[-6:],
    ]


def test_fills_for_returns_requested_count_of_distinct_colors():
    fills = fills_for(8)

    assert len(fills) == 8
    assert len({fill.start_color.rgb for fill in fills}) == 8
