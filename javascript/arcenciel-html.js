// arcenciel-html.js

console.log("ArcEnCiel extension JS loaded!");

/**
 * Utility to get the root of Gradio's DOM (if using shadowRoot).
 */
function getGradioAppRoot() {
  const gradioApp = document.querySelector("gradio-app");
  return gradioApp?.shadowRoot || document;
}

function arcencielQuerySelector(selector) {
  const root = getGradioAppRoot();
  return root?.querySelector(selector) || document.querySelector(selector);
}

function arcencielEscapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function arcencielSetInputValue(input, value) {
  if (!input || value === undefined || value === null || value === "")
    return false;
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function arcencielNormalizeSampler(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/_gpu\b/g, "")
    .replace(/^dpmpp/, "dpm++")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function arcencielSetSampler(root, sampler) {
  if (!sampler) return false;
  const samplerSelect = root.querySelector("#txt2img_sampling select");
  if (!samplerSelect) return false;

  const normalized = arcencielNormalizeSampler(sampler);
  const option = Array.from(samplerSelect.options || []).find((entry) => {
    return (
      entry.value === sampler ||
      entry.textContent === sampler ||
      arcencielNormalizeSampler(entry.value) === normalized ||
      arcencielNormalizeSampler(entry.textContent) === normalized
    );
  });

  if (!option) {
    console.warn("ArcEnCiel: sampler not found in txt2img dropdown", sampler);
    return false;
  }

  samplerSelect.value = option.value;
  samplerSelect.dispatchEvent(new Event("input", { bubbles: true }));
  samplerSelect.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function arcencielSetDownloadStatus(button, text, isError = false) {
  const versionBlock = button.closest(".version_block");
  const status = versionBlock?.querySelector(".arcen_download_status");
  if (!status) return;
  status.textContent = text || "";
  status.style.color = isError ? "#ff8a8a" : "#9ee493";
}

function arcencielPollDownloadStatus(jobId, button) {
  if (!jobId || !button) return;
  const poll = () => {
    fetch(`/arcenciel/download_status/${encodeURIComponent(jobId)}`)
      .then((resp) => resp.json())
      .then((data) => {
        if (data?.error) {
          arcencielSetDownloadStatus(button, data.error, true);
          button.disabled = false;
          return;
        }
        const state = data.state || "UNKNOWN";
        const progress = Number.isFinite(data.progress) ? data.progress : 0;
        const suffix = progress ? ` (${progress}%)` : "";
        arcencielSetDownloadStatus(
          button,
          data.message || `${state}${suffix}`,
          state === "ERROR",
        );
        if (["DONE", "ERROR", "CANCELED"].includes(state)) {
          button.disabled = false;
          arcencielRefreshDownloadHistory();
          return;
        }
        setTimeout(poll, 1000);
      })
      .catch((err) => {
        console.error("ArcEnCiel: download status fetch error:", err);
        arcencielSetDownloadStatus(button, "Status polling failed.", true);
        button.disabled = false;
      });
  };
  setTimeout(poll, 500);
}

function arcencielFormatTimestamp(timestamp) {
  const seconds = Number(timestamp || 0);
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleString();
}

function arcencielRenderDownloadHistory(jobs) {
  const panel = arcencielQuerySelector("#arcenciel_download_history_live");
  if (!panel) return;

  if (!Array.isArray(jobs) || jobs.length === 0) {
    panel.innerHTML =
      '<div class="arcen_download_empty">No downloads yet.</div>';
    return;
  }

  const rows = jobs
    .map((job) => {
      const state = String(job.state || "UNKNOWN").toUpperCase();
      const active = ["QUEUED", "DOWNLOADING", "RETRYING", "SIDECARS"].includes(
        state,
      );
      const retriable = ["ERROR", "CANCELED"].includes(state);
      const progress = Number.isFinite(job.progress) ? job.progress : 0;
      const actions = [];
      if (active) {
        actions.push(
          `<button type="button" class="arcen_download_action" data-action="cancel" data-job-id="${arcencielEscapeHtml(job.job_id)}">Cancel</button>`,
        );
      }
      if (retriable) {
        actions.push(
          `<button type="button" class="arcen_download_action" data-action="retry" data-job-id="${arcencielEscapeHtml(job.job_id)}">Retry</button>`,
        );
      }
      return `
        <tr class="arcen_download_row state-${arcencielEscapeHtml(state.toLowerCase())}">
          <td>
            <div class="arcen_download_file">${arcencielEscapeHtml(job.file_name || job.path || job.job_id)}</div>
            <div class="arcen_download_path">${arcencielEscapeHtml(job.path || "")}</div>
          </td>
          <td><span class="arcen_download_state">${arcencielEscapeHtml(state)}</span></td>
          <td>
            <div class="arcen_download_progress"><span style="width:${Math.max(0, Math.min(100, progress))}%"></span></div>
            <div class="arcen_download_progress_text">${progress}%</div>
          </td>
          <td>${arcencielEscapeHtml(job.message || "")}</td>
          <td>${arcencielEscapeHtml(arcencielFormatTimestamp(job.updated_at || job.created_at))}</td>
          <td>${actions.join(" ")}</td>
        </tr>
      `;
    })
    .join("");

  panel.innerHTML = `
    <table class="arcen_download_table">
      <thead>
        <tr>
          <th>File</th>
          <th>Status</th>
          <th>Progress</th>
          <th>Message</th>
          <th>Updated</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function arcencielRefreshDownloadHistory() {
  const panel = arcencielQuerySelector("#arcenciel_download_history_live");
  if (!panel) return;

  fetch("/arcenciel/downloads")
    .then((resp) => resp.json())
    .then((data) => {
      arcencielRenderDownloadHistory(data?.jobs || []);
    })
    .catch((err) => {
      console.error("ArcEnCiel: download history fetch error:", err);
      panel.innerHTML =
        '<div class="arcen_download_empty error">Failed to load download history.</div>';
    });
}

function arcencielRunDownloadAction(action, jobId) {
  if (!["cancel", "retry"].includes(action) || !jobId) return;
  const url =
    action === "cancel"
      ? `/arcenciel/download_cancel/${encodeURIComponent(jobId)}`
      : `/arcenciel/download_retry/${encodeURIComponent(jobId)}`;
  fetch(url, { method: "POST" })
    .then((resp) => resp.json().catch(() => ({})))
    .then(() => arcencielRefreshDownloadHistory())
    .catch((err) => console.error("ArcEnCiel: download action failed:", err));
}

function arcencielLoadSubfolders(input) {
  if (!input) return;
  const listId = input.getAttribute("list");
  const datalist = listId ? document.getElementById(listId) : null;
  if (!datalist || datalist.getAttribute("data-loaded") === "true") return;
  const modelType = input.getAttribute("data-model-type") || "OTHER";
  fetch(`/arcenciel/folders/${encodeURIComponent(modelType)}`)
    .then((resp) => resp.json())
    .then((data) => {
      if (!Array.isArray(data?.folders)) return;
      datalist.innerHTML = "";
      data.folders.forEach((folder) => {
        const option = document.createElement("option");
        option.value = folder;
        datalist.appendChild(option);
      });
      datalist.setAttribute("data-loaded", "true");
    })
    .catch((err) => console.warn("ArcEnCiel: subfolder load failed", err));
}

/**
 * Fills txt2img fields in stable-diffusion-webui:
 * prompt, negative prompt, steps, sampler, cfg, seed, etc.
 */
function arcencielSendToTxt2Img({
  prompt,
  negPrompt,
  sampler,
  seed,
  steps,
  cfg,
}) {
  const root = getGradioAppRoot();
  if (!root) {
    console.warn(
      "ArcEnCiel: Could not find gradio app root to set txt2img fields!",
    );
    return;
  }

  // txt2img prompt
  const txt2imgPrompt = root.querySelector("#txt2img_prompt textarea");
  arcencielSetInputValue(txt2imgPrompt, prompt);

  // negative prompt
  const txt2imgNegPrompt = root.querySelector("#txt2img_neg_prompt textarea");
  arcencielSetInputValue(txt2imgNegPrompt, negPrompt);

  // Steps => #txt2img_steps input[type='number']
  if (steps) {
    const stepsInput = root.querySelector(
      "#txt2img_steps input[type='number']",
    );
    arcencielSetInputValue(stepsInput, steps);
  }

  // Sampler => #txt2img_sampling select
  arcencielSetSampler(root, sampler);

  // CFG => #txt2img_cfg_scale input[type='number']
  if (cfg) {
    const cfgInput = root.querySelector(
      "#txt2img_cfg_scale input[type='number']",
    );
    arcencielSetInputValue(cfgInput, cfg);
  }

  // Seed => #txt2img_seed input[type='number']
  if (seed) {
    const seedInput = root.querySelector("#txt2img_seed input[type='number']");
    arcencielSetInputValue(seedInput, seed);
  }

  console.log("ArcEnCiel: set txt2img fields", {
    prompt,
    negPrompt,
    sampler,
    seed,
    steps,
    cfg,
  });
}

// ----------------------------------------------------------------------
// Event listeners
// ----------------------------------------------------------------------

document.addEventListener("click", function (e) {
  const refreshDownloadsBtn = e.target.closest(
    "#arcenciel_download_refresh_btn",
  );
  if (refreshDownloadsBtn) {
    e.preventDefault();
    arcencielRefreshDownloadHistory();
    return;
  }

  const cancelAllDownloadsBtn = e.target.closest(
    "#arcenciel_download_cancel_all_btn",
  );
  if (cancelAllDownloadsBtn) {
    e.preventDefault();
    fetch("/arcenciel/download_cancel_all", { method: "POST" })
      .then(() => arcencielRefreshDownloadHistory())
      .catch((err) =>
        console.error("ArcEnCiel: cancel all downloads failed:", err),
      );
    return;
  }

  const downloadActionBtn = e.target.closest(".arcen_download_action");
  if (downloadActionBtn) {
    e.preventDefault();
    arcencielRunDownloadAction(
      downloadActionBtn.getAttribute("data-action"),
      downloadActionBtn.getAttribute("data-job-id"),
    );
    return;
  }

  // 1) "Download with Extension" button
  const extBtn = e.target.closest(".arcen_extension_download_btn");
  if (extBtn) {
    e.preventDefault();
    const modelId = extBtn.getAttribute("data-model-id");
    const versionId = extBtn.getAttribute("data-version-id");
    const modelType = extBtn.getAttribute("data-model-type");
    const downloadUrl = extBtn.getAttribute("data-download-url");
    const fileName = extBtn.getAttribute("data-file-name");

    if (!downloadUrl) {
      arcencielSetDownloadStatus(extBtn, "No download URL available.", true);
      return;
    }

    // Find the subfolder input inside the same 'version_block' container
    let versionBlock = extBtn.closest(".version_block");
    let subfolderVal = "";
    if (versionBlock) {
      const subInput = versionBlock.querySelector(".arcen_subfolder_input");
      if (subInput) {
        subfolderVal = subInput.value.trim();
      }
    }

    console.log("ArcEnCiel: extension download =>", {
      modelId,
      versionId,
      modelType,
      downloadUrl,
      fileName,
      subfolder: subfolderVal,
    });

    extBtn.disabled = true;
    arcencielSetDownloadStatus(extBtn, "Queueing...");

    // Now pass 'subfolder: subfolderVal' to the server route
    fetch("/arcenciel/download_with_extension", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_id: modelId,
        version_id: versionId,
        model_type: modelType,
        url: downloadUrl,
        file_name: fileName,
        subfolder: subfolderVal,
      }),
    })
      .then((resp) => {
        if (!resp.ok) {
          console.error(
            "Extension download route error:",
            resp.status,
            resp.statusText,
          );
          return resp
            .json()
            .catch(() => ({ error: `Error: ${resp.statusText}` }));
        }
        return resp.json().catch(() => ({}));
      })
      .then((data) => {
        if (data?.error) {
          arcencielSetDownloadStatus(extBtn, data.error, true);
          extBtn.disabled = false;
          return;
        }
        arcencielSetDownloadStatus(extBtn, data?.message || "Queued.");
        arcencielRefreshDownloadHistory();
        if (data?.job_id) {
          arcencielPollDownloadStatus(data.job_id, extBtn);
        } else {
          extBtn.disabled = false;
        }
      })
      .catch((err) => {
        console.error("ArcEnCiel: extension download fetch error:", err);
        arcencielSetDownloadStatus(extBtn, "Request failed.", true);
        extBtn.disabled = false;
      });

    return;
  }

  // 2) If user clicked a gallery image
  const galItem = e.target.closest(".arcen_gallery_item");
  if (galItem) {
    const imgId = galItem.getAttribute("data-image-id");
    if (imgId) {
      fetch(`/arcenciel/image_details/${imgId}`)
        .then((resp) => resp.text())
        .then((html) => {
          const panel = document.querySelector("#arcen_image_details_panel");
          if (!panel) {
            console.warn("Could not find #arcen_image_details_panel");
            return;
          }
          panel.innerHTML = html;
        })
        .catch((err) => console.error("Error fetching image details:", err));
    } else {
      console.warn("ArcEnCiel: gallery item has no image id");
    }
    return;
  }

  // 3) If user clicked a model card
  const card = e.target.closest(".arcen_model_card");
  if (card) {
    const modelId = card.getAttribute("data-model-id");
    if (!modelId) return;

    const detailsDiv = document.querySelector("#arcenciel_model_details_html");
    if (detailsDiv) {
      detailsDiv.innerHTML = "<div>Loading model details...</div>";
    }

    fetch(`/arcenciel/model_details/${modelId}`)
      .then((response) => response.text())
      .then((html) => {
        if (!detailsDiv) {
          console.warn("Could not find #arcenciel_model_details_html");
          return;
        }
        detailsDiv.innerHTML = html;
      })
      .catch((err) => console.error("Failed to fetch model details:", err));
    return;
  }

  // 4) "Send to txt2img" button
  const sendBtn = e.target.closest(".arcen_send_to_txt2img_btn");
  if (sendBtn) {
    e.stopPropagation();
    const prompt = sendBtn.getAttribute("data-prompt") || "";
    const negPrompt = sendBtn.getAttribute("data-neg-prompt") || "";
    const sampler = sendBtn.getAttribute("data-sampler") || "";
    const seed = sendBtn.getAttribute("data-seed") || "";
    const steps = sendBtn.getAttribute("data-steps") || "";
    const cfg = sendBtn.getAttribute("data-cfg") || "";

    arcencielSendToTxt2Img({ prompt, negPrompt, sampler, seed, steps, cfg });
    return;
  }
});

document.addEventListener("focusin", function (e) {
  const subfolderInput = e.target.closest?.(".arcen_subfolder_input");
  if (subfolderInput) {
    arcencielLoadSubfolders(subfolderInput);
  }
});

// Listen for gear-button clicks, toggle the popup
document.addEventListener("click", function (e) {
  const settingsBtn = e.target.closest("#arcenciel_settings_button");
  if (settingsBtn) {
    e.stopPropagation();
    const popup = document.getElementById("arcenciel_settings_popup");
    if (popup) {
      popup.style.display = popup.style.display === "block" ? "none" : "block";
    }
    return;
  }
});

// Optionally hide if user clicks outside the popup
document.addEventListener("click", function (e) {
  const popup = document.getElementById("arcenciel_settings_popup");
  const settingsBtn = document.getElementById("arcenciel_settings_button");
  if (!popup || !settingsBtn) return;

  if (popup.style.display === "block") {
    const clickInside =
      popup.contains(e.target) || settingsBtn.contains(e.target);
    if (!clickInside) {
      popup.style.display = "none";
    }
  }
});

// ----------------------------------------------------------------------
// Automatic slider re-styling code, for card scale
// ----------------------------------------------------------------------
function setupArcencielSliderObserver() {
  const root = getGradioAppRoot();
  if (!root) return;

  const sliderWrapper = root.getElementById("arcenciel_card_scale_slider");
  if (!sliderWrapper) {
    setTimeout(setupArcencielSliderObserver, 1000);
    return;
  }
  const rangeInput = sliderWrapper.querySelector("input[type='range']");
  if (!rangeInput) {
    setTimeout(setupArcencielSliderObserver, 1000);
    return;
  }

  console.log("ArcEnCiel: Found the card scale slider:", rangeInput);

  let styleTag = document.getElementById("arcen_model_card_dynamic_style");
  if (!styleTag) {
    styleTag = document.createElement("style");
    styleTag.id = "arcen_model_card_dynamic_style";
    document.head.appendChild(styleTag);
  }

  rangeInput.addEventListener("input", (event) => {
    const val = parseFloat(event.target.value) || 30;
    const height = Math.round(val * 1.5);
    styleTag.textContent = `
        .arcen_model_card {
          width: ${val}em !important;
          height: ${height}em !important;
        }
      `;
  });
}

// Kick off the slider observer after a short delay
setTimeout(() => {
  setupArcencielSliderObserver();
  arcencielRefreshDownloadHistory();
}, 1000);

setInterval(() => {
  arcencielRefreshDownloadHistory();
}, 2500);
