# M7：登录态与用户授权访问

M7 为已有的视频、番剧和 UGC 合集路径增加一个可选的 Bilibili Web 登录态。登录不会
扩大内容边界：只有官方接口为当前账号返回普通、未加密 DASH 时，原有格式选择和下载
流程才会继续。

## CLI 与本地凭据

- `auth login` 在交互式终端显示二维码，每两秒轮询一次，180 秒超时。
- `auth import-cookie` 使用隐藏提示；`--stdin` 支持从剪贴板或重定向读取。
- `auth status [--json]` 使用 nav 接口验证当前登录，不输出任何 Cookie。
- `auth logout` 只删除当前目录的 `.velafetch/credentials.json`。
- 根级 `--anonymous` 完全跳过凭据读取，必须位于子命令之前。

凭据文件采用严格的 `schema_version = 1` JSON，并通过同目录临时文件和 `os.replace`
更新。只保存 `SESSDATA`、`bili_jct`、`DedeUserID`、`DedeUserID__ckMd5`、`sid` 以及安全
账号摘要。文件按项目选择保持明文；POSIX 尝试使用 `0600`，Windows 继承目录 ACL。
二维码 URL、`qrcode_key` 和 `refresh_token` 仅存在于当前登录进程。

## 请求与权限边界

登录 Cookie 通过 `curl_cffi` cookie jar 设置为 Domain `.bilibili.com`、Path `/`、Secure，
因此不会发送给 `.bilivideo.com` 媒体 CDN 或封面、字幕地址。普通命令没有凭据时仍按
M6 的匿名路径运行；凭据过期后明确提示重新登录，不实现自动刷新。

账号可见的画质、字幕和已授权番剧复用现有提取、选轨、Range 续传、FFmpeg 和 sidecar
流程。会员或购买权限不足、地区限制、preview-only 和 DRM 响应保持 unsupported。M7
不增加收藏夹、稍后再看、课程/cheese、密码/SMS 登录、TV token、任意 Cookie 参数或
远程账号操作。

## 验证记录

- 2026-08-10 匿名验证 Web QR generate/poll 端点仍返回当前二维码 key、URL 和轮询状态。
- 116 个离线测试覆盖 Cookie 解析、原子存储、二维码状态、重试、超时、取消、CLI、
  域作用范围、错误脱敏、登录态注入和 DRM 拒绝。
- 真实账号扫码、登录/匿名格式对比和下载仍需由用户在交互式终端完成；完成前 TODO 中
  的最后一项保持未勾选。
