const $ = id => document.getElementById(id);
const config = JSON.parse($("config").textContent);
const BH = new Set(config.bankHolidays);

function isWorking(iso) {
  const wd = new Date(iso + "T00:00:00Z").getUTCDay();
  return wd !== 0 && wd !== 6 && !BH.has(iso);
}
// Working days in a..b, counting a half day at either end (when that end is a working day) as 0.5.
function countDays(a, b, halfStart, halfEnd) {
  let n = 0;
  for (let t = Date.parse(a + "T00:00:00Z"), end = Date.parse(b + "T00:00:00Z"); t <= end; t += 864e5) {
    const iso = new Date(t).toISOString().slice(0, 10);
    if (!isWorking(iso)) continue;
    n += (iso === a && halfStart) || (iso === b && halfEnd) ? 0.5 : 1;
  }
  return n;
}
function preview() {
  const a = $("start").value, b = $("end").value;
  if (!a || !b) { $("preview").textContent = ""; return; }
  if (b < a) { $("preview").textContent = "The last day is before the first day."; return; }
  const n = countDays(a, b, $("half_start").checked, $("half_end").checked);
  $("preview").textContent = n + (n === 1 ? " working day" : " working days") + " in that range.";
}
$("start").addEventListener("input", () => { if (!$("end").value) $("end").value = $("start").value; preview(); });
for (const id of ["end", "half_start", "half_end"]) $(id).addEventListener("input", preview);
preview();
