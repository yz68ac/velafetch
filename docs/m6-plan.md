# M6：Bilibili 多条目与常用下载能力（已完成）

M6 把单视频下载扩展为普通多 P、公开番剧和公开 UGC season/series，并加入常用 sidecar、
批量结果、文件名模板、AV1 SDR 与 HEVC HDR。仍只处理匿名可访问内容。

## 阶段一：资源与批量

- 普通 BV/av/URL 接受正整数 `p`，CLI 的 `--page` 可覆盖 URL 选择。
- `ss`、`ep` 和严格的 `/bangumi/play/...` URL 投影为 season 与 episode 条目。
- 严格的 space list URL 支持 `type=season|series`，按服务端 total 完整分页并稳定去重。
- `--item` 选择 episode/合集条目；`--all` 顺序展开多 P、整个 season 或合集内全部 P。
- 批量先完成元数据枚举和文件名冲突检查，再在每个单元开始时获取播放地址。

## 阶段二：sidecar、模板与结果

- 默认尝试封面和全部公开字幕；弹幕通过 `--danmaku` 显式启用。
- 字幕可保存原始 JSON 结构或转换为稳定排序、毫秒时间戳的 UTF-8 SRT。
- sidecar 与媒体共用 stem，并通过同目录临时文件和 `os.replace` 发布。
- 封面失败只记 warning；字幕/弹幕失败使当前项为 `partial` 并继续；媒体或 FFmpeg
  失败使当前项为 `failed` 并停止后续批量。
- `download --json` 输出单一 `{ok, aborted, items}` 文档，不启用 Rich 进度。
- 模板只描述文件名 stem，支持 `{source_title}`、`{title}`、`{part_title}`、`{id}`、
  `{item}`、`{page}` 及整数宽度格式。

## 阶段三：兼容格式

- 默认 `dynamic-range=sdr`；同高度的 `auto` 顺序为 AVC、HEVC、AV1。
- AV1 仅自动处理 SDR MP4；HDR 仅自动处理 HEVC MP4。
- 显式 codec 与动态范围严格匹配，不跨 codec 或范围降级。
- Dolby Vision、FLAC 与 E-AC-3 继续显示在 `formats`，但因容器与设备兼容性保持
  report-only。

## 实际接口验收

2026-08-10 使用匿名会话完成以下检查：

- 公开多 P `BV1dujdzrEA4`：P2 选择正确，5 个 P 的 360p `--all --video-only` 顺序下载、
  子目录命名和 JSON 结果成功。
- 公开番剧 `ss47200`：season 列表和第 1 集格式成功；360p AV1 纯视频、封面和 XML 弹幕
  实际发布成功。
- 公开 UGC season `mid=546195, season_id=1903592` 与 series `series_id=4684427`：完整列表
  和选中条目格式成功。
- 字幕查询已改为带 WBI 签名的 `/x/player/wbi/v2`。当次匿名测试的公开样例返回
  `need_login_subtitle=true` 且无轨道；按照 M6 边界未加入 Cookie，也没有伪造“成功”。
  合成 fixtures 已完整验证多语言选择、SRT/JSON、重试和事务发布。

真实验收生成的媒体只位于 `.codex-tmp/m6-live`，完成后已清理。普通 pytest 始终离线。
