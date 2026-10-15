# job.json 输入

脚本路径通过调用位置或绝对路径解析，所有 job 素材路径相对 job.json。每次改版指定新的 output，保留已认可版本。默认目标是 1920×1080 30fps；其他画幅可渲染和写入配置，但必剪原生显示须另行验证。

```json
{
  "title": "本次视频的实际标题",
  "profile": "history",
  "output": "delivery-v1",
  "target_seconds": 360,
  "duration_policy": "soft",
  "overrun_ratio": 0.1,
  "fps": 30,
  "size": [1920, 1080],
  "voice": {"name": "zh-CN-YunjianNeural", "rate": "0%", "tempo": 1.0},
  "subtitle": {"size": 62, "max_chars": 22},
  "claims": [{"text": "已核查的旁白事实或原文引语", "source_url": "对应的实际来源URL", "context": "日期 单位 身份及证据边界"}],
  "assets": [
    {"id": "archive1", "path": "inputs/photo.jpg", "kind": "image", "role": "archive", "source_url": "原始史料页面URL", "context": "可核实的拍摄时间 人物与不能证明的内容", "provenance_id": "同一底图的稳定标识", "fit": "contain", "zoom": [1, 1.02]},
    {"id": "archive2", "path": "inputs/reviewed.mp4", "kind": "video", "role": "archive", "source_url": "原始影像来源URL", "context": "已经逐镜核对的真实片段", "clip_in": 0},
    {"id": "score", "path": "inputs/music.mp3", "kind": "audio", "source_url": "音乐作者或许可页面URL", "license": "实际适用许可与完整署名"}
  ],
  "segments": [
    {"id": "opening", "text": "已经核查且配有素材的完整口语化旁白。随后发生的具体事情，也要讲清楚。", "shots": [{"asset": "archive1"}, {"asset": "archive2", "cue": "随后发生"}]}
  ],
  "overlays": [{"text": "必要的事件日期或科学单位", "segment": "opening", "duration": 3, "size": 34, "x": 400, "y": 110, "layer": 1}],
  "music": [{"asset": "score", "start": 0, "end": "end", "trim": 0, "lufs": -29}],
  "variants": ["配乐版"]
}
```

上面是格式说明，不是可直接交付的选材或文案。Agent 填写真实输入并自行核查。

省略 variants 时默认仅输出配乐版，必须提供有效的 music 素材配置。用户明确要求无配乐时设为 ["无配乐版"]；明确要求两版时才设为 ["配乐版", "无配乐版"]。任何包含配乐版的请求若缺少 music，制作会在配音和渲染前报错，不能以无音乐音轨冒充配乐版。

## 旁白与字幕

正文保留标点用于自然配音，生成字幕移除语句标点。tempo 通过 atempo 保音高变速，rate 为合成服务参数，两者不同。风格按题材决定。

可提供 segment.audio 与 segment.word_events。词时序为 edge-tts WordBoundary 原始列表，每项含 text、offset、duration，时间单位为 100 纳秒，必须对应 audio 和正文。无词时间的现成录音先用实际可用的对齐/转写工具处理，不能伪造精确字幕。

segment.editorial_cuts 可为逐条字幕数组，去标点后拼接必须与正文一致，且不能跨句。长句自动切分后由 Agent 审查，发现人名、短主语等被拆开时显式指定。

没有旁白时 text 为空、duration 为明确秒数，适合原声/纯画面视频。不能以这个功能掩盖失败的旁白合成。

## 画面与声音

每段 shots 首镜头不带 cue，后续 cue 必须是正文中的实际短语；重复短语可用 occurrence 指定第几次。切点来自实际词时序，量化到帧。没有正文时每段用一个镜头，按多个 segment 安排切镜。

图片 fit 为 contain 或 fill；zoom 建议小幅，focus 是 0—1 的焦点坐标。裁切与改名仍须使用同一 provenance_id 计数。

视频 clip_in 是原片入点。默认按实际速度使用与时间线等长的片段，源片必须足够长；只有显式 retime=true 并给出 clip_duration 才可重定时。历史画面尽量正常速度。先截取并审核源片，再作为 asset，便于打包迁移。

视频镜头设 keep_audio=true 时独立提取原声，audio_gain_db 控制其音量。旁白与原声冲突需主动调低原声。音乐自动淡入淡出并用旁白/原声作侧链压低；素材不足时不能默认循环伪造连续音乐。

科学示意素材使用 profile=science，role=simulation 或 illustration，并在适用处用 overlay 明确“示意”。历史 archive 禁止 ai_generated=true。任何模式都需要 Agent 检查素材真实含义，字段声明不是真实性证明。

overlays 可用绝对 start/end，或 segment 加 cue/duration；end="end" 表示全片结束，end="segment" 表示所属段落结束。必须放在独立 layer，同层不能重叠。给日期/地点设与相关镜头一致的结束时间；标题不要挡住下一镜头的报纸版面。

默认 bundle_sources=true，交付保存源素材及可重建的 job-snapshot.json。大体积源片先选取审核片段再打包。若有明确原因关闭源素材打包，必剪仍可使用渲染镜头编辑，但须说明无法仅凭交付目录重新生成原始镜头。

交付文件均落在指定 output，脚本不会自动改写必剪索引。先 verify 和视觉检查，再显式 register。

历史视频必须有 claims 论断来源表，其他知识视频也应填写。工具将其与素材信息导出为 research.md；字段存在不等于事实已经核查，Agent 仍须实际读原文并判断证据。

同一 output 下请求内容或输入素材发生变化时，自动建立带内容标识的新目录，保留旧版。同项目的 .bcut-cache 缓存不变的合成旁白和镜头；交付复制完整媒体，可脱离缓存在必剪编辑。登记要求本次 verify 通过，且验收后的关键文件哈希未改变。
