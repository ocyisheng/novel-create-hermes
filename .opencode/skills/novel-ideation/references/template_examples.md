# 使用示例

## 示例1：玄幻修仙故事框架生成

```
输入:
  创意概念: "主角获得系统，在末法时代修炼逆袭"
  类型: 玄幻修仙
  篇幅: 长篇 (60万字)
  风格: 正剧

输出:
  推荐结构: 英雄之旅 + 修炼里程碑体系
  模板文件: references/genre_fantasy.md
  关键节点: 筑基(30章)→金丹(60章)→元婴(90章)→化神(150章)
```

## 示例2：悬疑推理故事框架生成

```
输入:
  创意概念: "侦探调查神秘连环杀人案，真凶是身边人"
  类型: 悬疑推理
  篇幅: 中篇 (20万字)
  风格: 心理惊悚

输出:
  推荐结构: 悬疑结构 + 线索分布图
  模板文件: references/genre_mystery.md
  关键节点: 案件(1-10章)→调查(11-60章)→突破(61-120章)→揭露(121-150章)
```

## 进阶用法

### 结构融合
可以将多个结构融合使用，创造独特的故事框架：
```bash
# 英雄之旅 + 悬疑结构融合
/novel-ideation-template-generator --structure hero-journey+mystery --type fantasy

# 五幕结构 + 成长结构组合
/novel-ideation-template-generator --structure five-act+growth --type urban
```

### 节奏定制
根据不同需求调整故事节奏：
```bash
# 快节奏模式 - 适合网络连载
/novel-ideation-template-generator --pace fast

# 慢节奏模式 - 适合深度文学
/novel-ideation-template-generator --pace slow

# 章节密度控制
/novel-ideation-template-generator --chapter-length 3000
```

### 批量生成
```bash
# 生成3个不同结构的变体
/novel-ideation-template-generator --variants 3 --type fantasy

# 比较不同结构的效果
/novel-ideation-template-generator --compare-structures
```