# 项目：Tool-box utilities to handle personal files 

## Environment

1. 技术栈
   - Python 3.12+
   - 每个子项目有独立 venv，所有操作在各自子项目的 venv 下进行；永远要先激活 venv，再运行 Python

2. String 比较规则
   - 所有字符串比较强制全小写 + 去空格，确保忽略大小写差异和格式杂质

3. 数值精度
   - 所有计算结果四舍五入，保留两位小数
