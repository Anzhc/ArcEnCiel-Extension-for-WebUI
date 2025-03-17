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
            console.log("ArcEnCiel: extension download response:", data);
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
            console.log("ArcEnCiel: clicked gallery image ID:", imgId);
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

        console.log("ArcEnCiel: clicked model card with ID:", modelId);

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
