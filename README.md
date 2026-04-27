# zhimedia-sandbox

完整可部署的智媒沙盘系统，包含 Flask 后端与 Node.js 前端。

## 目录结构
- ackend/ Flask 后端与 AI 逻辑
- rontend/ Node.js + Express 前端
- docs/ API 文档与部署配置

## 快速部署
### 后端
`ash
cd backend
cp .env.example .env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
gunicorn -k gevent -w 2 -b 0.0.0.0:5000 app:app
`

### 前端
`ash
cd frontend
cp .env.example .env
npm install
node server.js
`

### Nginx
参考 docs/nginx-front-back-integration.conf。
