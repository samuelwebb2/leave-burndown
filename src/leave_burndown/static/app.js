/** @typedef {{ bankHolidays: string[] }} Config */

/**
 * The element with this id, which must exist and be of the given kind.
 * @template {HTMLElement} T
 * @param {string} id
 * @param {new () => T} kind
 * @returns {T}
 */
function element(id, kind) {
  const found = document.getElementById(id);
  if (!(found instanceof kind)) {
    throw new Error(`#${id} is missing or is not a ${kind.name}`);
  }
  return found;
}

/** @type {Config} */
const config = JSON.parse(element("config", HTMLScriptElement).text);
const bankHolidays = new Set(config.bankHolidays);

const start = element("start", HTMLInputElement);
const end = element("end", HTMLInputElement);
const halfStart = element("half_start", HTMLInputElement);
const halfEnd = element("half_end", HTMLInputElement);
const hint = element("preview", HTMLElement);

/**
 * Whether leave on this day uses a day: not a weekend, not a bank holiday.
 * @param {string} iso An ISO date.
 * @returns {boolean}
 */
function isWorking(iso) {
  const weekday = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return weekday !== 0 && weekday !== 6 && !bankHolidays.has(iso);
}

/**
 * Working days from first to last (ISO dates, inclusive). A half day at either
 * end counts as 0.5, when that end is a working day.
 * @param {string} first
 * @param {string} last
 * @param {boolean} halfFirst
 * @param {boolean} halfLast
 * @returns {number}
 */
function countDays(first, last, halfFirst, halfLast) {
  const dayMs = 864e5;
  const stop = Date.parse(`${last}T00:00:00Z`);
  let days = 0;
  for (let t = Date.parse(`${first}T00:00:00Z`); t <= stop; t += dayMs) {
    const iso = new Date(t).toISOString().slice(0, 10);
    if (!isWorking(iso)) continue;
    const half = (iso === first && halfFirst) || (iso === last && halfLast);
    days += half ? 0.5 : 1;
  }
  return days;
}

function showPreview() {
  if (!start.value || !end.value) {
    hint.textContent = "";
  } else if (end.value < start.value) {
    hint.textContent = "The last day is before the first day.";
  } else {
    const days = countDays(start.value, end.value, halfStart.checked, halfEnd.checked);
    const unit = days === 1 ? "working day" : "working days";
    hint.textContent = `${days} ${unit} in that range.`;
  }
}

start.addEventListener("input", () => {
  if (!end.value) end.value = start.value;
  showPreview();
});
for (const input of [end, halfStart, halfEnd]) {
  input.addEventListener("input", showPreview);
}
showPreview();
