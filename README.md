# PyCon China 2026 Schedule

PyCon China 2026 的中英双语议程站点。页面内容由 YAML 数据自动生成，并通过
GitHub Actions 发布到 GitHub Pages。

## 修改议程

1. 编辑 [`data/agenda.yaml`](data/agenda.yaml)。
2. 提交 Pull Request。
3. PR 中的 `Build and deploy agenda` 检查会验证：
   - 议题 ID 唯一，必填信息及中英文标题完整。
   - 每项议程的起止时间与分享、QA 时长一致。
   - 签到、午餐、茶歇和议题均位于会议时间范围内。
   - 上午、下午、标准演讲和闪电演讲的会场及时段有效。
   - 同一会场没有时间冲突，分会场议题不与茶歇冲突。
4. PR 合并到 `main` 后，GitHub Pages 自动更新。

会议名称、日期、地点、签到、午餐和茶歇等全局信息位于
`agenda.yaml` 的 `conference`；分会场信息位于 `tracks`；议题位于 `talks`。

## 本地预览

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build.py
python -m http.server 8000 --directory site
```

浏览器打开 <http://localhost:8000>。

## 文件结构

```text
data/agenda.yaml       会议与议题数据，日常修改入口
templates/index.html.j2
assets/style.css
scripts/build.py       数据校验与静态页面生成
site/                  构建后的 GitHub Pages 内容
```
