const state = {
  projects: [],
  current: null,
  page: "overview",
  scheduleStrategy: "sequential",
  map: null,
  markers: {},
  comparisons: [],
  marketReport: null,
  marketSearchResults: [],
  // Authentication & Supabase state
  currentUser: null,
  token: localStorage.getItem("script_analyser_token") || "",
  supabase: null,
  authMode: "signin",
};

const $ = (id) => document.getElementById(id);

const pageInfo = {
  overview: ["PROJECT OVERVIEW", "Bring your story <em>into focus.</em>", "Turn a screenplay into a practical production plan, with transparent cost estimates and current market signals."],
  production: ["PRODUCTION BREAKDOWN", "Everything the story <em>calls for.</em>", "Production requirements inferred from your screenplay. Review these suggestions before production."],
  schedule: ["SHOOTING SCHEDULE", "Plan every scene, <em>day by day.</em>", "A structured production shooting plan consuming validated scene headings and configurable day assumptions."],
  characters: ["CHARACTER PROFILES", "Meet the people <em>driving the story.</em>", "Evidence-grounded character dossiers with extracted descriptions, traits, motivations, relationships, and story arcs."],
  locations: ["LOCATION BREAKDOWN & GIS", "Map the world <em>of your film.</em>", "Normalized scene locations with sub-location tracking, real-world OpenStreetMap resolution, and verified filming coordinates."],
  budget: ["COST ESTIMATION", "Know what it takes <em>to make it.</em>", "An adjustable planning estimate. Replace default assumptions with local vendor quotations."],
  market: ["COMPARATIVE MARKET ANALYSIS", "Find the audience <em>for your story.</em>", "Benchmark your screenplay against comparable films using OMDb metadata, audience ratings, reported box-office, and market intelligence."],
};

function money(n) {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return "Unavailable";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(n));
}

function number(n) {
  return new Intl.NumberFormat("en-IN").format(Number(n || 0));
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function showToast(message, error = false) {
  const el = $("toast");
  el.textContent = message;
  el.style.background = error ? "#873f32" : "#222a25";
  el.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.classList.remove("show"), 3800);
}

function getAuthToken() {
  return state.token || localStorage.getItem("script_analyser_token") || "";
}

function setAuthSession(token, user) {
  state.token = token || "";
  state.currentUser = user || null;
  if (token) {
    localStorage.setItem("script_analyser_token", token);
  } else {
    localStorage.removeItem("script_analyser_token");
  }
  updateUserUI();
}

function updateUserUI() {
  const user = state.currentUser;
  if (user) {
    const displayName = user.name || (user.email ? user.email.split("@")[0] : "User");
    const email = user.email || "authenticated";
    const initials = displayName.split(" ").filter(Boolean).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "U";

    if ($("userName")) $("userName").textContent = displayName;
    if ($("userEmail")) $("userEmail").textContent = email;
    if ($("userAvatar")) $("userAvatar").textContent = initials;
    if ($("authorFooter")) $("authorFooter").textContent = displayName;
    if ($("topUserStatus")) $("topUserStatus").textContent = email;
    if ($("topUserBadge")) $("topUserBadge").style.display = "inline-flex";
  } else {
    if ($("userName")) $("userName").textContent = "Not signed in";
    if ($("userEmail")) $("userEmail").textContent = "Sign in to continue";
    if ($("userAvatar")) $("userAvatar").textContent = "–";
    if ($("topUserStatus")) $("topUserStatus").textContent = "Not signed in";
  }
}

function showAuthModal(errorMsg = "", successMsg = "") {
  const modal = $("authModal");
  if (!modal) return;
  modal.classList.remove("hidden");

  const alertEl = $("authAlert");
  const successEl = $("authSuccess");
  if (alertEl) {
    if (errorMsg) {
      alertEl.textContent = errorMsg;
      alertEl.classList.add("show");
    } else {
      alertEl.classList.remove("show");
    }
  }
  if (successEl) {
    if (successMsg) {
      successEl.textContent = successMsg;
      successEl.classList.add("show");
    } else {
      successEl.classList.remove("show");
    }
  }
}

function hideAuthModal() {
  const modal = $("authModal");
  if (modal) modal.classList.add("hidden");
  const alertEl = $("authAlert");
  if (alertEl) alertEl.classList.remove("show");
  const successEl = $("authSuccess");
  if (successEl) successEl.classList.remove("show");
}

function setAuthMode(mode) {
  state.authMode = mode;
  const isSignUp = mode === "signup";

  const tabIn = $("tabSignIn");
  const tabUp = $("tabSignUp");
  if (tabIn && tabUp) {
    tabIn.classList.toggle("active", !isSignUp);
    tabIn.setAttribute("aria-selected", !isSignUp);
    tabUp.classList.toggle("active", isSignUp);
    tabUp.setAttribute("aria-selected", isSignUp);
  }

  const fnGroup = $("fullNameGroup");
  if (fnGroup) fnGroup.classList.toggle("hidden", !isSignUp);

  const submitText = $("authSubmitText");
  if (submitText) submitText.textContent = isSignUp ? "Create Account" : "Sign In";

  const alertEl = $("authAlert");
  if (alertEl) alertEl.classList.remove("show");
  const successEl = $("authSuccess");
  if (successEl) successEl.classList.remove("show");
}

function togglePasswordVisibility() {
  const pwdInput = $("authPassword");
  const toggleBtn = $("togglePasswordBtn");
  if (!pwdInput) return;
  if (pwdInput.type === "password") {
    pwdInput.type = "text";
    if (toggleBtn) toggleBtn.textContent = "🙈";
  } else {
    pwdInput.type = "password";
    if (toggleBtn) toggleBtn.textContent = "👁";
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const email = ($("authEmail")?.value || "").trim();
  const password = $("authPassword")?.value || "";
  const fullName = ($("authFullName")?.value || "").trim();

  if (!email || !password) {
    showAuthModal("Please enter your email and password.");
    return;
  }

  if (state.authMode === "signup" && password.length < 6) {
    showAuthModal("Password must be at least 6 characters long.");
    return;
  }

  const spinner = $("authSpinner");
  const submitBtn = $("authSubmitBtn");
  if (spinner) spinner.classList.remove("hidden");
  if (submitBtn) submitBtn.disabled = true;

  try {
    let result = null;

    if (state.supabase && state.authMode === "signin") {
      const { data, error } = await state.supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      result = {
        access_token: data.session.access_token,
        user: {
          id: data.user.id,
          email: data.user.email,
          name: data.user.user_metadata?.full_name || email.split("@")[0]
        }
      };
    } else if (state.supabase && state.authMode === "signup") {
      const { data, error } = await state.supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: fullName } }
      });
      if (error) throw error;
      result = {
        access_token: data.session?.access_token,
        user: {
          id: data.user.id,
          email: data.user.email,
          name: fullName || email.split("@")[0]
        }
      };
    } else {
      const endpoint = state.authMode === "signup" ? "/api/auth/register" : "/api/auth/login";
      const payload = { email, password };
      if (state.authMode === "signup") payload.full_name = fullName;

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({ detail: "Network authentication failed" }));
      if (!res.ok) throw new Error(data.detail || "Authentication failed");
      result = data;
    }

    if (result && result.access_token) {
      setAuthSession(result.access_token, result.user);
      hideAuthModal();
      showToast(state.authMode === "signup" ? "Account created successfully!" : "Signed in successfully!");
      await loadProjects();
    } else {
      showAuthModal("", "Account created. Please check your email or sign in.");
    }
  } catch (err) {
    showAuthModal(err.message || "Authentication failed. Please verify credentials.");
  } finally {
    if (spinner) spinner.classList.add("hidden");
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function handleDemoAccess() {
  const spinner = $("authSpinner");
  const demoBtn = $("demoAccessBtn");
  if (spinner) spinner.classList.remove("hidden");
  if (demoBtn) demoBtn.disabled = true;

  try {
    const res = await fetch("/api/auth/demo-login", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Demo access failed");

    setAuthSession(data.access_token, data.user);
    hideAuthModal();
    showToast("Faculty demonstration session active!");
    await loadProjects();
  } catch (err) {
    showAuthModal("Demo login error: " + err.message);
  } finally {
    if (spinner) spinner.classList.add("hidden");
    if (demoBtn) demoBtn.disabled = false;
  }
}

async function handleLogout() {
  try {
    if (state.supabase) {
      await state.supabase.auth.signOut().catch(() => {});
    }
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
  } finally {
    setAuthSession("", null);
    state.current = null;
    state.projects = [];
    state.comparisons = [];
    state.marketReport = null;
    renderRecent();
    navigate("overview");
    $("emptyState").classList.remove("hidden");
    $("dashboard").classList.add("hidden");
    showAuthModal("You have been signed out.");
    showToast("Signed out successfully.");
  }
}

async function api(url, options = {}) {
  const token = getAuthToken();
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    showAuthModal("Session expired or authentication required. Please sign in.");
    throw new Error("Authentication required");
  }
  const data = await response.json().catch(() => ({ detail: "Unexpected server response" }));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function currentAnalysis() {
  return state.current?.analysis || {};
}

// ============================================================
// INITIALIZATION
// ============================================================

function init() {
  // Authentication event handlers
  if ($("tabSignIn")) $("tabSignIn").onclick = () => setAuthMode("signin");
  if ($("tabSignUp")) $("tabSignUp").onclick = () => setAuthMode("signup");
  if ($("togglePasswordBtn")) $("togglePasswordBtn").onclick = togglePasswordVisibility;
  if ($("authForm")) $("authForm").onsubmit = handleAuthSubmit;
  if ($("demoAccessBtn")) $("demoAccessBtn").onclick = handleDemoAccess;
  if ($("logoutBtn")) $("logoutBtn").onclick = handleLogout;

  $("newProjectBtn").onclick = openModal;
  $("emptyNewBtn").onclick = openModal;
  $("closeModalBtn").onclick = closeModal;
  $("cancelModalBtn").onclick = closeModal;

  // Location modal handlers
  $("closeLocationModalBtn").onclick = closeLocationModal;
  $("cancelLocationModalBtn").onclick = closeLocationModal;
  $("locationModalForm").onsubmit = submitManualLocation;

  // Schedule modal handlers
  $("closeScheduleModalBtn").onclick = closeScheduleModal;
  $("cancelScheduleModalBtn").onclick = closeScheduleModal;
  $("scheduleModalForm").onsubmit = submitScheduleUpdate;

  $("projectForm").addEventListener("submit", createProject);
  $("mainNav").addEventListener("click", (e) => {
    const b = e.target.closest("[data-page]");
    if (b) navigate(b.dataset.page);
  });

  $("reanalyzeBtn").onclick = reanalyse;
  $("deleteProjectBtn").onclick = deleteProject;
  $("exportBtn").onclick = exportReport;

  document.addEventListener("submit", (e) => {
    if (e.target.id === "marketSearchForm") {
      e.preventDefault();
      const q = String(new FormData(e.target).get("query") || "").trim();
      if (!q) {
        showToast("Enter a movie title to search OMDb.", true);
        return;
      }
      searchMarket(q);
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target.id === "geocodeBtn") resolveLocations();
    if (e.target.id === "editBudgetBtn") openBudgetEditor();
    if (e.target.id === "editScheduleBtn") openScheduleModal();
    if (e.target.id === "findCompsBtn") findComparableFilms();
    if (e.target.id === "generateReportBtn") generateMarketReport();
    if (e.target.id === "seqScheduleBtn") setScheduleStrategy("sequential");
    if (e.target.id === "locScheduleBtn") setScheduleStrategy("by_location");

    // Location Focus button
    const focusBtn = e.target.closest("[data-focus-loc]");
    if (focusBtn) {
      focusLocationOnMap(focusBtn.dataset.focusLoc);
    }

    // Location Manual Edit button
    const editLocBtn = e.target.closest("[data-edit-loc]");
    if (editLocBtn) {
      openLocationModal(editLocBtn.dataset.editLoc);
    }

    // Add film to comparisons
    const addCompBtn = e.target.closest("[data-add-comp]");
    if (addCompBtn) {
      addMovieToComparison(addCompBtn.dataset.addComp);
    }

    // Remove film from comparisons
    const removeCompBtn = e.target.closest("[data-remove-comp]");
    if (removeCompBtn) {
      removeMovieFromComparison(removeCompBtn.dataset.removeComp);
    }
  });

  checkAuthAndInit();
}

async function checkAuthAndInit() {
  try {
    const cfg = await fetch("/api/config").then(r => r.json()).catch(() => ({}));
    if (cfg.author && $("authorSidebar")) $("authorSidebar").textContent = cfg.author;
    if (cfg.author && $("authorFooter")) $("authorFooter").textContent = cfg.author;

    // Supabase client initialization if configured
    if (cfg.supabase_configured && window.supabase) {
      try {
        state.supabase = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
        state.supabase.auth.onAuthStateChange((event, session) => {
          if (session?.access_token) {
            setAuthSession(session.access_token, {
              id: session.user.id,
              email: session.user.email,
              name: session.user.user_metadata?.full_name || session.user.email.split("@")[0]
            });
          }
        });
      } catch (e) {
        console.warn("Supabase init notice:", e);
      }
    }

    const token = getAuthToken();
    if (token) {
      const meRes = await fetch("/api/auth/me", {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (meRes.ok) {
        const meData = await meRes.json();
        setAuthSession(token, meData.user);
        hideAuthModal();
        await loadProjects();
        return;
      }
    }

    showAuthModal();
  } catch (e) {
    showAuthModal();
  }
}

async function loadProjects() {
  try {
    state.projects = await api("/api/projects");
    renderRecent();
    if (state.projects.length) {
      const keep = state.current?.id;
      const p = state.projects.find((x) => x.id === keep) || state.projects[0];
      await selectProject(p.id);
    } else {
      state.current = null;
      showEmpty();
    }
  } catch (e) {
    showToast("Could not load projects: " + e.message, true);
  }
}

function renderRecent() {
  $("projectCount").textContent = state.projects.length;
  $("recentProjects").innerHTML = state.projects.length
    ? state.projects
        .map(
          (p) => `
      <button class="recent-project ${state.current?.id === p.id ? "active" : ""}" data-id="${p.id}" title="${escapeHtml(p.title)}">
        <span class="project-swatch">${escapeHtml(p.title.slice(0, 1).toUpperCase())}</span>
        <span>${escapeHtml(p.title)}</span>
      </button>`
        )
        .join("")
    : '<p class="muted small">No projects yet</p>';

  $("recentProjects").querySelectorAll("[data-id]").forEach((b) => {
    b.onclick = () => selectProject(Number(b.dataset.id));
  });
}

function showEmpty() {
  $("emptyState").classList.remove("hidden");
  $("dashboard").classList.add("hidden");
  $("currentProjectName").textContent = "No project selected";
}

function openModal() {
  $("projectModal").classList.remove("hidden");
}
function closeModal() {
  $("projectModal").classList.add("hidden");
}

async function createProject(event) {
  event.preventDefault();
  const form = $("projectForm");
  const fd = new FormData(form);
  const title = String(fd.get("title") || "").trim();
  const author = String(fd.get("author") || "").trim();
  const scriptText = String(fd.get("script_text") || "").trim();
  const file = fd.get("file");

  const settings = {};
  [
    "cast_per_day",
    "crew_per_day",
    "equipment_per_day",
    "location_per_day",
    "food_transport_per_day",
    "postproduction_per_page",
    "minutes_per_scene",
    "shooting_hours_per_day",
  ].forEach((k) => (settings[k] = Number(fd.get(k))));

  const submit = $("createProjectSubmit");
  submit.disabled = true;
  submit.textContent = "Analysing screenplay…";

  try {
    let p;
    if (file && file.size) {
      const upload = new FormData();
      upload.append("title", title);
      upload.append("author", author);
      upload.append("budget_settings_json", JSON.stringify(settings));
      upload.append("file", file);
      p = await api("/api/projects/upload", { method: "POST", body: upload });
    } else {
      if (!scriptText) throw new Error("Paste screenplay text or choose a file.");
      p = await api("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, author, script_text: scriptText, budget_settings: settings }),
      });
    }
    closeModal();
    form.reset();
    state.projects.unshift(p);
    state.projects = state.projects.filter((x, i, a) => a.findIndex((y) => y.id === x.id) === i);
    renderRecent();
    await selectProject(p.id);
    showToast("Screenplay analysed and saved successfully.");
  } catch (e) {
    showToast(e.message, true);
  } finally {
    submit.disabled = false;
    submit.textContent = "Analyse screenplay";
  }
}

async function selectProject(id) {
  try {
    state.current = await api(`/api/projects/${id}`);
    state.comparisons = await api(`/api/projects/${id}/market/comparisons`).catch(() => []);
    state.marketReport = await api(`/api/projects/${id}/market/report`).catch(() => null);
    $("emptyState").classList.add("hidden");
    $("dashboard").classList.remove("hidden");
    $("currentProjectName").textContent = state.current.title;
    renderRecent();
    renderPage();
  } catch (e) {
    showToast(e.message, true);
  }
}

function navigate(page) {
  state.page = page;
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  renderPage();
}

function heading() {
  const p = pageInfo[state.page] || pageInfo.overview;
  $("pageEyebrow").textContent = p[0];
  $("pageTitle").innerHTML = p[1];
  $("pageDescription").textContent = p[2];
}

function renderPage() {
  if (!state.current) {
    showEmpty();
    return;
  }
  heading();
  const a = currentAnalysis();
  const root = $("pageContent");

  if (state.page === "overview") root.innerHTML = overview(a);
  else if (state.page === "production") root.innerHTML = production(a);
  else if (state.page === "schedule") root.innerHTML = schedule(a);
  else if (state.page === "characters") root.innerHTML = characters(a);
  else if (state.page === "locations") root.innerHTML = locations(a);
  else if (state.page === "budget") root.innerHTML = budget(a);
  else if (state.page === "market") root.innerHTML = marketView();

  if (state.page === "locations") initMap(a.locations || []);
  if (state.page === "market") renderMarketViewContent();
}

function stat(label, value, sub, icon = "◈") {
  return `
    <div class="stat-card">
      <div class="stat-label">${label}<span class="stat-icon">${icon}</span></div>
      <div class="stat-value">${value}</div>
      <div class="stat-sub">${sub || ""}</div>
    </div>`;
}

function stats(a) {
  return `
    <div class="stats-grid">
      ${stat("SCENES", number(a.scene_count || a.structured_scenes?.length), "Structured scene records", "▤")}
      ${stat("CHARACTERS", number(a.character_count || a.characters?.length), "Evidence-grounded profiles", "♙")}
      ${stat("SCRIPT LENGTH", `${number(a.estimated_pages)} pages`, `${number(a.word_count)} words estimated`, "▧")}
      ${stat("SHOOTING PLAN", `${number(a.budget?.shooting_days)} days`, "Planning estimate", "◷")}
    </div>`;
}

function noticeWarnings(a) {
  return (a.analysis_warnings || []).map((w) => `<div class="notice">${escapeHtml(w)}</div>`).join("");
}

// ============================================================
// 1. OVERVIEW PAGE
// ============================================================

function overview(a) {
  const b = a.budget || { breakdown: [], total: 0, total_with_contingency: 0 };
  const max = Math.max(1, ...(b.breakdown || []).map((x) => x.amount));
  const scenes = a.structured_scenes || [];

  return `
    ${stats(a)}
    ${noticeWarnings(a)}
    <div class="two-col">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3>Estimated production budget</h3>
            <div class="panel-sub">Calculated from the current project's editable assumptions</div>
          </div>
          <span class="pill">Planning estimate</span>
        </div>
        <div class="budget-hero">
          <div><small>ESTIMATED TOTAL</small><strong>${money(b.total_with_contingency)}</strong></div>
          <div><small>BASE ESTIMATE</small><strong>${money(b.total)}</strong></div>
          <div><small>CONTINGENCY (10%)</small><strong class="accent">${money(b.contingency)}</strong></div>
        </div>
        ${barList(b.breakdown || [], max)}
      </div>
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3>Genre signals</h3>
            <div class="panel-sub">Screenplay keyword signals, not a definitive commercial classification</div>
          </div>
        </div>
        ${genreBars(a.genre_signals || [])}
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Scene breakdown</h3>
          <div class="panel-sub">${number(scenes.length)} structured scene heading(s) extracted</div>
        </div>
        <button class="btn btn-light" onclick="navigate('schedule')">View shooting schedule</button>
      </div>
      ${sceneOverviewTable(scenes, 10)}
    </div>`;
}

function barList(items, max) {
  if (!items.length) return '<div class="empty-box">No budget breakdown available.</div>';
  return `
    <div class="bar-list">
      ${items
        .map(
          (x) => `
        <div class="bar-row">
          <span>${escapeHtml(x.department)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.max(1, (x.amount / max) * 100)}%"></div></div>
          <span class="bar-value">${money(x.amount)}</span>
        </div>`
        )
        .join("")}
    </div>`;
}

function genreBars(items) {
  if (!items.length) return '<div class="empty-box">Not enough screenplay signals to suggest a genre.</div>';
  const max = Math.max(1, ...items.map((x) => x.signals));
  return items
    .map(
      (x) => `
    <div class="genre-row">
      <span class="genre-name">${escapeHtml(x.genre)}</span>
      <div class="genre-track"><span style="width:${(x.signals / max) * 100}%"></span></div>
      <span class="genre-score">${x.signals}</span>
    </div>`
    )
    .join("");
}

function sceneOverviewTable(scenes, limit = 10) {
  if (!scenes.length) return '<div class="empty-box">No structured scene headings found.</div>';
  return `
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr><th>SCENE #</th><th>HEADING</th><th>PRIMARY LOCATION</th><th>SET / SUB-LOCATION</th><th>TIME</th></tr>
        </thead>
        <tbody>
          ${scenes
            .slice(0, limit)
            .map(
              (s) => `
            <tr>
              <td><strong>${escapeHtml(s.scene_number)}</strong></td>
              <td class="item-name">${escapeHtml(s.heading)}</td>
              <td>${escapeHtml(s.primary_location)}</td>
              <td>${escapeHtml(s.sub_location || "—")}</td>
              <td><span class="pill">${escapeHtml(s.time_of_day)}</span></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

// ============================================================
// 2. CHARACTERS PAGE (EVIDENCE-GROUNDED PROFILES)
// ============================================================

function characters(a) {
  const chars = a.characters || [];
  const rels = a.relationships || [];

  return `
    ${stats(a)}
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Evidence-grounded character profiles</h3>
          <div class="panel-sub">
            Grounded in actual screenplay dialogue, character actions, narrative decisions, and scene appearances.
          </div>
        </div>
        <span class="pill">${chars.length} characters identified</span>
      </div>
    </div>

    <div class="character-grid">
      ${
        chars.length
          ? chars
              .map((c) => {
                const name = c.name || "Unnamed character";
                const role = c.role || "Supporting";
                const roleClass = role.toLowerCase().includes("protagonist")
                  ? "role-protagonist"
                  : role.toLowerCase().includes("antagonist")
                  ? "role-antagonist"
                  : role.toLowerCase().includes("minor")
                  ? "role-minor"
                  : "role-supporting";

                const desc = c.description || "Grounded role established in screenplay dialogue.";
                const notes = c.notes || c.note || "Analysis based on extracted screenplay dialogue.";
                const motivation = c.motivation || "Objective defined by scene requirements.";
                const arc = c.character_arc || "Character development traced across narrative scenes.";
                const traits = c.trait_evidence || c.evidence || [];
                const strengths = c.strengths || [];
                const flaws = c.flaws || [];
                const confidence = c.confidence || "Moderate";

                // Find relationships for this character
                const charRels = rels.filter((r) => r.character_a === name || r.character_b === name);

                return `
                <article class="character-card">
                  <div class="character-top">
                    <div class="character-avatar">${escapeHtml(name.slice(0, 2).toUpperCase())}</div>
                    <div style="flex:1">
                      <div style="display:flex;justify-content:space-between;align-items:center">
                        <h3 style="margin:0">${escapeHtml(name)}</h3>
                        <span class="pill ${roleClass}">${escapeHtml(role)}</span>
                      </div>
                      <div class="panel-sub" style="margin-top:2px">${escapeHtml(c.role_basis || "")}</div>
                    </div>
                  </div>

                  <section class="character-detail">
                    <h4>Character description</h4>
                    <p>${escapeHtml(desc)}</p>
                  </section>

                  <section class="character-detail">
                    <h4>Personality traits & supporting evidence</h4>
                    <div style="margin-top:6px">
                      ${
                        traits.length
                          ? traits
                              .map(
                                (t) => `
                            <div class="trait-tag">
                              <div><strong>${escapeHtml(t.trait)}</strong> <span class="pill" style="font-size:8px;padding:2px 5px">${escapeHtml(t.confidence || "Moderate")}</span></div>
                              <div class="trait-quote">${escapeHtml(t.evidence || t.text || "")} (Scene ${escapeHtml(t.scene || t.scene_ref || "1")})</div>
                            </div>`
                              )
                              .join("")
                          : '<p class="muted small">Direct trait evidence limited in extracted dialogue.</p>'
                      }
                    </div>
                  </section>

                  <section class="character-detail">
                    <h4>Motivation and goals</h4>
                    <p>${escapeHtml(motivation)}</p>
                  </section>

                  ${
                    strengths.length || flaws.length
                      ? `
                  <section class="character-detail">
                    <h4>Strengths & flaws</h4>
                    <p>
                      ${strengths.length ? `<strong>Strengths:</strong> ${escapeHtml(strengths.join(", "))}<br>` : ""}
                      ${flaws.length ? `<strong>Flaws:</strong> ${escapeHtml(flaws.join(", "))}` : ""}
                    </p>
                  </section>`
                      : ""
                  }

                  <section class="character-detail">
                    <h4>Character development & arc</h4>
                    <p>${escapeHtml(arc)}</p>
                  </section>

                  ${
                    charRels.length
                      ? `
                  <section class="character-detail">
                    <h4>Relationships & conflicts</h4>
                    <div style="margin-top:4px">
                      ${charRels
                        .slice(0, 3)
                        .map(
                          (r) => `
                        <div class="small" style="margin-bottom:4px">
                          <strong>${escapeHtml(r.character_a === name ? r.character_b : r.character_a)}:</strong>
                          <span class="pill" style="padding:2px 6px;font-size:9px">${escapeHtml(r.relationship_type)}</span>
                          <span class="muted">(${r.shared_scenes_count} shared scene(s))</span>
                        </div>`
                        )
                        .join("")}
                    </div>
                  </section>`
                      : ""
                  }

                  <section class="character-detail">
                    <h4>Substantial character dossier</h4>
                    <p style="white-space:pre-line">${escapeHtml(notes)}</p>
                  </section>

                  <div class="panel-sub" style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line);padding-top:12px;margin-top:16px">
                    <span>Speaking cues: <strong>${c.cue_count || 0}</strong> · Words: <strong>${c.dialogue_word_count || 0}</strong></span>
                    <span class="pill">Confidence: ${escapeHtml(confidence)}</span>
                  </div>
                </article>`;
              })
              .join("")
          : '<div class="panel empty-box">No character cues identified. Ensure character names appear in uppercase before dialogue.</div>'
      }
    </div>
    ${noticeWarnings(a)}`;
}

// ============================================================
// 3. LOCATIONS PAGE & GIS MAP
// ============================================================

function locations(a) {
  const locs = a.locations || [];
  const resolvedCount = locs.filter((l) => l.latitude != null && l.longitude != null).length;

  return `
    ${stats(a)}
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Screenplay location GIS & map allocation</h3>
          <div class="panel-sub">
            Scenes are grouped by primary physical location. Fictional places remain unpinned until resolved or manually verified.
          </div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" id="geocodeBtn">Resolve real locations</button>
        </div>
      </div>
      <div id="locationMap" class="map-box">
        <div class="map-placeholder">Map will appear when coordinates are available.</div>
      </div>
      <div class="panel-sub" style="margin-bottom:14px">
        <strong>${resolvedCount}</strong> of <strong>${locs.length}</strong> primary filming locations resolved with coordinates.
      </div>

      <div class="location-grid">
        ${
          locs.length
            ? locs
                .map((l, i) => {
                  const hasCoords = l.latitude != null && l.longitude != null;
                  const isManual = l.resolution_status === "manual";
                  const statusClass = isManual ? "" : hasCoords ? "" : "warn";
                  const statusText = isManual
                    ? `Manual: ${Number(l.latitude).toFixed(4)}, ${Number(l.longitude).toFixed(4)}`
                    : hasCoords
                    ? `${Number(l.latitude).toFixed(4)}, ${Number(l.longitude).toFixed(4)}`
                    : "Unresolved";

                  return `
            <article class="location-card" id="locCard_${escapeHtml(l.name)}">
              <div class="location-band">
                ${escapeHtml(l.name.slice(0, 2).toUpperCase())}
                <span style="font-size:10px;font-style:normal">${escapeHtml(l.int_ext || "SET")} · ${l.scene_count || 0} SCENE(S)</span>
              </div>
              <div class="location-body">
                <h3>${escapeHtml(l.name)}</h3>
                <p>${l.display_name ? escapeHtml(l.display_name) : escapeHtml(l.unresolved_reason || "Coordinates not resolved yet.")}</p>

                ${
                  l.sub_locations && l.sub_locations.length
                    ? `
                <div style="margin:8px 0">
                  <small style="color:var(--muted);display:block;margin-bottom:3px">SUB-LOCATIONS / SETS:</small>
                  ${l.sub_locations.map((sub) => `<span class="subloc-tag">${escapeHtml(sub)}</span>`).join("")}
                </div>`
                    : ""
                }

                ${
                  l.scene_numbers && l.scene_numbers.length
                    ? `
                <div style="margin:8px 0">
                  <small style="color:var(--muted);display:block;margin-bottom:3px">SCENES FILMED HERE:</small>
                  ${l.scene_numbers.map((sn) => `<span class="scene-badge">Sc ${escapeHtml(sn)}</span>`).join("")}
                </div>`
                    : ""
                }

                <div style="margin-top:10px;display:flex;justify-content:space-between;align-items:center">
                  <span class="pill ${statusClass}">${escapeHtml(statusText)}</span>
                </div>

                <div class="card-actions">
                  ${hasCoords ? `<button class="btn btn-light" data-focus-loc="${escapeHtml(l.name)}">Focus on map</button>` : ""}
                  <button class="btn btn-light" data-edit-loc="${escapeHtml(l.name)}">Set coordinates / Edit</button>
                </div>
              </div>
            </article>`;
                })
                .join("")
            : '<div class="panel empty-box">No scene-heading locations extracted yet.</div>'
        }
      </div>
    </div>`;
}

function initMap(locs) {
  const mapEl = $("locationMap");
  if (!mapEl) return;

  if (state.map) {
    state.map.remove();
    state.map = null;
    state.markers = {};
  }

  const valid = locs.filter(
    (l) => l.latitude != null && l.longitude != null && Number.isFinite(Number(l.latitude)) && Number.isFinite(Number(l.longitude))
  );

  if (!window.L) {
    mapEl.innerHTML = '<div class="map-placeholder">Leaflet map library could not load. Check network connection.</div>';
    return;
  }

  mapEl.innerHTML = "";
  const initialCenter = valid.length ? [Number(valid[0].latitude), Number(valid[0].longitude)] : [51.505, -0.09];
  const map = L.map(mapEl).setView(initialCenter, valid.length ? 10 : 3);
  state.map = map;

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors",
  }).addTo(map);

  state.markers = {};
  if (valid.length) {
    const bounds = [];
    valid.forEach((l) => {
      const pos = [Number(l.latitude), Number(l.longitude)];
      bounds.push(pos);
      const marker = L.marker(pos).addTo(map);

      const sublocs = (l.sub_locations || []).join(", ") || "Main set";
      const scenes = (l.scene_numbers || []).join(", ") || "None";

      marker.bindPopup(`
        <div style="font-family:'DM Sans',sans-serif">
          <strong style="font-size:13px">${escapeHtml(l.name)}</strong><br>
          <span style="font-size:11px;color:#666">${escapeHtml(l.display_name || "")}</span>
          <hr style="border:0;border-top:1px solid #eee;margin:6px 0">
          <div style="font-size:10px"><strong>Scenes:</strong> ${escapeHtml(scenes)}</div>
          <div style="font-size:10px"><strong>Sub-locations:</strong> ${escapeHtml(sublocs)}</div>
          <div style="font-size:9px;color:#888;margin-top:4px">Lat: ${pos[0].toFixed(5)}, Lon: ${pos[1].toFixed(5)}</div>
        </div>
      `);

      state.markers[l.name] = marker;
    });

    if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [35, 35] });
    }
  } else {
    mapEl.innerHTML += `
      <div class="map-placeholder" style="position:relative;z-index:400;pointer-events:none">
        No coordinates resolved yet. Click “Resolve real locations” or use “Set coordinates” to specify real filming locations.
      </div>`;
  }
}

function focusLocationOnMap(locName) {
  const marker = state.markers[locName];
  if (marker && state.map) {
    state.map.setView(marker.getLatLng(), 14, { animate: true });
    marker.openPopup();
    const mapBox = $("locationMap");
    if (mapBox) mapBox.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    showToast(`No coordinates currently available for "${locName}". Use "Set coordinates" to add coordinates.`, true);
  }
}

function openLocationModal(locName) {
  const locs = currentAnalysis().locations || [];
  const loc = locs.find((l) => l.name === locName) || { name: locName };

  $("locationModalTitle").textContent = `Filming Location: ${locName}`;
  $("locModalNameHidden").value = locName;
  $("locModalNameDisplay").value = locName;
  $("locModalAddress").value = loc.display_name || "";
  $("locModalLat").value = loc.latitude != null ? loc.latitude : "";
  $("locModalLon").value = loc.longitude != null ? loc.longitude : "";

  $("locationModal").classList.remove("hidden");
}

function closeLocationModal() {
  $("locationModal").classList.add("hidden");
}

async function submitManualLocation(event) {
  event.preventDefault();
  if (!state.current) return;

  const fd = new FormData(event.target);
  const name = fd.get("name");
  const lat = parseFloat(fd.get("latitude"));
  const lon = parseFloat(fd.get("longitude"));
  const displayName = fd.get("display_name");

  if (isNaN(lat) || lat < -90 || lat > 90 || isNaN(lon) || lon < -180 || lon > 180) {
    showToast("Enter valid latitude (-90 to +90) and longitude (-180 to +180).", true);
    return;
  }

  const submitBtn = $("saveLocationModalSubmit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Saving…";

  try {
    state.current = await api(`/api/projects/${state.current.id}/locations/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, latitude: lat, longitude: lon, display_name: displayName }),
    });
    closeLocationModal();
    renderPage();
    showToast(`Coordinates for "${name}" saved and updated on the map.`);
    setTimeout(() => focusLocationOnMap(name), 300);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Save & Update Map";
  }
}

async function resolveLocations() {
  if (!state.current) return;
  const btn = $("geocodeBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Resolving via OpenStreetMap…";
  }
  try {
    state.current = await api(`/api/projects/${state.current.id}/locations/resolve`, { method: "POST" });
    await refreshProjectList();
    renderPage();
    const resolved = (state.current.analysis?.locations || []).filter((l) => l.latitude != null).length;
    showToast(`${resolved} location(s) resolved with OpenStreetMap. Fictional sets remain safely unmapped.`);
  } catch (e) {
    showToast(e.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Resolve real locations";
    }
  }
}

// ============================================================
// 4. SHOOTING SCHEDULE (STRUCTURED SCENE RECORDS)
// ============================================================

function schedule(a) {
  const sched = a.schedule || [];
  const scenes = a.structured_scenes || [];
  const days = a.budget?.shooting_days || 1;
  const minsPerScene = a.budget?.assumptions?.minutes_per_scene || 45;
  const hoursPerDay = a.budget?.assumptions?.shooting_hours_per_day || 8;

  return `
    ${stats(a)}
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Proposed shooting schedule</h3>
          <div class="panel-sub">
            Calculated from validated scene headings and production assumptions.
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <div class="btn-group">
            <button class="btn ${state.scheduleStrategy === "sequential" ? "active" : ""}" id="seqScheduleBtn">Script Order</button>
            <button class="btn ${state.scheduleStrategy === "by_location" ? "active" : ""}" id="locScheduleBtn">By Location</button>
          </div>
          <button class="btn btn-light" id="editScheduleBtn">Schedule options</button>
        </div>
      </div>

      <div class="stats-grid" style="margin-bottom:16px">
        ${stat("SHOOTING DAYS", `${days} days`, `At ${hoursPerDay} hrs / day`, "◷")}
        ${stat("SCENES TO SHOOT", `${scenes.length}`, "Total scenes in draft", "▤")}
        ${stat("TIME PER SCENE", `${minsPerScene} min`, "Estimated average duration", "⏱")}
        ${stat("STRATEGY", state.scheduleStrategy === "by_location" ? "Location Grouped" : "Sequential", "Configurable shooting order", "▦")}
      </div>

      ${
        sched.length
          ? `
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>DAY</th>
              <th>SCENE #</th>
              <th>HEADING</th>
              <th>PRIMARY LOCATION</th>
              <th>SUB-LOCATION / SET</th>
              <th>TIME</th>
              <th>EST. DURATION</th>
              <th>CHARACTERS</th>
              <th>PLANNING NOTE</th>
            </tr>
          </thead>
          <tbody>
            ${sched
              .map(
                (s) => `
              <tr>
                <td><strong>Day ${escapeHtml(s.day)}</strong></td>
                <td><span class="pill" style="font-weight:700">Sc ${escapeHtml(s.scene_number)}</span></td>
                <td class="item-name">${escapeHtml(s.heading)}</td>
                <td><strong>${escapeHtml(s.primary_location)}</strong></td>
                <td>${escapeHtml(s.sub_location || "—")}</td>
                <td><span class="pill">${escapeHtml(s.time_of_day)}</span></td>
                <td>${escapeHtml(s.est_duration || "45 min")}</td>
                <td><small>${escapeHtml((s.characters || []).join(", ") || "None specified")}</small></td>
                <td><span class="pill warn">${escapeHtml(s.planning_notes || "Standard setup")}</span></td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`
          : '<div class="empty-box">Structured scenes are required to calculate the shooting schedule.</div>'
      }
    </div>`;
}

function openScheduleModal() {
  const b = currentAnalysis().budget?.assumptions || {};
  $("schedModalStrategy").value = state.scheduleStrategy;
  $("schedModalMins").value = b.minutes_per_scene || 45;
  $("schedModalHours").value = b.shooting_hours_per_day || 8;
  $("scheduleModal").classList.remove("hidden");
}

function closeScheduleModal() {
  $("scheduleModal").classList.add("hidden");
}

async function setScheduleStrategy(strategy) {
  state.scheduleStrategy = strategy;
  if (!state.current) return;
  try {
    const b = currentAnalysis().budget?.assumptions || {};
    const res = await api(`/api/projects/${state.current.id}/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strategy,
        minutes_per_scene: b.minutes_per_scene || 45,
        shooting_hours_per_day: b.shooting_hours_per_day || 8,
      }),
    });
    if (state.current.analysis) {
      state.current.analysis.schedule = res.schedule;
    }
    renderPage();
    showToast(`Schedule re-ordered: ${strategy === "by_location" ? "Grouped by location" : "Script order (sequential)"}`);
  } catch (e) {
    showToast(e.message, true);
  }
}

async function submitScheduleUpdate(event) {
  event.preventDefault();
  if (!state.current) return;

  const fd = new FormData(event.target);
  const strategy = fd.get("strategy");
  const mins = parseFloat(fd.get("minutes_per_scene"));
  const hours = parseFloat(fd.get("shooting_hours_per_day"));

  state.scheduleStrategy = strategy;
  const submitBtn = $("saveScheduleModalSubmit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Calculating…";

  try {
    const res = await api(`/api/projects/${state.current.id}/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy, minutes_per_scene: mins, shooting_hours_per_day: hours }),
    });
    if (state.current.analysis) {
      state.current.analysis.schedule = res.schedule;
      if (state.current.analysis.budget?.assumptions) {
        state.current.analysis.budget.assumptions.minutes_per_scene = mins;
        state.current.analysis.budget.assumptions.shooting_hours_per_day = hours;
      }
    }
    closeScheduleModal();
    renderPage();
    showToast("Schedule updated with your production assumptions.");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Apply Schedule";
  }
}

// ============================================================
// 5. COMPARATIVE FILM-MARKET ANALYSIS DASHBOARD
// ============================================================

function marketView() {
  return `
    <div class="panel market-search" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div>
          <h3 style="margin:0">Comparative film-market analysis</h3>
          <div class="panel-sub">
            Benchmark your screenplay against comparable films using real OMDb records and structured intelligence.
          </div>
        </div>
        <button class="btn btn-primary" id="findCompsBtn">Find comparable films</button>
      </div>

      <form id="marketSearchForm">
        <label for="marketSearchInput">Search title to add to comparison set</label>
        <div class="market-search-row">
          <input id="marketSearchInput" name="query" type="search" maxlength="100" placeholder="e.g. Se7en, Zodiac, Prisoners, The Silence of the Lambs" autocomplete="off">
          <button class="btn btn-light" type="submit">Search OMDb</button>
        </div>
      </form>
      <p class="muted small" style="margin-top:8px">
        OMDb API key is secured on the backend. Candidate search results are live matches, not popularity rankings.
      </p>
    </div>

    <div id="marketSearchResultsContainer" style="display:none;margin-bottom:20px"></div>

    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Selected comparison films</h3>
          <div class="panel-sub">Side-by-side metric comparison. Missing box-office values are labeled "Not reported" (not zero).</div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" id="generateReportBtn">Generate market report</button>
        </div>
      </div>
      <div id="comparisonsContainer"></div>
    </div>

    <div id="marketReportContainer"></div>`;
}

function renderMarketViewContent() {
  renderComparisonsList();
  renderMarketReportSection();
}

function renderComparisonsList() {
  const container = $("comparisonsContainer");
  if (!container) return;

  const comps = state.comparisons || [];
  if (!comps.length) {
    container.innerHTML = `
      <div class="empty-box">
        No comparison films added yet. Click <strong>“Find comparable films”</strong> above to automatically recommend films matching this screenplay's genre and themes, or search for titles to add.
      </div>`;
    return;
  }

  container.innerHTML = `
    <div class="comp-matrix">
      ${comps
        .map(
          (m) => `
        <article class="comp-card">
          <div class="comp-header">
            <div>
              <h3>${escapeHtml(m.title)} <small style="color:var(--muted)">(${escapeHtml(m.year)})</small></h3>
              <span class="pill" style="margin-top:4px">${escapeHtml(m.rated || "Unrated")}</span>
            </div>
            <button class="btn btn-light" style="padding:4px 8px;font-size:10px" data-remove-comp="${escapeHtml(m.imdb_id)}">✕ Remove</button>
          </div>
          <div class="comp-body">
            <div class="comp-row"><small>GENRES</small><strong>${escapeHtml(m.genre_str || m.genres?.join(", ") || "—")}</strong></div>
            <div class="comp-row"><small>DIRECTOR</small><strong>${escapeHtml(m.director || "—")}</strong></div>
            <div class="comp-row"><small>IMDb RATING</small><strong>${escapeHtml(m.imdb_rating || "Not reported")}</strong></div>
            <div class="comp-row"><small>IMDb VOTES</small><strong>${escapeHtml(m.imdb_votes || "Not reported")}</strong></div>
            <div class="comp-row"><small>ROTTEN TOMATOES</small><strong>${escapeHtml(m.rotten_tomatoes || "Not reported")}</strong></div>
            <div class="comp-row"><small>METASCORE</small><strong>${escapeHtml(m.metascore || "Not reported")}</strong></div>
            <div class="comp-row"><small>REPORTED BOX OFFICE</small><strong class="accent">${escapeHtml(m.box_office || "Not reported")}</strong></div>
            <div class="comp-row"><small>RUNTIME</small><strong>${escapeHtml(m.runtime || "—")}</strong></div>
            <p style="font-size:11px;color:#6b726d;margin:8px 0 0;line-height:1.5">${escapeHtml(m.plot || m.overview || "")}</p>
          </div>
        </article>`
        )
        .join("")}
    </div>`;
}

function renderMarketReportSection() {
  const container = $("marketReportContainer");
  if (!container) return;

  const report = state.marketReport;
  if (!report || !report.sections) {
    container.innerHTML = "";
    return;
  }

  const s = report.sections;
  container.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Comparative market intelligence report</h3>
          <div class="panel-sub">
            Generated analysis for <strong>"${escapeHtml(report.project_title || "")}"</strong> based on ${report.comp_films_count} comparative benchmark film(s).
          </div>
        </div>
        <span class="pill">Structured Analysis</span>
      </div>

      <div class="report-section">
        <h3>1. Benchmark Selection Rationale</h3>
        <p>${escapeHtml(s.comparison_rationale)}</p>
      </div>

      <div class="report-section">
        <h3>2. Thematic & Premise Alignment</h3>
        <p>${escapeHtml(s.thematic_premise_alignment)}</p>
      </div>

      <div class="report-section">
        <h3>3. Audience & Critical Reception</h3>
        <p>${escapeHtml(s.audience_reception)}</p>
      </div>

      <div class="report-section">
        <h3>4. Commercial Box-Office Benchmarking</h3>
        <p>${escapeHtml(s.commercial_box_office)}</p>
      </div>

      <div class="report-section">
        <h3>5. Data Limitations & Industry Caveats</h3>
        <p>${escapeHtml(s.data_limitations)}</p>
      </div>

      <div class="report-section">
        <h3>6. Target Audience Positioning</h3>
        <p>${escapeHtml(s.target_audience_positioning)}</p>
      </div>

      <div class="report-section">
        <h3>7. Differentiators & Competitive Strengths</h3>
        <p>${escapeHtml(s.differentiators)}</p>
      </div>

      <div class="report-section">
        <h3>8. Market Risks & Uncertainties</h3>
        <p>${escapeHtml(s.risks_and_uncertainties)}</p>
      </div>

      <div class="report-section">
        <h3>9. Strategic Development Recommendations</h3>
        <p>${escapeHtml(s.strategic_recommendations)}</p>
      </div>
    </div>`;
}

async function searchMarket(query) {
  const container = $("marketSearchResultsContainer");
  if (!container) return;

  container.style.display = "block";
  container.innerHTML = `<div class="panel"><p class="small muted">Searching OMDb for “${escapeHtml(query)}”…</div>`;

  try {
    const data = await api(`/api/market?query=${encodeURIComponent(query)}`);
    const movies = data.movies || [];

    if (!movies.length) {
      container.innerHTML = `<div class="panel empty-box">${escapeHtml(data.message || "No matching titles found on OMDb.")}</div>`;
      return;
    }

    container.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3>Search results for “${escapeHtml(query)}”</h3>
            <div class="panel-sub">Select films to add to your side-by-side comparison matrix.</div>
          </div>
          <button class="btn btn-light" onclick="$('marketSearchResultsContainer').style.display='none'">Close</button>
        </div>
        <div class="movie-grid">
          ${movies
            .map(
              (m) => `
            <article class="movie-card">
              <div class="movie-poster">
                ${m.poster_path ? `<img src="${escapeHtml(m.poster_path)}" alt="${escapeHtml(m.title)} poster">` : "Poster unavailable"}
              </div>
              <div class="movie-info">
                <h3>${escapeHtml(m.title)}</h3>
                <div class="movie-meta">${escapeHtml(m.release_date || m.year)} · ${escapeHtml(m.genre_str || m.genres?.join(", ") || "")}</div>
                <p class="movie-overview">${escapeHtml(m.overview || m.plot || "")}</p>
                <div class="movie-numbers">
                  <div><small>IMDb RATING</small><strong>${escapeHtml(m.imdb_rating || "Not reported")}</strong></div>
                  <div><small>BOX OFFICE</small><strong>${escapeHtml(m.box_office || "Not reported")}</strong></div>
                </div>
                <button class="btn btn-primary" style="margin-top:10px" data-add-comp="${escapeHtml(m.imdb_id)}">＋ Add to comparison</button>
              </div>
            </article>`
            )
            .join("")}
        </div>
      </div>`;
  } catch (e) {
    container.innerHTML = `<div class="panel empty-box error-text">${escapeHtml(e.message)}</div>`;
  }
}

async function findComparableFilms() {
  if (!state.current) return;
  const btn = $("findCompsBtn");
  btn.disabled = true;
  btn.textContent = "Proposing comparable titles…";

  try {
    const res = await api(`/api/projects/${state.current.id}/market/recommendations`);
    const candidates = res.candidates || [];

    if (!candidates.length) {
      showToast("No automated recommendations available. Try searching OMDb by movie title above.", true);
      return;
    }

    for (const c of candidates) {
      await api(`/api/projects/${state.current.id}/market/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imdb_id: c.imdb_id }),
      });
    }

    state.comparisons = await api(`/api/projects/${state.current.id}/market/comparisons`);
    renderComparisonsList();
    showToast(`Added ${candidates.length} comparable title(s) based on screenplay genre and premise.`);

    // Auto-generate report with new comps
    generateMarketReport();
  } catch (e) {
    showToast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Find comparable films";
  }
}

async function addMovieToComparison(imdbId) {
  if (!state.current) return;
  try {
    state.comparisons = await api(`/api/projects/${state.current.id}/market/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ imdb_id: imdbId }),
    });
    renderComparisonsList();
    showToast("Film added to comparison matrix.");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function removeMovieFromComparison(imdbId) {
  if (!state.current) return;
  try {
    state.comparisons = await api(`/api/projects/${state.current.id}/market/compare/${imdbId}`, {
      method: "DELETE",
    });
    renderComparisonsList();
    showToast("Film removed from comparison matrix.");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function generateMarketReport() {
  if (!state.current) return;
  const btn = $("generateReportBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Generating intelligence report…";
  }

  try {
    state.marketReport = await api(`/api/projects/${state.current.id}/market/report`, { method: "POST" });
    renderMarketReportSection();
    showToast("Comparative market intelligence report generated.");
  } catch (e) {
    showToast(e.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Generate market report";
    }
  }
}

// ============================================================
// 6. PRODUCTION & BUDGET VIEWS
// ============================================================

function production(a) {
  const items = a.production_items || [];
  return `
    ${stats(a)}
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Master production requirements</h3>
          <div class="panel-sub">Inferred from screenplay action lines and props keywords.</div>
        </div>
        <span class="pill">${items.length} suggestions</span>
      </div>
      ${
        items.length
          ? `
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>ITEM</th><th>MENTIONS</th><th>CATEGORY</th><th>CONFIDENCE</th></tr></thead>
          <tbody>
            ${items
              .map(
                (x) => `
              <tr>
                <td class="item-name">${escapeHtml(x.item)}</td>
                <td>${x.mentions}</td>
                <td>${escapeHtml(x.category)}</td>
                <td><span class="pill warn">Review</span></td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`
          : '<div class="empty-box">No recognizable production keywords found in screenplay.</div>'
      }
    </div>
    ${noticeWarnings(a)}`;
}

function budget(a) {
  const b = a.budget || {};
  const max = Math.max(1, ...(b.breakdown || []).map((x) => x.amount));
  return `
    ${stats(a)}
    <div class="budget-hero">
      <div><small>ESTIMATED TOTAL</small><strong>${money(b.total_with_contingency)}</strong><small>INR · planning estimate</small></div>
      <div><small>SHOOTING DAYS</small><strong>${number(b.shooting_days)}</strong><small>Assumption-based</small></div>
      <div><small>CONTINGENCY (10%)</small><strong class="accent">${money(b.contingency)}</strong><small>Recommended reserve</small></div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div>
          <h3>Cost breakdown by department</h3>
          <div class="panel-sub">Values are computed from assumptions below, not vendor quotes.</div>
        </div>
        <button class="btn btn-light" id="editBudgetBtn">Edit assumptions</button>
      </div>
      ${barList(b.breakdown || [], max)}
      <div class="table-scroll" style="margin-top:22px">
        <table class="data-table">
          <thead><tr><th>DEPARTMENT</th><th>ESTIMATED COST</th><th>SHARE OF BASE</th></tr></thead>
          <tbody>
            ${(b.breakdown || [])
              .map(
                (x) => `
              <tr>
                <td>${escapeHtml(x.department)}</td>
                <td class="item-name">${money(x.amount)}</td>
                <td>${b.total ? Math.round((x.amount / b.total) * 100) : 0}%</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
    <div class="notice">Budget estimates depend on default assumptions. Edit them to match your region, crew size, production scale, and real supplier quotes before making decisions.</div>`;
}

function openBudgetEditor() {
  if (!state.current) return;
  const b = state.current.analysis?.budget?.assumptions || {};
  const keys = [
    ["cast_per_day", "Cast per day"],
    ["crew_per_day", "Crew per day"],
    ["equipment_per_day", "Equipment per day"],
    ["location_per_day", "Locations per day"],
    ["food_transport_per_day", "Food & transport per day"],
    ["postproduction_per_page", "Post-production per page"],
    ["minutes_per_scene", "Minutes per scene"],
    ["shooting_hours_per_day", "Shooting hours per day"],
  ];
  const form = document.createElement("div");
  form.className = "modal-backdrop";
  form.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <div><p class="eyebrow">BUDGET SETTINGS</p><h2>Adjust planning assumptions</h2></div>
        <button class="icon-btn" id="budgetClose">×</button>
      </div>
      <form id="budgetForm">
        <div class="settings-grid">
          ${keys.map(([k, label]) => `<label>${label}<input name="${k}" type="number" min="0" value="${Number(b[k] ?? 0)}" required></label>`).join("")}
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn-light" id="budgetCancel">Cancel</button>
          <button class="btn btn-primary" type="submit">Recalculate budget</button>
        </div>
      </form>
      <p class="small muted">Use local quotes when available. These inputs are estimates only.</p>
    </div>`;
  document.body.appendChild(form);
  const close = () => form.remove();
  form.querySelector("#budgetClose").onclick = close;
  form.querySelector("#budgetCancel").onclick = close;
  form.querySelector("form").onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const settings = {};
    keys.forEach(([k]) => (settings[k] = Number(fd.get(k))));
    try {
      state.current = await api(`/api/projects/${state.current.id}/reanalyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ budget_settings: settings }),
      });
      await refreshProjectList();
      close();
      renderPage();
      showToast("Budget recalculated with your assumptions.");
    } catch (err) {
      showToast(err.message, true);
    }
  };
}

// ============================================================
// 7. PROJECT ACTIONS (REANALYSE, DELETE, EXPORT)
// ============================================================

async function reanalyse() {
  if (!state.current) return;
  try {
    state.current = await api(`/api/projects/${state.current.id}/reanalyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ budget_settings: state.current.analysis?.budget?.assumptions || {} }),
    });
    await refreshProjectList();
    renderPage();
    showToast("Screenplay re-analysed and updated.");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deleteProject() {
  if (!state.current) return;
  if (!confirm(`Delete "${state.current.title}" and its saved analysis? This cannot be undone.`)) return;
  try {
    await api(`/api/projects/${state.current.id}`, { method: "DELETE" });
    state.current = null;
    state.comparisons = [];
    state.marketReport = null;
    await loadProjects();
    showToast("Project deleted.");
  } catch (e) {
    showToast(e.message, true);
  }
}

async function refreshProjectList() {
  state.projects = await api("/api/projects");
  renderRecent();
}

async function exportReport() {
  if (!state.current) {
    showToast("Select a project first.", true);
    return;
  }
  try {
    const full = await api(`/api/projects/${state.current.id}/report`);
    const blob = new Blob([JSON.stringify(full, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${state.current.title.replace(/[^a-z0-9-_]+/gi, "_")}_full_report.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Complete JSON report exported.");
  } catch (e) {
    showToast("Export failed: " + e.message, true);
  }
}

init();
