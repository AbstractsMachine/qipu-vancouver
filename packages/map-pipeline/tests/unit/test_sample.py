from pathlib import Path

from qipu_map.sample import SAMPLE_RAW, steps


def test_the_sample_raw_data_ships_with_the_repository() -> None:
    assert (SAMPLE_RAW / "footprints.geojson").is_file()


def test_steps_run_every_stage_in_order() -> None:
    chain = steps(Path("w"), Path("raw"), "preview", "identity")
    commands = [" ".join(argv[:2]) if argv[0] == "eras" else argv[0] for argv in chain]
    assert commands == [
        "ingest",
        "scene",
        "eras scene",
        "render",
        "paint",
        "paint",
        "paint",
        "paint",
        "paint",
        "eras layers",
        "tiles",
        "publish",
    ]
    years = [argv[argv.index("--year") + 1] for argv in chain if argv[0] == "paint"]
    assert years == ["2026", "1930", "1950", "1972", "1982"]
    assert all(argv[argv.index("--work") : argv.index("--work") + 2] == ["--work", "w"] for argv in chain)


def test_gpu_backends_are_passed_through() -> None:
    chain = steps(Path("w"), Path("raw"), "blender", "diffusers")
    assert chain[3][-2:] == ["--backend", "blender"]
    assert all(argv[argv.index("--backend") + 1] == "diffusers" for argv in chain if argv[0] == "paint")
