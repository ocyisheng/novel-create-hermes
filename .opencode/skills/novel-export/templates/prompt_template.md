## TASK

导出项目 {项目名} 为 {导出格式}。

## CONTEXT

项目路径: {项目路径}
导出格式: {导出格式}
作者名: {作者名}

## EXECUTION

调用导出脚本完成，**不要自行用 AI 生成文件内容**：

```bash
python .opencode/shared/export.py \
    --project-root "{项目路径}" \
    --format {导出格式} \
    --author "{作者名}"
```

脚本自动完成章节收集、格式化、写入 `output/` 目录。确认脚本执行成功（exit code 0）后报告输出路径。

## HARD CONSTRAINTS

1. MUST call export.py — do NOT generate export files via AI
2. 检查脚本 exit code，失败则报告错误
3. 不修改任何章节正文文件
