const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const express = require("express");
const cors = require("cors");
const nodemailer = require("nodemailer");
require("dotenv").config();

const app = express();
const port = Number(process.env.PORT || 5500);
const smtpPort = Number(process.env.SMTP_PORT || 465);
const CODE_EXPIRE_MS = 5 * 60 * 1000;
const codeStore = new Map();
const USERS_FILE = path.resolve(__dirname, "data", "users.json");

if (!process.env.SMTP_USER || !process.env.SMTP_PASS) {
  console.warn("Missing SMTP_USER or SMTP_PASS in .env");
}

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST || "smtp.qq.com",
  port: smtpPort,
  secure: smtpPort === 465,
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS,
  },
});

app.use(cors());
app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({ ok: true });
});

function makeCodeKey(email, scene) {
  return `${String(scene || "login").trim().toLowerCase()}::${String(email || "").trim().toLowerCase()}`;
}

function createCode() {
  return String(Math.floor(100000 + Math.random() * 900000));
}

function setVerificationCode(email, scene, code) {
  const key = makeCodeKey(email, scene);
  codeStore.set(key, {
    code: String(code),
    expireAt: Date.now() + CODE_EXPIRE_MS,
  });
}

function verifyCode(email, scene, code) {
  const key = makeCodeKey(email, scene);
  const saved = codeStore.get(key);
  if (!saved) {
    return { ok: false, message: "请先发送验证码", reason: "missing_code" };
  }
  if (Date.now() > saved.expireAt) {
    codeStore.delete(key);
    return { ok: false, message: "验证码已过期，请重新发送", reason: "expired" };
  }
  if (saved.code !== String(code || "").trim()) {
    return { ok: false, message: "验证码错误", reason: "invalid_code" };
  }
  codeStore.delete(key);
  return { ok: true };
}

function ensureUsersFile() {
  const dir = path.dirname(USERS_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(USERS_FILE)) fs.writeFileSync(USERS_FILE, "[]", "utf8");
}

function loadUsers() {
  ensureUsersFile();
  try {
    const parsed = JSON.parse(fs.readFileSync(USERS_FILE, "utf8") || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveUsers(users) {
  ensureUsersFile();
  fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2), "utf8");
}

function makeUserId() {
  return `user_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString("hex");
  const hash = crypto.pbkdf2Sync(String(password), salt, 100000, 32, "sha256").toString("hex");
  return `${salt}:${hash}`;
}

function verifyPassword(password, stored) {
  if (!stored || !stored.includes(":")) return String(password) === String(stored || "");
  const [salt, expected] = stored.split(":");
  const actual = crypto.pbkdf2Sync(String(password), salt, 100000, 32, "sha256").toString("hex");
  return actual === expected;
}

function sanitizeUser(user) {
  return {
    id: user.id,
    username: user.username,
    email: user.email,
    avatar: user.avatar || "👤",
    role: user.role || "一线记者",
    createdAt: user.createdAt,
  };
}

function findUserByEmail(users, email) {
  const key = String(email || "").trim().toLowerCase();
  return users.find((u) => String(u.email || "").toLowerCase() === key);
}

function findUserByAccount(users, account) {
  const key = String(account || "").trim().toLowerCase();
  return users.find((u) => String(u.email || "").toLowerCase() === key || String(u.username || "").toLowerCase() === key);
}

async function handleSendCode(req, res) {
  const { toEmail, code: requestedCode, scene } = req.body || {};
  if (!toEmail) {
    return res.status(400).json({ ok: false, message: "Missing toEmail" });
  }
  const code = String(requestedCode || createCode());
  const currentScene = String(scene || "login");

  try {
    await transporter.sendMail({
      from: process.env.SMTP_FROM || process.env.SMTP_USER,
      to: toEmail,
      subject: "智媒沙盘验证码",
      text: `您的验证码是：${code}（场景：${currentScene}）。5分钟内有效。`,
      html: `<div style="font-family:Arial,sans-serif;">
        <h3>智媒沙盘验证码</h3>
        <p>您的验证码是：<b style="font-size:24px;letter-spacing:2px;">${code}</b></p>
        <p>场景：${currentScene}</p>
        <p>5分钟内有效，请勿泄露给他人。</p>
      </div>`,
    });
    setVerificationCode(toEmail, currentScene, code);
    return res.json({ ok: true });
  } catch (error) {
    return res.status(500).json({
      ok: false,
      message: "Failed to send email",
      error: String(error && error.message ? error.message : error),
    });
  }
}

function handleVerifyCode(req, res) {
  const { email, scene, code } = req.body || {};
  if (!email || !code) {
    return res.status(400).json({ ok: false, message: "Missing email or code" });
  }
  const result = verifyCode(email, scene || "login", code);
  if (!result.ok) {
    return res.status(400).json(result);
  }
  return res.json({ ok: true });
}

app.post(["/api/send-code", "/mail-api/send-code"], handleSendCode);
app.post(["/api/verify-code", "/mail-api/verify-code"], handleVerifyCode);

app.get("/auth/user-by-email", (req, res) => {
  const email = String(req.query.email || "");
  if (!email) return res.status(400).json({ ok: false, message: "Missing email" });
  const user = findUserByEmail(loadUsers(), email);
  if (!user) return res.status(404).json({ ok: false, message: "用户不存在" });
  return res.json({ ok: true, user: sanitizeUser(user) });
});

app.get("/auth/user-by-account", (req, res) => {
  const account = String(req.query.account || "");
  if (!account) return res.status(400).json({ ok: false, message: "Missing account" });
  const user = findUserByAccount(loadUsers(), account);
  if (!user) return res.status(404).json({ ok: false, message: "用户不存在" });
  return res.json({ ok: true, user: sanitizeUser(user) });
});

app.post("/auth/register", (req, res) => {
  const { username, email, password, avatar, role } = req.body || {};
  const name = String(username || "").trim();
  const userEmail = String(email || "").trim().toLowerCase();
  const rawPassword = String(password || "");
  if (!name || !userEmail || !rawPassword) {
    return res.status(400).json({ ok: false, message: "Missing username/email/password" });
  }

  const users = loadUsers();
  if (findUserByEmail(users, userEmail)) {
    return res.status(409).json({ ok: false, message: "该邮箱已绑定账号，一个邮箱仅能对应一个用户名/头像/密码" });
  }
  if (users.some((u) => String(u.username || "") === name)) {
    return res.status(409).json({ ok: false, message: "用户名已存在" });
  }

  const user = {
    id: makeUserId(),
    username: name,
    email: userEmail,
    password: hashPassword(rawPassword),
    avatar: avatar || "👤",
    role: role || "一线记者",
    createdAt: new Date().toISOString(),
  };
  users.push(user);
  saveUsers(users);
  return res.json({ ok: true, user: sanitizeUser(user) });
});

app.post("/auth/verify-password", (req, res) => {
  const { account, password } = req.body || {};
  if (!account || !password) {
    return res.status(400).json({ ok: false, message: "Missing account or password" });
  }
  const users = loadUsers();
  const user = findUserByAccount(users, account);
  if (!user) return res.status(404).json({ ok: false, message: "账号不存在" });
  if (!verifyPassword(password, user.password)) {
    return res.status(401).json({ ok: false, message: "账号或密码错误" });
  }
  return res.json({ ok: true, user: sanitizeUser(user) });
});

app.post("/auth/update-password", (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) {
    return res.status(400).json({ ok: false, message: "Missing email or password" });
  }
  const users = loadUsers();
  const idx = users.findIndex((u) => String(u.email || "").toLowerCase() === String(email).trim().toLowerCase());
  if (idx < 0) return res.status(404).json({ ok: false, message: "该邮箱未注册账号" });
  users[idx].password = hashPassword(password);
  saveUsers(users);
  return res.json({ ok: true, user: sanitizeUser(users[idx]) });
});

// Serve static files after API routes so POST /mail-api/* is never shadowed.
app.use(express.static(path.resolve(__dirname)));

app.listen(port, () => {
  console.log(`Server running at http://127.0.0.1:${port}`);
});
