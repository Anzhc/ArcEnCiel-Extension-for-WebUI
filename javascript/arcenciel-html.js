// arcenciel-html.js

console.log("ArcEnCiel extension JS loaded!");

/**
 * Utility to get the root of Gradio's DOM (if using shadowRoot).
 */
function getGradioAppRoot() {
    const gradioApp = document.querySelector('gradio-app');
    return gradioApp?.shadowRoot || document;
}

/**
 * Fills txt2img fields in stable-diffusion-webui:
 * prompt, negative prompt, steps, sampler, cfg, seed, etc.
 */
function arcencielSendToTxt2Img({prompt, negPrompt, sampler, seed, steps, cfg}) {
    const root = getGradioAppRoot();
    if (!root) {
        console.warn("ArcEnCiel: Could not find gradio app root to set txt2img fields!");
        return;
    }

    // txt2img prompt
    const txt2imgPrompt = root.querySelector("#txt2img_prompt textarea");
    if (txt2imgPrompt && prompt) {
        txt2imgPrompt.value = prompt;
        txt2imgPrompt.dispatchEvent(new Event("input", {bubbles: true}));
    }

    // negative prompt
    const txt2imgNegPrompt = root.querySelector("#txt2img_neg_prompt textarea");
    if (txt2imgNegPrompt && negPrompt) {
        txt2imgNegPrompt.value = negPrompt;
        txt2imgNegPrompt.dispatchEvent(new Event("input", {bubbles: true}));
    }

    // Steps => #txt2img_steps input[type='number']
    if (steps) {
        const stepsInput = root.querySelector("#txt2img_steps input[type='number']");
        if (stepsInput) {
            stepsInput.value = steps;
            stepsInput.dispatchEvent(new Event("input", {bubbles: true}));
        }
    }

    // Sampler => #txt2img_sampling select
    if (sampler) {
        const samplerSelect = root.querySelector("#txt2img_sampling select");
        if (samplerSelect) {
            samplerSelect.value = sampler;
            samplerSelect.dispatchEvent(new Event("input", {bubbles: true}));
        }
    }

    // CFG => #txt2img_cfg_scale input[type='number']
    if (cfg) {
        const cfgInput = root.querySelector("#txt2img_cfg_scale input[type='number']");
        if (cfgInput) {
            cfgInput.value = cfg;
            cfgInput.dispatchEvent(new Event("input", {bubbles: true}));
        }
    }

    // Seed => #txt2img_seed input[type='number']
    if (seed) {
        const seedInput = root.querySelector("#txt2img_seed input[type='number']");
        if (seedInput) {
            seedInput.value = seed;
            seedInput.dispatchEvent(new Event("input", {bubbles: true}));
        }
    }

    console.log("ArcEnCiel: set txt2img fields", {prompt, negPrompt, sampler, seed, steps, cfg});
}

// ----------------------------------------------------------------------
// Existing event listeners
// ----------------------------------------------------------------------

document.addEventListener("click", function (e) {
    // 1) "Download with Extension" button
    const extBtn = e.target.closest(".arcen_extension_download_btn");
    if (extBtn) {
        const modelId = extBtn.getAttribute("data-model-id");
        const versionId = extBtn.getAttribute("data-version-id");
        const modelType = extBtn.getAttribute("data-model-type");
        const downloadUrl = extBtn.getAttribute("data-download-url");
        const fileName = extBtn.getAttribute("data-file-name");

        console.log("ArcEnCiel: extension download =>", {
            modelId, versionId, modelType, downloadUrl, fileName
        });

        fetch("/arcenciel/download_with_extension", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model_id: modelId,
                version_id: versionId,
                model_type: modelType,
                url: downloadUrl,
                file_name: fileName
            })
        })
        .then(resp => {
            if (!resp.ok) {
                console.error("Extension download route error:", resp.status, resp.statusText);
                return {message: `Error: ${resp.statusText}`};
            }
            return resp.json().catch(() => ({}));
        })
        .then(data => {
            // console.log("ArcEnCiel: extension download response:", data);
        })
        .catch(err => console.error("ArcEnCiel: extension download fetch error:", err));

        return;
    }

    // 2) If user clicked a gallery image
    const galItem = e.target.closest(".arcen_gallery_item");
    if (galItem) {
        const imgId = galItem.getAttribute("data-image-id");
        if (imgId) {
            fetch(`/arcenciel/image_details/${imgId}`)
                .then(resp => resp.text())
                .then(html => {
                    const panel = document.querySelector("#arcen_image_details_panel");
                    if (!panel) {
                        console.warn("Could not find #arcen_image_details_panel");
                        return;
                    }
                    panel.innerHTML = html;
                })
                .catch(err => console.error("Error fetching image details:", err));
        }
        return; 
    }

    // 3) If user clicked a model card
    const card = e.target.closest(".arcen_model_card");
    if (card) {
        const modelId = card.getAttribute("data-model-id");
        if (!modelId) return;

        fetch(`/arcenciel/model_details/${modelId}`)
            .then(response => response.text())
            .then(html => {
                const detailsDiv = document.querySelector("#arcenciel_model_details_html");
                if (!detailsDiv) {
                    console.warn("Could not find #arcenciel_model_details_html");
                    return;
                }
                detailsDiv.innerHTML = html;
            })
            .catch(err => console.error("Failed to fetch model details:", err));
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

        arcencielSendToTxt2Img({prompt, negPrompt, sampler, seed, steps, cfg});
        return;
    }
});

// Listen for gear-button clicks, toggle the popup
document.addEventListener("click", function (e) {
    const settingsBtn = e.target.closest("#arcenciel_settings_button");
    if (settingsBtn) {
        e.stopPropagation();
        const popup = document.getElementById("arcenciel_settings_popup");
        if (popup) {
            popup.style.display = (popup.style.display === "block") ? "none" : "block";
        }
        return;
    }
});

// Optionally hide if user clicks outside the popup
document.addEventListener("click", function(e) {
    const popup = document.getElementById("arcenciel_settings_popup");
    const settingsBtn = document.getElementById("arcenciel_settings_button");
    if (!popup || !settingsBtn) return;

    if (popup.style.display === "block") {
        const clickInside = popup.contains(e.target) || settingsBtn.contains(e.target);
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

setTimeout(() => {
  setupArcencielSliderObserver();
}, 1000);
