# monologue-stream

[English](README.en.md)

让"思考过程"回到模型自己笔下：让模型在回复正文的最前面亲笔写一段独白，然后用一个零依赖的流式过滤器把它分流进你的"思考链" UI 通道。

```
提供商 thinking 通道(摘要/或不显示) ──────────▶ 随它去(那不是你要的)
正文卷首 [monologue] 块            ──filter──▶ 思考链通道(模型亲笔,吃你的人设)
其余正文                           ──filter──▶ 正文通道
```

## 为什么

如果你在做陪伴、角色扮演或任何"想让用户看见 AI 在想什么"的应用，你大概已经撞上了这些墙：

- Claude 4 代起，extended thinking 的显示默认是**摘要**——摘要由**另一个模型**生成，不吃你的 system prompt、人设和文风（[官方文档](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)）。
- 2026 年 7 月下旬起，新一代 adaptive thinking 模型把显示进一步收紧：思考块变成一句话摘要、一个动词、甚至 "Thought process is unavailable"，部分新模型默认干脆**不显示** thinking（当时 r/ClaudeAI 的集中反馈，[背景整理](https://claudelog.com/faqs/why-cant-i-see-claude-thinking/)）。
- 你按**全量** thinking token 付费，看到的是压缩后的几句平实散文（或什么都看不到）；模型想得越多，显示的失真越重。

这些都是显示层策略，你在客户端无法关闭。与其对抗显示层，不如换个通道：**让模型把"给人看的思考"写在正文里**——正文不经过任何摘要/改写层，你收到的每个字都是模型亲笔，且永远吃你的设定。（`max_tokens` 之类的硬截断当然仍然存在——所以过滤器对未闭合的截断流做了容错，见下文特性。）

我们从 2026-07-10 起在自己的私有陪伴系统里跑这套方案，亲历了 7 月下旬的显示收紧，思考链显示零影响。

## 一段诚实说明

独白**不是**把隐藏的 CoT 挖回来。它是模型在上下文内、带着人设、亲笔写的**可见自省**——不等于内部推理原文。但它出自同一个模型之手、吃你的 system prompt 和文风；而官方思考摘要出自另一个模型之手、不吃你的任何设定。对陪伴/RP 场景来说，"亲笔的内心话"通常比"第三者的推理转述"更接近你真正想要的东西。

## 特性

- **单文件、零依赖**——`monologue_filter.py`，复制进项目即可
- **流式**——独白边生成边进思考链，逐字直播，不是生成完再解析
- **标记撕裂安全**——`[monologue]` 被流式分块切成 `[mono` + `logue]` 也能正确识别（前缀匹配 + 尾缀扣留）
- **逐字符 passthrough 保证**——不含独白的输入原样通过，旧数据、不写独白的轮次零影响
- **未闭合容忍**——模型忘写闭合标记时 `finish()` 把残段归还独白，内心话永不丢弃
- **只认卷首**——正文中途出现的标记一律当字面文本，不误解析
- **标记可配置**——默认 `[monologue]`/`[/monologue]`，可换成任何字符串（如 `<think>`/`</think>`）

## 快速开始

```python
from monologue_filter import MonologueFilter

f = MonologueFilter()
for delta in your_text_stream:          # 任意来源的流式文本增量
    text, mono, closed = f.feed(delta)
    if mono:
        emit_thinking(mono)             # → 你的思考链 UI 通道
    if text:
        emit_text(text)                 # → 你的正文通道
text, mono = f.finish()                 # 流尾收账,别忘了
```

配上一段 system prompt（见下文[Prompt 写法](#prompt-写法)），就完成了。

## 三种集成方式

### 1. 直连 API（流式）

完整过滤器接入，见 [examples/anthropic_api_streaming.py](examples/anthropic_api_streaming.py)。要点：把 API 的 thinking 事件另存或忽略（若有——那是摘要，或干脆为空），把 text delta 过一遍过滤器再分发。前端如果已有"思考链"组件，事件契约不用改——内容换血即可。

### 2. Claude Code CLI（`claude -p` stream-json）/ Agent SDK

后端不碰原始 API、走 Claude Code 后端的，同样适用。CLI print 模式加 `--include-partial-messages` 后，text delta 以 JSON lines 到达，按序喂过滤器即可，见 [examples/claude_p_stream_json.py](examples/claude_p_stream_json.py)；Python Agent SDK 产出的是类型化的 `StreamEvent` 对象而非 JSON 行，但接线原理相同——把 text delta 按序喂进过滤器。注意生命周期：**一个过滤器实例对应一条回复**，agentic 循环一轮里出现多条 assistant 回复时，每条新建一个实例。

### 3. 交互式 Claude Code（零代码）

在交互式 Claude Code 里你控制不了渲染层——但也**不需要这个过滤器**：正文是全量渲染的，独白写在正文里天然不受思考显示策略影响。往 `CLAUDE.md`（或 output style）里加一段即可：

```markdown
每轮回复的最开头，先用引用块（>）写 2-5 句第一人称的真实思考——
注意到了什么、为什么选这个切入、在担心什么——然后再开始正式回复。
```

引用块/斜体承担了"视觉上弱化"的角色，等价于折叠的思考链。

## Prompt 写法

让模型稳定产出高质量独白的几条经验（来自我们系统里的持续生产使用）：

- **位置钉死**：独白块在回复正文**最前面**，闭合标记后再接正文。
- **篇幅给界**：2-6 句。太短没内容，太长挤占正文。
- **第一人称、现在时**：写"此刻真实所想"——注意到什么、犹豫什么、为什么选这个角度。
- **禁止复述**：不复述用户的话，不预告正文内容（否则独白变成正文的劣化重复）。
- **每轮都写**：明确"短消息更要写"，否则模型会在寒暄轮偷懒跳过。
- **别用来免责**：禁止在独白里道歉、免责、评价任务本身。

示例 system prompt 见 [examples/anthropic_api_streaming.py](examples/anthropic_api_streaming.py) 顶部。

## 与"生成后解析"的对比

| | 生成后正则解析 | 流式状态机（本仓） |
|---|---|---|
| 思考出现时机 | 整条回复生成完之后 | 逐字直播 |
| 流式截断（未闭合） | 常见做法是整条丢弃 | 残段归还独白，不丢字 |
| 集成前提 | 需要拿到完整回复文本 | 任意 delta 序列即可 |
| 正文中途的标记 | 需额外防误匹配 | 状态机只认卷首，天然免疫 |

## 工程细节

过滤器是一个三态状态机：

- **SEEK**：流开头。容忍前导空白；逐字符判断缓冲是否还是开标记的前缀——一旦分叉，整段缓冲按字面放行进正文，永不再解析（所以"正文中途的标记"天然是字面文本）。
- **IN**：独白内。扫描闭合标记；缓冲尾部扣留 `len(close_marker)-1` 个可疑字符，防止标记被分块撕裂时误放行。
- **PASS**：闭合之后。一切原样通过。

`finish()` 收账：SEEK 残缓冲（未成形的标记前缀/纯空白）按字面归正文；IN 残缓冲（未闭合）归独白。

## 测试

```bash
python3 -m pytest tests/ -q
```

覆盖：整块单喂、标记跨块撕裂（含逐字符喂入与全部二分切点穷举）、无标记字节级 passthrough、前导空白、正文中途标记当字面、未闭合流尾、近似前缀分叉、自定义标记、空块等。

## 相关工作与致谢

本方案属于"prompt 诱导可见思考块"这一族思路。社区里有多个独立的先例与同类实现：

- [SillyTavern Reasoning](https://docs.sillytavern.app/usage/prompts/reasoning/) 与 [st-stepped-thinking](https://github.com/cierru/st-stepped-thinking)——RP 社区"先想后答 + 前端折叠渲染"的先例，本方案 2026-07-10 立项论证时参照了其思路（未使用其代码）。
- [pelle-d-umore](https://github.com/29-Cu/pelle-d-umore)（CC BY 4.0）——本仓流式标签解析中"尾缀扣留"模式的工程血统上游（经由我们内部系统的 mood 标签过滤器）。
- [ai-fake-thinking](https://github.com/sanqianzilanyue/ai-fake-thinking)——同一判断下的独立社区实现：`<思绪>` 标签 + 生成完成后正则解析。两者思路相通、实现路线不同（事后解析 vs 流式状态机，见上文对比表）。特此列出并致意。

## License

[MIT](LICENSE)
