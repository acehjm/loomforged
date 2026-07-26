---
name: memory-recall
description: 从经验资产库（Experience）中唤醒与当前任务相关的历史经验，为当前分析、设计和决策提供参考。
---
# Memory Recall

从 Experience 库中寻找与当前任务相关的历史经验，帮助 Agent 理解问题、作出判断和复用已有做法。

Memory Recall 只读取和引用已有 Experience，不修改 Experience 库。历史经验需要结合当前场景判断，不能直接替代当前分析。

## Experience 库

Experience 根目录：

```text
E:/资料/内容仓库/Agents/experience/
```

Experience 入口文件：

```text
E:/资料/内容仓库/Agents/experience/index.md
```

index.md 同时记录 Experience Space 和单条 Experience 的检索信息。Recall 应先根据标题、Space、类型、状态和标签查找候选项，再根据索引中的文件路径和 Experience ID 读取完整内容。

默认不扫描全部经验文件。根目录或索引文件无法访问时，停止检索并说明原因。

## 使用场景

当当前任务可能从已有经验中获得帮助时使用，例如：

- 遇到与过去相似的问题或场景
- 需要作出判断、选择或取舍
- 希望复用已有的方法、流程或处理方式
- 需要了解长期有效的条件、限制或偏好
- 进入不熟悉的领域，希望参考相关经验

Recall 也可以由 Agent 在分析任务时主动使用，不要求用户明确提出检索 Experience。

## 核心原则

Recall 面向当前任务寻找有帮助的 Experience，而不是查找某个项目、文件或历史对话。

检索以经验的实际价值为准，不因标题或关键词相同就直接返回，也不限制 Experience 必须来自当前项目或同一领域。

默认只使用 `active` Experience。`superseded` Experience 仅在需要了解历史变化、决策演进或旧方案时参考，并明确说明其已经被替代。

历史 Experience 只作为参考。使用前应结合当前任务的目标、场景、条件和限制判断是否适用，不得直接作为当前任务的最终结论。

## 执行流程

### 1. 理解当前任务

识别当前任务要解决的问题、目标、背景和限制，确定可能需要参考的经验方向。

### 2. 查找候选 Experience

先读取 `index.md`，根据标题、Space、类型、状态和标签查找可能相关的 Experience。

优先查找 `active` Experience，不因 Space 不同而直接排除，也不能只凭关键词相同判断相关。

### 3. 读取并判断

根据索引中的文件路径和 Experience ID 读取完整内容，并结合当前任务判断：

- 这条 Experience 是否真正相关
- 哪些内容可以借鉴
- 当前场景是否满足其适用条件
- 是否存在限制、冲突或已经变化的前提

只保留能够实际帮助当前任务的少量 Experience，避免返回大量关联较弱的内容。

### 4. 提供经验参考

将相关 Experience 自然融入当前分析，说明可以借鉴的内容以及需要注意的条件。

历史 Experience 不能直接替代当前判断。存在明显差异、限制或不确定性时，应明确指出。

## 输出结果

将相关 Experience 自然融入当前回答，只说明可以借鉴的内容和必要的适用条件，不重复完整正文。没有找到相关 Experience 时，直接说明未找到，并基于当前上下文继续处理。