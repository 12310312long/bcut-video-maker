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

`build`检测到请求与现有`build-request.json`不同，会在输出目录名后追加请求标识；以后续实际返回的`delivery`路径为准，不假设仍在job指定的旧目录。更名或复制交付目录后先重定位，更新配置、成片名及说明，再对当前产物验收、登记和打包。不同修改版本的草稿名称应便于用户辨认。

Windows下读写JSON、字幕和中文文案显式指定UTF-8；运行项目Python脚本可用`-X utf8`，不依赖系统默认代码页。多行脚本或包含多层引号的命令先写入文件再执行，避免PowerShell与Python重复解析引号、反引号和变量。

默认制作一个配乐版本，Agent 应主动选择并配置有明确使用许可的音乐；不默认附送无配乐版。用户指定的 `source_audio` 已含原配乐时，按 [完整原声](original-audio.md) 标记并保留，不再强制叠音乐。其他配乐版缺少音乐配置时提前报错。

时序按整数帧，转换为必剪毫秒与索引微秒时分别换算。唯一连续主视频轨保留分镜粒度。视频原声可独立提取为轨道，配音与音乐分轨。

## 版本与登记

sanitized-template.bjson 是 3.11.25 的字段样板，已去除旧路径和内容，不是官方接口。版本优先从现有 project.bjson 检测，其次为程序版本。仅检测到程序不等于 schema 已验证。

3.11.25 且结构匹配时可登记。其他版本先对比 videoTracks/audioTracks/captionTracks/config 与片段样例，使用已核实的适配模板；工具不提供跳过检查的通用强制开关。

```text
PYTHON scripts/studio.py register X:/project/delivery --drafts-dir <草稿目录> --bcut-dir <安装目录>
```

必剪运行时只拒绝登记并保留成片，Agent 在最后提示保存退出一次，不强杀进程。索引备份后写临时文件并原子替换，用新 UUID 登记；同交付重复登记依标记复用条目。

草稿未出现在首页时，先用 `doctor` 和 Windows `User Shell Folders/Personal` 确认实际文档位置；OneDrive可能将其重定向，不能认定 `%USERPROFILE%/Documents` 一定生效。核对该位置已有 `Bcut Drafts/draftInfo.json` 与UUID子目录，不通过遍历全盘或猜多个目录反复写入。只复制工程到普通交付目录不会自动出现在草稿箱。

登记后读取目标索引，检查新条目的ID、名称、微秒时长与对应UUID目录中的 `project.bjson`，并核对媒体和字体路径可读。用户禁止computer-use时沿用禁令；可交付明确草稿名供用户手动打开，并如实区分“登记成功”与“实际打开成功”。

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
