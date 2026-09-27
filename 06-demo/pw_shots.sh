#!/usr/bin/env bash
# The screenshots that close every polish batch (06-demo/CLAUDE.md), taken with
# playwright-cli at 1440 x 900 and as an iPhone 15.
#
#   bash 06-demo/pw_shots.sh OUTDIR
#
# Needs the field app on 8770 (or FIELD_URL) and base on 8781 (or BASE_URL),
# and at least one saved answer, comparison, refusal and child's profile, which
# a suite run leaves behind. Reads only; it presses nothing that saves.

set -eu
cd "$(dirname "$0")/.." || exit 99
mkdir -p "${1:?usage: bash 06-demo/pw_shots.sh OUTDIR}"
OUT=$(cd "$1" && pwd)
FIELD=${FIELD_URL:-http://127.0.0.1:8770}
BASE=${BASE_URL:-http://127.0.0.1:8781}

# The newest saved assessment of each kind, so a batch photographs its own run.
read -r ANSWER PAIR REFUSAL CHILD < <(curl -s "$FIELD/api/conversations" | .venv/bin/python -c '
import json, sys
cs = json.load(sys.stdin)["conversations"]
ok = lambda s: s.get("state") in ("red", "yellow", "green")
def pick(f): return next((c["id"] for c in cs if f(c)), "-")
print(pick(lambda c: len(c["sides"]) == 1 and ok(c["sides"][0])),
      pick(lambda c: len(c["sides"]) == 2 and all(map(ok, c["sides"]))),
      pick(lambda c: any(s.get("state") == "refused" for s in c["sides"])),
      pick(lambda c: any(s.get("state") == "child" for s in c["sides"])))')

# playwright-cli keeps snapshots in its working directory; keep them out of the repo.
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

script() {   # $1 prefix, $2 phone true|false
  cat > "$WORK/$1.js" <<EOF
async page => {
  const OUT = "$OUT", P = "$1", phone = $2;
  const FIELD = "$FIELD", BASE = "$BASE";
  const ids = { answer: "$ANSWER", pair: "$PAIR", refusal: "$REFUSAL", child: "$CHILD" };
  const done = [];
  const settle = async (wait) => {
    await page.waitForFunction(() => document.readyState === "complete"
      && !document.querySelector(".loading"), null, { timeout: 20000 });
    if (wait) await page.waitForSelector(wait, { timeout: 15000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
  };
  // Chromium cannot capture past 16384 device pixels and repeats the page
  // instead, so a long page is cut at 16000 and the list below says so.
  const shot = async (name, full = false) => {
    const opts = { path: OUT + "/" + P + "-" + name + (full ? "-full" : "") + ".png", fullPage: full, animations: "disabled" };
    if (full) {
      const { h, dpr } = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, dpr: devicePixelRatio }));
      const max = Math.floor(16000 / dpr);
      if (h > max) opts.clip = { x: 0, y: 0, width: page.viewportSize().width, height: max };
    }
    await page.screenshot(opts);
    const tall = full && opts.clip ? await page.evaluate(() => document.documentElement.scrollHeight) : 0;
    done.push(name + (full ? (tall ? " (full, first " + opts.clip.height + " of " + tall + "px)" : " (full)") : ""));
  };
  const at = async (url, wait) => { await page.goto(url); await settle(wait); };

  await at(FIELD + "/"); await shot("01-new");
  await page.click("#forwho"); await page.waitForSelector("#picker[open]"); await page.waitForTimeout(250);
  await shot("02-picker");
  if (phone) {
    await at(FIELD + "/"); await page.click("#menu"); await page.waitForSelector(".side.open");
    await page.waitForTimeout(250); await shot("03-drawer");
  }
  if (ids.answer !== "-") {
    await at(FIELD + "/c/" + ids.answer); await shot("04-answer"); await shot("04-answer", true);
    // Sources are closed since the overhaul (2026-09-27): open them, as a person would.
    if (await page.\$(".sources .cite")) {
      await page.click(".sources [data-fold]"); await page.waitForTimeout(200); await shot("04-answer-sources");
      await page.click(".sources .cite"); await page.waitForSelector("#sheet[open]"); await page.waitForTimeout(300);
      await shot("05-source");
    }
  }
  if (ids.pair !== "-") {
    await at(FIELD + "/c/" + ids.pair); await shot("06-compare"); await shot("06-compare", true);
    const b = await page.\$(".turn.pair .tabs [data-tab='1']");
    if (phone && b && await b.isVisible()) { await b.click(); await page.waitForTimeout(200); await shot("06-compare-b"); }
  }
  if (ids.refusal !== "-") { await at(FIELD + "/c/" + ids.refusal); await shot("07-refusal"); }
  if (ids.child !== "-") { await at(FIELD + "/c/" + ids.child); await shot("08-not-assessed"); }
  await at(FIELD + "/people"); await shot("09-people", true);
  await at(FIELD + "/people/mum", ".preview .w-rule"); await shot("10-person", true);
  await at(FIELD + "/queue"); await shot("11-caseload", true);
  await at(FIELD + "/sync"); await shot("12-sync", true);
  await at(FIELD + "/regions"); await shot("13-regions", true);
  try {
    await page.goto(BASE + "/");
    await page.waitForFunction(() => document.readyState === "complete" && !document.querySelector(".fine"), null, { timeout: 20000 });
    await page.waitForTimeout(300); await shot("14-base", true);
    const t = page.locator(".ttl:visible").first();
    if (await t.count()) { await t.click(); await page.waitForSelector(".det"); await page.waitForTimeout(300); await shot("15-base-assessment", true); }
  } catch (e) { done.push("base skipped: " + e.message.split("\n")[0]); }
  return done.join(", ");
}
EOF
}

script desktop false
script iphone15 true
cd "$WORK"
playwright-cli -s=gd-desk open >/dev/null
playwright-cli -s=gd-desk resize 1440 900 >/dev/null
echo "desktop 1440x900: $(playwright-cli -s=gd-desk --raw run-code --filename="$WORK/desktop.js")"
playwright-cli -s=gd-desk close >/dev/null
playwright-cli -s=gd-phone open --device="iPhone 15" >/dev/null
echo "iPhone 15: $(playwright-cli -s=gd-phone --raw run-code --filename="$WORK/iphone15.js")"
playwright-cli -s=gd-phone close >/dev/null
# A run-code that throws still lets the lines above print, so count what landed.
for prefix in desktop iphone15; do
  n=$(ls "$OUT/$prefix-"*.png 2>/dev/null | wc -l | tr -d ' ')
  if [ "$n" -lt 10 ]; then
    echo "FAIL  only $n $prefix screenshots were saved; the run-code output above says why" >&2
    exit 1
  fi
done
echo "saved to $OUT"
