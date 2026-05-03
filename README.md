# zhimedia-sandbox

完整可部署的智媒沙盘系统，包含 Flask 后端与 Node.js 前端。

## 目录结构

- `backend/` Flask 后端与 AI 逻辑
- `frontend/` Node.js + Express 前端
- `docs/` API 文档与部署配置

## 快速部署

### 后端

```bash
cd backend
cp .env.example .env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
gunicorn -k gevent -w 2 -b 0.0.0.0:5000 app:app
```

### 前端

```bash
cd frontend
cp .env.example .env
npm install
node server.js
```

### Nginx

参考 `docs/nginx-front-back-integration.conf`。

### 服务器 `deploy.sh`（仓库根目录）

- 路径示例：`/var/www/zhimedia-sandbox/deploy.sh`；首次在服务器可执行：`chmod +x deploy.sh`。
- 脚本会：`git pull`、`npm install`、`pip install`，并对 PM2：**若进程不存在则 `start`，存在则 `restart`**（避免空列表时 `restart` 报 not found）。
- 前端默认端口 **`PORT=3000`**（可在运行前 `export PORT=...` 覆盖）。

---

## 代码与「环境 / 本地数据」如何对齐云端

| 内容 | 同步方式 | 说明 |
|------|----------|------|
| 已提交到 Git 的代码与文档 | `git push` + 服务器 `deploy.sh` | `.env`、`frontend/data/` **不会**进仓库 |
| `frontend/.env`、`backend/.env` | 见下方「全量 SSH 同步」 | 含 SMTP、LLM 密钥等，仅拷到服务器 |
| `frontend/data/`（注册用户等） | 同上 | 按需上传；与本地一致则覆盖服务器同路径文件 |

**为什么不能用 Git「上传全部」：** 把 `.env` 和用户数据提交到 GitHub 会泄露密钥与隐私，因此仓库用 `.gitignore` 排除它们；云端仍需要这些文件时，请用 SSH 拷贝。

### 全量 SSH 同步（本机 → 云）

1. 复制配置模板并填写（`scripts/sync.env` 已被忽略，不会进 Git）：

   ```bash
   cp scripts/sync.env.example scripts/sync.env
   # 编辑 scripts/sync.env：主机、SSH 用户、远端项目根路径
   ```

2. 确保本机已能 **免密** `ssh 用户@主机`。

3. **Windows（PowerShell）**，在仓库根目录执行：

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/full-sync-to-server.ps1
   ```

4. **Linux / macOS**：

   ```bash
   chmod +x scripts/full-sync-to-server.sh
   ./scripts/full-sync-to-server.sh
   ```

5. 上传完成后在服务器加载新环境变量（若改了 `.env`）：

   ```bash
   pm2 restart zhimedia-frontend --update-env
   pm2 restart zhimedia-backend --update-env
   pm2 save
   ```

**推荐完整流程：** 先 `git push` 并在服务器跑 `deploy.sh` 更新代码，再按需运行上述脚本同步 `.env` 与 `data/`。
