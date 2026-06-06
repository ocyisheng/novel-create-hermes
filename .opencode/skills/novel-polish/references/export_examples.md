# 导出示例

本文件包含从 SKILL.md 移出的导出示例。

---

## 示例一：导出 EPUB 电子书

### 需求
```yaml
项目：星辰修仙路
格式：EPUB
平台：微信读书
```

### 步骤

1. **收集章节**
   ```
   扫描 chapters/ 目录
   确认 100 个章节
   ↓
   按序号排序
   ```

2. **格式化**
   ```
   标题格式：「第1章 入门」
   段落：首行缩进
   引号：「」
   ```

3. **元数据**
   ```
   书名：星辰修仙路
   作者：XXX
   简介：...
   分类：玄幻修仙
   标签：仙侠、修炼、升级
   ```

4. **目录**
   ```
   生成 toc.ncx
   包含章节目录
   ```

5. **生成 EPUB**
   ```
   输出：星辰修仙路.epub
   ```

### 输出
```
novels/星辰修仙路.epub
```

---

## 示例二：导出 PDF 打印版

### 需求
```yaml
项目：星辰修仙路
格式：PDF
版式：A5/双页
```

### 步骤

1-4：同上

5. **生成 PDF**
   ```
   页面布局设置
   页面大小：A5
   字体嵌入
   双页模式
   ↓
   输出：星辰修仙路.pdf
   ```

### 额外配置
```yaml
pdf:
  页面大小: A5
  版式: 双页
  字体: 思源宋体
  边距: 2cm
  行距: 1.5
```

---

## 示例三：导出 HTML 网页

### 需求
```yaml
项目：星辰修仙路
格式：HTML
```

### 步骤

1. **收集章节**
   - 扫描 chapters/

2. **格式化**
   - HTML 标签包裹
   - 样式表嵌入

3. **生成 HTML**
   ```
   单一页面：index.html
   分章页面：chapter_01.html
   样式：style.css
   ↓
   输出：星辰修仙路/
   ```

### 输出结构
```
星辰修仙路/
├── index.html
├── chapter_01.html
├── chapter_02.html
├── style.css
└── assets/
```

---

## 示例四：导出 TXT 纯文本

### 需求
```yaml
项目：星辰修仙路
格式：TXT
```

### 步骤

1. **收集章节**

2. **格式化**
   - 移除特殊格式
   - 纯文本输出

3. **生成 TXT**
   ```
   标题：《星辰修仙路》
   作者：XXX
   章节内容
   ↓
   输出：星辰修仙路.txt
   ```

---

## 示例五：导出 DOCX Word 文档

### 需求
```yaml
项目：星辰修仙路
格式：DOCX
```

### 步骤

1. **收集章节**

2. **格式化**
   - Word 格式
   - 样式设置

3. **生成 DOCX**
   ```
   标题样式：标题1
   正文样式：正文
   页眉：书名
   页脚：作者
   ↓
   输出：星辰修仙路.docx
   ```

---

## 导出命令速查

```bash
# 导出为 EPUB
python scripts/export.py --format epub --input "项目目录" --output "小说名.epub"

# 导出为 PDF
python scripts/export.py --format pdf --input "项目目录" --output "小说名.pdf"

# 导出为 HTML
python scripts/export.py --format html --input "项目目录" --output "小说名.html"

# 导出为 TXT
python scripts/export.py --format txt --input "项目目录" --output "小说名.txt"

# 导出为 DOCX
python scripts/export.py --format docx --input "项目目录" --output "小说名.docx"
```

---

## 输出格式速查

| 格式 | 用途 | 平台支持 |
|------|------|----------|
| EPUB | 电子书阅读器 | 微信读书/多看/Kindle |
| PDF | 打印/阅读 | 通用 |
| HTML | 网页发布 | Web |
| TXT | 纯文本 | 通用 |
| DOCX | 编辑排版 | Word |