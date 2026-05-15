from tools.enhancement import (
    build_brightness_clique_batches,
    build_brightness_cliques,
    expand_cliques_to_pixels,
    extract_image_tile,
    merge_image_tile,
    plan_adaptive_brightness_tiles,
)


def test_adaptive_tile_plan_covers_large_image() -> None:
    plan = plan_adaptive_brightness_tiles(
        width=512,
        height=384,
        addr_bits=16,
        launch_threads=128,
    )

    assert plan["tile_count"] > 1
    assert plan["tile_width"] == 512
    assert plan["tile_height"] > 1

    covered_pixels = sum(tile["pixels"] for tile in plan["tiles"])
    assert covered_pixels == 512 * 384
    assert all(tile["padded_pixels"] <= plan["max_padded_pixels"] for tile in plan["tiles"])


def test_adaptive_tile_plan_falls_back_to_row_segments() -> None:
    plan = plan_adaptive_brightness_tiles(
        width=70000,
        height=2,
        addr_bits=16,
        launch_threads=128,
    )

    assert plan["tile_height"] == 1
    assert plan["tile_width"] == plan["max_padded_pixels"]
    assert plan["tile_count"] == 4


def test_extract_and_merge_tile_round_trip() -> None:
    width = 6
    height = 4
    pixels = list(range(width * height))
    output = [-1] * (width * height)

    tile_pixels = extract_image_tile(
        pixels=pixels,
        image_width=width,
        left=2,
        top=1,
        tile_width=3,
        tile_height=2,
    )

    assert tile_pixels == [8, 9, 10, 14, 15, 16]

    merge_image_tile(
        output_pixels=output,
        image_width=width,
        left=2,
        top=1,
        tile_width=3,
        tile_height=2,
        tile_pixels=tile_pixels,
    )

    assert output[8:11] == [8, 9, 10]
    assert output[14:17] == [14, 15, 16]


def test_brightness_cliques_group_similar_runs() -> None:
    cliques = build_brightness_cliques([10, 11, 12, 40, 42, 90], threshold=2)

    assert [clique["length"] for clique in cliques] == [3, 2, 1]
    assert [clique["representative"] for clique in cliques] == [11, 41, 90]

    expanded = expand_cliques_to_pixels(cliques, brightness=10)
    assert expanded == [21, 21, 21, 51, 51, 100]


def test_brightness_clique_batches_split_by_capacity() -> None:
    pixels = [10, 11, 50, 51, 90, 91, 130, 131, 170, 171]
    batch_plan = build_brightness_clique_batches(
        width=10,
        height=1,
        pixels=pixels,
        brightness=5,
        threshold=1,
        addr_bits=3,
        thread_count_bits=16,
        launch_threads=2,
    )

    assert batch_plan["metadata"]["batch_count"] == 3
    assert batch_plan["metadata"]["clique_count"] == 5
    assert batch_plan["expected_pixels"] == [16, 16, 56, 56, 96, 96, 136, 136, 176, 176]
