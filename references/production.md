# 执行与迁移

`studio.py doctor` 输出 Python、FFmpeg/ffprobe、Pillow、edge-tts、必剪安装候选和用户文档草稿目录。支持显式 --bcut-dir、--drafts-dir；这些是机器配置，不能写死进新任务。

依赖为 Python 3.10+、FFmpeg/ffprobe、Pillow；自动配音另需 edge-tts。优先现有运行时，缺失时在项目中建立 venv 并安装 scripts/requirements.txt。FFmpeg 缺失时依据当前官方来源或可信软件包安装，不下载未知二进制。字体和 OFL 许可随项目携带。

GPU 可用时尝试 NVENC 实际编码，失败自动用 libx264。云配音失败有限重试并报告，不以静音冒充成功旁白。

```text
PYTHON scripts/studio.py doctor
PYTHON scripts/studio.py build X:/project/job.json
PYTHON scripts/studio.py verify X:/project/delivery
```

工具生成 timeline.json、字幕、独立镜头、旁白/原声/音乐轨、MP4、原生草稿和 portable.json。媒体路径均在交付目录内；原始素材来源单独保存。不需要登录、发消息或发布 B 站作品。

默认制作一个配乐版本，Agent 应主动选择并配置有明确使用许可的音乐；不默认附送无配乐版。只有用户明确要求才调整 variants，配乐版缺少音乐配置时提前报错。

时序按整数帧，转换为必剪毫秒与索引微秒时分别换算。唯一连续主视频轨保留分镜粒度。视频原声可独立提取为轨道，配音与音乐分轨。

## 版本与登记

sanitized-template.bjson 是 3.11.25 的字段样板，已去除旧路径和内容，不是官方接口。版本优先从现有 project.bjson 检测，其次为程序版本。仅检测到程序不等于 schema 已验证。

3.11.25 且结构匹配时可登记。其他版本先对比 videoTracks/audioTracks/captionTracks/config 与片段样例，使用已核实的适配模板；工具不提供跳过检查的通用强制开关。

```text
PYTHON scripts/studio.py register X:/project/delivery --drafts-dir <草稿目录> --bcut-dir <安装目录>
```

必剪运行时只拒绝登记并保留成片，Agent 在最后提示保存退出一次，不强杀进程。索引备份后写临时文件并原子替换，用新 UUID 登记；同交付重复登记依标记复用条目。

## 换电脑

复制完整 delivery 目录并保持内部结构：

```text
PYTHON scripts/studio.py relocate Y:/new-folder/delivery --bcut-dir <新安装目录>
PYTHON scripts/studio.py verify Y:/new-folder/delivery
PYTHON scripts/studio.py register Y:/new-folder/delivery --drafts-dir <新机草稿目录> --bcut-dir <新安装目录>
```

portable.json 保存可重定位字段，重建原生工程和公共时间轴中的媒体路径。默认文字资源路径从当前必剪目录解析，不复制整个程序资源。字体按用户级注册，不需要管理员权限。

目录更名同样先 relocate 再登记；登记标记按目标草稿目录独立记录，避免与旧电脑标记混淆。

离线回归测试：`PYTHON scripts/selftest.py`。它检查字幕句界、孤立尾字、科学符号和模板清洁，不替代实际视频制作、迁移或 GUI 验证。
