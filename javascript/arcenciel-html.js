// arcenciel-html.js

console.log("ArcEnCiel extension JS loaded!");

document.addEventListener("click", function (e) {
    // 1) If user clicked a "Download with Extension" button
    const extBtn = e.target.closest(".arcen_extension_download_btn");
    if (extBtn) {
        const modelId = extBtn.getAttribute("data-model-id");
        const versionId = extBtn.getAttribute("data-version-id");
        const modelType = extBtn.getAttribute("data-model-type");
        const downloadUrl = extBtn.getAttribute("data-download-url");
        const fileName = extBtn.getAttribute("data-file-name");

        console.log("ArcEnCiel: extension download button =>", {
            modelId, versionId, modelType, downloadUrl, fileName
        });

        // Always call the same route, no matter if it's huggingface or arcenciel
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
            //console.log("ArcEnCiel: extension download response:", data);
            // No pop-up, just console log
        })
        .catch(err => console.error("ArcEnCiel: extension download fetch error:", err));

        return; // handled this click
    }

    // 2) If user clicked a gallery image
    const galItem = e.target.closest(".arcen_gallery_item");
    if (galItem) {
        const imgId = galItem.getAttribute("data-image-id");
        if (imgId) {
            //console.log("ArcEnCiel: clicked gallery image ID:", imgId);
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

        //console.log("ArcEnCiel: clicked model card with ID:", modelId);

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

    // Otherwise do nothing
});

// Listen for gear-button clicks, toggle the popup
document.addEventListener("click", function (e) {
    const settingsBtn = e.target.closest("#arcenciel_settings_button");
    if (settingsBtn) {
        e.stopPropagation();
        const popup = document.getElementById("arcenciel_settings_popup");
        if (popup) {
            if (popup.style.display === "block") {
                popup.style.display = "none";
            } else {
                popup.style.display = "block";
            }
        }
        return;
    }
});
// Optionally hide if user clicks outside
document.addEventListener("click", function(e) {
    const popup = document.getElementById("arcenciel_settings_popup");
    const settingsBtn = document.getElementById("arcenciel_settings_button");
    if (!popup || !settingsBtn) return;

    if (popup.style.display === "block") {
        // check if the click was inside
        const clickInside = popup.contains(e.target) || settingsBtn.contains(e.target);
        if (!clickInside) {
            popup.style.display = "none";
        }
    }
});

function getGradioAppRoot() {
    const gradioApp = document.querySelector('gradio-app');
    // If WebUI is using shadow DOM:
    return gradioApp?.shadowRoot || document;
  }
  
  function setupArcencielSliderObserver() {
    const root = getGradioAppRoot();
    if (!root) return;
  
    // Attempt to find the slider's container by ID
    const sliderWrapper = root.getElementById("arcenciel_card_scale_slider");
    if (!sliderWrapper) {
      //console.log("ArcEnCiel: #arcenciel_card_scale_slider not found yet, retrying...");
      // retry in 1s
      setTimeout(setupArcencielSliderObserver, 1000);
      return;
    }
  
    // Now find the actual <input type="range">
    const rangeInput = sliderWrapper.querySelector("input[type='range']");
    if (!rangeInput) {
      //console.log("ArcEnCiel: range input not found under slider wrapper, retrying...");
      setTimeout(setupArcencielSliderObserver, 1000);
      return;
    }
  
    console.log("ArcEnCiel: Found the card scale slider:", rangeInput);
  
    // Create or reuse a <style> tag where we inject dynamic CSS
    let styleTag = document.getElementById("arcen_model_card_dynamic_style");
    if (!styleTag) {
      styleTag = document.createElement("style");
      styleTag.id = "arcen_model_card_dynamic_style";
      // Place it in <head> or inside the shadow root <head> if you prefer
      document.head.appendChild(styleTag);
    }
  
    // On slider moves, update .arcen_model_card width/height
    rangeInput.addEventListener("input", (event) => {
      const val = parseFloat(event.target.value) || 30;
      const height = Math.round(val * 1.5); // preserve 2:3 ratio
      styleTag.textContent = `
        .arcen_model_card {
          width: ${val}em !important;
          height: ${height}em !important;
        }
      `;
    });
  }
  
  // Schedule the first attempt after everything is (mostly) loaded
  setTimeout(() => {
    setupArcencielSliderObserver();
  }, 1000);