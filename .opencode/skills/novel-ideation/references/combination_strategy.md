 约束组合策略

## 推荐组合模式

1. **基本组合**: 结构约束 + 内容约束 + 角色约束
2. **创新组合**: 元素融合 + 规则破坏 + 形式创新
3. **类型组合**: 针对特定类型的专用约束组合
4. **挑战组合**: 多个高难度约束的组合

## 组合生成规则

- 每次生成3-5个约束
- 至少有一个与用户指定类型相关
- 至少有一个带来创新或反转
- 约束之间要有内在逻辑联系
- 避免过多冲突导致无法执行

## 工具和脚本

本技能包含以下工具：

### 约束生成器
```
python constraint_generator.py --count 3 --type structure content
python constraint_generator.py --genre fantasy --count 4
python constraint_generator.py --list-types
python constraint_generator.py --list-genres
```