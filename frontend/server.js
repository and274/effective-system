const path = require("path");
const express = require("express");
const cors = require("cors");
const nodemailer = require("nodemailer");
require("dotenv").config();

const app = express();
const port = Number(process.env.PORT || 5500);
const smtpPort = Number(process.env.SMTP_PORT || 465);

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
app.use(express.static(path.resolve(__dirname)));

app.get("/health", (_req, res) => {
  res.json({ ok: true });
});

app.post("/api/send-code", async (req, res) => {
  const { toEmail, code, scene } = req.body || {};
  if (!toEmail || !code) {
    return res.status(400).json({ ok: false, message: "Missing toEmail or code" });
  }

  try {
    await transporter.sendMail({
      from: process.env.SMTP_FROM || process.env.SMTP_USER,
      to: toEmail,
      subject: "智媒沙盘验证码",
      text: `您的验证码是：${code}（场景：${scene || "login"}）。5分钟内有效。`,
      html: `<div style="font-family:Arial,sans-serif;">
        <h3>智媒沙盘验证码</h3>
        <p>您的验证码是：<b style="font-size:24px;letter-spacing:2px;">${code}</b></p>
        <p>场景：${scene || "login"}</p>
        <p>5分钟内有效，请勿泄露给他人。</p>
      </div>`,
    });
    return res.json({ ok: true });
  } catch (error) {
    return res.status(500).json({
      ok: false,
      message: "Failed to send email",
      error: String(error && error.message ? error.message : error),
    });
  }
});

app.listen(port, () => {
  console.log(`Server running at http://127.0.0.1:${port}`);
});
