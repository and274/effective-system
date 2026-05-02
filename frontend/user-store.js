(function () {
  const KEY_USERS = "app_users";
  const KEY_CURRENT_USER_ID = "app_current_user_id";
  const KEY_CURRENT_USER = "app_current_user";

  function safeParseArray(raw) {
    try {
      const data = JSON.parse(raw || "[]");
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  }

  function normalizeUser(u) {
    return {
      id: u.id || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      username: (u.username || u.name || "").trim(),
      email: (u.email || "").trim().toLowerCase(),
      password: u.password || "",
      avatar: u.avatar || "👤",
      role: u.role || "一线记者",
      createdAt: u.createdAt || new Date().toISOString(),
    };
  }

  function loadUsers() {
    const current = safeParseArray(localStorage.getItem(KEY_USERS));
    if (current.length) return current.map(normalizeUser);

    const legacyUsers = safeParseArray(localStorage.getItem("users"));
    const legacyFeUsers = safeParseArray(localStorage.getItem("fe_users"));
    const merged = [...legacyUsers, ...legacyFeUsers]
      .map(normalizeUser)
      .filter(
        (u, idx, arr) =>
          u.username &&
          u.email &&
          arr.findIndex((x) => x.email === u.email || x.username === u.username) === idx
      );
    if (merged.length) saveUsers(merged);
    return merged;
  }

  function saveUsers(users) {
    localStorage.setItem(KEY_USERS, JSON.stringify(users));
    localStorage.setItem("users", JSON.stringify(users));
    localStorage.setItem("fe_users", JSON.stringify(users));
  }

  function resolveApiBase() {
    const byStorage = (localStorage.getItem("API_BASE") || "").trim();
    const byGlobal = (window.__API_BASE__ || "").trim();
    const fallback =
      window.location.protocol === "file:" || window.location.port === "5500"
        ? "http://127.0.0.1:5500"
        : window.location.origin;
    return (byStorage || byGlobal || fallback).replace(/\/$/, "");
  }

  function shouldAllowLocalFallback() {
    if (window.location.protocol === "file:") return true;
    const host = window.location.hostname || "";
    return host === "127.0.0.1" || host === "localhost";
  }

  async function requestJson(path, options) {
    const resp = await fetch(`${resolveApiBase()}${path}`, options);
    let data = null;
    try {
      data = await resp.json();
    } catch {
      data = null;
    }
    if (!resp.ok) {
      const message = (data && data.message) || "请求失败";
      return { ok: false, message, status: resp.status };
    }
    return { ok: true, data };
  }

  async function findUserByAccount(account) {
    const result = await requestJson(`/auth/user-by-account?account=${encodeURIComponent(account || "")}`);
    if (result.ok) return result.data.user;
    if (result.status === 404) return null;
    if (!shouldAllowLocalFallback()) {
      return { __lookupError: true, message: result.message || "账号服务不可用" };
    }
    // 仅本地开发/离线演示回退到本地数据。
    const keyword = (account || "").trim().toLowerCase();
    return loadUsers().find(
      (u) => u.username.toLowerCase() === keyword || u.email.toLowerCase() === keyword
    );
  }

  async function findUserByEmail(email) {
    const result = await requestJson(`/auth/user-by-email?email=${encodeURIComponent(email || "")}`);
    if (result.ok) return result.data.user;
    if (result.status === 404) return null;
    if (!shouldAllowLocalFallback()) {
      return { __lookupError: true, message: result.message || "邮箱服务不可用" };
    }
    const key = (email || "").trim().toLowerCase();
    return loadUsers().find((u) => u.email.toLowerCase() === key);
  }

  async function createUser(input) {
    const result = await requestJson("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input || {}),
    });
    if (result.ok) {
      return { ok: true, user: result.data.user };
    }
    if (!shouldAllowLocalFallback()) {
      return { ok: false, message: result.message || "注册服务不可用" };
    }
    // 后端不可达时回退旧逻辑
    const users = loadUsers();
    const normalizedEmail = (input.email || "").trim().toLowerCase();
    const normalizedUsername = (input.username || "").trim();
    const emailDuplicate = users.find((u) => u.email === normalizedEmail);
    if (emailDuplicate) {
      return { ok: false, message: "该邮箱已绑定账号，一个邮箱仅能对应一个用户名/头像/密码" };
    }
    const usernameDuplicate = users.find((u) => u.username === normalizedUsername);
    if (usernameDuplicate) return { ok: false, message: "用户名已存在" };
    let passwordHash = input.password;
    if (input.password && !input.password.includes(":")) {
      const hashed = await PasswordHash.hashAndStore(input.password);
      passwordHash = hashed.storedValue;
    }
    const user = normalizeUser({
      username: normalizedUsername,
      email: normalizedEmail,
      password: passwordHash,
      avatar: input.avatar,
      role: input.role,
    });
    users.push(user);
    saveUsers(users);
    return { ok: true, user: sanitizeUserClient(user) };
  }

  function sanitizeUserClient(user) {
    const normalized = normalizeUser(user);
    delete normalized.password;
    return normalized;
  }

  async function verifyPassword(account, password) {
    const result = await requestJson("/auth/verify-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account, password }),
    });
    if (result.ok) {
      return { ok: true, user: result.data.user };
    }
    if (!shouldAllowLocalFallback()) {
      return { ok: false, message: result.message || "登录服务不可用" };
    }

    const found = loadUsers().find((u) => {
      const key = (account || "").trim().toLowerCase();
      return u.username.toLowerCase() === key || u.email.toLowerCase() === key;
    });
    if (!found) return { ok: false, message: "账号不存在" };
    if (!found.password || !found.password.includes(":")) {
      return password === found.password
        ? { ok: true, user: sanitizeUserClient(found) }
        : { ok: false, message: "账号或密码错误" };
    }
    const ok = await PasswordHash.verifyPassword(password, found.password);
    return ok ? { ok: true, user: sanitizeUserClient(found) } : { ok: false, message: "账号或密码错误" };
  }

  async function updateUserPasswordByEmail(email, newPassword) {
    const result = await requestJson("/auth/update-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password: newPassword }),
    });
    if (result.ok) return { ok: true, user: result.data.user };
    if (!shouldAllowLocalFallback()) return { ok: false, message: result.message || "密码服务不可用" };

    const users = loadUsers();
    const key = (email || "").trim().toLowerCase();
    const idx = users.findIndex((u) => u.email === key);
    if (idx < 0) return { ok: false, message: "该邮箱未注册账号" };
    const hashed = await PasswordHash.hashAndStore(newPassword);
    users[idx].password = hashed.storedValue;
    saveUsers(users);
    return { ok: true, user: sanitizeUserClient(users[idx]) };
  }

  function saveLoginSession(user) {
    localStorage.setItem(KEY_CURRENT_USER_ID, user.id);
    localStorage.setItem(KEY_CURRENT_USER, JSON.stringify(user));
    localStorage.setItem("user", JSON.stringify(user));
    localStorage.setItem("fe_current_user", JSON.stringify(user));
  }

  function getCurrentUser() {
    try {
      const cached = JSON.parse(localStorage.getItem(KEY_CURRENT_USER) || "null");
      if (cached && cached.id) return cached;
      return JSON.parse(localStorage.getItem("user") || "null");
    } catch {
      return null;
    }
  }

  function logout() {
    localStorage.removeItem(KEY_CURRENT_USER_ID);
    localStorage.removeItem(KEY_CURRENT_USER);
    localStorage.removeItem("user");
    localStorage.removeItem("fe_current_user");
  }

  window.AppUserStore = {
    KEY_USERS,
    KEY_CURRENT_USER_ID,
    loadUsers,
    saveUsers,
    findUserByAccount,
    findUserByEmail,
    createUser,
    updateUserPasswordByEmail,
    saveLoginSession,
    getCurrentUser,
    logout,
    verifyPassword,
  };
})();
