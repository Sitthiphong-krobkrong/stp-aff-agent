---
description: STP Picks daily run — get today's product list, make N videos, report what to post
argument-hint: "[count=3]"
---
Run the STP Picks daily flow in this repo. Count = $ARGUMENTS (default 3). Reply to the operator in Thai, short.

1. Environment: `source .venv/bin/activate` (create it with python3.12 + `pip install -r requirements.txt` if missing).
   `git pull` first.
2. Product list: look for today's `~/Downloads/stp-offers-$(date +%F).json`.
   - If missing and Claude in Chrome tools are available: open
     https://affiliate.shopee.co.th/offer/product_offer in the operator's Chrome, and run the code of
     `tools/bookmarklet.js` on that page once (it only re-reads the list the page shows, 5 pages with pauses).
     If a login page or CAPTCHA appears, STOP and ask the operator to handle it — never solve CAPTCHAs or type passwords.
   - Otherwise ask the operator to click the "ส่งให้ bot" bookmark (install: `python -m agent bookmarklet | pbcopy`)
     and wait for the file.
3. Run: `python -m agent auto --count <count> --director claude_cli` (takes a few minutes per product; don't use a short timeout).
4. Report per run: state, product name, commission, `runs/<id>/out/final.mp4`. Open each `check.jpg` and look at it;
   flag text overlapping the product, wrong product images, or odd Thai. Quote any BLOCK/warn lines from the output.
5. For READY_FOR_APPROVAL runs show the `post.txt` Shopee caption + affiliate link, remind the operator to listen
   for English/model-name pronunciation before posting. Do NOT run `decide ... approve` yourself and never post anything.
6. If a step fails: show the error, check `runs/<id>/events.jsonl`, fix only obvious local issues (missing package,
   venv), and say what you changed. Do not edit pipeline code without asking.
