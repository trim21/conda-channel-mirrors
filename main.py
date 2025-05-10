import subprocess
import itertools
from pathlib import Path

import shutil
import httpx
from rattler import Gateway, Platform, RepoDataRecord
import asyncio

from rattler.platform import PlatformLiteral


rattler_build = shutil.which("rattler-build")
if rattler_build is None:
    raise RuntimeError("can't find rattler-build executable")

platforms: list[Platform | PlatformLiteral] = [
    "noarch",
    "linux-64",
    "linux-aarch64",
    "osx-64",
    "osx-arm64",
    "win-64",
    "win-arm64",
]

cache_dir = Path(__file__).parent / ".cache"
package_cache_dir = Path(__file__).parent / ".packages"
package_cache_dir.mkdir(exist_ok=True, parents=True)


async def main():
    channel = Gateway(cache_dir=cache_dir)
    for source_channel, dest_channel in [
        ("https://repo.prefix.dev/pypi-mirrors", "pypi-mirrors"),
        ("https://repo.prefix.dev/bit-torrent", "bit-torrent"),
        ("https://repo.prefix.dev/trim21-pkgs", "trim21-pkgs"),
    ]:
        print("mirror from {} to {}".format(source_channel, dest_channel))
        names = await channel.names(
            channels=[source_channel],
            platforms=platforms,
        )

        for name in names:
            source_package_files: list[RepoDataRecord] = list(
                itertools.chain.from_iterable(
                    await channel.query(
                        channels=[source_channel],
                        specs=[name.normalized],
                        platforms=platforms,
                    )
                )
            )
            dest_package_files = {
                x.file_name
                for x in list(
                    itertools.chain.from_iterable(
                        await channel.query(
                            channels=[dest_channel],
                            specs=[name.normalized],
                            platforms=platforms,
                        )
                    )
                )
            }

            need_mirror = [
                x for x in source_package_files if x.file_name not in dest_package_files
            ]

            for i, package in enumerate(
                sorted(
                    need_mirror,
                    key=lambda package: (
                        package.version,
                        package.build_number,
                        package.build,
                    ),
                )
            ):
                f = package_cache_dir.joinpath(package.file_name)
                f.write_bytes(
                    httpx.get(package.url, follow_redirects=True)
                    .raise_for_status()
                    .content
                )
                print(
                    "uploading {}/{} {}".format(
                        i + 1, len(need_mirror), package.file_name
                    )
                )
                subprocess.check_call(
                    [
                        str(rattler_build),
                        "upload",
                        "anaconda",
                        "--owner",
                        dest_channel,
                        f.as_posix(),
                    ]
                )


if __name__ == "__main__":
    asyncio.new_event_loop().run_until_complete(main())
