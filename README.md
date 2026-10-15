# 必剪自主视频制作 · bcut-video-maker

面向 Windows 与 Codex 的视频制作 skill。给出主题和要求后，由 Agent 完成研究、文案、选材、配音、剪辑与检查，交付 MP4 和可在必剪继续修改的分轨草稿。

适用于科普、历史及其他讲解视频。默认直接制作，最后审看成片；也可单独要求提纲、文案或修改已有项目。

> 这是供 Agent 调用的工作流与工具集，不是必剪插件或官方 MCP 服务。脚本负责确定性制作，研究、选材和审稿由 Agent 完成。

## 功能与创作原则

| 能力 | 交付方式 |
| --- | --- |
| 研究与故事 | 核查事实、引语与时间，记录来源，围绕人物行动及后果组织叙事 |
| 画面编排 | 视频、照片、原始文献与必要的动态示意，切镜跟随实际旁白时间 |
| 声音 | 可配置音色与语速，旁白、原声、音乐分轨，支持配乐和无配乐版本 |
| 字幕 | 粗宋体、白字描边，生成 SRT、ASS 和必剪原生字幕 |
| 必剪工程 | 镜头片段、字幕、旁白、配乐分别可编辑，登记到草稿箱 |
| 迁移与检查 | 媒体打包、路径重建，检查黑屏、时间线、字幕、字体与声音，生成抽帧图 |

- **不做 PPT 式讲解页**：不用背景加大段文字代替素材与剪辑。
- **历史题材使用真实史料**：禁止 AI 编造历史照片、现场影像、人物言行；现代示意须与实拍区分。
- **科普讲清证据与机制**：模拟不能冒充真实实验，必要时注明示意和适用条件。
- **故事优先**：说明人物做了什么、后果是什么、任务为什么难，避免空泛排比和生硬总结。
- **字幕去语句标点**：保留小数点、正负号、比例、单位与公式中的必要符号；配音正文仍保留标点。
- **优先代码、CLI 和可用 MCP**：非必要不使用 computer-use。
- **保留已认可版本**：改版另建输出，允许小幅超时讲完整故事，明确的硬性时长上限优先。

音色、速度、音乐、画幅和版本数量按题材选择。云健 1.2 倍速是历史项目使用过的选项，并非通用固定设置。照片运镜可预渲染为独立镜头，不承诺每个动画参数都是必剪原生关键帧。

## 安装到 Codex

先准备 Git，并确保当前电脑有访问此私有仓库的 GitHub 凭据。在 PowerShell 中执行：

```powershell
$skillsRoot = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
} else {
    Join-Path $env:USERPROFILE '.codex\skills'
}
New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null
git clone https://github.com/12310312long/bcut-video-maker.git (Join-Path $skillsRoot 'bcut-video-maker')
```

同名目录已存在时，先检查并备份自己的修改，不要直接覆盖。也可下载 ZIP，将包含 `SKILL.md` 的目录命名为 `bcut-video-maker`，放入上述 `skills` 目录，保留全部子目录结构。

安装后在新会话中确认 skill 可被发现。已有 Git 克隆在工作区干净时可更新：

```powershell
git -C (Join-Path $skillsRoot 'bcut-video-maker') pull --ff-only
```

## 使用示例

在 Codex 中直接描述任务。以下仅为调用示例，**不代表仓库附带这些成片**。

```text
使用 $bcut-video-maker 制作一段约 5 分钟的科普视频
主题是飞机为什么能飞 面向高中生
重点解释升力和迎角 避免常见误解
交付必剪分轨工程及 MP4 最后给我看成片
```

```text
使用 $bcut-video-maker 制作一段约 6 分钟的历史视频
主题是上海解放和银元之战 米棉之战
使用可核实的历史素材 要有具体人物与博弈细节
云健配音 1.2 倍速 配乐和无配乐各一版
```

最好提供主题、受众、用途、时长、画幅和必须包含的内容。有参考风格、已有素材或指定来源也可一起提供。非关键设置由 Agent 选择；环境阻塞或新增授权需求仍可能需要你参与。

## 环境与兼容性

| 项目 | 要求或边界 |
| --- | --- |
| 系统 | Windows，适配不同用户名、盘符与必剪安装位置 |
| Python | 3.10+，建议使用项目独立虚拟环境 |
| 媒体工具 | FFmpeg 与 ffprobe，需可被发现 |
| Python 依赖 | Pillow，云配音另需 edge-tts，见 scripts/requirements.txt |
| GPU | 可选，尝试 NVENC，失败回退 CPU 编码 |
| 必剪 | 原生模板基于 Windows 3.11.25，其他版本须检查并适配 |
| 输出基线 | 1920×1080、30fps，其他画幅的原生显示须另行验证 |

云配音需要网络与可用服务。仓库不内置 Python、FFmpeg、必剪或商业配音服务额度。

工程写入使用经过验证的 `.bjson` 字段样板，不依赖官方开放工程 API。JSON 可解析不代表跨版本兼容。

## 工具入口

以下在仓库根目录执行，`python` 应替换为当前环境可用的解释器。建议在独立虚拟环境中安装依赖：

```powershell
python -m pip install -r scripts/requirements.txt
python scripts/studio.py doctor
python scripts/selftest.py
```

完成研究、文案与真实选材后，按 [job.json 格式](references/job-format.md) 准备项目：

```powershell
python scripts/studio.py build 'D:\MyVideo\job.json'
python scripts/studio.py verify 'D:\MyVideo\delivery'
```

`delivery` 是示例目录，实际以任务配置和工具返回路径为准。自动检查后，Agent 仍需审看抽帧、核查画面与文案的相关性，并在具备音频检查能力时抽听。

必剪退出、验收通过后，显式登记到草稿箱：

```powershell
python scripts/studio.py register 'D:\MyVideo\delivery' --drafts-dir '实际草稿目录' --bcut-dir '实际必剪安装目录'
```

工具先备份索引再写入。必剪运行时拒绝登记，不强制关闭程序；制作和导出可先完成。

## 交付与跨电脑迁移

交付目录包含 MP4、必剪草稿、独立镜头与音频、字幕、公共时间轴、来源记录和迁移清单。默认还打包源素材及可重建的 `job-snapshot.json`。

将**完整交付目录**复制到新电脑，准备依赖与必剪，再重定位、检查、登记：

```powershell
python scripts/studio.py relocate 'E:\MyVideo\delivery' --bcut-dir '新电脑必剪安装目录'
python scripts/studio.py verify 'E:\MyVideo\delivery'
python scripts/studio.py register 'E:\MyVideo\delivery' --drafts-dir '新电脑草稿目录' --bcut-dir '新电脑必剪安装目录'
```

不要只复制 `.bjson` 文件。移动目录或更改盘符后也需要重定位。安装 skill 和迁移某个视频项目是两个独立操作。

## 验证范围

已进行字幕与模板离线回归测试、历史与科普短样片制作、独立原声轨测试、本机不同目录迁移及隔离草稿索引登记测试。必剪 3.11.25 模板曾用于历史项目并经用户打开核验。

这些验证不等于所有题材、版本和电脑均已测试；仓库不附带已完成的约 5 分钟科普视频。自动验收不能替代事实核查、审美判断或当前必剪版本的实际打开检查。

## 目录与详细文档

```text
SKILL.md                         Agent 工作流与默认偏好
agents/openai.yaml               skill 显示信息
scripts/studio.py                制作 检查 迁移 登记入口
scripts/bcut.py                  必剪工程及草稿索引处理
scripts/captions.py              字幕断句与标点处理
scripts/selftest.py              离线回归测试
scripts/requirements.txt         Python 依赖
assets/sanitized-template.bjson  清理后的工程模板
assets/ShanghaiSerif-Bold.ttf    随附粗宋体字体
assets/OFL.txt                   字体许可
references/                      研究 编辑 制作与检查说明
```

- [完整 skill 指令](SKILL.md)
- [研究与叙事](references/editorial.md)
- [执行、登记与迁移](references/production.md)
- [项目输入格式](references/job-format.md)
- [检查与修订](references/quality.md)

仓库不包含原历史项目素材、成片或个人凭据。随附字体遵循 [OFL 许可](assets/OFL.txt)；其他图片、影像及音乐需分别记录并遵守来源和许可。访问私有仓库的权限不代表获得第三方素材的使用授权。
