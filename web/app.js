const TOOL_DEFINITIONS = [
  {
    id: "douyin-video",
    label: "抖音去水印",
    category: "抖音",
    description: "粘贴 v.douyin.com 短链，获取可用分辨率，预览并下载无水印视频。",
    badge: "已接入",
    viewSelector: '[data-tool-view="douyin-video"]',
    controller: initDouyinVideoTool,
  },
  {
    id: "token-converter",
    label: "Token 格式互转",
    category: "开发",
    description: "Codex auth.json、CPA、Sub2API 三向互转，纯前端离线运行。",
    badge: "离线",
    viewSelector: '[data-tool-view="token-converter"]',
    controller: initTokenConverterTool,
  },
];

const toolTabs = document.getElementById("toolTabs");
const toolGrid = document.getElementById("toolGrid");
const toolViews = [...document.querySelectorAll("[data-tool-view]")];
const controllers = new Map();

bootstrapToolbox();

function bootstrapToolbox() {
  renderToolTabs();
  renderToolGrid();
  TOOL_DEFINITIONS.forEach((tool) => {
    controllers.set(tool.id, tool.controller());
  });
  window.addEventListener("popstate", () => {
    activateTool(getToolFromUrl(), { updateUrl: false });
  });
  activateTool(getToolFromUrl(), { updateUrl: false });
}

function renderToolTabs() {
  toolTabs.replaceChildren();
  const homeButton = document.createElement("button");
  homeButton.type = "button";
  homeButton.className = "tool-tab";
  homeButton.dataset.tool = "home";
  homeButton.textContent = "工具集合";
  homeButton.addEventListener("click", () => activateTool("home"));
  toolTabs.appendChild(homeButton);

  TOOL_DEFINITIONS.forEach((tool) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tool-tab";
    button.dataset.tool = tool.id;
    button.textContent = tool.label;
    button.addEventListener("click", () => activateTool(tool.id));
    toolTabs.appendChild(button);
  });
}

function renderToolGrid() {
  toolGrid.replaceChildren();
  TOOL_DEFINITIONS.forEach((tool) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tool-card";
    button.dataset.tool = tool.id;
    button.innerHTML = `
      <span class="tool-card-kicker">${escapeHtml(tool.category)}</span>
      <strong>${escapeHtml(tool.label)}</strong>
      <span class="tool-card-desc">${escapeHtml(tool.description)}</span>
      <span class="tool-card-footer">
        <span>${escapeHtml(tool.badge)}</span>
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="M5 12h12m0 0-5-5m5 5-5 5" />
        </svg>
      </span>
    `;
    button.addEventListener("click", () => activateTool(tool.id));
    toolGrid.appendChild(button);
  });
}

function getToolFromUrl() {
  const toolId = new URLSearchParams(window.location.search).get("tool");
  return TOOL_DEFINITIONS.some((tool) => tool.id === toolId) ? toolId : "home";
}

function activateTool(toolId, options = {}) {
  const activeTool = TOOL_DEFINITIONS.find((tool) => tool.id === toolId);
  const activeId = activeTool?.id || "home";
  if (options.updateUrl !== false) {
    updateToolUrl(activeId);
  }
  [...toolTabs.querySelectorAll(".tool-tab")].forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tool === activeId);
    tab.hidden = activeId === "home" && tab.dataset.tool !== "home";
  });
  toolViews.forEach((view) => {
    view.hidden = view.dataset.toolView !== activeId;
  });
  if (activeTool) {
    controllers.get(activeTool.id)?.onActivate?.();
  }
}

function updateToolUrl(toolId) {
  const url = new URL(window.location.href);
  if (toolId === "home") {
    url.searchParams.delete("tool");
  } else {
    url.searchParams.set("tool", toolId);
  }
  window.history.pushState({ tool: toolId }, "", url);
}

function initDouyinVideoTool() {
  const form = document.getElementById("resolveForm");
  const resultTabs = document.getElementById("resultTabs");
  const resultPanels = [...document.querySelectorAll("[data-result-panel]")];
  const imageTabBtn = document.getElementById("imageTabBtn");
  const shareInput = document.getElementById("shareInput");
  const submitBtn = document.getElementById("submitBtn");
  const clearBtn = document.getElementById("clearBtn");
  const statusBox = document.getElementById("statusBox");
  const statusText = document.getElementById("statusText");
  const errorBox = document.getElementById("errorBox");
  const metaLine = document.getElementById("metaLine");
  const qualityBar = document.getElementById("qualityBar");
  const videoPreview = document.getElementById("videoPreview");
  const emptyPreview = document.getElementById("emptyPreview");
  const downloadBtn = document.getElementById("downloadBtn");
  const copyBtn = document.getElementById("copyBtn");
  const currentRatio = document.getElementById("currentRatio");
  const currentSize = document.getElementById("currentSize");
  const currentBitrate = document.getElementById("currentBitrate");
  const currentUrl = document.getElementById("currentUrl");
  const downloadProgress = document.getElementById("downloadProgress");
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");
  const coverPreview = document.getElementById("coverPreview");
  const captionText = document.getElementById("captionText");
  const captionMeta = document.getElementById("captionMeta");

  let currentResult = null;
  let selectedVariant = null;
  let activeResultTab = "video";

  resultTabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-result-tab]");
    if (!button) {
      return;
    }
    setResultTab(button.dataset.resultTab);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = normalizeShareInput();
    if (!input) {
      showError("仅支持 https://v.douyin.com 开头的抖音短链");
      setStatus("输入不符合要求", false);
      return;
    }

    setLoading(true);
    showError("");
    setStatus("正在解析分享页和视频分辨率", true);
    resetResult(false);

    try {
      const response = await fetch("/api/douyin/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "解析失败");
      }
      renderResult(data);
      setStatus(`已解析 ${data.variants.length} 个可用分辨率`, false);
    } catch (error) {
      resetResult(true);
      showError(error.message || String(error));
      setStatus("解析失败", false);
    } finally {
      setLoading(false);
    }
  });

  clearBtn.addEventListener("click", () => {
    shareInput.value = "";
    shareInput.focus();
    resetResult(true);
    showError("");
    setStatus("等待输入", false);
  });

  shareInput.addEventListener("paste", () => {
    window.setTimeout(() => {
      normalizeShareInput();
    });
  });

  shareInput.addEventListener("blur", () => {
    normalizeShareInput();
  });

  downloadBtn.addEventListener("click", () => {
    if (selectedVariant) {
      downloadSelected(selectedVariant);
    }
  });

  copyBtn.addEventListener("click", async () => {
    if (!selectedVariant) {
      return;
    }
    try {
      await copyText(selectedVariant.url, currentUrl);
      setStatus("已复制当前分辨率地址", false);
    } catch (error) {
      showError("复制失败，请手动选择地址");
    }
  });

  videoPreview.addEventListener("error", () => {
    if (selectedVariant) {
      setStatus("视频预览加载失败，请重新解析后再试", false);
    }
  });

  function renderResult(data) {
    currentResult = data;
    if (data.input_url) {
      shareInput.value = data.input_url;
    }
    metaLine.textContent = [data.author, data.title].filter(Boolean).join(" · ") || data.aweme_id;
    captionText.textContent = data.title || "未解析到文案";
    captionMeta.textContent = [data.author, data.aweme_id].filter(Boolean).join(" · ") || "未解析";
    imageTabBtn.hidden = !data.cover;
    coverPreview.src = data.cover || "";
    coverPreview.alt = data.title ? `视频封面：${data.title}` : "视频封面";

    qualityBar.replaceChildren();
    data.variants.forEach((variant) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "quality-btn";
      button.dataset.id = variant.id;
      button.innerHTML = `
        <strong>${escapeHtml(variant.ratio)}</strong>
        <span>${formatBytes(variant.size)} · ${formatBitrate(variant)}</span>
      `;
      button.addEventListener("click", () => selectVariant(variant));
      qualityBar.appendChild(button);
    });

    const preferred = data.variants.find((item) => item.ratio === "1080p") || data.variants[0];
    selectVariant(preferred);
    setResultTab("video");
  }

  function selectVariant(variant) {
    selectedVariant = variant;
    [...qualityBar.querySelectorAll(".quality-btn")].forEach((button) => {
      button.classList.toggle("active", button.dataset.id === variant.id);
    });

    currentRatio.textContent = variant.ratio;
    currentSize.textContent = formatBytes(variant.size);
    currentBitrate.textContent = formatBitrate(variant);
    currentUrl.value = variant.url;
    downloadBtn.disabled = false;
    copyBtn.disabled = false;
    emptyPreview.classList.add("hidden");

    videoPreview.poster = currentResult?.cover || "";
    videoPreview.src = variant.media_url;
    videoPreview.load();
  }

  async function downloadSelected(variant) {
    downloadBtn.disabled = true;
    downloadProgress.hidden = false;
    progressBar.style.width = "0";
    progressText.textContent = "准备下载";
    setStatus(`正在下载 ${variant.ratio}`, true);

    try {
      const response = await fetch(variant.download_url);
      if (!response.ok) {
        let message = `下载失败: HTTP ${response.status}`;
        try {
          const data = await response.json();
          message = data.error || message;
        } catch (_) {
          // 保留 HTTP 错误信息。
        }
        throw new Error(message);
      }

      const total = Number(response.headers.get("Content-Length") || variant.size || 0);
      const blob = response.body ? await readStreamAsBlob(response, total) : await response.blob();

      saveBlob(blob, variant.filename || `douyin_${variant.ratio}.mp4`);
      progressBar.style.width = "100%";
      progressText.textContent = "下载完成";
      setStatus("下载已触发保存", false);
    } catch (error) {
      showError(error.message || String(error));
      setStatus("下载失败", false);
    } finally {
      downloadBtn.disabled = false;
    }
  }

  async function readStreamAsBlob(response, total) {
    const reader = response.body.getReader();
    const chunks = [];
    let received = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      chunks.push(value);
      received += value.length;
      if (total > 0) {
        const percent = Math.min(100, Math.round((received / total) * 100));
        progressBar.style.width = `${percent}%`;
        progressText.textContent = `${percent}%`;
      } else {
        progressText.textContent = `${formatBytes(received)}`;
      }
    }

    return new Blob(chunks, {
      type: response.headers.get("Content-Type") || "video/mp4",
    });
  }

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    submitBtn.querySelector("span").textContent = isLoading ? "解析中" : "解析视频";
  }

  function setStatus(message, loading) {
    statusText.textContent = message;
    statusBox.classList.toggle("loading", loading);
  }

  function showError(message) {
    errorBox.hidden = !message;
    errorBox.textContent = message;
  }

  function resetResult(includeMeta) {
    currentResult = null;
    selectedVariant = null;
    qualityBar.replaceChildren();
    videoPreview.removeAttribute("src");
    videoPreview.removeAttribute("poster");
    videoPreview.load();
    emptyPreview.classList.remove("hidden");
    downloadBtn.disabled = true;
    copyBtn.disabled = true;
    currentRatio.textContent = "-";
    currentSize.textContent = "-";
    currentBitrate.textContent = "-";
    currentUrl.value = "";
    imageTabBtn.hidden = true;
    coverPreview.removeAttribute("src");
    coverPreview.alt = "视频封面";
    captionText.textContent = "解析后显示文案";
    captionMeta.textContent = "未解析";
    downloadProgress.hidden = true;
    progressBar.style.width = "0";
    progressText.textContent = "准备下载";
    setResultTab("video");
    if (includeMeta) {
      metaLine.textContent = "未解析";
    }
  }

  function setResultTab(tabName) {
    if (tabName === "image" && imageTabBtn.hidden) {
      tabName = "video";
    }
    activeResultTab = tabName;
    [...resultTabs.querySelectorAll(".result-tab")].forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.resultTab === tabName);
    });
    resultPanels.forEach((panel) => {
      panel.hidden = panel.dataset.resultPanel !== tabName;
    });
  }

  function normalizeShareInput() {
    const url = extractDouyinShortUrl(shareInput.value);
    if (!url) {
      return "";
    }
    shareInput.value = url;
    return url;
  }

  return {
    onActivate() {
      setResultTab(activeResultTab);
      shareInput.focus({ preventScroll: true });
    },
  };
}

function initTokenConverterTool() {
  return {};
}

function extractDouyinShortUrl(text) {
  const match = String(text || "").match(/https?:\/\/[^\s，。！？、；;]+/);
  if (!match) {
    return "";
  }
  const rawUrl = match[0].replace(/[.,;:!?，。；：！？）)\]}]+$/g, "");
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:" || url.hostname !== "v.douyin.com") {
      return "";
    }
    return url.href;
  } catch (_) {
    return "";
  }
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function copyText(text, fallbackInput) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  fallbackInput.select();
  document.execCommand("copy");
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function formatBitrate(variant) {
  const value = variant.br || variant.bt;
  return value ? `${value} kbps` : "-";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
