(() => {
    "use strict";

    // The known provider order. Cards always render in this order regardless of
    // map iteration order so the layout is stable.
    const PROVIDER_ORDER = ["open_meteo", "wttr", "opensensemap", "oceandrivers", "seven_timer"];
    const PROVIDER_LABEL = {
        open_meteo:   "Open-Meteo",
        wttr:         "wttr (goweather)",
        opensensemap: "openSenseMap",
        oceandrivers: "OceanDrivers",
        seven_timer:  "7Timer",
    };

    const $ = (id) => document.getElementById(id);

    // ---- API base URL --------------------------------------------------------
    // Same-origin by default. Override via ?api=<URL> or persisted localStorage.
    // When hosted on GitHub Pages there's no API on the same origin, so we
    // default to a local uvicorn — the user is expected to run the server
    // themselves, with WEATHER_CORS_ALLOW_ORIGINS set.

    const STORAGE_KEY = "weather_api_base";
    const isGitHubPages = location.hostname.endsWith(".github.io");
    const queryApi = new URLSearchParams(location.search).get("api");
    const savedApi = localStorage.getItem(STORAGE_KEY);
    const defaultApi = isGitHubPages ? "http://127.0.0.1:8000" : "";
    const apiBaseInitial = (queryApi || savedApi || defaultApi).replace(/\/$/, "");

    const form = $("weather-form");
    const cityInput = $("city");
    const countryInput = $("country");
    const apiInput = $("api-base");
    const submitBtn = $("submit");
    const formHint = $("form-hint");

    if (apiInput) {
        apiInput.value = apiBaseInitial;
        apiInput.addEventListener("change", () => {
            const v = apiInput.value.trim().replace(/\/$/, "");
            if (v) localStorage.setItem(STORAGE_KEY, v);
            else localStorage.removeItem(STORAGE_KEY);
        });
    }

    function currentApiBase() {
        return apiInput ? apiInput.value.trim().replace(/\/$/, "") : "";
    }

    const resultsEl = $("results");
    const stepGeocode = $("step-geocode");
    const geocodeStatus = $("geocode-status");
    const geocodeDetails = $("geocode-details");
    const stepProviders = $("step-providers");
    const providersStatus = $("providers-status");
    const providerGrid = $("provider-grid");
    const stepParallelism = $("step-parallelism");
    const stepSummary = $("step-summary");
    const summaryText = $("summary-text");
    const stepDetails = $("step-details");
    const providerDetails = $("provider-details");
    const errorBanner = $("error-banner");

    // ---- Form validation -----------------------------------------------------

    function updateButtonState() {
        const valid = cityInput.value.trim().length > 0 && countryInput.value.trim().length > 0;
        submitBtn.disabled = !valid;
        formHint.textContent = valid
            ? "Ready &mdash; click the button to send."
            : "Fill in city and country to unlock the button.";
    }

    cityInput.addEventListener("input", updateButtonState);
    countryInput.addEventListener("input", updateButtonState);
    updateButtonState();

    // ---- Submit handler ------------------------------------------------------

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (submitBtn.disabled) return;

        submitBtn.disabled = true;
        submitBtn.textContent = "Working…";
        resetResults();
        showLoadingState();

        const params = new URLSearchParams();
        params.set("city", cityInput.value.trim());
        params.set("country", countryInput.value.trim());
        const state = $("state").value.trim();
        const date = $("date").value.trim();
        const units = document.querySelector('input[name="units"]:checked').value;
        if (state) params.set("state", state);
        if (date) params.set("date", date);
        params.set("units", units);

        const url = `${currentApiBase()}/weather?${params.toString()}`;
        const startedAt = performance.now();

        try {
            const resp = await fetch(url, { headers: { Accept: "application/json" } });
            const wallMs = Math.round(performance.now() - startedAt);
            const body = await resp.json();

            if (!resp.ok) {
                showError(resp.status, body);
                return;
            }
            await renderResponse(body, wallMs);
        } catch (err) {
            showError(0, { detail: `Network or parsing error: ${err.message || err}` });
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Get weather";
        }
    });

    // ---- Visual orchestration ------------------------------------------------

    function resetResults() {
        errorBanner.hidden = true;
        errorBanner.innerHTML = "";
        for (const step of [stepGeocode, stepProviders, stepParallelism, stepSummary, stepDetails]) {
            step.hidden = true;
        }
        geocodeDetails.innerHTML = "";
        providerGrid.innerHTML = "";
        providerDetails.innerHTML = "";
        $("proof-bars").innerHTML = "";
        summaryText.textContent = "";
    }

    function showLoadingState() {
        resultsEl.hidden = false;
        stepGeocode.hidden = false;
        geocodeStatus.innerHTML = '<span class="spinner"></span>Resolving location and querying APIs…';

        stepProviders.hidden = false;
        providersStatus.innerHTML = '<span class="spinner"></span>Calling 5 APIs in parallel…';
        for (const name of PROVIDER_ORDER) {
            const card = document.createElement("div");
            card.className = "provider-card loading";
            card.id = `pc-${name}`;
            card.innerHTML = `
                <div class="provider-name">${PROVIDER_LABEL[name]}</div>
                <div class="provider-status"><span class="spinner"></span>waiting…</div>
                <div class="provider-time">&mdash;</div>
            `;
            providerGrid.appendChild(card);
        }
    }

    async function renderResponse(body, wallMs) {
        // Step 1 — show the geocoded inputs.
        await sleep(220);
        const t = body.transformed_inputs;
        geocodeStatus.textContent = `Resolved in your input to a real location:`;
        geocodeDetails.innerHTML = `
            <dt>Resolved name</dt><dd>${escapeHtml(t.resolved_name || "—")}</dd>
            <dt>Latitude / Longitude</dt><dd>${t.lat.toFixed(4)}, ${t.lon.toFixed(4)}</dd>
            <dt>Timezone</dt><dd>${escapeHtml(t.timezone || "—")}</dd>
            <dt>Date</dt><dd>${escapeHtml(t.date)}</dd>
            <dt>Units (display)</dt><dd>${escapeHtml(t.units)}</dd>
            <dt>Country code</dt><dd>${escapeHtml(t.country_code || "—")}</dd>
        `;

        // Step 2 — staggered reveal of provider cards in order of completion
        // (smallest elapsed_ms first), so the user visually "sees" the parallelism
        // unfold even though the response arrived as one payload.
        const providers = body.result.providers;
        const sortedNames = [...PROVIDER_ORDER].sort((a, b) => {
            const ea = (providers[a] && providers[a].elapsed_ms) || 0;
            const eb = (providers[b] && providers[b].elapsed_ms) || 0;
            return ea - eb;
        });

        const stagger = 180; // ms between reveals; total ~900ms for 5 providers
        for (let i = 0; i < sortedNames.length; i++) {
            const name = sortedNames[i];
            await sleep(stagger);
            renderProviderCard(name, providers[name]);
        }

        providersStatus.textContent = `All 5 providers complete.`;

        // Step 3 — parallelism proof.
        await sleep(220);
        renderParallelismProof(providers, wallMs);

        // Step 4 — aggregated summary.
        await sleep(150);
        stepSummary.hidden = false;
        summaryText.textContent = body.result.summary;

        // Step 5 — full per-provider details.
        await sleep(150);
        renderProviderDetails(providers);
    }

    function renderProviderCard(name, pr) {
        const card = $(`pc-${name}`);
        if (!card) return;
        card.classList.remove("loading");

        const snap = pr.normalized || {};
        const isFallback = snap.source_quality === "fallback";
        const isError = pr.status === "error";

        const cardClass = isError ? "error" : (isFallback ? "fallback" : "live");
        card.className = `provider-card ${cardClass}`;

        const tempBit = (snap.temperature_c !== null && snap.temperature_c !== undefined)
            ? `${snap.temperature_c.toFixed(1)}°C`
            : "—";
        const conditions = snap.conditions || "—";

        const statusLabel = isError ? "ERROR" : (isFallback ? "FALLBACK" : "OK");

        card.innerHTML = `
            <div class="provider-name">${PROVIDER_LABEL[name]}</div>
            <div class="provider-status">${statusLabel} &middot; ${escapeHtml(conditions)}</div>
            <div class="provider-time">${tempBit} &middot; ${formatMs(pr.elapsed_ms)}</div>
        `;
    }

    function renderParallelismProof(providers, wallMs) {
        stepParallelism.hidden = false;

        const elapsedMsByName = {};
        let sumMs = 0;
        let maxMs = 0;
        for (const name of PROVIDER_ORDER) {
            const e = (providers[name] && providers[name].elapsed_ms) || 0;
            elapsedMsByName[name] = e;
            sumMs += e;
            if (e > maxMs) maxMs = e;
        }

        $("sum-ms").textContent = formatMs(sumMs);
        $("wall-ms").textContent = formatMs(wallMs);
        const speedup = maxMs > 0 ? (sumMs / Math.max(wallMs, maxMs)) : 0;
        $("speedup").textContent = `${speedup.toFixed(2)}×`;

        // Bars scaled to the longest single provider; the wall-clock dashed line
        // also lives within this scale.
        const scaleMs = Math.max(maxMs, wallMs, 1);
        const bars = $("proof-bars");
        bars.innerHTML = "";
        for (const name of PROVIDER_ORDER) {
            const pr = providers[name] || {};
            const e = elapsedMsByName[name];
            const widthPct = (e / scaleMs) * 100;
            const fillClass = pr.status === "error"
                ? "error"
                : (pr.normalized && pr.normalized.source_quality === "fallback")
                    ? "fallback"
                    : "";

            const row = document.createElement("div");
            row.className = "bar-row";
            row.innerHTML = `
                <div class="bar-name">${PROVIDER_LABEL[name]}</div>
                <div class="bar-track">
                    <div class="bar-fill ${fillClass}" style="width: 0%"></div>
                </div>
                <div class="bar-time">${formatMs(e)}</div>
            `;
            bars.appendChild(row);
            // Animate width on next frame so the transition kicks in.
            const fill = row.querySelector(".bar-fill");
            requestAnimationFrame(() => { fill.style.width = `${widthPct}%`; });
        }
    }

    function renderProviderDetails(providers) {
        stepDetails.hidden = false;
        providerDetails.innerHTML = "";

        for (const name of PROVIDER_ORDER) {
            const pr = providers[name];
            if (!pr) continue;

            const snap = pr.normalized || {};
            const isError = pr.status === "error";
            const isFallback = snap.source_quality === "fallback";
            const badgeClass = isError ? "error" : (isFallback ? "fallback" : "live");
            const badgeText = isError ? "error" : (isFallback ? "fallback" : "live");

            const node = document.createElement("article");
            node.className = "provider-detail";
            node.innerHTML = `
                <header>
                    <h3>${PROVIDER_LABEL[name]}</h3>
                    <div>
                        <span class="badge ${badgeClass}">${badgeText}</span>
                        <span class="provider-time">${formatMs(pr.elapsed_ms)}</span>
                    </div>
                </header>
                ${renderSnapshotDl(snap)}
                ${snap.notes ? `<p class="notes">Note: ${escapeHtml(snap.notes)}</p>` : ""}
                ${pr.error ? `<p class="error-msg">${escapeHtml(pr.error)}</p>` : ""}
                <details class="raw-json">
                    <summary>Raw upstream response</summary>
                    <pre><code>${escapeHtml(JSON.stringify(pr.data, null, 2))}</code></pre>
                </details>
            `;
            providerDetails.appendChild(node);
        }
    }

    function renderSnapshotDl(snap) {
        const rows = [
            ["Temperature", snap.temperature_c != null ? `${snap.temperature_c.toFixed(1)} °C` : null],
            ["Humidity", snap.humidity_pct != null ? `${snap.humidity_pct.toFixed(0)} %` : null],
            ["Wind", snap.wind_kph != null ? `${snap.wind_kph.toFixed(1)} km/h` : null],
            ["Cloud cover", snap.cloud_cover_pct != null ? `${snap.cloud_cover_pct.toFixed(0)} %` : null],
            ["Precipitation", snap.precipitation_mm != null ? `${snap.precipitation_mm.toFixed(1)} mm` : null],
            ["Conditions", snap.conditions || null],
            ["Forecast", snap.is_forecast ? "yes" : "no"],
            ["For date", snap.forecast_for_date || null],
        ].filter(([, v]) => v !== null && v !== undefined);

        if (rows.length === 0) {
            return `<p class="notes">No normalised fields were extracted from this provider.</p>`;
        }

        return `<dl class="snapshot">${
            rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(String(v))}</dd>`).join("")
        }</dl>`;
    }

    // ---- Error rendering -----------------------------------------------------

    function showError(status, body) {
        // Hide step panels: the response was a failure, no point pretending.
        for (const step of [stepGeocode, stepProviders, stepParallelism, stepSummary, stepDetails]) {
            step.hidden = true;
        }
        resultsEl.hidden = false;
        errorBanner.hidden = false;

        let title;
        let detail;
        if (status === 422) {
            title = "Validation error";
            detail = body && body.detail ? JSON.stringify(body.detail, null, 2) : "Bad input.";
        } else if (status === 404) {
            title = "Could not resolve that location";
            detail = body && body.detail ? body.detail : "Geocoder returned no usable result.";
        } else if (status === 0) {
            title = "Network error";
            detail = body && body.detail ? body.detail : "Could not reach the server.";
        } else {
            title = `HTTP ${status}`;
            detail = body && body.detail ? JSON.stringify(body.detail) : "Unexpected error.";
        }

        errorBanner.innerHTML = `
            <h2>${escapeHtml(title)}</h2>
            <pre>${escapeHtml(detail)}</pre>
        `;
    }

    // ---- Utilities -----------------------------------------------------------

    function sleep(ms) {
        return new Promise((res) => setTimeout(res, ms));
    }

    function formatMs(ms) {
        if (ms == null) return "—";
        if (ms < 1000) return `${Math.round(ms)} ms`;
        return `${(ms / 1000).toFixed(2)} s`;
    }

    function escapeHtml(s) {
        if (s === null || s === undefined) return "";
        return String(s)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }
})();
