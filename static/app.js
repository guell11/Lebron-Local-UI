"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  settings: null,
  chats: [],
  folders: [],
  currentChat: null,
  messages: [],
  attachments: [],
  generating: false,
  runtime: null,
  notes: [],
  currentNote: null,
  runtimePoll: null,
};

const els = {};

window.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheElements();
  bindEvents();
  await Promise.all([loadSettings(), loadChats(), refreshSystem(false)]);
  await refreshRuntime();
  state.runtimePoll = setInterval(refreshRuntime, 2200);
  autoResize(els.welcomeInput);
  autoResize(els.chatInput);
}

function cacheElements() {
  [
    "sidebar", "sidebarToggle", "newChatButton", "searchButton", "notesButton", "workspaceButton",
    "addFolderButton", "folderList", "chatGroups", "gpuFooter", "modelButton", "modelName",
    "modelSubline", "modelDropdown", "openSettingsFromModel", "runtimePill", "systemButton",
    "settingsButton", "welcomeView", "chatView", "heroModelName", "welcomeInput", "welcomeSend",
    "chatInput", "chatSend", "messages", "suggestions", "fileInput", "attachmentChips",
    "welcomeAttachmentCount", "stopButton", "backdrop", "settingsDrawer", "engineSelect",
    "modelLabelInput", "repoPathInput", "baseModelInput", "revisionInput", "dictionaryInput",
    "adapterInput", "hfTokenInput", "ggufInput", "jspaceFields", "ggufFields", "systemPromptInput",
    "saveAndLoadButton", "unloadButton", "runtimeError", "maxTokensInput", "maxTokensOutput",
    "temperatureInput", "temperatureOutput", "topPInput", "topPOutput", "loopsInput", "loopsOutput",
    "contextInput", "reserveInput", "reserveOutput", "saveGenerationButton", "accentSelect",
    "suggestionsToggle", "compactToggle", "saveAppearanceButton", "searchModal", "searchInput",
    "searchResults", "notesModal", "notesList", "newNoteButton", "noteTitle", "noteContent",
    "saveNoteButton", "deleteNoteButton", "workspaceModal", "workspaceGrid", "systemModal",
    "systemContent", "toolsPopover", "toolsButton", "chatToolsButton", "closeTools", "quickTemp",
    "quickTempOutput", "quickLoops", "quickLoopsOutput", "quickTokens", "quickTokensOutput", "toastStack"
  ].forEach((id) => els[id] = document.getElementById(id));
}

function bindEvents() {
  els.sidebarToggle.addEventListener("click", () => {
    document.body.classList.toggle("compact");
    if (state.settings) {
      state.settings.ui.compact_sidebar = document.body.classList.contains("compact");
      saveSettingsSilently();
    }
  });
  els.newChatButton.addEventListener("click", newChat);
  els.searchButton.addEventListener("click", openSearch);
  els.notesButton.addEventListener("click", openNotes);
  els.workspaceButton.addEventListener("click", openWorkspace);
  els.addFolderButton.addEventListener("click", createFolder);
  els.modelButton.addEventListener("click", (event) => {
    event.stopPropagation();
    els.modelDropdown.classList.toggle("hidden");
  });
  $$("[data-engine]", els.modelDropdown).forEach((button) => button.addEventListener("click", () => {
    state.settings.engine = button.dataset.engine;
    fillSettingsForm();
    renderModelHeader();
    els.modelDropdown.classList.add("hidden");
    openDrawer();
  }));
  els.openSettingsFromModel.addEventListener("click", () => { els.modelDropdown.classList.add("hidden"); openDrawer(); });
  els.settingsButton.addEventListener("click", openDrawer);
  els.systemButton.addEventListener("click", openSystem);
  els.backdrop.addEventListener("click", closeOverlays);
  $$(".close-overlay").forEach((button) => button.addEventListener("click", closeOverlays));
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".model-menu-wrap")) els.modelDropdown.classList.add("hidden");
  });
  document.addEventListener("keydown", globalKeys);

  [els.welcomeInput, els.chatInput].forEach((input) => {
    input.addEventListener("input", () => autoResize(input));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendFrom(input === els.welcomeInput ? "welcome" : "chat");
      }
    });
  });
  els.welcomeSend.addEventListener("click", () => sendFrom("welcome"));
  els.chatSend.addEventListener("click", () => sendFrom("chat"));
  els.stopButton.addEventListener("click", stopGeneration);
  $$(".attach-trigger").forEach((button) => button.addEventListener("click", () => els.fileInput.click()));
  els.fileInput.addEventListener("change", handleFiles);
  $$(".voice-icon").forEach((button) => button.addEventListener("click", () => startDictation(button.closest(".welcome-composer") ? els.welcomeInput : els.chatInput)));
  $$("#suggestions button").forEach((button) => button.addEventListener("click", () => {
    els.welcomeInput.value = button.dataset.prompt || "";
    autoResize(els.welcomeInput);
    els.welcomeInput.focus();
  }));

  els.engineSelect.addEventListener("change", () => toggleEngineFields(els.engineSelect.value));
  els.saveAndLoadButton.addEventListener("click", saveAndLoad);
  els.unloadButton.addEventListener("click", unloadRuntime);
  els.saveGenerationButton.addEventListener("click", saveGeneration);
  els.saveAppearanceButton.addEventListener("click", saveAppearance);
  $$(".drawer-tabs button").forEach((button) => button.addEventListener("click", () => switchDrawerTab(button.dataset.tab)));
  $$('[data-dialog]').forEach((button) => button.addEventListener("click", () => openNativeDialog(button.dataset.dialog, button.dataset.target)));
  [els.maxTokensInput, els.temperatureInput, els.topPInput, els.loopsInput, els.reserveInput].forEach((input) => input.addEventListener("input", updateRangeOutputs));

  els.searchInput.addEventListener("input", debounce(searchChats, 180));
  els.newNoteButton.addEventListener("click", newNote);
  els.saveNoteButton.addEventListener("click", saveNote);
  els.deleteNoteButton.addEventListener("click", deleteNote);

  els.toolsButton.addEventListener("click", () => toggleTools(els.toolsButton));
  els.chatToolsButton.addEventListener("click", () => toggleTools(els.chatToolsButton));
  els.closeTools.addEventListener("click", () => els.toolsPopover.classList.add("hidden"));
  [els.quickTemp, els.quickLoops, els.quickTokens].forEach((input) => input.addEventListener("input", () => {
    state.settings.generation.temperature = Number(els.quickTemp.value);
    state.settings.generation.loops = Number(els.quickLoops.value);
    state.settings.generation.max_new_tokens = Number(els.quickTokens.value);
    updateQuickOutputs();
  }));

  els.messages.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy-code]");
    if (!copy) return;
    const code = copy.closest(".code-block")?.querySelector("code")?.textContent || "";
    navigator.clipboard.writeText(code).then(() => toast("Código copiado.", "success"));
  });
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch { payload = { detail: await response.text() }; }
  if (!response.ok) throw new Error(payload.detail || payload.error || `Erro HTTP ${response.status}`);
  return payload;
}

async function loadSettings() {
  const data = await api("/api/settings");
  state.settings = data.settings;
  applyAppearance();
  fillSettingsForm();
  renderModelHeader();
}

async function saveSettingsSilently() {
  try { await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: state.settings }) }); } catch {}
}

function fillSettingsForm() {
  if (!state.settings) return;
  const s = state.settings;
  els.engineSelect.value = s.engine;
  els.modelLabelInput.value = s.model_label || "";
  els.repoPathInput.value = s.lebron_repo || "";
  els.baseModelInput.value = s.base_model || "";
  els.revisionInput.value = s.model_revision || "";
  els.dictionaryInput.value = s.dictionary_path || "";
  els.adapterInput.value = s.adapter_dir || "";
  els.ggufInput.value = s.gguf_path || "";
  els.systemPromptInput.value = s.system_prompt || "";
  const g = s.generation;
  els.maxTokensInput.value = g.max_new_tokens;
  els.temperatureInput.value = g.temperature;
  els.topPInput.value = g.top_p;
  els.loopsInput.value = g.loops;
  els.contextInput.value = String(g.context_size);
  els.reserveInput.value = s.memory.gpu_reserve_gib;
  els.accentSelect.value = s.ui.accent;
  els.suggestionsToggle.checked = Boolean(s.ui.show_suggestions);
  els.compactToggle.checked = Boolean(s.ui.compact_sidebar);
  els.quickTemp.value = g.temperature;
  els.quickLoops.value = g.loops;
  els.quickTokens.value = g.max_new_tokens;
  toggleEngineFields(s.engine);
  updateRangeOutputs();
  updateQuickOutputs();
}

function collectSettingsForm() {
  const s = structuredClone(state.settings);
  s.engine = els.engineSelect.value;
  s.model_label = els.modelLabelInput.value.trim() || "LeBRON Local";
  s.lebron_repo = els.repoPathInput.value.trim();
  s.base_model = els.baseModelInput.value.trim();
  s.model_revision = els.revisionInput.value.trim();
  s.dictionary_path = els.dictionaryInput.value.trim();
  s.adapter_dir = els.adapterInput.value.trim();
  s.gguf_path = els.ggufInput.value.trim();
  s.system_prompt = els.systemPromptInput.value;
  s.generation.max_new_tokens = Number(els.maxTokensInput.value);
  s.generation.temperature = Number(els.temperatureInput.value);
  s.generation.top_p = Number(els.topPInput.value);
  s.generation.loops = Number(els.loopsInput.value);
  s.generation.context_size = Number(els.contextInput.value);
  s.memory.gpu_reserve_gib = Number(els.reserveInput.value);
  return s;
}

function toggleEngineFields(engine) {
  els.jspaceFields.classList.toggle("hidden", engine !== "jspace_nf4");
  els.ggufFields.classList.toggle("hidden", engine !== "gguf");
}

function updateRangeOutputs() {
  els.maxTokensOutput.textContent = els.maxTokensInput.value;
  els.temperatureOutput.textContent = Number(els.temperatureInput.value).toFixed(2);
  els.topPOutput.textContent = Number(els.topPInput.value).toFixed(2);
  els.loopsOutput.textContent = els.loopsInput.value;
  els.reserveOutput.textContent = `${Number(els.reserveInput.value).toFixed(2)} GiB`;
}

function updateQuickOutputs() {
  els.quickTempOutput.textContent = Number(els.quickTemp.value).toFixed(2);
  els.quickLoopsOutput.textContent = els.quickLoops.value;
  els.quickTokensOutput.textContent = els.quickTokens.value;
}

async function saveAndLoad() {
  try {
    state.settings = collectSettingsForm();
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: state.settings }) });
    const result = await api("/api/runtime/load", {
      method: "POST",
      body: JSON.stringify({ settings: state.settings, hf_token: els.hfTokenInput.value.trim() || null }),
    });
    els.hfTokenInput.value = "";
    els.runtimeError.classList.add("hidden");
    state.runtime = result.runtime;
    renderRuntime();
    renderModelHeader();
    toast("Carregamento iniciado. O primeiro download pode demorar.", "success");
  } catch (error) {
    showRuntimeError(error.message);
    toast(error.message, "error");
  }
}

async function unloadRuntime() {
  try {
    const data = await api("/api/runtime/unload", { method: "POST", body: "{}" });
    state.runtime = data.runtime;
    renderRuntime();
    toast("Modelo descarregado.", "success");
  } catch (error) { toast(error.message, "error"); }
}

async function refreshRuntime() {
  try {
    const data = await api("/api/runtime/status");
    const previous = state.runtime?.state;
    state.runtime = data.runtime;
    renderRuntime();
    if (state.runtime.state === "error") showRuntimeError(state.runtime.error || state.runtime.message);
    if (previous === "loading" && state.runtime.state === "loaded") toast("Modelo carregado e pronto.", "success");
  } catch {}
}

function renderRuntime() {
  if (!state.runtime) return;
  const status = state.runtime.state || "unloaded";
  els.runtimePill.className = `runtime-pill ${status}`;
  const labels = { unloaded: "descarregado", loading: "carregando", loaded: "pronto", unloading: "liberando", error: "erro" };
  $("span", els.runtimePill).textContent = labels[status] || status;
  renderModelHeader();
}

function renderModelHeader() {
  if (!state.settings) return;
  const name = state.settings.model_label || state.settings.base_model || "LeBRON Local";
  els.modelName.textContent = name;
  els.heroModelName.textContent = name;
  const engine = state.settings.engine === "gguf" ? "GGUF Q4 • base" : "NF4 4-bit • J-Space";
  const status = state.runtime?.state === "loaded" ? "pronto" : state.runtime?.state === "loading" ? "carregando" : "não carregado";
  els.modelSubline.textContent = `${engine} • ${status}`;
}

function showRuntimeError(message) {
  els.runtimeError.textContent = message || "Erro desconhecido.";
  els.runtimeError.classList.remove("hidden");
}

async function saveGeneration() {
  state.settings = collectSettingsForm();
  await saveSettingsSilently();
  fillSettingsForm();
  toast("Parâmetros salvos.", "success");
}

async function saveAppearance() {
  state.settings.ui.accent = els.accentSelect.value;
  state.settings.ui.show_suggestions = els.suggestionsToggle.checked;
  state.settings.ui.compact_sidebar = els.compactToggle.checked;
  applyAppearance();
  await saveSettingsSilently();
  toast("Interface atualizada.", "success");
}

function applyAppearance() {
  if (!state.settings) return;
  document.body.classList.remove("accent-blue", "accent-violet", "accent-green");
  if (state.settings.ui.accent !== "amber") document.body.classList.add(`accent-${state.settings.ui.accent}`);
  document.body.classList.toggle("compact", Boolean(state.settings.ui.compact_sidebar));
  els.suggestions?.classList.toggle("hidden", !state.settings.ui.show_suggestions);
}

async function loadChats(query = "", folder = null) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (folder !== null) params.set("folder", folder);
  const data = await api(`/api/chats?${params}`);
  state.chats = data.chats;
  state.folders = data.folders;
  renderChats();
  renderFolders();
}

function renderChats() {
  const groups = new Map();
  for (const chat of state.chats) {
    const label = relativeGroup(chat.updated_at);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(chat);
  }
  els.chatGroups.innerHTML = "";
  for (const [label, chats] of groups) {
    const wrap = document.createElement("div");
    wrap.innerHTML = `<div class="chat-group-label">${escapeHtml(label)}</div>`;
    for (const chat of chats) {
      const row = document.createElement("div");
      row.className = `chat-item ${state.currentChat?.id === chat.id ? "active" : ""}`;
      row.dataset.chatId = chat.id;
      row.innerHTML = `<span>${escapeHtml(chat.title)}</span><button class="chat-item-menu" title="Opções">•••</button>`;
      row.addEventListener("click", (event) => {
        if (event.target.closest(".chat-item-menu")) return chatMenu(chat);
        openChat(chat.id);
      });
      wrap.appendChild(row);
    }
    els.chatGroups.appendChild(wrap);
  }
}

function renderFolders() {
  els.folderList.innerHTML = "";
  const palette = ["#7fcf87", "#e95e70", "#6aa9ff", "#b58cff", "#e4b85c"];
  state.folders.forEach((folder, index) => {
    const button = document.createElement("button");
    button.className = "side-entry";
    button.innerHTML = `<span class="folder-dot" style="background:${palette[index % palette.length]}"></span><span>${escapeHtml(folder)}</span>`;
    button.addEventListener("click", () => filterFolder(folder));
    els.folderList.appendChild(button);
  });
}

async function newChat() {
  state.currentChat = null;
  state.messages = [];
  state.attachments = [];
  els.welcomeInput.value = "";
  els.chatInput.value = "";
  renderAttachmentChips();
  els.welcomeView.classList.remove("hidden");
  els.chatView.classList.add("hidden");
  $$(".chat-item.active").forEach((item) => item.classList.remove("active"));
  if (window.innerWidth <= 780) document.body.classList.remove("mobile-sidebar");
  els.welcomeInput.focus();
}

async function ensureChat() {
  if (state.currentChat) return state.currentChat;
  const data = await api("/api/chats", { method: "POST", body: JSON.stringify({ title: "Nova conversa", folder: "" }) });
  state.currentChat = data.chat;
  await loadChats();
  return state.currentChat;
}

async function openChat(chatId) {
  try {
    const data = await api(`/api/chats/${chatId}`);
    state.currentChat = data.chat;
    state.messages = data.messages;
    state.attachments = [];
    els.welcomeView.classList.add("hidden");
    els.chatView.classList.remove("hidden");
    renderMessages();
    renderAttachmentChips();
    renderChats();
    requestAnimationFrame(() => scrollMessages(true));
    if (window.innerWidth <= 780) document.body.classList.remove("mobile-sidebar");
  } catch (error) { toast(error.message, "error"); }
}

async function chatMenu(chat) {
  const action = prompt("Digite: renomear, pasta ou excluir", "renomear");
  if (!action) return;
  if (action.toLowerCase().startsWith("r")) {
    const title = prompt("Novo nome da conversa:", chat.title);
    if (title) await api(`/api/chats/${chat.id}`, { method: "PATCH", body: JSON.stringify({ title }) });
  } else if (action.toLowerCase().startsWith("p")) {
    const folder = prompt("Nome da pasta:", chat.folder || "");
    if (folder !== null) await api(`/api/chats/${chat.id}`, { method: "PATCH", body: JSON.stringify({ folder }) });
  } else if (action.toLowerCase().startsWith("e")) {
    if (confirm(`Excluir “${chat.title}”?`)) {
      await api(`/api/chats/${chat.id}`, { method: "DELETE" });
      if (state.currentChat?.id === chat.id) await newChat();
    }
  }
  await loadChats();
}

async function createFolder() {
  const folder = prompt("Nome da nova pasta:");
  if (!folder) return;
  if (!state.currentChat) {
    toast("Abra uma conversa e depois mova-a para a pasta.");
    state.folders = [...new Set([...state.folders, folder])];
    renderFolders();
    return;
  }
  await api(`/api/chats/${state.currentChat.id}`, { method: "PATCH", body: JSON.stringify({ folder }) });
  await loadChats();
}

async function filterFolder(folder) {
  await loadChats("", folder);
  openWorkspace();
}

function renderMessages() {
  els.messages.innerHTML = "";
  for (const message of state.messages) appendMessageElement(message.role, message.content, message.meta || {});
}

function appendMessageElement(role, content, meta = {}, pending = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.dataset.role = role;
  if (role === "assistant") {
    article.innerHTML = `<div class="message-avatar">L</div><div class="message-body">${pending ? loadingHtml() : renderMarkdown(content)}${renderMeta(meta)}</div>`;
  } else {
    article.innerHTML = `<div class="message-body">${renderMarkdown(content)}</div>`;
  }
  els.messages.appendChild(article);
  return article;
}

function renderMeta(meta) {
  if (!meta || (!meta.tokens_per_second && meta.confidence == null && !meta.warning)) return "";
  const bits = [];
  if (meta.tokens_per_second) bits.push(`${Number(meta.tokens_per_second).toFixed(1)} tok/s`);
  if (meta.generated_tokens) bits.push(`${meta.generated_tokens} tokens`);
  if (meta.confidence != null) bits.push(`confiança interna ${(Number(meta.confidence) * 100).toFixed(0)}%`);
  if (meta.warning) bits.push(meta.warning);
  return `<div class="message-meta">${bits.map(escapeHtml).join("<span>•</span>")}</div>`;
}

function loadingHtml() { return `<span class="thinking-dots"><i></i><i></i><i></i></span>`; }

async function sendFrom(source) {
  if (state.generating) return;
  if (state.runtime?.state !== "loaded") {
    toast("Carregue o modelo local antes de conversar.", "error");
    openDrawer();
    return;
  }
  const input = source === "welcome" ? els.welcomeInput : els.chatInput;
  const content = input.value.trim();
  if (!content) return;
  const chat = await ensureChat();
  els.welcomeView.classList.add("hidden");
  els.chatView.classList.remove("hidden");
  input.value = "";
  autoResize(input);
  const attachments = [...state.attachments];
  state.attachments = [];
  renderAttachmentChips();
  appendMessageElement("user", content, { attachments: attachments.map((a) => a.name) });
  const assistantEl = appendMessageElement("assistant", "", {}, true);
  scrollMessages(true);
  state.generating = true;
  updateGeneratingUI();

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chat.id,
        content,
        attachments,
        generation: state.settings.generation,
      }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || err.error || `Erro HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";
    let finalMeta = {};
    const body = $(".message-body", assistantEl);
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.event === "token") {
          fullText += event.text || "";
          body.innerHTML = renderMarkdown(fullText);
          scrollMessages(false);
        } else if (event.event === "done") {
          fullText = event.text || fullText;
          finalMeta = event;
          body.innerHTML = renderMarkdown(fullText) + renderMeta(event);
        } else if (event.event === "error") {
          throw new Error(event.error || "Falha na geração.");
        }
      }
    }
    state.messages.push({ role: "user", content, meta: { attachments: attachments.map((a) => a.name) } });
    state.messages.push({ role: "assistant", content: fullText, meta: finalMeta });
    await loadChats();
  } catch (error) {
    $(".message-body", assistantEl).innerHTML = `<div class="error-box">${escapeHtml(error.message)}</div>`;
    toast(error.message, "error");
  } finally {
    state.generating = false;
    updateGeneratingUI();
    els.chatInput.focus();
  }
}

async function stopGeneration() {
  await api("/api/runtime/stop", { method: "POST", body: "{}" }).catch(() => {});
  toast("Parada solicitada.");
}

function updateGeneratingUI() {
  els.stopButton.classList.toggle("hidden", !state.generating);
  els.chatSend.disabled = state.generating;
  els.welcomeSend.disabled = state.generating;
}

async function handleFiles(event) {
  const files = [...event.target.files].slice(0, 8 - state.attachments.length);
  for (const file of files) {
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch("/api/files/read", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Falha ao ler arquivo.");
      state.attachments.push({ name: data.name, content: data.content });
    } catch (error) { toast(`${file.name}: ${error.message}`, "error"); }
  }
  event.target.value = "";
  renderAttachmentChips();
}

function renderAttachmentChips() {
  els.attachmentChips.innerHTML = "";
  state.attachments.forEach((file, index) => {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    chip.innerHTML = `<span>📄 ${escapeHtml(file.name)}</span><button title="Remover">×</button>`;
    $("button", chip).addEventListener("click", () => { state.attachments.splice(index, 1); renderAttachmentChips(); });
    els.attachmentChips.appendChild(chip);
  });
  els.welcomeAttachmentCount.textContent = `${state.attachments.length} arquivo${state.attachments.length === 1 ? "" : "s"}`;
  els.welcomeAttachmentCount.classList.toggle("hidden", state.attachments.length === 0);
}

function openDrawer() {
  fillSettingsForm();
  openOverlay(els.settingsDrawer);
}
function openSearch() { openOverlay(els.searchModal); setTimeout(() => els.searchInput.focus(), 80); }
async function openNotes() { await loadNotes(); openOverlay(els.notesModal); }
async function openWorkspace() { await loadChats(); renderWorkspace(); openOverlay(els.workspaceModal); }
async function openSystem() { await refreshSystem(true); openOverlay(els.systemModal); }
function openOverlay(element) { closeOverlays(); els.backdrop.classList.remove("hidden"); element.classList.remove("hidden"); }
function closeOverlays() { els.backdrop.classList.add("hidden"); $$(".drawer, .modal").forEach((el) => el.classList.add("hidden")); els.toolsPopover.classList.add("hidden"); }

function switchDrawerTab(tab) {
  $$(".drawer-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab));
}

function toggleTools(anchor) {
  fillSettingsForm();
  els.toolsPopover.classList.toggle("hidden");
  if (!els.toolsPopover.classList.contains("hidden")) {
    const rect = anchor.getBoundingClientRect();
    els.toolsPopover.style.left = `${Math.max(12, Math.min(window.innerWidth - 312, rect.left - 80))}px`;
    els.toolsPopover.style.bottom = `${Math.max(82, window.innerHeight - rect.top + 8)}px`;
  }
}

async function openNativeDialog(kind, targetId) {
  try {
    const data = await api("/api/dialog", { method: "POST", body: JSON.stringify({ kind, title: "Selecionar caminho" }) });
    if (data.path) document.getElementById(targetId).value = data.path;
  } catch (error) {
    toast(`${error.message} Cole o caminho manualmente.`, "error");
  }
}

async function searchChats() {
  const query = els.searchInput.value.trim();
  if (!query) { els.searchResults.innerHTML = `<div class="empty-small">Digite para pesquisar no histórico local.</div>`; return; }
  const data = await api(`/api/chats?q=${encodeURIComponent(query)}`);
  els.searchResults.innerHTML = "";
  if (!data.chats.length) { els.searchResults.innerHTML = `<div class="empty-small">Nada encontrado.</div>`; return; }
  data.chats.forEach((chat) => {
    const button = document.createElement("button");
    button.className = "search-result";
    button.innerHTML = `<strong>${escapeHtml(chat.title)}</strong><small>${chat.message_count} mensagens${chat.folder ? ` • ${escapeHtml(chat.folder)}` : ""}</small>`;
    button.addEventListener("click", () => { closeOverlays(); openChat(chat.id); });
    els.searchResults.appendChild(button);
  });
}

async function loadNotes() {
  const data = await api("/api/notes");
  state.notes = data.notes;
  renderNotes();
  if (!state.currentNote && state.notes[0]) selectNote(state.notes[0]);
  if (!state.notes.length) newNote();
}

function renderNotes() {
  els.notesList.innerHTML = "";
  state.notes.forEach((note) => {
    const button = document.createElement("button");
    button.className = `note-list-item ${state.currentNote?.id === note.id ? "active" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(note.title)}</strong><small>${new Date(note.updated_at * 1000).toLocaleString("pt-BR")}</small>`;
    button.addEventListener("click", () => selectNote(note));
    els.notesList.appendChild(button);
  });
}

function selectNote(note) { state.currentNote = note; els.noteTitle.value = note.title; els.noteContent.value = note.content; renderNotes(); }
function newNote() { state.currentNote = null; els.noteTitle.value = ""; els.noteContent.value = ""; els.noteTitle.focus(); renderNotes(); }
async function saveNote() {
  const data = await api("/api/notes", { method: "POST", body: JSON.stringify({ id: state.currentNote?.id || null, title: els.noteTitle.value, content: els.noteContent.value }) });
  state.currentNote = data.note;
  await loadNotes();
  toast("Nota salva.", "success");
}
async function deleteNote() {
  if (!state.currentNote || !confirm("Excluir esta nota?")) return;
  await api(`/api/notes/${state.currentNote.id}`, { method: "DELETE" });
  state.currentNote = null;
  await loadNotes();
}

function renderWorkspace() {
  els.workspaceGrid.innerHTML = "";
  const groups = new Map([["Sem pasta", []]]);
  state.folders.forEach((f) => groups.set(f, []));
  state.chats.forEach((chat) => {
    const key = chat.folder || "Sem pasta";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(chat);
  });
  let index = 0;
  for (const [folder, chats] of groups) {
    const card = document.createElement("button");
    card.className = "folder-card";
    card.innerHTML = `<span class="folder-dot" style="background:hsl(${(index++ * 67) % 360} 62% 62%)"></span><strong>${escapeHtml(folder)}</strong><small>${chats.length} conversa${chats.length === 1 ? "" : "s"}</small>`;
    card.addEventListener("click", async () => { closeOverlays(); await loadChats("", folder === "Sem pasta" ? "" : folder); });
    els.workspaceGrid.appendChild(card);
  }
}

async function refreshSystem(render = true) {
  try {
    const data = await api("/api/system");
    const gpu = data.gpus?.[0];
    els.gpuFooter.textContent = gpu ? `${gpu.name} • ${(gpu.memory_total_mb / 1024).toFixed(0)} GB` : "GPU não detectada";
    if (!render) return;
    const gpuCards = (data.gpus || []).map((item) => `<div class="system-card"><h3>${escapeHtml(item.name)}</h3><div class="metric-grid"><div class="metric"><small>VRAM</small><strong>${(item.memory_used_mb/1024).toFixed(1)} / ${(item.memory_total_mb/1024).toFixed(1)} GiB</strong></div><div class="metric"><small>Uso</small><strong>${item.utilization.toFixed(0)}%</strong></div><div class="metric"><small>Temperatura</small><strong>${item.temperature_c.toFixed(0)} °C</strong></div></div></div>`).join("");
    els.systemContent.innerHTML = `<div class="system-card"><h3>Computador</h3><div class="metric-grid"><div class="metric"><small>CPU</small><strong>${data.cpu_percent.toFixed(0)}%</strong></div><div class="metric"><small>RAM</small><strong>${data.ram_used_gib} / ${data.ram_total_gib} GiB</strong></div><div class="metric"><small>Python</small><strong>${escapeHtml(data.python)}</strong></div></div></div>${gpuCards || '<div class="notice"><strong>NVIDIA não detectada</strong><span>Verifique o driver e o comando nvidia-smi.</span></div>'}`;
  } catch {}
}

function startDictation(target) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { toast("Ditado não disponível neste navegador.", "error"); return; }
  const recognition = new SpeechRecognition();
  recognition.lang = "pt-BR";
  recognition.interimResults = true;
  let finalText = target.value;
  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalText += `${finalText ? " " : ""}${event.results[i][0].transcript}`;
      else interim += event.results[i][0].transcript;
    }
    target.value = `${finalText}${interim ? ` ${interim}` : ""}`;
    autoResize(target);
  };
  recognition.onerror = () => toast("Não foi possível usar o microfone.", "error");
  recognition.start();
}

function globalKeys(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openSearch(); }
  if (event.key === "Escape") { closeOverlays(); els.modelDropdown.classList.add("hidden"); }
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "o") { event.preventDefault(); document.body.classList.toggle("mobile-sidebar"); }
}

function autoResize(textarea) { textarea.style.height = "auto"; textarea.style.height = `${Math.min(170, textarea.scrollHeight)}px`; }
function scrollMessages(force) {
  const distance = els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight;
  if (force || distance < 180) els.messages.scrollTop = els.messages.scrollHeight;
}
function relativeGroup(timestamp) {
  const date = new Date(timestamp * 1000); const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = Math.round((start - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000);
  if (day <= 0) return "Hoje"; if (day === 1) return "Ontem"; if (day < 7) return "Últimos 7 dias"; if (day < 30) return "Últimos 30 dias"; return date.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
}
function debounce(fn, wait) { let id; return (...args) => { clearTimeout(id); id = setTimeout(() => fn(...args), wait); }; }
function toast(message, type = "") {
  const item = document.createElement("div"); item.className = `toast ${type}`; item.textContent = message; els.toastStack.appendChild(item);
  setTimeout(() => item.remove(), 4500);
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;" }[char])); }

function renderMarkdown(markdown) {
  if (!markdown) return "";
  const codes = [];
  let text = String(markdown).replace(/```([\w.+-]*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const index = codes.length;
    codes.push(`<div class="code-block"><div class="code-head"><span>${escapeHtml(lang || "código")}</span><button data-copy-code>Copiar</button></div><pre><code>${escapeHtml(code.replace(/^\n|\n$/g, ""))}</code></pre></div>`);
    return `\n@@CODE_${index}@@\n`;
  });
  text = escapeHtml(text);
  text = text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  const lines = text.split("\n");
  const out = [];
  let listType = null;
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^@@CODE_\d+@@$/.test(line.trim())) {
      if (listType) { out.push(`</${listType}>`); listType = null; }
      out.push(line.trim()); continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    if (heading) {
      if (listType) { out.push(`</${listType}>`); listType = null; }
      const n = heading[1].length; out.push(`<h${n}>${heading[2]}</h${n}>`); continue;
    }
    const ul = line.match(/^[-*]\s+(.+)/); const ol = line.match(/^\d+[.)]\s+(.+)/);
    if (ul || ol) {
      const type = ul ? "ul" : "ol";
      if (listType !== type) { if (listType) out.push(`</${listType}>`); out.push(`<${type}>`); listType = type; }
      out.push(`<li>${(ul || ol)[1]}</li>`); continue;
    }
    if (listType) { out.push(`</${listType}>`); listType = null; }
    if (!line.trim()) { out.push(""); continue; }
    if (line.startsWith("&gt; ")) out.push(`<blockquote>${line.slice(5)}</blockquote>`);
    else out.push(`<p>${line}</p>`);
  }
  if (listType) out.push(`</${listType}>`);
  let html = out.join("").replace(/<p>@@CODE_(\d+)@@<\/p>|@@CODE_(\d+)@@/g, (_m, a, b) => codes[Number(a ?? b)] || "");
  return html;
}
