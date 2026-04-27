(function () {
  const KEY_USERS = "app_users";
  const KEY_CURRENT_USER_ID = "app_current_user_id";

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

  function findUserByAccount(account) {
    const keyword = (account || "").trim().toLowerCase();
    return loadUsers().find(
      (u) => u.username.toLowerCase() === keyword || u.email.toLowerCase() === keyword
    );
  }

  function findUserByEmail(email) {
    const key = (email || "").trim().toLowerCase();
    return loadUsers().find((u) => u.email.toLowerCase() === key);
  }

  // 创建用户（异步，使用密码哈希）
  async function createUser(input) {
    const users = loadUsers();
    const normalizedEmail = (input.email || "").trim().toLowerCase();
    const normalizedUsername = (input.username || "").trim();
    const emailDuplicate = users.find((u) => u.email === normalizedEmail);
    if (emailDuplicate) {
      return { ok: false, message: "该邮箱已绑定账号，一个邮箱仅能对应一个用户名/头像/密码" };
    }
    const usernameDuplicate = users.find((u) => u.username === normalizedUsername);
    if (usernameDuplicate) return { ok: false, message: "用户名已存在" };

    // 哈希密码
    let passwordHash = input.password;
    if (input.password && !input.password.includes(':')) {
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
    return { ok: true, user };
  }

  // 验证密码（异步）
  async function verifyPassword(password, storedPassword) {
    // 如果是旧格式（未哈希），直接比较
    if (!storedPassword || !storedPassword.includes(':')) {
      return password === storedPassword;
    }
    // 新格式：使用 PBKDF2 验证
    return await PasswordHash.verifyPassword(password, storedPassword);
  }

  // 更新密码（异步）
  async function updateUserPasswordByEmail(email, newPassword) {
    const users = loadUsers();
    const key = (email || "").trim().toLowerCase();
    const idx = users.findIndex((u) => u.email === key);
    if (idx < 0) return { ok: false, message: "该邮箱未注册账号" };

    // 哈希新密码
    const hashed = await PasswordHash.hashAndStore(newPassword);
    users[idx].password = hashed.storedValue;
    saveUsers(users);
    return { ok: true, user: users[idx] };
  }

  // 升级旧密码（如果有的话）
  async function upgradePasswordIfNeeded(user, password) {
    if (!user.password || user.password.includes(':')) {
      return user.password;
    }
    // 旧密码，升级到新格式
    const hashed = await PasswordHash.hashAndStore(password);
    const users = loadUsers();
    const idx = users.findIndex(u => u.id === user.id);
    if (idx >= 0) {
      users[idx].password = hashed.storedValue;
      saveUsers(users);
    }
    return hashed.storedValue;
  }

  function saveLoginSession(user) {
    localStorage.setItem(KEY_CURRENT_USER_ID, user.id);
    localStorage.setItem("user", JSON.stringify(user));
    localStorage.setItem("fe_current_user", JSON.stringify(user));
  }

  function getCurrentUser() {
    const users = loadUsers();
    const uid = localStorage.getItem(KEY_CURRENT_USER_ID);
    if (uid) {
      const matched = users.find((u) => u.id === uid);
      if (matched) return matched;
    }
    try {
      return JSON.parse(localStorage.getItem("user") || "null");
    } catch {
      return null;
    }
  }

  function logout() {
    localStorage.removeItem(KEY_CURRENT_USER_ID);
    localStorage.removeItem("user");
    localStorage.removeItem("fe_current_user");
  }

  // 同步版本（保持向后兼容，用于加载等操作）
  window.AppUserStore = {
    KEY_USERS,
    KEY_CURRENT_USER_ID,
    loadUsers,
    saveUsers,
    findUserByAccount,
    findUserByEmail,
    createUser,           // 现在是异步的
    updateUserPasswordByEmail,  // 现在是异步的
    saveLoginSession,
    getCurrentUser,
    logout,
    // 新增
    verifyPassword,       // 异步
    upgradePasswordIfNeeded,  // 异步
  };
})();
