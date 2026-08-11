# Third-party notices

VelaFetch is distributed under the MIT License. CPython and the Python runtime dependencies retain
their own licenses; the Windows portable build includes those license files under `licenses/`.

The portable build also includes an unmodified FFmpeg executable and shared libraries from
[BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds). That build is distributed under the
GNU Lesser General Public License version 3 or later. VelaFetch starts `ffmpeg.exe` as a separate
process and does not link its Python code to FFmpeg libraries.

The exact binary archive, checksums, FFmpeg source commit, build-script commit, configuration, and
source download locations are recorded in `FFMPEG_BUILD_INFO.txt`. The corresponding source
archives are published beside the portable ZIP in the same GitHub Release.

FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project. VelaFetch is not
affiliated with or endorsed by the FFmpeg project, BtbN, or Bilibili.
