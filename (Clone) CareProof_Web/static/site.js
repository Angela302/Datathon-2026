// Section 1. Request helpers and page state

const el = (id) => document.getElementById(id);

const state = {
  options: null,
  query: null,
  request: 0,
  timer: null,
  map: null,
  markers: null,
};

const weightLabels = {
  distance: "Distance",
  facilities: "Facilities",
  personnel: "Personnel",
  reliability: "Reliability",
};

function label(code) {
  const abbreviations = {
    mri: "MRI", ct: "CT", icu: "ICU", nicu: "NICU", xray: "X-ray",
  };

  return code.replace(/^specialty_/, "").split("_").map((part) =>
    abbreviations[part] || part.charAt(0).toUpperCase() + part.slice(1)
  ).join(" ");
}

function status(id, message) {
  el(id).textContent = message;
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : "Check the required inputs and try again."
    );
  }

  return result;
}


// Section 2. Department, equipment, and preference controls

function fillSelect(select, codes, placeholder) {
  select.replaceChildren(
    new Option(placeholder, ""),
    ...codes.map((code) => new Option(label(code), code)),
  );
}

function equipmentCodes() {
  return [...el("equipment").querySelectorAll("select")]
    .map((select) => select.value)
    .filter(Boolean);
}

function updatePreferenceOptions() {
  const equipment = new Set(equipmentCodes());

  for (const group of ["facilities", "personnel"]) {
    const container = el(group);
    const checked = new Set(
      [...container.querySelectorAll(":checked")].map((input) => input.value)
    );
    container.replaceChildren();

    for (const code of state.options[group]) {
      if (equipment.has(code)) continue;

      const row = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = code;
      checkbox.checked = checked.has(code);
      row.append(checkbox, document.createTextNode(` ${label(code)}`));
      container.append(row);
    }
  }
}

function showSearchForm(suggestion) {
  if (suggestion) {
    el("department").value = suggestion.department;
    [...el("equipment").querySelectorAll("select")].forEach((select, index) => {
      select.value = suggestion.equipment[index] || "";
    });
  }

  updatePreferenceOptions();
  el("search-section").hidden = false;
  el("department").focus();
}


// Section 3. Ranking sliders

function readWeights() {
  return Object.fromEntries(
    [...el("weights").querySelectorAll("input")].map((input) => [
      input.name, input.valueAsNumber,
    ])
  );
}

function updateWeightLabels() {
  const weights = readWeights();
  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  for (const [key, value] of Object.entries(weights)) {
    el(`weight-${key}`).textContent =
      `${total ? Math.round(100 * value / total) : 0}%`;
  }
}

function buildSliders() {
  for (const [key, title] of Object.entries(weightLabels)) {
    const wrapper = document.createElement("label");
    wrapper.htmlFor = `slider-${key}`;
    wrapper.textContent = title;

    const output = document.createElement("output");
    output.id = `weight-${key}`;
    wrapper.append(output);

    const slider = document.createElement("input");
    Object.assign(slider, {
      type: "range",
      id: `slider-${key}`,
      name: key,
      min: 0,
      max: 100,
      step: "any",
      value: 100 * state.options.weights[key],
    });

    slider.addEventListener("input", () => {
      updateWeightLabels();
      clearTimeout(state.timer);
      state.request += 1;
      state.timer = setTimeout(() => runRanking(readWeights()), 225);
    });

    el("weights").append(wrapper, slider);
  }

  updateWeightLabels();
}


// Section 4. Top-three cards, reported offerings, and map

// Send the latest Top 3 to the embedded map.
const hospitalMapFrame = document.getElementById("hospital-map");
let latestMapData = null;

function renderLatestMap() {
  if (!latestMapData) return;

  const map = hospitalMapFrame.contentWindow?.CareProofMap;
  if (typeof map?.render === "function") {
    map.render(latestMapData);
  }
}

hospitalMapFrame.addEventListener("load", renderLatestMap);

function renderMap(top, query) {
  latestMapData = {
    origin: {
      latitude: query.latitude,
      longitude: query.longitude,
    },
    hospitals: top.map((hospital, index) => {
      const equipment = hospital.equipment ?? [];

      return {
        ...hospital,
        rank: index + 1,
        matched_equipment: equipment
          .filter((item) => item.reported)
          .map((item) => label(item.code)),
        equipment_unconfirmed: equipment
          .filter((item) => !item.reported)
          .map((item) => label(item.code)),
        reported_offerings: (hospital.reported_offerings ?? []).map(label),
      };
    }),
  };

  if (!hospitalMapFrame.hasAttribute("src")) {
    hospitalMapFrame.src = "/static/four-point-map.html";
  } else {
    renderLatestMap();
  }
}

function renderResults(result, query) {
  el("results").hidden = false;
  status("method", `${result.count} nearby eligible hospitals compared · ${result.method}`);

  const list = el("rankings");
  list.replaceChildren();

  result.top.forEach((hospital, index) => {
    const card = document.createElement("li");
    const title = document.createElement("h3");
    title.textContent = `${index + 1}. ${hospital.name}`;

    const scores = document.createElement("p");
    scores.textContent =
      `${hospital.distance_km.toFixed(1)} km · ${hospital.primary_score.toFixed(2)}/100 · +${hospital.bonus.toFixed(2)}/5`;

    const coordinates = document.createElement("p");
    coordinates.className = "muted";
    coordinates.textContent =
      `Latitude ${hospital.latitude.toFixed(5)} · Longitude ${hospital.longitude.toFixed(5)}`;

    const matches = document.createElement("p");
    matches.textContent = "AI-recommended items: " + hospital.equipment
      .map((item) => `${label(item.code)} (${item.reported ? "reported" : "unconfirmed"})`)
      .join(", ");

    const details = document.createElement("details");
    const heading = document.createElement("summary");
    heading.textContent = "What this hospital reports";

    const offerings = document.createElement("p");
    const reported = hospital.reported_offerings || [];
    offerings.textContent = reported.length
      ? reported.map(label).join(", ")
      : "No offerings were recorded for this hospital.";

    details.append(heading, offerings);
    card.append(title, scores, coordinates, matches, details);
    list.append(card);
  });

  renderMap(result.top, query);
}

async function runRanking(weights) {
  if (!state.query) return;

  const request = ++state.request;
  const query = { ...state.query, weights };
  status("search-status", "Ranking nearby hospitals…");

  try {
    const result = await api("/api/recommend", query);
    if (request !== state.request) return;

    renderResults(result, query);
    status("search-status", result.count
      ? ""
      : "No hospitals reported this department with usable coordinates.");
  } catch (error) {
    if (request === state.request) status("search-status", error.message);
  }
}


// Section 5. Connect the forms and sliders

async function start() {
  try {
    state.options = await api("/api/options");
  } catch (error) {
    status("ai-status", error.message);
    return;
  }

  fillSelect(el("department"), state.options.departments, "Select a department");

  for (let index = 0; index < 3; index += 1) {
    const wrapper = document.createElement("label");
    wrapper.textContent = `Priority ${index + 1}`;

    const select = document.createElement("select");
    select.required = index === 0;
    fillSelect(select, state.options.equipment, index === 0 ? "Select an item" : "Optional");
    wrapper.append(select);
    el("equipment").append(wrapper);
  }

  buildSliders();
  el("suggest").disabled = false;
  el("manual").disabled = false;

  el("equipment").addEventListener("change", updatePreferenceOptions);
  el("manual").addEventListener("click", () => showSearchForm());

  el("symptom-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    el("suggest").disabled = true;
    status("ai-status", "Looking up care options…");

    try {
      const suggestion = await api("/api/ai/suggest", {
        symptoms: el("symptoms").value,
      });
      showSearchForm(suggestion);
      status("ai-status", "Review the suggested department and equipment below.");
    } catch (error) {
      status("ai-status", error.message);
      showSearchForm();
    } finally {
      el("suggest").disabled = false;
    }
  });

  el("search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const equipment = equipmentCodes();

    if (new Set(equipment).size !== equipment.length) {
      status("search-status", "Select distinct equipment or services for each priority.");
      return;
    }

    clearTimeout(state.timer);
    state.query = {
      department: el("department").value,
      equipment,
      latitude: el("latitude").valueAsNumber,
      longitude: el("longitude").valueAsNumber,
      preferences: [...el("search-form").querySelectorAll("input[type=checkbox]:checked")]
        .map((input) => input.value),
    };

    runRanking(readWeights());
  });

  el("reset").addEventListener("click", () => {
    clearTimeout(state.timer);

    for (const input of el("weights").querySelectorAll("input")) {
      input.value = 100 * state.options.weights[input.name];
    }

    updateWeightLabels();
    runRanking(null);
  });
}

start();