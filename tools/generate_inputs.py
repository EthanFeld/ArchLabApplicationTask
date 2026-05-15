from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"

SOURCE_FILENAMES = {
    "green_parrot": "green_parrot.jpg",
    "red_flower": "red_flower.jpg",
}


def build_square_variant(source_path: Path, size: int) -> Image.Image:
    image = Image.open(source_path).convert("RGB")
    return ImageOps.fit(image, (size, size), method=Image.Resampling.LANCZOS)


def generate_variants(source_dir: Path, output_dir: Path, sizes: list[int]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for stem, filename in SOURCE_FILENAMES.items():
        source_path = source_dir / filename
        if not source_path.exists():
            raise FileNotFoundError(f"Missing source image: {source_path}")

        for size in sizes:
            output_path = output_dir / f"{stem}_{size}.png"
            build_square_variant(source_path, size).save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate square benchmark images from source photos.")
    parser.add_argument("--source-dir", type=Path, default=INPUTS)
    parser.add_argument("--output-dir", type=Path, default=INPUTS)
    parser.add_argument("--sizes", nargs="+", type=int, default=[64, 128])
    args = parser.parse_args()

    generate_variants(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        sizes=args.sizes,
    )


if __name__ == "__main__":
    main()
