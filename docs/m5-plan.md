# M5：轻量下载可靠性（已完成）

M5 没有把下载器改造成通用框架。它只把 M4 中已经出现的单轨道流式传输拆到
`application/transfer.py`，并补上备用地址、三次尝试、跨运行续传和长度检查。

## 当前流程

```text
选定一条轨道
  → 找到稳定的 .part 路径
  → 已有 partial 时用 bytes=0-0 探测远端总大小
  → 从现有字节继续，失败时轮换到下一 CDN 地址
  → 最多进行三次实际传输
  → 完整轨道交还 DownloadService 发布或混流
```

partial 固定保存在：

```text
OUTPUT/.velafetch/<canonical-id>/page-1/<format-id>.<container>.part
```

路径只使用规范化媒体 ID、页码、稳定 format ID 和容器，不保存标题、媒体 URL、签名或
请求头。同一轨道刷新播放地址后仍可复用 partial。

## Range 与长度规则

- 媒体请求固定发送 `Accept-Encoding: identity`。
- 有 partial 时先发 `Range: bytes=0-0`。本地与远端一样长就直接完成；本地过长则丢弃；
  无法探测时保留现有字节并由真实续传响应决定。
- `200` 表示完整响应。服务器忽略 Range 时先清空旧 partial，再使用当前响应重下。
- `206` 必须带可解析且起点匹配的 `Content-Range`，否则换地址重试。
- `416` 后再次探测远端大小；本地确实完整则成功，否则下一次从零下载。
- `Content-Length` 或 `Content-Range` 提供了总长度时，EOF 后必须匹配最终大小。
- 无 `Content-Length` 的 `200` 只要 EOF 时文件非空即可完成。
- 短 partial 保留续传；过长或协议互相矛盾的 partial 删除。

每条轨道最多三次实际传输。地址按主地址、备用地址顺序循环，重试前等待 0.5 秒。网络
错误、非成功状态、提前 EOF 和无效 Range 可以重试；本地文件系统错误直接失败。最终错误
只报告轨道类型、尝试次数和必要状态码，不包含私有 URL。

## 生命周期

- 视频和音频仍顺序下载，不并行。
- 默认模式在两个 partial 完成后使用 FFmpeg `-c copy` 混流；成功发布后删除两条 partial。
- video-only、audio-only 和 no-mux 用 `os.replace` 将对应 partial 发布为最终文件。
- 网络失败、取消或 FFmpeg 失败保留可用 partial；只逐级删除已经为空的内部目录。
- `--overwrite` 只控制最终文件，不影响续传。M5 的单媒体路径会跳过已有结果；M6 为补齐
  缺失的封面、字幕或弹幕，重跑时仍会读取元数据，但不会重新传输已有媒体。

## 验证与边界

离线测试用可编排的内存 HTTP fake 覆盖主/备用地址、三次尝试、流中断、跨运行续传、
200/206/416、Range 被忽略、缺失长度、提前 EOF、远端长度变化和取消清理。真实 DASH
探测确认同一轨道的三个候选地址都接受 1 字节 Range，并报告相同总长度；同时确认 416
响应不一定包含 `Content-Range`，因此不能只依赖 416 判断本地文件是否完整。

M5 不加入并行、限速、状态 JSON、校验和、ETag、URL 刷新或 no-mux 多文件事务回滚。这些
能力只有在实际使用暴露对应问题后才进入后续工作。

M6 已把 partial 的资源段扩展到番剧 episode 和 UGC 合集条目；这里的 `page-1` 路径仍是
普通单视频示例。
