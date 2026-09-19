const $ = id => document.getElementById(id);
const config = JSON.parse($("config").textContent);
const BH = new Set(config.bankHolidays);
const SKIP = config.skipBankHolidays;

function countDays(a, b) {
  let n = 0;
  for (let t = Date.parse(a + "T00:00:00Z"), end = Date.parse(b + "T00:00:00Z"); t <= end; t += 864e5) {
    const d = new Date(t), iso = d.toISOString().slice(0, 10), wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6 && !(SKIP && BH.has(iso))) n++;
  }
  return n;
}
function preview() {
  const a = $("start").value, b = $("end").value;
  if (!a || !b) { $("preview").textContent = ""; return; }
  if (b < a) { $("preview").textContent = "The last day is before the first day."; return; }
  const n = countDays(a, b);
  $("preview").textContent = n + (n === 1 ? " working day" : " working days") + " in that range.";
}
$("start").addEventListener("input", () => { if (!$("end").value) $("end").value = $("start").value; preview(); });
$("end").addEventListener("input", preview);
preview();
