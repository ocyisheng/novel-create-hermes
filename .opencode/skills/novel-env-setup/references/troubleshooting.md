# 环境问题排查指南

## 快速诊断流程

```
用户报告环境问题
    ↓
运行: python scripts/setup.py --check
    ↓
根据输出状态判断问题类型
```

---

## 问题分类与解决方案

### 1. Python 未安装

**症状**：
```
❌ 未检测到 Python，请先安装 Python 3.8+
```

**解决方案**：
1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.8+ 安装包
3. 安装时**务必勾选** "Add Python to PATH"
4. 重新打开终端，运行 `python --version` 验证

---

### 2. Python 版本过低

**症状**：
```
❌ Python 版本 3.7.x 不满足要求（需要 >= 3.8）
```

**解决方案**：
1. 升级 Python 到 3.8+ 版本
2. 确认终端使用的是新版本：`python --version`

---

### 3. venv 模块缺失

**症状**：
```
❌ 虚拟环境创建失败: Error: [Errno 2] No such file or directory: 'venv'
```

**解决方案**：

**Ubuntu/Debian**：
```bash
sudo apt-get install python3-venv
```

**CentOS/RHEL**：
```bash
sudo yum install python3-venv
```

**Windows**：
- 重新安装 Python，确保勾选 "tcl/tk and IDLE" 和 "Python test suite"（venv 是标准库，通常自带）

---

### 4. 依赖安装失败（网络问题）

**症状**：
```
❌ 依赖安装失败: Could not fetch URL https://pypi.org/simple/pyyaml/
```

**解决方案**：

**使用国内镜像源**：
```bash
# 临时使用
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 永久配置
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

**常用镜像源**：
| 源 | URL |
|---|---|
| 清华 | https://pypi.tuna.tsinghua.edu.cn/simple |
| 阿里云 | https://mirrors.aliyun.com/pypi/simple |
| 腾讯云 | https://mirrors.cloud.tencent.com/pypi/simple |

---

### 5. 权限不足

**症状**：
```
❌ 异常: [Errno 13] Permission denied: 'C:\path\to\.venv'
```

**解决方案**：
1. 以管理员身份运行终端
2. 或更改项目目录权限：
   ```bash
   # Linux/macOS
    chmod -R u+w .opencode/skills/novel-env-setup/
   ```

---

### 6. .venv 目录损坏

**症状**：
- `.venv` 目录存在但脚本执行报错
- `setup.py` 检查失败

**解决方案**：
```bash
# 删除损坏环境
rm -rf {小说项目父目录}/.venv    # macOS/Linux
rmdir /s /q {小说项目父目录}\.venv  # Windows

# 重新初始化
python scripts/setup.py --force
```

---

### 7. PyYAML 安装成功但导入失败

**症状**：
```
✅ 依赖已安装
❌ PyYAML 未安装
```

**原因**：
- 使用了系统 Python 而非虚拟环境中的 Python
- 虚拟环境未正确激活

**解决方案**：
```bash
# 确保使用虚拟环境中的 python
# Windows
call {小说项目父目录}\.venv\Scripts\activate
python -c "import yaml; print(yaml.__version__)"

# macOS/Linux
source {小说项目父目录}/.venv/bin/activate
python -c "import yaml; print(yaml.__version__)"
```

---

## 离线安装指南

若目标机器无网络访问，可提前准备离线包：

```bash
# 在有网络的机器上下载
pip download -r requirements.txt -d ./offline_packages

# 在目标机器上离线安装
pip install --no-index --find-links=./offline_packages -r requirements.txt
```

---

## 环境验证清单

完成环境初始化后，运行以下命令验证：

```bash
# 1. 检查 Python 版本
python --version                    # 应 >= 3.8

# 2. 检查虚拟环境
ls {小说项目父目录}/.venv     # 目录应存在

# 3. 激活环境
# Windows
call {小说项目父目录}\.venv\Scripts\activate
# macOS/Linux
source {小说项目父目录}/.venv/bin/activate

# 4. 验证依赖
python -c "import yaml; print('PyYAML', yaml.__version__)"

# 5. 运行完整检查
python scripts/setup.py
```

全部通过 → 环境就绪 ✅
